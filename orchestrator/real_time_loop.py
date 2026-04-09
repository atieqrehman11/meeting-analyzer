"""
RealTimeLoop — per-meeting background evaluation loop.

Runs every REALTIME_LOOP_INTERVAL_SECONDS after an initial start delay.
Responsibilities (per orchestrator_v1.md):
  1. Agenda adherence — similarity check, off-track / agenda-unclear alerts
  2. Purpose detection — classify meeting purpose once, then re-check for drift
  3. Tone monitoring — detect tone issues, send private/meeting alerts
  4. Participation pulse — snapshot active/silent speakers, alert on silence
  5. Time remaining — warn when approaching scheduled end, list open items
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from orchestrator.config import OrchestratorConfig
from shared_models.mcp_client import BaseMcpClient, McpCallError
from shared_models.mcp_types import MeetingRecord, ParticipationPulseSnapshot
from shared_models.a2a_schemas import ComputeParticipationPulseTask, ComputeParticipationPulseResponse

logger = logging.getLogger("orchestrator.realtime")


class RealTimeLoop:
    """
    Runs the real-time evaluation loop for a single active meeting.
    Constructed by Orchestrator._start_loops() and run as an asyncio Task.
    """

    def __init__(
        self,
        meeting_id: str,
        record: MeetingRecord,
        mcp: BaseMcpClient,
        cfg: OrchestratorConfig,
        agenda: list[str] | None = None,
        scheduled_end_time: str | None = None,
    ) -> None:
        self._meeting_id = meeting_id
        self._record = record
        self._mcp = mcp
        # Agenda is sourced from the calendar event at meeting start.
        # Falls back to empty list if not provided (no-agenda meeting).
        self._agenda: list[str] = agenda or []

        # Scheduled end time from calendar event (ISO8601). Used for time-remaining alert.
        # Falls back to record.end_time if not explicitly provided.
        raw_end = scheduled_end_time or getattr(record, "end_time", None)
        self._scheduled_end: Optional[datetime] = _parse_iso(raw_end)

        # Scale time-sensitive thresholds to meeting duration
        from orchestrator.config_scaler import ConfigScaler
        self._cfg = ConfigScaler().scale(cfg, self._scheduled_end)

        logger.debug(
            "[RealTimeLoop] Created for meeting=%s agenda_topics=%d %s scheduled_end=%s "
            "start_delay=%ds interval=%ds purpose_delay=%ds pulse_interval=%dm",
            meeting_id,
            len(self._agenda),
            self._agenda if self._agenda else "(none)",
            self._scheduled_end.isoformat() if self._scheduled_end else "none",
            self._cfg.realtime_loop_start_delay_seconds,
            self._cfg.realtime_loop_interval_seconds,
            self._cfg.purpose_detection_delay_seconds,
            self._cfg.participation_pulse_interval_minutes,
        )

        # Agenda adherence state
        self._similarity_buffer: list[float] = []
        # Per-topic last-seen max score — used to determine which topics are uncovered
        self._topic_max_scores: dict[str, float] = {}
        self._alert_timestamps: dict[str, float] = {}  # alert_type → epoch

        # Purpose detection state
        self._purpose_detected: bool = False
        self._purpose_detected_at: Optional[float] = None
        self._purpose_divergence_ticks: int = 0
        self._last_purpose_check: Optional[float] = None

        # Participation pulse state
        self._pulse_snapshot_count: int = 0
        self._last_pulse_at: Optional[float] = None

        # Time remaining state — fire once only
        self._time_remaining_sent: bool = False
        # Transcript state — skip realtime checks until first segment captured
        self._has_transcript: bool = False
        self._tick_count: int = 0

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def notify_transcript_captured(self) -> None:
        """Called by Orchestrator when a transcript segment is successfully captured."""
        if not self._has_transcript:
            logger.info("[RealTimeLoop] First transcript captured — enabling realtime checks for meeting=%s", self._meeting_id)
        self._has_transcript = True

    async def run(self) -> None:
        """Main loop — waits for start delay then ticks at configured interval."""
        logger.debug("[RealTimeLoop] Starting for meeting=%s delay=%ds",
                    self._meeting_id, self._cfg.realtime_loop_start_delay_seconds)
        await asyncio.sleep(self._cfg.realtime_loop_start_delay_seconds)
        logger.debug("[RealTimeLoop] Delay complete, entering tick loop for meeting=%s", self._meeting_id)

        while True:
            await self._tick()
            await asyncio.sleep(self._cfg.realtime_loop_interval_seconds)

    # ------------------------------------------------------------------
    # Single evaluation tick
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        logger.debug("[RealTimeLoop] Tick — meeting=%s", self._meeting_id)
        now = time.monotonic()
        # Skip checks until transcript is captured OR 2 intervals have passed (agent may be slow)
        if not self._has_transcript and self._tick_count < 2:
            self._tick_count += 1
            logger.debug("[RealTimeLoop] Skipping tick — no transcript yet (tick %d/2)", self._tick_count)
            await self._check_time_remaining()
            return
        self._tick_count += 1
        await self._check_agenda_adherence()
        await self._check_purpose(now)
        self._check_tone()
        await self._check_participation_pulse(now)
        await self._check_time_remaining()
        logger.debug("[RealTimeLoop] Tick complete — meeting=%s", self._meeting_id)

    # ------------------------------------------------------------------
    # 1. Agenda adherence
    # ------------------------------------------------------------------

    async def _check_agenda_adherence(self) -> None:
        if not self._agenda:
            logger.debug("[RealTimeLoop] Agenda adherence skipped — no agenda topics")
            return
        logger.debug("[RealTimeLoop] Checking agenda adherence — meeting=%s topics=%d", self._meeting_id, len(self._agenda))

        try:
            result = await self._mcp.compute_similarity(
                text=f"recent transcript window for {self._meeting_id}",
                agenda_topics=self._agenda,
                meeting_id=self._meeting_id,
            )
        except McpCallError as exc:
            logger.warning("Similarity check failed for %s: %s", self._meeting_id, exc)
            return

        max_score = result.max_score
        self._similarity_buffer.append(max_score)

        # Track per-topic best score seen so far (for time-remaining open items)
        for score_entry in result.scores:
            prev = self._topic_max_scores.get(score_entry.topic, 0.0)
            self._topic_max_scores[score_entry.topic] = max(prev, score_entry.score)

        # Keep only the last N windows
        window = self._cfg.off_track_consecutive_windows
        if len(self._similarity_buffer) > window:
            self._similarity_buffer = self._similarity_buffer[-window:]

        # Off-track: all recent windows below threshold
        if (
            len(self._similarity_buffer) >= window
            and all(s < self._cfg.off_track_similarity_threshold for s in self._similarity_buffer)
        ):
            await self._send_throttled_alert("off_track", {
                "type": "off_track",
                "meeting_id": self._meeting_id,
                "max_similarity": max_score,
            })

        # Agenda unclear: no score above unclear threshold within trigger window
        trigger_ticks = self._cfg.agenda_unclear_trigger_minutes * 60 / self._cfg.realtime_loop_interval_seconds
        second_ticks = self._cfg.agenda_unclear_second_alert_minutes * 60 / self._cfg.realtime_loop_interval_seconds

        if (
            len(self._similarity_buffer) >= trigger_ticks
            and all(s < self._cfg.agenda_unclear_threshold for s in self._similarity_buffer)
        ):
            if len(self._similarity_buffer) >= second_ticks:
                await self._send_throttled_alert("agenda_unclear_second", {
                    "type": "agenda_unclear_second",
                    "meeting_id": self._meeting_id,
                })
            else:
                await self._send_throttled_alert("agenda_unclear", {
                    "type": "agenda_unclear",
                    "meeting_id": self._meeting_id,
                })

    # ------------------------------------------------------------------
    # 2. Purpose detection
    # ------------------------------------------------------------------

    async def _check_purpose(self, now: float) -> None:
        delay = self._cfg.purpose_detection_delay_seconds
        logger.debug("[RealTimeLoop] Purpose check — meeting=%s detected=%s", self._meeting_id, self._purpose_detected)

        if not self._purpose_detected:
            if self._purpose_detected_at is None:
                self._purpose_detected_at = now + delay
                return
            if now < self._purpose_detected_at:
                return
            # Time to detect purpose
            await self._detect_purpose()
            self._purpose_detected = True
            self._last_purpose_check = now
            return

        # Re-check for drift
        recheck_interval = self._cfg.purpose_recheck_interval_minutes * 60
        if self._last_purpose_check is None or (now - self._last_purpose_check) < recheck_interval:
            return

        self._last_purpose_check = now
        drifted = self._recheck_purpose_drift()
        if drifted:
            self._purpose_divergence_ticks += 1
            drift_threshold = self._cfg.purpose_drift_consecutive_minutes * 60 / self._cfg.realtime_loop_interval_seconds
            if self._purpose_divergence_ticks >= drift_threshold:
                await self._send_throttled_alert("purpose_drift", {
                    "type": "purpose_drift",
                    "meeting_id": self._meeting_id,
                })
        else:
            self._purpose_divergence_ticks = 0

    async def _detect_purpose(self) -> None:
        """Send purpose_detected alert (actual classification would call an LLM)."""
        logger.info("Purpose detection triggered for meeting %s", self._meeting_id)
        await self._send_alert("purpose_detected", {
            "type": "purpose_detected",
            "meeting_id": self._meeting_id,
            "purpose": "unknown",
            "mismatch": False,
        })

    def _recheck_purpose_drift(self) -> bool:
        """Returns True if purpose appears to have drifted (stub — real impl calls LLM)."""
        logger.debug("Purpose drift re-check for meeting %s", self._meeting_id)
        return False

    # ------------------------------------------------------------------
    # 3. Tone monitoring
    # ------------------------------------------------------------------

    def _check_tone(self) -> None:
        """
        Tone analysis stub — real implementation would call an LLM with the
        recent transcript window and parse tone issues from the response.
        Issues are persisted to the MeetingRecord via store_meeting_record.
        """
        logger.debug("Tone check tick for meeting %s", self._meeting_id)

    # ------------------------------------------------------------------
    # 4. Participation pulse
    # ------------------------------------------------------------------

    async def _check_participation_pulse(self, now: float) -> None:
        interval_seconds = self._cfg.participation_pulse_interval_minutes * 60
        if self._last_pulse_at is not None and (now - self._last_pulse_at) < interval_seconds:
            logger.debug("[RealTimeLoop] Pulse skipped — next in %.0fs", interval_seconds - (now - self._last_pulse_at))
            return
        logger.debug("[RealTimeLoop] Running participation pulse — meeting=%s snapshot=%d", self._meeting_id, self._pulse_snapshot_count)

        self._last_pulse_at = now

        try:
            from orchestrator.foundry_client import FoundryClient  # avoid circular at module level
        except ImportError:
            return

        # Dispatch participation pulse task via MCP participant rates as a proxy
        try:
            participant_ids = list(getattr(self._record, "participants", []))
            if not participant_ids:
                return

            rates = await self._mcp.get_participant_rates(self._meeting_id, participant_ids)
            active = [r.participant_id for r in rates.rates if r.hourly_rate is not None]
            silent = [r.participant_id for r in rates.rates if r.hourly_rate is None]

            snapshot = ParticipationPulseSnapshot(
                snapshot_number=self._pulse_snapshot_count,
                captured_at=_utcnow(),
                active_speakers=active,
                silent_participants=silent,
                energy_level="Medium",
            )
            self._pulse_snapshot_count += 1

            # Persist snapshot to record
            if hasattr(self._record, "participation_pulse_snapshots"):
                self._record.participation_pulse_snapshots.append(snapshot)

            # Alert on silent participants exceeding threshold
            threshold_seconds = self._cfg.silent_participant_threshold_minutes * 60
            pulse_interval = self._cfg.participation_pulse_interval_minutes * 60
            silent_ticks_threshold = threshold_seconds / pulse_interval

            if len(silent) > 0 and self._pulse_snapshot_count >= silent_ticks_threshold:
                await self._send_throttled_alert("silent_participant", {
                    "type": "silent_participant",
                    "meeting_id": self._meeting_id,
                    "silent_participants": silent,
                })

        except McpCallError as exc:
            logger.warning("Participation pulse failed for %s: %s", self._meeting_id, exc)

    # ------------------------------------------------------------------
    # 5. Time remaining — wrap-up alert
    # ------------------------------------------------------------------

    async def _check_time_remaining(self) -> None:
        """
        When the meeting is within `time_remaining_alert_minutes` of its
        scheduled end, send a single alert listing:
          - Agenda topics not yet covered (similarity never exceeded threshold)
          - A note to resolve open items before time is up
        Fires once per meeting only.
        """
        if self._time_remaining_sent or self._scheduled_end is None:
            logger.debug("[RealTimeLoop] Time remaining check skipped — sent=%s has_end=%s",
                        self._time_remaining_sent, self._scheduled_end is not None)
            return

        now_utc = datetime.now(timezone.utc)
        remaining_seconds = (self._scheduled_end - now_utc).total_seconds()
        threshold_seconds = self._cfg.time_remaining_alert_minutes * 60
        logger.debug("[RealTimeLoop] Time remaining — meeting=%s remaining=%.0fs threshold=%ds",
                    self._meeting_id, remaining_seconds, threshold_seconds)

        if remaining_seconds > threshold_seconds or remaining_seconds <= 0:
            return

        # Determine which agenda topics haven't been adequately covered
        uncovered = [
            topic for topic in self._agenda
            if self._topic_max_scores.get(topic, 0.0) < self._cfg.off_track_similarity_threshold
        ]

        minutes_left = max(0, int(remaining_seconds // 60))
        plural = "s" if minutes_left != 1 else ""

        if uncovered:
            message = (
                f"About {minutes_left} minute{plural} remain. "
                "Please focus on resolving the following open issues and next steps before time is up."
            )
        else:
            message = (
                f"About {minutes_left} minute{plural} remain. "
                "Please wrap up any open action items before time is up."
            )

        card = {
            "type": "time_remaining",
            "meeting_id": self._meeting_id,
            "minutes_remaining": minutes_left,
            "uncovered_agenda_topics": uncovered,
            "message": message,
        }

        await self._send_alert("time_remaining", card)
        self._time_remaining_sent = True
        logger.info(
            "Time remaining alert sent for meeting %s — %d min left, %d uncovered topics",
            self._meeting_id, minutes_left, len(uncovered),
        )

    async def _send_throttled_alert(self, alert_type: str, card: dict) -> None:
        """Send alert only if outside the throttle window."""
        now = time.monotonic()
        last = self._alert_timestamps.get(alert_type, 0.0)
        if (now - last) < self._cfg.alert_throttle_window_seconds:
            logger.debug("Alert '%s' throttled for meeting %s", alert_type, self._meeting_id)
            return
        await self._send_alert(alert_type, card)

    async def _send_alert(self, alert_type: str, card: dict) -> None:
        try:
            await self._mcp.send_realtime_alert(self._meeting_id, alert_type, card)
            self._alert_timestamps[alert_type] = time.monotonic()
            logger.info("Alert '%s' sent for meeting %s", alert_type, self._meeting_id)
        except McpCallError as exc:
            logger.warning("Alert '%s' failed for %s: %s", alert_type, self._meeting_id, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> Optional[datetime]:
    """Parse an ISO8601 string to a timezone-aware datetime. Returns None on failure."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None

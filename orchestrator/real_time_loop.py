"""
RealTimeLoop — per-meeting background evaluation loop.

Runs every REALTIME_LOOP_INTERVAL_SECONDS after an initial start delay.
Responsibilities (per orchestrator_v1.md):
  1. Agenda adherence — similarity check, off-track / agenda-unclear alerts
  2. Purpose detection — classify meeting purpose once, then re-check for drift
  3. Tone monitoring — detect tone issues, send private/meeting alerts
  4. Participation pulse — snapshot active/silent speakers, alert on silence
"""
from __future__ import annotations

import asyncio
import logging
import time
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
    ) -> None:
        self._meeting_id = meeting_id
        self._record = record
        self._mcp = mcp
        self._cfg = cfg
        # Agenda is sourced from the calendar event at meeting start.
        # Falls back to empty list if not provided (no-agenda meeting).
        self._agenda: list[str] = agenda or []

        # Agenda adherence state
        self._similarity_buffer: list[float] = []
        self._alert_timestamps: dict[str, float] = {}  # alert_type → epoch

        # Purpose detection state
        self._purpose_detected: bool = False
        self._purpose_detected_at: Optional[float] = None
        self._purpose_divergence_ticks: int = 0
        self._last_purpose_check: Optional[float] = None

        # Participation pulse state
        self._pulse_snapshot_count: int = 0
        self._last_pulse_at: Optional[float] = None

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main loop — waits for start delay then ticks at configured interval."""
        logger.info("RealTimeLoop starting for meeting %s (delay=%ds)",
                    self._meeting_id, self._cfg.realtime_loop_start_delay_seconds)
        await asyncio.sleep(self._cfg.realtime_loop_start_delay_seconds)

        while True:
            await self._tick()
            await asyncio.sleep(self._cfg.realtime_loop_interval_seconds)

    # ------------------------------------------------------------------
    # Single evaluation tick
    # ------------------------------------------------------------------

    async def _tick(self) -> None:
        now = time.monotonic()
        await self._check_agenda_adherence()
        await self._check_purpose(now)
        await self._check_tone()
        await self._check_participation_pulse(now)

    # ------------------------------------------------------------------
    # 1. Agenda adherence
    # ------------------------------------------------------------------

    async def _check_agenda_adherence(self) -> None:
        if not self._agenda:
            return

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

        # Keep only the last N windows
        window = self._cfg.off_track_consecutive_windows
        if len(self._similarity_buffer) > window:
            self._similarity_buffer = self._similarity_buffer[-window:]

        elapsed_minutes = self._cfg.realtime_loop_interval_seconds * len(self._similarity_buffer) / 60

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
        drifted = await self._recheck_purpose_drift()
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

    async def _recheck_purpose_drift(self) -> bool:
        """Returns True if purpose appears to have drifted (stub — real impl calls LLM)."""
        logger.debug("Purpose drift re-check for meeting %s", self._meeting_id)
        return False

    # ------------------------------------------------------------------
    # 3. Tone monitoring
    # ------------------------------------------------------------------

    async def _check_tone(self) -> None:
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
            return

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
    # Alert helpers
    # ------------------------------------------------------------------

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

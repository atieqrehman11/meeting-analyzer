"""
Orchestrator — meeting lifecycle coordinator.
Delegates post-meeting work to PostMeetingAnalyzer,
real-time evaluation to RealTimeLoop,
and all I/O to McpClient / FoundryClient.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from orchestrator.config import OrchestratorConfig
from orchestrator.foundry_client import FoundryClient, build_foundry_client, load_agent_ids
from shared_models.mcp_client import BaseMcpClient
from orchestrator.meeting_initiator import MeetingInitiator
from orchestrator.post_meeting_analyzer import PostMeetingAnalyzer
from shared_models.a2a_schemas import CaptureTranscriptSegmentTask

logger = logging.getLogger("orchestrator")


class Orchestrator:
    """
    Owns the meeting lifecycle for a single meeting.
    One instance per active meeting — created by the Bot on meeting_start.
    """

    def __init__(self, config: OrchestratorConfig, mcp: BaseMcpClient) -> None:
        self._cfg = config
        self._mcp = mcp
        self._foundry: FoundryClient = build_foundry_client(config)
        self._agent_ids: dict[str, str] = load_agent_ids()

        self._capture_task: Optional[asyncio.Task] = None
        self._realtime_task: Optional[asyncio.Task] = None
        self._end_timer_task: Optional[asyncio.Task] = None

        self._initiator = MeetingInitiator(mcp=self._mcp)
        self._post_analyzer = PostMeetingAnalyzer(
            foundry=self._foundry,
            mcp=self._mcp,
            agent_ids=self._agent_ids,
            timeout_seconds=config.specialist_agent_timeout_seconds,
        )

    # ------------------------------------------------------------------
    # Public lifecycle hooks
    # ------------------------------------------------------------------

    async def on_meeting_start(self, meeting_id: str, participant_roster: list[dict]) -> None:
        logger.info("Meeting started: %s", meeting_id)
        record = await self._initiator.initialise(meeting_id, participant_roster)
        self._start_loops(meeting_id, record)
        # Fallback: auto-end if Teams doesn't send the end event
        end_time = getattr(record, "end_time", None)
        if end_time:
            self._end_timer_task = asyncio.create_task(
                self._auto_end(meeting_id, end_time),
                name=f"end-timer-{meeting_id}",
            )
        else:
            # No scheduled end time (ad-hoc meeting) — use max duration fallback
            logger.info("No scheduled end time for meeting %s — using 1h max duration fallback", meeting_id)
            self._end_timer_task = asyncio.create_task(
                self._auto_end_after(meeting_id, seconds=1 * 3600),
                name=f"end-timer-{meeting_id}",
            )

    async def on_meeting_end(self, meeting_id: str) -> None:
        logger.info("Meeting ended: %s", meeting_id)
        if hasattr(self, "_end_timer_task") and self._end_timer_task:
            self._end_timer_task.cancel()
        await self._cancel_loops()
        await self._post_analyzer.run(meeting_id)

    async def _auto_end(self, meeting_id: str, end_time_iso: str) -> None:
        """Trigger on_meeting_end automatically if Teams doesn't send the event.

        Logic:
        - Before scheduled end: poll every 60s, trigger on inactivity
        - After scheduled end: keep polling, trigger on inactivity (meeting ran over)
        - Never force-end while transcript capture is still active
        """
        from datetime import datetime, timezone
        try:
            end_dt = datetime.fromisoformat(end_time_iso.replace("Z", "+00:00"))
            inactivity_limit = self._cfg.transcript_capture_interval_seconds * 3
            poll_interval = 60.0
            logger.info(
                "Auto-end watchdog started for meeting %s (scheduled end: %s, inactivity limit: %ds)",
                meeting_id, end_time_iso, inactivity_limit
            )

            while True:
                await asyncio.sleep(poll_interval)

                now = datetime.now(timezone.utc)
                past_end = now > end_dt
                last_capture = getattr(self, "_last_capture_at", None)
                idle = (asyncio.get_event_loop().time() - last_capture) if last_capture else None

                if idle is not None and idle > inactivity_limit:
                    logger.warning(
                        "Auto-end triggered for %s — inactivity %.0fs (past_scheduled_end=%s)",
                        meeting_id, idle, past_end
                    )
                    break

                if past_end:
                    logger.debug("Meeting %s running over scheduled end — waiting for inactivity", meeting_id)

            await self.on_meeting_end(meeting_id)
        except asyncio.CancelledError:
            logger.debug("Auto-end watchdog cancelled for meeting %s (end event received)", meeting_id)

    async def _auto_end_after(self, meeting_id: str, seconds: float) -> None:
        """Fallback for ad-hoc meetings with no scheduled end time."""
        try:
            logger.info("Auto-end fallback: will trigger after %.0fs for meeting %s", seconds, meeting_id)
            await asyncio.sleep(seconds)
            logger.warning("Auto-end max duration reached for meeting %s", meeting_id)
            await self.on_meeting_end(meeting_id)
        except asyncio.CancelledError:
            logger.debug("Auto-end fallback cancelled for meeting %s", meeting_id)

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    def _start_loops(self, meeting_id: str, record) -> None:
        from orchestrator.real_time_loop import RealTimeLoop

        self._capture_task = asyncio.create_task(
            self._transcript_capture_loop(meeting_id),
            name=f"capture-{meeting_id}",
        )
        loop = RealTimeLoop(
            meeting_id, record, self._mcp, self._cfg,
            agenda=getattr(record, "agenda", []) or [],
            scheduled_end_time=getattr(record, "end_time", None),
        )
        self._realtime_task = asyncio.create_task(
            loop.run(), name=f"realtime-{meeting_id}"
        )

    async def _cancel_loops(self) -> None:
        for task in (self._capture_task, self._realtime_task, self._end_timer_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    async def _transcript_capture_loop(self, meeting_id: str) -> None:
        interval = self._cfg.transcript_capture_interval_seconds
        while True:
            await asyncio.sleep(interval)
            await self._capture_segment(meeting_id, interval)
            # Update last activity timestamp for inactivity detection
            if hasattr(self, "_end_timer_task"):
                self._last_capture_at = asyncio.get_event_loop().time()

    async def _capture_segment(self, meeting_id: str, window_seconds: int) -> None:
        task = CaptureTranscriptSegmentTask(
            meeting_id=meeting_id, segment_window_seconds=window_seconds
        )
        response = await self._foundry.dispatch(
            self._agent_ids["transcript"], task.model_dump()
        )
        if response.get("gap_detected"):
            logger.warning("Transcript gap detected in meeting %s", meeting_id)

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
        self._realtime_loop = None
        self._last_capture_at: Optional[float] = None

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
        end_time = getattr(record, "end_time", None)
        if end_time:
            self._end_timer_task = asyncio.create_task(
                self._auto_end(meeting_id, end_time),
                name=f"end-timer-{meeting_id}",
            )
        else:
            logger.info("No scheduled end time for meeting %s — using 30m max duration fallback", meeting_id)
            self._end_timer_task = asyncio.create_task(
                self._auto_end_after(meeting_id, seconds=1800),
                name=f"end-timer-{meeting_id}",
            )

    async def on_meeting_end(self, meeting_id: str) -> None:
        logger.info("Meeting ended: %s", meeting_id)
        if self._end_timer_task:
            self._end_timer_task.cancel()
        await self._cancel_loops()
        await self._post_analyzer.run(meeting_id)


    # ------------------------------------------------------------------
    # Auto-end watchdog
    # ------------------------------------------------------------------

    async def _auto_end(self, meeting_id: str, end_time_iso: str) -> None:
        """Poll until inactivity detected, then trigger on_meeting_end."""
        from datetime import datetime, timezone
        try:
            end_dt = datetime.fromisoformat(end_time_iso.replace("Z", "+00:00"))
            inactivity_limit = self._cfg.transcript_capture_interval_seconds * 3
            logger.info(
                "Auto-end watchdog started for meeting %s (scheduled end: %s, inactivity limit: %ds)",
                meeting_id, end_time_iso, inactivity_limit,
            )
            while True:
                await asyncio.sleep(60.0)
                now = datetime.now(timezone.utc)
                past_end = now > end_dt
                idle = (asyncio.get_event_loop().time() - self._last_capture_at) if self._last_capture_at else None
                if idle is not None and idle > inactivity_limit:
                    logger.warning("Auto-end triggered for %s — inactivity %.0fs (past_end=%s)", meeting_id, idle, past_end)
                    break
                if past_end:
                    logger.debug("Meeting %s running over scheduled end — waiting for inactivity", meeting_id)
            await self.on_meeting_end(meeting_id)
        except asyncio.CancelledError:
            logger.debug("Auto-end watchdog cancelled for meeting %s", meeting_id)

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
        self._realtime_loop = loop
        self._realtime_task = asyncio.create_task(
            loop.run(), name=f"realtime-{meeting_id}",
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
        logger.info("Transcript capture loop started for meeting %s (interval=%ds)", meeting_id, interval)
        while True:
            await asyncio.sleep(interval)
            logger.debug("Transcript capture tick for meeting %s", meeting_id)
            await self._capture_segment(meeting_id, interval)
            self._last_capture_at = asyncio.get_event_loop().time()

    async def _capture_segment(self, meeting_id: str, window_seconds: int) -> None:
        task = CaptureTranscriptSegmentTask(
            meeting_id=meeting_id, segment_window_seconds=window_seconds
        )
        response = await self._foundry.dispatch(
            self._agent_ids["transcript"], task.model_dump()
        )
        logger.debug("Transcript agent response for meeting %s: %s", meeting_id, response)
        if response.get("status") == "error":
            logger.error("Transcript agent error for meeting %s: %s", meeting_id, response.get("error"))
        elif response.get("gap_detected"):
            logger.warning("Transcript gap detected in meeting %s", meeting_id)
        else:
            logger.debug("Transcript segment captured for meeting %s", meeting_id)
            if self._realtime_loop is not None:
                self._realtime_loop.notify_transcript_captured()
            else:
                logger.warning("Transcript captured but realtime_loop is None for meeting %s", meeting_id)

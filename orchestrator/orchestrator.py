"""
Orchestrator — meeting lifecycle coordinator.
Delegates post-meeting work to PostMeetingAnalyzer,
real-time evaluation to RealTimeLoop,
and all I/O to McpClient / FoundryClient.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import OrchestratorConfig
from foundry_client import FoundryClient, build_foundry_client, load_agent_ids
from mcp_client import McpClient
from meeting_initiator import MeetingInitiator
from post_meeting_analyzer import PostMeetingAnalyzer
from shared_models.a2a_schemas import CaptureTranscriptSegmentTask

logger = logging.getLogger("orchestrator")


class Orchestrator:
    """
    Owns the meeting lifecycle for a single meeting.
    One instance per active meeting — created by the Bot on meeting_start.
    """

    def __init__(self, config: OrchestratorConfig, mcp: McpClient) -> None:
        self._cfg = config
        self._mcp = mcp
        self._foundry: FoundryClient = build_foundry_client(config)
        self._agent_ids: dict[str, str] = load_agent_ids()

        self._capture_task: Optional[asyncio.Task] = None
        self._realtime_task: Optional[asyncio.Task] = None

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

    async def on_meeting_start(
        self, meeting_id: str, participant_roster: list[dict]
    ) -> None:
        logger.info("Meeting started: %s", meeting_id)
        record = await self._initiator.initialise(meeting_id, participant_roster)
        self._start_loops(meeting_id, record)

    async def on_meeting_end(self, meeting_id: str) -> None:
        logger.info("Meeting ended: %s", meeting_id)
        await self._cancel_loops()
        await self._post_analyzer.run(meeting_id)

    # ------------------------------------------------------------------
    # Background loops
    # ------------------------------------------------------------------

    def _start_loops(self, meeting_id: str, record) -> None:
        from real_time_loop import RealTimeLoop

        self._capture_task = asyncio.create_task(
            self._transcript_capture_loop(meeting_id),
            name=f"capture-{meeting_id}",
        )
        loop = RealTimeLoop(meeting_id, record, self._mcp, self._cfg)
        self._realtime_task = asyncio.create_task(
            loop.run(), name=f"realtime-{meeting_id}"
        )

    async def _cancel_loops(self) -> None:
        for task in (self._capture_task, self._realtime_task):
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

    async def _capture_segment(self, meeting_id: str, window_seconds: int) -> None:
        task = CaptureTranscriptSegmentTask(
            meeting_id=meeting_id, segment_window_seconds=window_seconds
        )
        response = await self._foundry.dispatch(
            self._agent_ids["transcript"], task.model_dump()
        )
        if response.get("gap_detected"):
            logger.warning("Transcript gap detected in meeting %s", meeting_id)

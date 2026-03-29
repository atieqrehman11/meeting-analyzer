"""
PostMeetingAnalyzer — orchestrates the full post-meeting pipeline.

Responsibilities:
- Finalise the transcript via the Transcription Agent
- Dispatch analysis and sentiment agents in parallel
- Compile and deliver the final AnalysisReport
"""
from __future__ import annotations

import asyncio
import logging

from foundry_client import FoundryClient
from mcp_client import McpClient, McpCallError
from report_builder import build_report_card, compile_report
from shared_models.a2a_schemas import (
    AnalyzeMeetingResponse,
    AnalyzeMeetingTask,
    AnalyzeSentimentResponse,
    AnalyzeSentimentTask,
    FinalizeTranscriptResponse,
    FinalizeTranscriptTask,
)
from shared_models.mcp_types import AnalysisReport

logger = logging.getLogger("orchestrator.post_meeting")


class PostMeetingAnalyzer:
    """
    Runs the post-meeting pipeline for a single meeting.
    Injected with FoundryClient and McpClient — fully testable via mocks.
    """

    def __init__(
        self,
        foundry: FoundryClient,
        mcp: McpClient,
        agent_ids: dict[str, str],
        timeout_seconds: float,
    ) -> None:
        self._foundry = foundry
        self._mcp = mcp
        self._agent_ids = agent_ids
        self._timeout = timeout_seconds

    async def run(self, meeting_id: str) -> AnalysisReport:
        """Execute the full post-meeting pipeline and return the compiled report."""
        transcript_url = await self._finalise_transcript(meeting_id)
        report = await self._analyse(meeting_id, transcript_url)
        await self._deliver(meeting_id, report)
        return report

    # ------------------------------------------------------------------
    # Transcript finalisation
    # ------------------------------------------------------------------

    async def _finalise_transcript(self, meeting_id: str) -> str:
        task = FinalizeTranscriptTask(meeting_id=meeting_id)
        raw = await self._foundry.dispatch(
            self._agent_ids["transcript"], task.model_dump()
        )
        response = FinalizeTranscriptResponse(**raw)
        if response.status == "error" or not response.transcript_blob_url:
            raise RuntimeError(
                f"Transcript finalisation failed for {meeting_id}: {response.error}"
            )
        logger.info("Transcript finalised: %s", meeting_id)
        return response.transcript_blob_url

    # ------------------------------------------------------------------
    # Parallel analysis
    # ------------------------------------------------------------------

    async def _analyse(self, meeting_id: str, transcript_url: str) -> AnalysisReport:
        analysis, sentiment = await asyncio.gather(
            self._dispatch_analysis(meeting_id, transcript_url),
            self._dispatch_sentiment(meeting_id, transcript_url),
            return_exceptions=True,
        )
        return compile_report(meeting_id, analysis, sentiment)

    async def _dispatch_analysis(
        self, meeting_id: str, transcript_url: str
    ) -> AnalyzeMeetingResponse:
        task = AnalyzeMeetingTask(
            meeting_id=meeting_id, transcript_blob_url=transcript_url
        )
        raw = await self._foundry.dispatch_with_timeout(
            self._agent_ids["analysis"], task.model_dump(), self._timeout
        )
        return AnalyzeMeetingResponse(**raw)

    async def _dispatch_sentiment(
        self, meeting_id: str, transcript_url: str
    ) -> AnalyzeSentimentResponse:
        task = AnalyzeSentimentTask(
            meeting_id=meeting_id, transcript_blob_url=transcript_url
        )
        raw = await self._foundry.dispatch_with_timeout(
            self._agent_ids["sentiment"], task.model_dump(), self._timeout
        )
        return AnalyzeSentimentResponse(**raw)

    # ------------------------------------------------------------------
    # Report delivery
    # ------------------------------------------------------------------

    async def _deliver(self, meeting_id: str, report: AnalysisReport) -> None:
        await self._mcp.store_analysis_report(report)
        await self._post_card(meeting_id, report)

    async def _post_card(self, meeting_id: str, report: AnalysisReport) -> None:
        card = build_report_card(report)
        try:
            await self._mcp.post_adaptive_card(meeting_id, card)
        except McpCallError as exc:
            logger.error("Report card delivery failed for %s: %s", meeting_id, exc)
            await self._send_fallback_dm(meeting_id)

    async def _send_fallback_dm(self, meeting_id: str) -> None:
        try:
            await self._mcp.post_adaptive_card(
                meeting_id,
                {"type": "message", "text": f"Meeting report ready for {meeting_id}."},
            )
        except McpCallError as exc:
            logger.error("Fallback DM also failed for %s: %s", meeting_id, exc)

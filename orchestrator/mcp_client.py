"""
Typed async HTTP client for the MCP server.
All Orchestrator code calls this — never raw HTTP directly.
Handles retries for retryable errors and raises McpCallError on failures.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from shared_models.mcp_types import (
    CalendarEventOutput,
    GetRecordingStatusOutput,
    MeetingRecord,
    TranscriptSegment,
    ConsentRecord,
    AnalysisReport,
    ComputeSimilarityOutput,
    GetParticipantRatesOutput,
    MeetingCostSnapshot,
    ActionItem,
)

logger = logging.getLogger("orchestrator.mcp_client")


class McpCallError(Exception):
    """Raised when an MCP tool call fails after all retries."""
    def __init__(self, code: str, message: str, retryable: bool) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(f"[{code}] {message}")


class McpClient:
    """
    Async client for all MCP server tools.
    Base URL is read from config at construction time.
    Retries retryable errors up to max_retries times with exponential backoff.
    """

    BASE = "/v1/tools"

    def __init__(
        self,
        base_url: str,
        max_retries: int = 3,
        backoff: tuple[float, ...] = (1.0, 2.0, 4.0),
        timeout: float = 30.0,
    ) -> None:
        self._http = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._max_retries = max_retries
        self._backoff = backoff

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "McpClient":
        return self

    async def __aexit__(self, *_) -> None:
        await self.aclose()

    # ------------------------------------------------------------------
    # Stage 1 — Meeting
    # ------------------------------------------------------------------

    async def get_calendar_event(self, meeting_id: str) -> CalendarEventOutput:
        data = await self._post("/meeting/get_calendar_event", {"meeting_id": meeting_id})
        return CalendarEventOutput(**data)

    async def get_recording_status(self, meeting_id: str) -> GetRecordingStatusOutput:
        data = await self._post("/meeting/get_recording_status", {"meeting_id": meeting_id})
        return GetRecordingStatusOutput(**data)

    async def store_meeting_record(self, record: MeetingRecord) -> None:
        await self._post("/meeting/store_meeting_record",
                         {"meeting_record": record.model_dump()}, expect_body=False)

    async def post_adaptive_card(
        self,
        meeting_id: str,
        card_payload: dict,
        target_participant_ids: Optional[list[str]] = None,
    ) -> None:
        await self._post("/meeting/post_adaptive_card", {
            "meeting_id": meeting_id,
            "card_payload": card_payload,
            "target_participant_ids": target_participant_ids,
        }, expect_body=False)

    # ------------------------------------------------------------------
    # Stage 1 — Transcript
    # ------------------------------------------------------------------

    async def store_transcript_segment(self, segment: TranscriptSegment) -> None:
        await self._post("/transcript/store_transcript_segment",
                         {"segment": segment.model_dump()}, expect_body=False)

    # ------------------------------------------------------------------
    # Stage 1 — Consent
    # ------------------------------------------------------------------

    async def store_consent_record(self, record: ConsentRecord) -> None:
        await self._post("/consent/store_consent_record",
                         {"consent_record": record.model_dump()}, expect_body=False)

    # ------------------------------------------------------------------
    # Stage 1 — Analysis
    # ------------------------------------------------------------------

    async def store_analysis_report(self, report: AnalysisReport) -> None:
        await self._post("/analysis/store_analysis_report",
                         {"report": report.model_dump()}, expect_body=False)

    async def get_analysis_report(self, meeting_id: str) -> AnalysisReport:
        data = await self._post("/analysis/get_analysis_report", {"meeting_id": meeting_id})
        return AnalysisReport(**data)

    # ------------------------------------------------------------------
    # Stage 1 — Similarity
    # ------------------------------------------------------------------

    async def compute_similarity(
        self,
        text: str,
        agenda_topics: list[str],
        meeting_id: str,
    ) -> ComputeSimilarityOutput:
        data = await self._post("/similarity/compute_similarity", {
            "text": text,
            "agenda_topics": agenda_topics,
            "meeting_id": meeting_id,
        })
        return ComputeSimilarityOutput(**data)

    # ------------------------------------------------------------------
    # Stage 2 — Real-time
    # ------------------------------------------------------------------

    async def send_realtime_alert(
        self,
        meeting_id: str,
        alert_type: str,
        card_payload: dict,
        target_participant_ids: Optional[list[str]] = None,
    ) -> None:
        await self._post("/realtime/send_realtime_alert", {
            "meeting_id": meeting_id,
            "alert_type": alert_type,
            "card_payload": card_payload,
            "target_participant_ids": target_participant_ids,
        }, expect_body=False)

    async def get_participant_rates(
        self,
        meeting_id: str,
        participant_ids: list[str],
    ) -> GetParticipantRatesOutput:
        data = await self._post("/realtime/get_participant_rates", {
            "meeting_id": meeting_id,
            "participant_ids": participant_ids,
        })
        return GetParticipantRatesOutput(**data)

    async def store_cost_snapshot(self, snapshot: MeetingCostSnapshot) -> None:
        await self._post("/realtime/store_cost_snapshot",
                         {"snapshot": snapshot.model_dump()}, expect_body=False)

    # ------------------------------------------------------------------
    # Stage 3 — Poll
    # ------------------------------------------------------------------

    async def create_poll(self, meeting_id: str, action_items: list[ActionItem]) -> str:
        data = await self._post("/poll/create_poll", {
            "meeting_id": meeting_id,
            "action_items": [item.model_dump() for item in action_items],
        })
        return data["poll_id"]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _post(self, path: str, payload: dict, *, expect_body: bool = True) -> dict:
        url = f"{self.BASE}{path}"
        last_error: Optional[McpCallError] = None

        for attempt, delay in enumerate((*self._backoff, None)):
            error = await self._attempt(url, payload, expect_body, path, attempt)
            if error is None:
                return self._last_response  # type: ignore[attr-defined]
            last_error = error
            if not error.retryable or delay is None:
                raise error
            await asyncio.sleep(delay)

        raise last_error  # type: ignore[misc]

    async def _attempt(
        self, url: str, payload: dict, expect_body: bool, path: str, attempt: int
    ) -> Optional[McpCallError]:
        """Execute one HTTP attempt. Returns None on success (sets _last_response), McpCallError on failure."""
        try:
            resp = await self._http.post(url, json=payload)
        except httpx.TransportError as exc:
            logger.warning("MCP transport error on %s (attempt %d): %s", path, attempt + 1, exc)
            return McpCallError("TRANSPORT_ERROR", str(exc), retryable=True)

        if resp.status_code in (200, 204):
            self._last_response = resp.json() if expect_body and resp.content else {}
            return None

        error = self._parse_error(resp)
        if error.retryable:
            logger.warning("MCP retryable error on %s (attempt %d): [%s] %s",
                           path, attempt + 1, error.code, error.message)
        return error

    @staticmethod
    def _parse_error(resp: httpx.Response) -> McpCallError:
        """Extract a McpCallError from an error response."""
        try:
            err = resp.json().get("error", {})
            return McpCallError(
                code=err.get("code", "UNKNOWN"),
                message=err.get("message", resp.text),
                retryable=err.get("retryable", False),
            )
        except Exception:
            return McpCallError("UNKNOWN", resp.text, retryable=False)

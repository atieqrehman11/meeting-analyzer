from __future__ import annotations

from shared_models.mcp_client import BaseMcpClient
from shared_models.mcp_types import (
    AnalysisReport,
    CalendarEventOutput,
    ConsentRecord,
    GetRecordingStatusOutput,
    MeetingRecord,
)


class TeamBotMcpClient(BaseMcpClient):
    """MCP client wrapper exposing only the tools needed by the Teams bot."""

    async def get_calendar_event(self, meeting_id: str) -> CalendarEventOutput:
        data = await self._post("/meeting/get_calendar_event", {"meeting_id": meeting_id})
        return CalendarEventOutput(**data)

    async def get_recording_status(self, meeting_id: str) -> GetRecordingStatusOutput:
        data = await self._post("/meeting/get_recording_status", {"meeting_id": meeting_id})
        return GetRecordingStatusOutput(**data)

    async def store_meeting_record(self, record: MeetingRecord) -> None:
        await self._post(
            "/meeting/store_meeting_record",
            {"meeting_record": record.model_dump()},
            expect_body=False,
        )

    async def post_adaptive_card(
        self,
        meeting_id: str,
        card_payload: dict,
        target_participant_ids: list[str] | None = None,
    ) -> None:
        await self._post(
            "/meeting/post_adaptive_card",
            {
                "meeting_id": meeting_id,
                "card_payload": card_payload,
                "target_participant_ids": target_participant_ids,
            },
            expect_body=False,
        )

    async def store_consent_record(self, record: ConsentRecord) -> None:
        await self._post(
            "/consent/store_consent_record",
            {"consent_record": record.model_dump()},
            expect_body=False,
        )

    async def store_analysis_report(self, report: AnalysisReport) -> None:
        await self._post(
            "/analysis/store_analysis_report",
            {"report": report.model_dump()},
            expect_body=False,
        )

    async def send_realtime_alert(
        self,
        meeting_id: str,
        alert_type: str,
        card_payload: dict,
        target_participant_ids: list[str] | None = None,
    ) -> None:
        await self._post(
            "/realtime/send_realtime_alert",
            {
                "meeting_id": meeting_id,
                "alert_type": alert_type,
                "card_payload": card_payload,
                "target_participant_ids": target_participant_ids,
            },
            expect_body=False,
        )

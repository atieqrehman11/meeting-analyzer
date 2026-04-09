"""
MeetingInitiator — handles meeting setup on join.

Responsibilities:
- Fetch calendar event and extract agenda
- Send missing_agenda alert if no agenda found
- Build and persist the initial MeetingRecord
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone

from shared_models.mcp_client import BaseMcpClient, McpCallError
from shared_models.mcp_types import CalendarEventOutput, MeetingRecord
from shared_models.meeting_id import to_storage_key

logger = logging.getLogger("orchestrator.meeting_initiator")


class MeetingInitiator:
    """
    Handles all setup work when a meeting starts.
    Injected with McpClient — fully testable via mocks.
    """

    def __init__(self, mcp: BaseMcpClient) -> None:
        self._mcp = mcp

    async def initialise(
        self, meeting_id: str, participant_roster: list[dict]
    ) -> MeetingRecord:
        """Fetch calendar data, persist the meeting record, and return it."""
        calendar = await self._mcp.get_calendar_event(meeting_id)

        if not calendar.agenda:
            await self._send_alert(meeting_id, "missing_agenda", {})

        record = _build_meeting_record(meeting_id, calendar, participant_roster)
        await self._mcp.store_meeting_record(record)

        logger.info(
            "Meeting initialised: %s (agenda topics: %d, participants: %d)",
            meeting_id,
            len(calendar.agenda),
            len(participant_roster),
        )
        return record

    async def _send_alert(
        self, meeting_id: str, alert_type: str, card: dict
    ) -> None:
        try:
            await self._mcp.send_realtime_alert(meeting_id, alert_type, card)
        except McpCallError as exc:
            logger.warning("Alert '%s' failed for %s: %s", alert_type, meeting_id, exc)


# ---------------------------------------------------------------------------
# Pure helper — no I/O, no side effects
# ---------------------------------------------------------------------------

def _build_meeting_record(
    meeting_id: str,
    calendar: CalendarEventOutput,
    participant_roster: list[dict],
) -> MeetingRecord:
    """Build a MeetingRecord from calendar data and the initial participant roster."""
    now = datetime.now(timezone.utc).isoformat()
    participants = [p["id"] for p in participant_roster if "id" in p]
    return MeetingRecord(
        id=f"meeting_{to_storage_key(meeting_id)}",
        meeting_id=meeting_id,
        organizer_id=calendar.organizer_id,
        organizer_name=calendar.organizer_name,
        subject=calendar.subject,
        start_time=calendar.start_time,
        end_time=calendar.end_time,
        participants=participants,
        stage="transcribing",
        created_at=now,
        updated_at=now,
        azure_region=os.environ.get("AZURE_REGION", "eastus"),
        retention_expires_at=(
            datetime.fromisoformat(calendar.start_time) + timedelta(days=90)
        ).isoformat(),
    )

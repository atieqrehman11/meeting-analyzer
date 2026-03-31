"""Tests for MeetingInitiator and _build_meeting_record."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from orchestrator.meeting_initiator import MeetingInitiator, _build_meeting_record
from shared_models.mcp_types import CalendarEventOutput


def _calendar(agenda: list[str] | None = None) -> CalendarEventOutput:
    return CalendarEventOutput(
        meeting_id="mtg-001",
        subject="Q1 Review",
        agenda=["Budget", "Timeline"] if agenda is None else agenda,
        start_time="2026-01-01T10:00:00+00:00",
        end_time="2026-01-01T11:00:00+00:00",
        organizer_id="org-1",
        organizer_name="Alice",
    )


def _roster() -> list[dict]:
    return [{"id": "p-1", "name": "Bob"}, {"id": "p-2", "name": "Carol"}]


# ------------------------------------------------------------------
# _build_meeting_record — pure function tests (no mocks needed)
# ------------------------------------------------------------------

def test_build_meeting_record_sets_correct_ids():
    record = _build_meeting_record("mtg-001", _calendar(), _roster())
    assert record.id == "meeting_mtg-001"
    assert record.meeting_id == "mtg-001"
    assert record.organizer_id == "org-1"


def test_build_meeting_record_extracts_participant_ids():
    record = _build_meeting_record("mtg-001", _calendar(), _roster())
    assert record.participants == ["p-1", "p-2"]


def test_build_meeting_record_skips_participants_without_id():
    roster = [{"id": "p-1"}, {"name": "no-id"}]
    record = _build_meeting_record("mtg-001", _calendar(), roster)
    assert record.participants == ["p-1"]


def test_build_meeting_record_retention_expiry_is_90_days_after_start():
    record = _build_meeting_record("mtg-001", _calendar(), _roster())
    start = datetime.fromisoformat("2026-01-01T10:00:00+00:00")
    expiry = datetime.fromisoformat(record.retention_expires_at)
    assert (expiry - start).days == 90


def test_build_meeting_record_stage_is_transcribing():
    record = _build_meeting_record("mtg-001", _calendar(), _roster())
    assert record.stage == "transcribing"


# ------------------------------------------------------------------
# MeetingInitiator — async tests with mocked McpClient
# ------------------------------------------------------------------

@pytest.fixture
def mcp():
    m = MagicMock()
    m.get_calendar_event = AsyncMock(return_value=_calendar())
    m.store_meeting_record = AsyncMock()
    m.send_realtime_alert = AsyncMock()
    return m


@pytest.mark.anyio
async def test_initialise_returns_meeting_record(mcp):
    initiator = MeetingInitiator(mcp=mcp)
    record = await initiator.initialise("mtg-001", _roster())
    assert record.meeting_id == "mtg-001"
    mcp.store_meeting_record.assert_awaited_once()


@pytest.mark.anyio
async def test_initialise_does_not_alert_when_agenda_present(mcp):
    initiator = MeetingInitiator(mcp=mcp)
    await initiator.initialise("mtg-001", _roster())
    mcp.send_realtime_alert.assert_not_awaited()


@pytest.mark.anyio
async def test_initialise_sends_missing_agenda_alert_when_no_agenda(mcp):
    mcp.get_calendar_event = AsyncMock(return_value=_calendar(agenda=[]))
    initiator = MeetingInitiator(mcp=mcp)
    await initiator.initialise("mtg-001", _roster())
    mcp.send_realtime_alert.assert_awaited_once_with("mtg-001", "missing_agenda", {})


@pytest.mark.anyio
async def test_initialise_continues_if_alert_fails(mcp):
    from orchestrator.mcp_client import McpCallError
    mcp.get_calendar_event = AsyncMock(return_value=_calendar(agenda=[]))
    mcp.send_realtime_alert = AsyncMock(
        side_effect=McpCallError("GRAPH_UNAVAILABLE", "Graph down", retryable=True)
    )
    initiator = MeetingInitiator(mcp=mcp)
    # Should not raise — alert failure is logged and swallowed
    record = await initiator.initialise("mtg-001", _roster())
    assert record.meeting_id == "mtg-001"
    mcp.store_meeting_record.assert_awaited_once()

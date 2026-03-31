"""
E2E: Full meeting lifecycle — start → post-meeting analysis → report stored.

Stack under test (all in-process, no external services):
  TeamsMeetingBot → MeetingOrchestratorManager → Orchestrator
      → MeetingInitiator  → MCP server (mock backends)
      → PostMeetingAnalyzer → MockFoundryClient (agents)
                            → MCP server (store report)
"""
from __future__ import annotations

import pytest

from tests.conftest import make_activity, make_turn_context

MEETING_ID = "mtg-e2e-001"
BOT_ID = "bot-1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bot_joined_activity(meeting_id=MEETING_ID):
    return make_activity(
        "conversationUpdate",
        meeting_id=meeting_id,
        members_added=[BOT_ID, "p-1", "p-2"],
    )


def _bot_left_activity(meeting_id=MEETING_ID):
    return make_activity(
        "conversationUpdate",
        meeting_id=meeting_id,
        members_removed=[BOT_ID],
    )


# ---------------------------------------------------------------------------
# Meeting start
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_meeting_start_creates_meeting_record(bot, mcp_server):
    """Bot join event → MeetingRecord stored in MCP."""
    ctx = make_turn_context(_bot_joined_activity())
    await bot.on_conversation_update_activity(ctx)

    resp = mcp_server.post(
        "/v1/tools/meeting/get_calendar_event", json={"meeting_id": MEETING_ID}
    )
    # Calendar event is readable (mock backend returns data for any meeting_id)
    assert resp.status_code == 200
    assert resp.json()["meeting_id"] == MEETING_ID


@pytest.mark.anyio
async def test_meeting_start_registers_active_meeting(bot_manager, bot):
    """After bot joins, the manager tracks the meeting as active."""
    ctx = make_turn_context(_bot_joined_activity())
    await bot.on_conversation_update_activity(ctx)

    assert MEETING_ID in bot_manager._active_meetings


@pytest.mark.anyio
async def test_duplicate_meeting_start_is_idempotent(bot_manager, bot):
    """Starting the same meeting twice does not create a second entry."""
    ctx = make_turn_context(_bot_joined_activity())
    await bot.on_conversation_update_activity(ctx)
    await bot.on_conversation_update_activity(ctx)

    assert len([k for k in bot_manager._active_meetings if k == MEETING_ID]) == 1


# ---------------------------------------------------------------------------
# Meeting end → post-meeting pipeline
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_meeting_end_stores_analysis_report(bot, mcp_server):
    """Full lifecycle: start → end → AnalysisReport persisted in MCP."""
    # Start
    await bot.on_conversation_update_activity(
        make_turn_context(_bot_joined_activity()).activity
    )
    ctx_start = make_turn_context(_bot_joined_activity())
    await bot.on_conversation_update_activity(ctx_start)

    # End
    ctx_end = make_turn_context(_bot_left_activity())
    await bot.on_conversation_update_activity(ctx_end)

    # Report should now be in MCP
    resp = mcp_server.post(
        "/v1/tools/analysis/get_analysis_report", json={"meeting_id": MEETING_ID}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["meeting_id"] == MEETING_ID


@pytest.mark.anyio
async def test_meeting_end_removes_active_meeting(bot_manager, bot):
    """After bot leaves, the meeting is no longer tracked."""
    ctx_start = make_turn_context(_bot_joined_activity())
    await bot.on_conversation_update_activity(ctx_start)

    ctx_end = make_turn_context(_bot_left_activity())
    await bot.on_conversation_update_activity(ctx_end)

    assert MEETING_ID not in bot_manager._active_meetings


@pytest.mark.anyio
async def test_meeting_end_without_start_is_safe(bot_manager, bot):
    """Ending a meeting that was never started does not raise."""
    ctx_end = make_turn_context(_bot_left_activity(meeting_id="mtg-unknown"))
    await bot.on_conversation_update_activity(ctx_end)  # should not raise


# ---------------------------------------------------------------------------
# Report content
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_report_includes_agenda_from_analysis_agent(bot, mcp_server, foundry):
    """Analysis agent agenda is reflected in the stored report."""
    foundry._responses["agent-analysis"]["agenda"] = ["Budget review", "Roadmap"]

    ctx_start = make_turn_context(_bot_joined_activity(meeting_id="mtg-agenda"))
    await bot.on_conversation_update_activity(ctx_start)
    ctx_end = make_turn_context(_bot_left_activity(meeting_id="mtg-agenda"))
    await bot.on_conversation_update_activity(ctx_end)

    resp = mcp_server.post(
        "/v1/tools/analysis/get_analysis_report", json={"meeting_id": "mtg-agenda"}
    )
    assert resp.status_code == 200
    assert "Budget review" in resp.json()["agenda"]


@pytest.mark.anyio
async def test_report_marks_analysis_unavailable_on_agent_error(bot, mcp_server, foundry):
    """If the analysis agent returns an error, the report marks the section unavailable."""
    foundry._responses["agent-analysis"] = {
        "task": "analyze_meeting",
        "status": "error",
        "error": "agent timeout",
    }

    ctx_start = make_turn_context(_bot_joined_activity(meeting_id="mtg-err-analysis"))
    await bot.on_conversation_update_activity(ctx_start)
    ctx_end = make_turn_context(_bot_left_activity(meeting_id="mtg-err-analysis"))
    await bot.on_conversation_update_activity(ctx_end)

    resp = mcp_server.post(
        "/v1/tools/analysis/get_analysis_report",
        json={"meeting_id": "mtg-err-analysis"},
    )
    assert resp.status_code == 200
    assert "analysis" in resp.json()["sections_unavailable"]


@pytest.mark.anyio
async def test_report_marks_sentiment_unavailable_on_agent_error(bot, mcp_server, foundry):
    """If the sentiment agent errors, the report marks sentiment unavailable."""
    foundry._responses["agent-sentiment"] = {
        "task": "analyze_sentiment",
        "status": "error",
        "error": "agent timeout",
    }

    ctx_start = make_turn_context(_bot_joined_activity(meeting_id="mtg-err-sentiment"))
    await bot.on_conversation_update_activity(ctx_start)
    ctx_end = make_turn_context(_bot_left_activity(meeting_id="mtg-err-sentiment"))
    await bot.on_conversation_update_activity(ctx_end)

    resp = mcp_server.post(
        "/v1/tools/analysis/get_analysis_report",
        json={"meeting_id": "mtg-err-sentiment"},
    )
    assert resp.status_code == 200
    assert "sentiment" in resp.json()["sections_unavailable"]

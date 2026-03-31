"""
E2E: Orchestrator ↔ MCP server data pipeline.

Tests the McpClient talking to the real in-process MCP server
(mock backends) — no bot layer, no Foundry.

Covers:
  - Meeting record round-trip
  - Consent record storage
  - Transcript segment storage
  - Analysis report store + retrieve
  - Similarity computation
  - Post-meeting pipeline via PostMeetingAnalyzer
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from shared_models.mcp_types import (
    MeetingRecord,
    ConsentRecord,
    TranscriptSegment,
    AnalysisReport,
)
from orchestrator.post_meeting_analyzer import PostMeetingAnalyzer
from tests.conftest import AGENT_IDS, DEFAULT_AGENT_RESPONSES, MockFoundryClient


# ---------------------------------------------------------------------------
# Meeting record
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_and_retrieve_meeting_record_via_mcp_client(mcp_client, mcp_server):
    record = MeetingRecord(
        id="meeting_mtg-pipe-001",
        meeting_id="mtg-pipe-001",
        organizer_id="org-1",
        organizer_name="Alice",
        subject="Pipeline Test",
        start_time="2026-01-01T10:00:00Z",
        created_at="2026-01-01T09:55:00Z",
        updated_at="2026-01-01T09:55:00Z",
        azure_region="eastus",
        retention_expires_at="2026-04-01T00:00:00Z",
    )
    await mcp_client.store_meeting_record(record)

    # Verify via direct MCP HTTP (no McpClient abstraction)
    resp = mcp_server.post(
        "/v1/tools/meeting/get_calendar_event", json={"meeting_id": "mtg-pipe-001"}
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Consent record
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_consent_record(mcp_client):
    record = ConsentRecord(
        id="consent_mtg-pipe-001_p-1",
        meeting_id="mtg-pipe-001",
        participant_id="p-1",
        participant_name="Alice",
        decision="granted",
        timestamp="2026-01-01T10:01:00Z",
    )
    # Should not raise
    await mcp_client.store_consent_record(record)


# ---------------------------------------------------------------------------
# Transcript segment
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_transcript_segment(mcp_client):
    segment = TranscriptSegment(
        id="seg_mtg-pipe-001_1",
        meeting_id="mtg-pipe-001",
        sequence=1,
        participant_id="p-1",
        participant_name="Alice",
        text="Let us review the Q1 budget.",
        start_time="2026-01-01T10:02:00Z",
        end_time="2026-01-01T10:02:10Z",
        duration_seconds=10.0,
    )
    await mcp_client.store_transcript_segment(segment)


# ---------------------------------------------------------------------------
# Analysis report round-trip
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_and_retrieve_analysis_report(mcp_client):
    report = AnalysisReport(
        id="report_mtg-pipe-002",
        meeting_id="mtg-pipe-002",
        generated_at="2026-01-01T11:00:00Z",
        agenda=["Budget", "Roadmap"],
    )
    await mcp_client.store_analysis_report(report)

    retrieved = await mcp_client.get_analysis_report("mtg-pipe-002")
    assert retrieved.meeting_id == "mtg-pipe-002"
    assert "Budget" in retrieved.agenda


@pytest.mark.anyio
async def test_get_analysis_report_raises_for_unknown_meeting(mcp_client):
    from shared_models.mcp_client import McpCallError

    with pytest.raises(McpCallError) as exc_info:
        await mcp_client.get_analysis_report("mtg-does-not-exist")
    assert exc_info.value.code == "REPORT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_compute_similarity_returns_scores(mcp_client):
    result = await mcp_client.compute_similarity(
        text="We need to review the quarterly budget numbers.",
        agenda_topics=["Budget review", "Roadmap planning"],
        meeting_id="mtg-pipe-001",
    )
    assert len(result.scores) == 2
    assert 0.0 <= result.max_score <= 1.0


# ---------------------------------------------------------------------------
# PostMeetingAnalyzer → MCP pipeline
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_meeting_analyzer_stores_report_in_mcp(mcp_client):
    """PostMeetingAnalyzer.run() stores the compiled report via the real MCP client."""
    foundry = MockFoundryClient(dict(DEFAULT_AGENT_RESPONSES))
    analyzer = PostMeetingAnalyzer(
        foundry=foundry,
        mcp=mcp_client,
        agent_ids=AGENT_IDS,
        timeout_seconds=10.0,
    )

    report = await analyzer.run("mtg-pipe-003")

    assert report.meeting_id == "mtg-pipe-003"

    # Verify it was actually persisted
    retrieved = await mcp_client.get_analysis_report("mtg-pipe-003")
    assert retrieved.meeting_id == "mtg-pipe-003"


@pytest.mark.anyio
async def test_post_meeting_analyzer_partial_failure_still_stores_report(mcp_client):
    """Even when sentiment agent fails, a partial report is stored."""
    responses = dict(DEFAULT_AGENT_RESPONSES)
    responses["agent-sentiment"] = {
        "task": "analyze_sentiment",
        "status": "error",
        "error": "unavailable",
    }
    foundry = MockFoundryClient(responses)
    analyzer = PostMeetingAnalyzer(
        foundry=foundry,
        mcp=mcp_client,
        agent_ids=AGENT_IDS,
        timeout_seconds=10.0,
    )

    report = await analyzer.run("mtg-pipe-004")

    assert "sentiment" in report.sections_unavailable
    retrieved = await mcp_client.get_analysis_report("mtg-pipe-004")
    assert "sentiment" in retrieved.sections_unavailable


# ---------------------------------------------------------------------------
# Realtime tools
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_send_realtime_alert_known_type_succeeds(mcp_client):
    """Known alert types are accepted by the MCP server."""
    await mcp_client.send_realtime_alert(
        meeting_id="mtg-pipe-001",
        alert_type="off_track",
        card_payload={"type": "off_track", "meeting_id": "mtg-pipe-001"},
    )


@pytest.mark.anyio
async def test_send_realtime_alert_unknown_type_raises(mcp_client):
    """Unknown alert types are rejected with FEATURE_NOT_ENABLED."""
    from shared_models.mcp_client import McpCallError

    with pytest.raises(McpCallError) as exc_info:
        await mcp_client.send_realtime_alert(
            meeting_id="mtg-pipe-001",
            alert_type="not_a_real_alert",
            card_payload={},
        )
    assert exc_info.value.code == "FEATURE_NOT_ENABLED"


@pytest.mark.anyio
async def test_get_participant_rates_returns_rates(mcp_client):
    result = await mcp_client.get_participant_rates(
        meeting_id="mtg-pipe-001",
        participant_ids=["p-1", "p-2"],
    )
    assert len(result.rates) == 2
    assert all(r.participant_id in ("p-1", "p-2") for r in result.rates)


@pytest.mark.anyio
async def test_store_cost_snapshot(mcp_client):
    from shared_models.mcp_types import MeetingCostSnapshot

    snapshot = MeetingCostSnapshot(
        id="cost_mtg-pipe-001_0",
        meeting_id="mtg-pipe-001",
        snapshot_index=0,
        captured_at="2026-01-01T10:05:00Z",
        elapsed_minutes=5.0,
        active_participant_count=2,
        total_cost=50.0,
    )
    await mcp_client.store_cost_snapshot(snapshot)


# ---------------------------------------------------------------------------
# RealTimeLoop → MCP realtime endpoints (integration)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_real_time_loop_tick_calls_similarity_via_mcp(mcp_client):
    """A single RealTimeLoop tick calls compute_similarity through the real MCP client."""
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "orchestrator"))
    from real_time_loop import RealTimeLoop
    from config import OrchestratorConfig
    from shared_models.mcp_types import MeetingRecord

    record = MeetingRecord(
        id="meeting_mtg-rt-e2e",
        meeting_id="mtg-rt-e2e",
        organizer_id="org-1",
        organizer_name="Alice",
        subject="RT E2E",
        start_time="2026-01-01T10:00:00Z",
        created_at="2026-01-01T09:55:00Z",
        updated_at="2026-01-01T09:55:00Z",
        azure_region="eastus",
        retention_expires_at="2026-04-01T00:00:00Z",
        participants=["p-1", "p-2"],
    )
    cfg = OrchestratorConfig(
        realtime_loop_interval_seconds=60,
        off_track_consecutive_windows=3,
        off_track_similarity_threshold=0.35,
        agenda_unclear_threshold=0.4,
        agenda_unclear_trigger_minutes=5,
        agenda_unclear_second_alert_minutes=8,
        alert_throttle_window_seconds=300,
        participation_pulse_interval_minutes=5,
        silent_participant_threshold_minutes=10,
        purpose_detection_delay_seconds=9999,
    )
    loop = RealTimeLoop(
        meeting_id="mtg-rt-e2e",
        record=record,
        mcp=mcp_client,
        cfg=cfg,
        agenda=["Budget review", "Roadmap"],
    )

    # Run one tick — this calls compute_similarity on the real MCP server
    await loop._check_agenda_adherence()

    # Buffer should have one score from the real similarity service
    assert len(loop._similarity_buffer) == 1
    assert 0.0 <= loop._similarity_buffer[0] <= 1.0

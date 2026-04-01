"""
Tests for McpClient — verifies every tool method calls the correct endpoint
and deserialises the response into the correct typed model.
"""
import pytest
from datetime import datetime, timezone

from shared_models.mcp_types import (
    MeetingRecord, TranscriptSegment, ConsentRecord, AnalysisReport,
    MeetingCostSnapshot,
)
from orchestrator.mcp_client import McpClient, McpCallError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _meeting(meeting_id: str = "mtg-001") -> MeetingRecord:
    return MeetingRecord(
        id=f"meeting_{meeting_id}",
        meeting_id=meeting_id,
        organizer_id="org-1",
        organizer_name="Alice",
        subject="Q1 Review",
        start_time=_now(),
        created_at=_now(),
        updated_at=_now(),
        azure_region="eastus",
        retention_expires_at=_now(),
    )


def _segment(meeting_id: str = "mtg-001") -> TranscriptSegment:
    return TranscriptSegment(
        id=f"seg_{meeting_id}_1",
        meeting_id=meeting_id,
        sequence=1,
        participant_id="p-1",
        participant_name="Bob",
        text="Let us review the Q1 budget.",
        start_time=_now(),
        end_time=_now(),
        duration_seconds=10.0,
        consent_verified=True,
    )


def _consent(meeting_id: str = "mtg-001", decision: str = "granted") -> ConsentRecord:
    return ConsentRecord(
        id=f"consent_{meeting_id}_p-1",
        meeting_id=meeting_id,
        participant_id="p-1",
        participant_name="Bob",
        decision=decision,
        timestamp=_now(),
    )


def _report(meeting_id: str = "mtg-001") -> AnalysisReport:
    return AnalysisReport(
        id=f"report_{meeting_id}",
        meeting_id=meeting_id,
        generated_at=_now(),
    )


# ------------------------------------------------------------------
# Stage 1 — Meeting tools
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_calendar_event(mcp: McpClient):
    result = await mcp.get_calendar_event("mtg-001")
    assert result.meeting_id == "mtg-001"
    assert result.subject
    assert isinstance(result.agenda, list)


@pytest.mark.anyio
async def test_get_recording_status(mcp: McpClient):
    result = await mcp.get_recording_status("mtg-001")
    assert result.meeting_id == "mtg-001"
    assert isinstance(result.recording_enabled, bool)


@pytest.mark.anyio
async def test_store_meeting_record(mcp: McpClient):
    await mcp.store_meeting_record(_meeting("mtg-store-001"))


@pytest.mark.anyio
async def test_post_adaptive_card_broadcast(mcp: McpClient):
    await mcp.post_adaptive_card("mtg-001", {"type": "AdaptiveCard"})


@pytest.mark.anyio
async def test_post_adaptive_card_targeted(mcp: McpClient):
    await mcp.post_adaptive_card("mtg-001", {"type": "AdaptiveCard"}, ["p-1", "p-2"])


# ------------------------------------------------------------------
# Stage 1 — Transcript
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_transcript_segment_consented(mcp: McpClient):
    await mcp.store_transcript_segment(_segment())


@pytest.mark.anyio
async def test_store_transcript_segment_no_consent_raises(mcp: McpClient):
    from unittest.mock import patch
    seg = _segment()
    seg.consent_verified = False
    with patch("app.api.v1.tools.transcript.settings") as mock_settings:
        mock_settings.consent_required = True
        with pytest.raises(McpCallError) as exc_info:
            await mcp.store_transcript_segment(seg)
    assert exc_info.value.code == "CONSENT_REQUIRED"
    assert exc_info.value.retryable is False


# ------------------------------------------------------------------
# Stage 1 — Consent
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_consent_record(mcp: McpClient):
    await mcp.store_consent_record(_consent())


# ------------------------------------------------------------------
# Stage 1 — Analysis
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_store_and_get_analysis_report(mcp: McpClient):
    await mcp.store_analysis_report(_report("mtg-rpt-001"))
    result = await mcp.get_analysis_report("mtg-rpt-001")
    assert result.meeting_id == "mtg-rpt-001"


@pytest.mark.anyio
async def test_get_analysis_report_not_found_raises(mcp: McpClient):
    with pytest.raises(McpCallError) as exc_info:
        await mcp.get_analysis_report("no-such-meeting")
    assert exc_info.value.code == "REPORT_NOT_FOUND"
    assert exc_info.value.retryable is False


# ------------------------------------------------------------------
# Stage 1 — Similarity
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_compute_similarity_returns_valid_scores(mcp: McpClient):
    result = await mcp.compute_similarity(
        text="budget review for Q1",
        agenda_topics=["budget", "timeline"],
        meeting_id="mtg-sim-001",
    )
    assert 0.0 <= result.max_score <= 1.0
    assert len(result.scores) == 2
    for s in result.scores:
        assert 0.0 <= s.score <= 1.0


@pytest.mark.anyio
async def test_compute_similarity_empty_topics(mcp: McpClient):
    result = await mcp.compute_similarity("some text", [], "mtg-sim-002")
    assert result.max_score == 0.0
    assert result.scores == []


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_non_retryable_error_raised_immediately(mcp: McpClient):
    """CONSENT_REQUIRED is non-retryable — should raise on first attempt with no retries."""
    from unittest.mock import patch
    seg = _segment()
    seg.consent_verified = False
    call_count = 0
    original_post = mcp._post

    async def counting_post(path, payload, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_post(path, payload, **kwargs)

    mcp._post = counting_post
    with patch("app.api.v1.tools.transcript.settings") as mock_settings:
        mock_settings.consent_required = True
        try:
            with pytest.raises(McpCallError):
                await mcp.store_transcript_segment(seg)
            assert call_count == 1  # no retries for non-retryable
        finally:
            mcp._post = original_post

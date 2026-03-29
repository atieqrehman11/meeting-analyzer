"""Tests for PostMeetingAnalyzer."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from post_meeting_analyzer import PostMeetingAnalyzer
from shared_models.a2a_schemas import (
    AnalyzeMeetingResponse,
    AnalyzeSentimentResponse,
    FinalizeTranscriptResponse,
)


AGENT_IDS = {
    "transcript": "agent-transcript",
    "analysis": "agent-analysis",
    "sentiment": "agent-sentiment",
}


def _make_foundry(
    finalize_response: dict | None = None,
    analysis_response: dict | None = None,
    sentiment_response: dict | None = None,
) -> MagicMock:
    foundry = MagicMock()
    foundry.dispatch = AsyncMock(
        return_value=finalize_response or {
            "task": "finalize_transcript",
            "status": "ok",
            "transcript_blob_url": "mock://transcripts/mtg-001/final.json",
        }
    )
    foundry.dispatch_with_timeout = AsyncMock(side_effect=[
        analysis_response or {
            "task": "analyze_meeting",
            "status": "ok",
            "agenda": ["Budget"],
            "agenda_source": "calendar",
        },
        sentiment_response or {
            "task": "analyze_sentiment",
            "status": "ok",
            "participation_summary": [],
        },
    ])
    return foundry


def _make_mcp() -> MagicMock:
    mcp = MagicMock()
    mcp.store_analysis_report = AsyncMock()
    mcp.post_adaptive_card = AsyncMock()
    return mcp


def _analyzer(foundry=None, mcp=None) -> PostMeetingAnalyzer:
    return PostMeetingAnalyzer(
        foundry=foundry or _make_foundry(),
        mcp=mcp or _make_mcp(),
        agent_ids=AGENT_IDS,
        timeout_seconds=5.0,
    )


# ------------------------------------------------------------------
# run() — happy path
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_run_returns_analysis_report():
    analyzer = _analyzer()
    report = await analyzer.run("mtg-001")
    assert report.meeting_id == "mtg-001"


@pytest.mark.anyio
async def test_run_stores_report():
    mcp = _make_mcp()
    analyzer = _analyzer(mcp=mcp)
    await analyzer.run("mtg-001")
    mcp.store_analysis_report.assert_awaited_once()


@pytest.mark.anyio
async def test_run_posts_adaptive_card():
    mcp = _make_mcp()
    analyzer = _analyzer(mcp=mcp)
    await analyzer.run("mtg-001")
    mcp.post_adaptive_card.assert_awaited_once()


# ------------------------------------------------------------------
# Transcript finalisation
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_run_raises_if_transcript_finalisation_fails():
    foundry = _make_foundry(finalize_response={
        "task": "finalize_transcript",
        "status": "error",
        "error": "Graph API unavailable",
    })
    analyzer = _analyzer(foundry=foundry)
    with pytest.raises(RuntimeError, match="Transcript finalisation failed"):
        await analyzer.run("mtg-001")


@pytest.mark.anyio
async def test_run_raises_if_transcript_url_missing():
    foundry = _make_foundry(finalize_response={
        "task": "finalize_transcript",
        "status": "ok",
        "transcript_blob_url": None,
    })
    analyzer = _analyzer(foundry=foundry)
    with pytest.raises(RuntimeError):
        await analyzer.run("mtg-001")


# ------------------------------------------------------------------
# Analysis / sentiment failures
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_run_marks_analysis_unavailable_on_agent_error():
    foundry = _make_foundry(
        analysis_response={"task": "analyze_meeting", "status": "error", "error": "timeout"},
        sentiment_response={"task": "analyze_sentiment", "status": "ok", "participation_summary": []},
    )
    analyzer = _analyzer(foundry=foundry)
    report = await analyzer.run("mtg-001")
    assert "analysis" in report.sections_unavailable


@pytest.mark.anyio
async def test_run_marks_sentiment_unavailable_on_agent_error():
    foundry = _make_foundry(
        analysis_response={"task": "analyze_meeting", "status": "ok", "agenda": [], "agenda_source": "calendar"},
        sentiment_response={"task": "analyze_sentiment", "status": "error", "error": "timeout"},
    )
    analyzer = _analyzer(foundry=foundry)
    report = await analyzer.run("mtg-001")
    assert "sentiment" in report.sections_unavailable


# ------------------------------------------------------------------
# Report card delivery fallback
# ------------------------------------------------------------------

@pytest.mark.anyio
async def test_run_attempts_fallback_dm_if_card_delivery_fails():
    from mcp_client import McpCallError
    mcp = _make_mcp()
    mcp.post_adaptive_card = AsyncMock(
        side_effect=[
            McpCallError("GRAPH_UNAVAILABLE", "Graph down", retryable=True),
            None,  # fallback DM succeeds
        ]
    )
    analyzer = _analyzer(mcp=mcp)
    # Should not raise — fallback is attempted
    await analyzer.run("mtg-001")
    assert mcp.post_adaptive_card.await_count == 2

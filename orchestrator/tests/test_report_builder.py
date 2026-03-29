"""Tests for report_builder pure functions."""
import pytest
from datetime import datetime, timezone

from report_builder import compile_report, build_report_card
from shared_models.a2a_schemas import (
    AnalyzeMeetingResponse,
    AnalyzeSentimentResponse,
    AgendaAdherenceItem,
    ParticipationSummaryItem,
)
from shared_models.mcp_types import AnalysisReport


def _ok_analysis(agenda: list[str] | None = None) -> AnalyzeMeetingResponse:
    return AnalyzeMeetingResponse(
        status="ok",
        agenda=agenda or ["Budget", "Timeline"],
        agenda_source="calendar",
        agenda_adherence=[
            AgendaAdherenceItem(
                topic="Budget",
                status="Covered",
                similarity_score=0.8,
                time_minutes=20.0,
                time_percentage=40.0,
            )
        ],
    )


def _ok_sentiment() -> AnalyzeSentimentResponse:
    return AnalyzeSentimentResponse(
        status="ok",
        participation_summary=[
            ParticipationSummaryItem(
                participant_id="p-1",
                speaking_time_seconds=120.0,
                speaking_time_percentage=60.0,
                turn_count=5,
            )
        ],
    )


# ------------------------------------------------------------------
# compile_report
# ------------------------------------------------------------------

def test_compile_report_sets_meeting_id():
    report = compile_report("mtg-001", _ok_analysis(), _ok_sentiment())
    assert report.meeting_id == "mtg-001"
    assert report.id == "report_mtg-001"


def test_compile_report_populates_agenda_from_analysis():
    report = compile_report("mtg-001", _ok_analysis(["Budget", "Timeline"]), _ok_sentiment())
    assert report.agenda == ["Budget", "Timeline"]
    assert report.agenda_source == "calendar"


def test_compile_report_populates_participation_from_sentiment():
    report = compile_report("mtg-001", _ok_analysis(), _ok_sentiment())
    assert len(report.participation_summary) == 1
    assert report.participation_summary[0].participant_id == "p-1"


def test_compile_report_marks_analysis_unavailable_on_error():
    error_analysis = AnalyzeMeetingResponse(status="error", error="Agent failed")
    report = compile_report("mtg-001", error_analysis, _ok_sentiment())
    assert "analysis" in report.sections_unavailable


def test_compile_report_marks_sentiment_unavailable_on_error():
    error_sentiment = AnalyzeSentimentResponse(status="error", error="Agent failed")
    report = compile_report("mtg-001", _ok_analysis(), error_sentiment)
    assert "sentiment" in report.sections_unavailable


def test_compile_report_marks_both_unavailable_on_exceptions():
    report = compile_report("mtg-001", RuntimeError("analysis down"), ValueError("sentiment down"))
    assert "analysis" in report.sections_unavailable
    assert "sentiment" in report.sections_unavailable


def test_compile_report_includes_sections_failed_from_partial():
    partial = AnalyzeMeetingResponse(
        status="partial",
        agenda=["Budget"],
        agenda_source="calendar",
        sections_failed=["agreement_detection"],
    )
    report = compile_report("mtg-001", partial, _ok_sentiment())
    assert "agreement_detection" in report.sections_unavailable


def test_compile_report_generated_at_is_iso8601():
    report = compile_report("mtg-001", _ok_analysis(), _ok_sentiment())
    # Should parse without error
    datetime.fromisoformat(report.generated_at)


# ------------------------------------------------------------------
# build_report_card
# ------------------------------------------------------------------

def test_build_report_card_returns_adaptive_card():
    report = compile_report("mtg-001", _ok_analysis(), _ok_sentiment())
    card = build_report_card(report)
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"


def test_build_report_card_includes_meeting_id():
    report = compile_report("mtg-001", _ok_analysis(), _ok_sentiment())
    card = build_report_card(report)
    body_text = card["body"][0]["text"]
    assert "mtg-001" in body_text


def test_build_report_card_shows_no_data_when_no_adherence():
    report = AnalysisReport(
        id="report_mtg-002",
        meeting_id="mtg-002",
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    card = build_report_card(report)
    assert "_No data_" in card["body"][1]["text"]


def test_build_report_card_shows_unavailable_sections():
    report = AnalysisReport(
        id="report_mtg-003",
        meeting_id="mtg-003",
        generated_at=datetime.now(timezone.utc).isoformat(),
        sections_unavailable=["analysis", "sentiment"],
    )
    card = build_report_card(report)
    assert "analysis" in card["body"][1]["text"]
    assert "sentiment" in card["body"][1]["text"]

"""
Pure report builder functions — no I/O, no logging, no side effects.
All functions are fully unit-testable in isolation.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared_models.a2a_schemas import AnalyzeMeetingResponse, AnalyzeSentimentResponse
from shared_models.mcp_types import (
    AgendaAdherenceEntry,
    AnalysisReport,
    ParticipationSummaryEntry,
)

def compile_report(
    meeting_id: str,
    analysis: Union[AnalyzeMeetingResponse, BaseException],
    sentiment: Union[AnalyzeSentimentResponse, BaseException],
) -> AnalysisReport:
    """Merge analysis and sentiment results into a single AnalysisReport."""
    report = AnalysisReport(
        id=f"report_{meeting_id}",
        meeting_id=meeting_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    _apply_analysis(report, analysis)
    _apply_sentiment(report, sentiment)
    return report


def build_report_card(report: AnalysisReport) -> dict:
    """Build an Adaptive Card payload summarising the analysis report."""
    adherence_lines = [
        f"- {e.topic}: {e.status} ({e.similarity_score:.0%})"
        for e in report.agenda_adherence
    ]
    body_text = "**Agenda Adherence**\n" + (
        "\n".join(adherence_lines) if adherence_lines else "_No data_"
    )
    if report.sections_unavailable:
        body_text += f"\n\n⚠️ Sections unavailable: {', '.join(report.sections_unavailable)}"

    return {
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Meeting Report — {report.meeting_id}",
                "weight": "Bolder",
                "size": "Medium",
            },
            {"type": "TextBlock", "text": body_text, "wrap": True},
        ],
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _apply_analysis(
    report: AnalysisReport,
    analysis: Union[AnalyzeMeetingResponse, BaseException],
) -> None:
    if isinstance(analysis, AnalyzeMeetingResponse) and analysis.status != "error":
        report.agenda = analysis.agenda
        report.agenda_source = analysis.agenda_source
        report.agenda_adherence = [_to_adherence_entry(i) for i in analysis.agenda_adherence]
        report.sections_unavailable += analysis.sections_failed
    else:
        report.sections_unavailable.append("analysis")


def _apply_sentiment(
    report: AnalysisReport,
    sentiment: Union[AnalyzeSentimentResponse, BaseException],
) -> None:
    if isinstance(sentiment, AnalyzeSentimentResponse) and sentiment.status != "error":
        report.participation_summary = [_to_participation_entry(i) for i in sentiment.participation_summary]
        report.sections_unavailable = list(
            set(report.sections_unavailable) | set(sentiment.sections_failed)
        )
    else:
        report.sections_unavailable.append("sentiment")


def _to_adherence_entry(item) -> AgendaAdherenceEntry:
    return AgendaAdherenceEntry(
        topic=item.topic,
        status=item.status,
        similarity_score=item.similarity_score,
        time_minutes=item.time_minutes,
        time_percentage=item.time_percentage,
    )


def _to_participation_entry(item) -> ParticipationSummaryEntry:
    return ParticipationSummaryEntry(
        participant_id=item.participant_id,
        participant_name=item.participant_id,  # name not available in sentiment response
        speaking_time_seconds=item.speaking_time_seconds,
        speaking_time_percentage=item.speaking_time_percentage,
        turn_count=item.turn_count,
        participation_flag=item.participation_flag,
        sentiment=item.sentiment,
    )

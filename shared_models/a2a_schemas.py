"""
A2A task and response schemas for inter-agent communication.
All agents communicate via these typed Pydantic models.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Task schemas (Orchestrator → Specialist agents)
# ---------------------------------------------------------------------------

class CaptureTranscriptSegmentTask(BaseModel):
    task: Literal["capture_transcript_segment"] = "capture_transcript_segment"
    meeting_id: str
    segment_window_seconds: int = 60


class AnalyzeMeetingTask(BaseModel):
    task: Literal["analyze_meeting"] = "analyze_meeting"
    meeting_id: str
    transcript_blob_url: str
    agenda: list[str] = Field(default_factory=list)


class AnalyzeSentimentTask(BaseModel):
    task: Literal["analyze_sentiment"] = "analyze_sentiment"
    meeting_id: str
    transcript_blob_url: str
    audio_blob_url: Optional[str] = None


class ComputeParticipationPulseTask(BaseModel):
    task: Literal["compute_participation_pulse"] = "compute_participation_pulse"
    meeting_id: str
    snapshot_number: int


class FinalizeTranscriptTask(BaseModel):
    task: Literal["finalize_transcript"] = "finalize_transcript"
    meeting_id: str


# ---------------------------------------------------------------------------
# Response schemas (Specialist agents → Orchestrator)
# ---------------------------------------------------------------------------

class AgendaAdherenceItem(BaseModel):
    topic: str
    status: Literal["Covered", "Partially Covered", "Not Covered"]
    similarity_score: float = Field(ge=0.0, le=1.0)
    time_minutes: float
    time_percentage: float = Field(ge=0.0)


class TimeAllocationItem(BaseModel):
    label: str  # agenda topic or "Preamble" / "Off-agenda"
    time_minutes: float
    time_percentage: float = Field(ge=0.0)


class ActionItemResult(BaseModel):
    description: str
    owner_participant_id: str
    owner_name: str
    due_date: str  # ISO8601 date or "Not Specified"
    transcript_timestamp: str  # ISO8601
    status: Literal["Proposed", "Confirmed"]


class CaptureTranscriptSegmentResponse(BaseModel):
    task: Literal["capture_transcript_segment"] = "capture_transcript_segment"
    status: Literal["ok", "error"]
    segments_captured: int = 0
    blob_url: Optional[str] = None
    gap_detected: bool = False
    error: Optional[str] = None


class AnalyzeMeetingResponse(BaseModel):
    task: Literal["analyze_meeting"] = "analyze_meeting"
    status: Literal["ok", "partial", "error"]
    agenda: list[str] = Field(default_factory=list)
    agenda_source: Literal["calendar", "inferred", "not_determined"] = "not_determined"
    agenda_adherence: list[AgendaAdherenceItem] = Field(default_factory=list)
    time_allocation: list[TimeAllocationItem] = Field(default_factory=list)
    action_items: list[ActionItemResult] = Field(default_factory=list)
    sections_failed: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class ParticipantEngagementIndicator(BaseModel):
    participant_id: str
    indicator: str


class ComputeParticipationPulseResponse(BaseModel):
    task: Literal["compute_participation_pulse"] = "compute_participation_pulse"
    status: Literal["ok", "error"]
    active_speakers: list[str] = Field(default_factory=list)
    silent_participants: list[str] = Field(default_factory=list)
    energy_level: Literal["High", "Medium", "Low"] = "Medium"
    per_participant_engagement: list[ParticipantEngagementIndicator] = Field(default_factory=list)
    error: Optional[str] = None


class ParticipationSummaryItem(BaseModel):
    participant_id: str
    speaking_time_seconds: float
    speaking_time_percentage: float = Field(ge=0.0)
    turn_count: int
    participation_flag: Optional[Literal["Low Participation", "Dominant Speaker"]] = None
    sentiment: Literal["Positive", "Neutral", "Negative", "Insufficient Data"] = "Insufficient Data"


class AnalyzeSentimentResponse(BaseModel):
    task: Literal["analyze_sentiment"] = "analyze_sentiment"
    status: Literal["ok", "partial", "error"]
    participation_summary: list[ParticipationSummaryItem] = Field(default_factory=list)
    sections_failed: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class FinalizeTranscriptResponse(BaseModel):
    task: Literal["finalize_transcript"] = "finalize_transcript"
    status: Literal["ok", "error"]
    transcript_blob_url: Optional[str] = None
    error: Optional[str] = None

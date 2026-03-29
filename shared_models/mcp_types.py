"""
Pydantic models for all MCP server tool inputs, outputs, and stored document types.
All store_* tools validate against these schemas before executing.
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared error envelope (Property 20)
# ---------------------------------------------------------------------------

class McpError(BaseModel):
    code: str
    message: str
    retryable: bool


class McpErrorResponse(BaseModel):
    error: McpError


# ---------------------------------------------------------------------------
# Stored document models
# ---------------------------------------------------------------------------

class ConsentEntry(BaseModel):
    consented: bool
    timestamp: str  # ISO8601
    late_joiner: bool = False
    join_time: Optional[str] = None  # ISO8601


class MeetingRecord(BaseModel):
    id: str  # "meeting_{meeting_id}"
    type: Literal["meeting"] = "meeting"
    meeting_id: str
    organizer_id: str
    organizer_name: str
    subject: str
    start_time: str  # ISO8601
    end_time: Optional[str] = None
    duration_minutes: Optional[float] = None
    participants: list[str] = Field(default_factory=list)
    consent_status: dict[str, ConsentEntry] = Field(default_factory=dict)
    stage: Literal["joining", "transcribing", "analyzing", "complete", "aborted"] = "joining"
    transcript_blob_url: Optional[str] = None
    audio_blob_url: Optional[str] = None
    analysis_report_id: Optional[str] = None
    created_at: str  # ISO8601
    updated_at: str  # ISO8601
    azure_region: str
    retention_expires_at: str  # ISO8601
    recording_enabled: bool = False
    high_value_participant_mode: bool = False
    high_value_participants: list[str] = Field(default_factory=list)
    meeting_purpose: Optional[Literal[
        "Decision meeting", "Status update", "Brainstorming",
        "Client presentation", "Problem-solving"
    ]] = None
    meeting_purpose_mismatch: bool = False


class TranscriptSegment(BaseModel):
    id: str  # "seg_{meeting_id}_{sequence}"
    type: Literal["transcript_segment"] = "transcript_segment"
    meeting_id: str
    sequence: int
    participant_id: str
    participant_name: str
    text: str
    start_time: str  # ISO8601
    end_time: str    # ISO8601
    duration_seconds: float
    prosody: "ProsodyFeatures" = Field(default_factory=lambda: ProsodyFeatures())
    consent_verified: bool = True


class ProsodyFeatures(BaseModel):
    speaking_rate_wpm: Optional[float] = None
    pitch_mean_hz: Optional[float] = None
    pitch_variance: Optional[float] = None


class ConsentRecord(BaseModel):
    id: str  # "consent_{meeting_id}_{participant_id}"
    type: Literal["consent"] = "consent"
    meeting_id: str
    participant_id: str
    participant_name: str
    decision: Literal["granted", "declined", "pending"]
    timestamp: str  # ISO8601
    revoked: bool = False
    revoked_at: Optional[str] = None
    deletion_triggered: bool = False


class AgendaAdherenceEntry(BaseModel):
    topic: str
    status: Literal["Covered", "Partially Covered", "Not Covered"]
    similarity_score: float = Field(ge=0.0, le=1.0)
    time_minutes: float
    time_percentage: float = Field(ge=0.0)


class OffAgendaSegment(BaseModel):
    topic_summary: str
    start_time: str   # ISO8601
    end_time: str     # ISO8601
    duration_minutes: float


class SentimentShift(BaseModel):
    timestamp: str  # ISO8601
    from_sentiment: str = Field(alias="from")
    to_sentiment: str = Field(alias="to")

    model_config = {"populate_by_name": True}


class OpinionMiningAspect(BaseModel):
    aspect: str
    sentiment: Literal["positive", "negative", "neutral"]


class ParticipationSummaryEntry(BaseModel):
    participant_id: str
    participant_name: str
    speaking_time_seconds: float
    speaking_time_percentage: float = Field(ge=0.0)
    turn_count: int
    participation_flag: Optional[Literal["Low Participation", "Dominant Speaker"]] = None
    sentiment: Literal["Positive", "Neutral", "Negative", "Insufficient Data"] = "Insufficient Data"
    sentiment_shifts: list[SentimentShift] = Field(default_factory=list)
    opinion_mining_aspects: list[OpinionMiningAspect] = Field(default_factory=list)
    prosody: ProsodyFeatures = Field(default_factory=ProsodyFeatures)
    contribution_score: Optional[float] = None
    relevance: Optional[Literal["Highly Relevant", "Relevant", "Low Relevance", "Observer"]] = None


class ToneIssue(BaseModel):
    timestamp: str  # ISO8601
    participant_id: str
    severity: Literal["Minor", "Moderate", "Severe"]
    issue_type: Literal["aggressive", "dismissive", "interruption", "profanity", "disrespectful"]
    private_alert_sent: bool = False
    meeting_alert_sent: bool = False


class ParticipationPulseSnapshot(BaseModel):
    snapshot_number: int
    captured_at: str  # ISO8601
    active_speakers: list[str] = Field(default_factory=list)
    silent_participants: list[str] = Field(default_factory=list)
    energy_level: Literal["High", "Medium", "Low"] = "Medium"


class AnalysisReport(BaseModel):
    id: str  # "report_{meeting_id}"
    type: Literal["analysis_report"] = "analysis_report"
    meeting_id: str
    generated_at: str  # ISO8601
    agenda: list[str] = Field(default_factory=list)
    agenda_source: Literal["calendar", "inferred", "not_determined"] = "not_determined"
    agenda_adherence: list[AgendaAdherenceEntry] = Field(default_factory=list)
    off_agenda_segments: list[OffAgendaSegment] = Field(default_factory=list)
    preamble_duration_minutes: float = 0.0
    extended_duration_flag: bool = False
    action_items: list[str] = Field(default_factory=list)  # action_item IDs
    participation_summary: list[ParticipationSummaryEntry] = Field(default_factory=list)
    final_meeting_cost: Optional[float] = None
    sections_unavailable: list[str] = Field(default_factory=list)
    poll_id: Optional[str] = None
    poll_status: Optional[Literal["pending", "open", "closed"]] = None
    meeting_purpose: Optional[str] = None
    meeting_purpose_mismatch: bool = False
    high_value_participant_mode: bool = False
    tone_issues: list[ToneIssue] = Field(default_factory=list)
    participation_pulse_snapshots: list[ParticipationPulseSnapshot] = Field(default_factory=list)


class ActionItem(BaseModel):
    id: str  # "action_{meeting_id}_{sequence}"
    type: Literal["action_item"] = "action_item"
    meeting_id: str
    sequence: int
    description: str
    owner_participant_id: str
    owner_name: str
    due_date: str  # ISO8601 date or "Not Specified"
    transcript_timestamp: str  # ISO8601
    status: Literal["Proposed", "Confirmed", "Disputed", "Unresolved", "Disputed by Poll"]
    agreement_evidence: list[str] = Field(default_factory=list)
    disagreeing_participants: list[str] = Field(default_factory=list)
    poll_responses: dict[str, Literal["Confirm", "Dispute", "Abstain"]] = Field(default_factory=dict)


class PerParticipantCost(BaseModel):
    participant_id: str
    participant_name: str
    hourly_rate: Optional[float] = None
    elapsed_cost: Optional[float] = None
    excluded: bool = False


class MeetingCostSnapshot(BaseModel):
    id: str  # "cost_{meeting_id}_{snapshot_index}"
    type: Literal["cost_snapshot"] = "cost_snapshot"
    meeting_id: str
    snapshot_index: int
    captured_at: str  # ISO8601
    elapsed_minutes: float
    active_participant_count: int
    total_cost: float
    currency: str = "USD"
    per_participant: list[PerParticipantCost] = Field(default_factory=list)
    excluded_participant_count: int = 0


# ---------------------------------------------------------------------------
# MCP tool input/output models
# ---------------------------------------------------------------------------

class StoreMeetingRecordInput(BaseModel):
    meeting_record: MeetingRecord


class StoreTranscriptSegmentInput(BaseModel):
    segment: TranscriptSegment


class StoreConsentRecordInput(BaseModel):
    consent_record: ConsentRecord


class StoreAnalysisReportInput(BaseModel):
    report: AnalysisReport


class GetAnalysisReportInput(BaseModel):
    meeting_id: str


class GetCalendarEventInput(BaseModel):
    meeting_id: str


class CalendarEventOutput(BaseModel):
    meeting_id: str
    subject: str
    description: Optional[str] = None
    agenda: list[str] = Field(default_factory=list)
    start_time: str
    end_time: str
    organizer_id: str
    organizer_name: str


class PostAdaptiveCardInput(BaseModel):
    meeting_id: str
    card_payload: dict
    target_participant_ids: Optional[list[str]] = None
    update_existing: bool = False


class SendRealtimeAlertInput(BaseModel):
    meeting_id: str
    alert_type: str
    card_payload: dict
    target_participant_ids: Optional[list[str]] = None


class ComputeSimilarityInput(BaseModel):
    text: str
    agenda_topics: list[str]
    meeting_id: str  # used for embedding cache key


class SimilarityScore(BaseModel):
    topic: str
    score: float = Field(ge=0.0, le=1.0)


class ComputeSimilarityOutput(BaseModel):
    scores: list[SimilarityScore]
    max_score: float = Field(ge=0.0, le=1.0)


class GetParticipantRatesInput(BaseModel):
    meeting_id: str
    participant_ids: list[str]


class ParticipantRate(BaseModel):
    participant_id: str
    seniority_level: Optional[str] = None
    hourly_rate: Optional[float] = None


class GetParticipantRatesOutput(BaseModel):
    rates: list[ParticipantRate]


class StoreCostSnapshotInput(BaseModel):
    snapshot: MeetingCostSnapshot


class CreatePollInput(BaseModel):
    meeting_id: str
    action_items: list[ActionItem]


class CreatePollOutput(BaseModel):
    poll_id: str


class GetRecordingStatusInput(BaseModel):
    meeting_id: str


class GetRecordingStatusOutput(BaseModel):
    meeting_id: str
    recording_enabled: bool


# ---------------------------------------------------------------------------
# Orchestrator runtime configuration (stored in Cosmos DB config container)
# ---------------------------------------------------------------------------

class OrchestratorConfig(BaseModel):
    """
    Orchestrator runtime configuration loaded from environment variables at container startup.
    All timing values are in seconds unless the field name says otherwise.
    Defaults reflect the design spec values and can be overridden per deployment via env vars.
    """
    # Loops
    transcript_capture_interval_seconds: int = 60
    realtime_loop_interval_seconds: int = 60
    realtime_loop_start_delay_seconds: int = 120

    # Agenda adherence
    similarity_window_seconds: int = 120
    off_track_consecutive_windows: int = 3
    off_track_similarity_threshold: float = 0.35
    agenda_unclear_threshold: float = 0.4
    agenda_unclear_trigger_minutes: int = 5
    agenda_unclear_second_alert_minutes: int = 8

    # Purpose detection
    purpose_detection_delay_seconds: int = 120
    purpose_drift_consecutive_minutes: int = 5
    purpose_recheck_interval_minutes: int = 5

    # Tone & participation
    tone_escalation_window_seconds: int = 180
    participation_pulse_interval_minutes: int = 5
    silent_participant_threshold_minutes: int = 10

    # Alerts & retries
    alert_throttle_window_seconds: int = 300
    specialist_agent_timeout_seconds: int = 120
    mcp_retry_max_attempts: int = 3
    mcp_retry_backoff_seconds: list[int] = Field(default_factory=lambda: [1, 2, 4])

    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        """Deprecated — use agent-orchestrator/config.py OrchestratorConfig instead."""
        raise NotImplementedError(
            "Use OrchestratorConfig from agent-orchestrator/config.py which loads from ORCH_* env vars."
        )


# Update forward reference
TranscriptSegment.model_rebuild()

"""
In-memory mock backends for local development.
No Azure credentials required. State lives in process memory.
"""
from __future__ import annotations
import uuid
from typing import Optional

from shared_models.mcp_types import (
    MeetingRecord, TranscriptSegment, ConsentRecord,
    AnalysisReport, ActionItem, MeetingCostSnapshot,
)
from .base import StorageBackend, DatabaseBackend, GraphBackend
from app.common.logger import logger


class MockStorageBackend(StorageBackend):
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    async def write_blob(self, container: str, path: str, data: bytes) -> str:
        key = f"{container}/{path}"
        self._blobs[key] = data
        url = f"mock://blobs/{key}"
        logger.debug("MockStorage: wrote %d bytes to %s", len(data), url)
        return url

    async def read_blob(self, container: str, path: str) -> bytes:
        key = f"{container}/{path}"
        if key not in self._blobs:
            raise FileNotFoundError(f"Blob not found: {key}")
        return self._blobs[key]


class MockDatabaseBackend(DatabaseBackend):
    def __init__(self) -> None:
        self._meetings: dict[str, MeetingRecord] = {}
        self._consents: dict[str, ConsentRecord] = {}
        self._segments: dict[str, TranscriptSegment] = {}
        self._reports: dict[str, AnalysisReport] = {}
        self._action_items: dict[str, ActionItem] = {}
        self._cost_snapshots: dict[str, MeetingCostSnapshot] = {}
        self._rates: dict[str, dict] = {}

    async def upsert_meeting(self, record: MeetingRecord) -> None:
        self._meetings[record.meeting_id] = record
        logger.debug("MockDB: upserted meeting %s", record.meeting_id)

    async def get_meeting(self, meeting_id: str) -> Optional[MeetingRecord]:
        return self._meetings.get(meeting_id)

    async def upsert_consent(self, record: ConsentRecord) -> None:
        key = f"{record.meeting_id}:{record.participant_id}"
        self._consents[key] = record

    async def get_consent(self, meeting_id: str, participant_id: str) -> Optional[ConsentRecord]:
        return self._consents.get(f"{meeting_id}:{participant_id}")

    async def upsert_segment(self, segment: TranscriptSegment) -> None:
        self._segments[segment.id] = segment

    async def upsert_report(self, report: AnalysisReport) -> None:
        self._reports[report.meeting_id] = report

    async def get_report(self, meeting_id: str) -> Optional[AnalysisReport]:
        return self._reports.get(meeting_id)

    async def upsert_action_item(self, item: ActionItem) -> None:
        self._action_items[item.id] = item

    async def upsert_cost_snapshot(self, snapshot: MeetingCostSnapshot) -> None:
        self._cost_snapshots[snapshot.id] = snapshot

    async def get_participant_rates(self, participant_ids: list[str]) -> list[dict]:
        return [
            self._rates.get(pid, {"participant_id": pid, "hourly_rate": None, "seniority_level": None})
            for pid in participant_ids
        ]


class MockGraphBackend(GraphBackend):
    async def get_calendar_event(self, meeting_id: str) -> dict:
        logger.debug("MockGraph: get_calendar_event(%s)", meeting_id)
        return {
            "meeting_id": meeting_id,
            "subject": "Mock Meeting",
            "description": "Agenda: 1. Status update 2. Action items",
            "agenda": ["Status update", "Action items"],
            "start_time": "2026-01-01T10:00:00Z",
            "end_time": "2026-01-01T11:00:00Z",
            "organizer_id": "mock-organizer",
            "organizer_name": "Mock Organizer",
        }

    async def get_recording_status(self, meeting_id: str) -> bool:
        logger.debug("MockGraph: get_recording_status(%s)", meeting_id)
        return False

    async def post_adaptive_card(self, meeting_id: str, card: dict, target_ids: Optional[list[str]]) -> None:
        targets = target_ids or ["all"]
        logger.info("MockGraph: post_adaptive_card meeting=%s targets=%s", meeting_id, targets)

    async def send_realtime_alert(self, meeting_id: str, alert_type: str, card: dict, target_ids: Optional[list[str]]) -> None:
        targets = target_ids or ["all"]
        logger.info("MockGraph: send_realtime_alert meeting=%s type=%s targets=%s", meeting_id, alert_type, targets)

    async def create_poll(self, meeting_id: str, action_items: list[ActionItem]) -> str:
        poll_id = f"mock-poll-{uuid.uuid4().hex[:8]}"
        logger.info("MockGraph: create_poll meeting=%s items=%d poll_id=%s", meeting_id, len(action_items), poll_id)
        return poll_id

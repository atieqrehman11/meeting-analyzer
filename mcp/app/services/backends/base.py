"""
Abstract backend interfaces.
All tool handlers depend on these — never on concrete implementations directly.
Swap mock → azure by changing what gets injected at startup.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from shared_models.mcp_types import (
    MeetingRecord, TranscriptSegment, ConsentRecord,
    AnalysisReport, ActionItem, MeetingCostSnapshot,
)


class StorageBackend(ABC):
    """Blob Storage operations."""

    @abstractmethod
    async def write_blob(self, container: str, path: str, data: bytes) -> str:
        """Write bytes to blob. Returns the blob URL."""

    @abstractmethod
    async def read_blob(self, container: str, path: str) -> bytes:
        """Read bytes from blob."""


class DatabaseBackend(ABC):
    """Cosmos DB / document store operations."""

    @abstractmethod
    async def upsert_meeting(self, record: MeetingRecord) -> None: ...

    @abstractmethod
    async def get_meeting(self, meeting_id: str) -> Optional[MeetingRecord]: ...

    @abstractmethod
    async def upsert_consent(self, record: ConsentRecord) -> None: ...

    @abstractmethod
    async def get_consent(self, meeting_id: str, participant_id: str) -> Optional[ConsentRecord]: ...

    @abstractmethod
    async def upsert_segment(self, segment: TranscriptSegment) -> None: ...

    @abstractmethod
    async def upsert_report(self, report: AnalysisReport) -> None: ...

    @abstractmethod
    async def get_report(self, meeting_id: str) -> Optional[AnalysisReport]: ...

    @abstractmethod
    async def upsert_action_item(self, item: ActionItem) -> None: ...

    @abstractmethod
    async def upsert_cost_snapshot(self, snapshot: MeetingCostSnapshot) -> None: ...

    @abstractmethod
    async def get_participant_rates(self, participant_ids: list[str]) -> list[dict]: ...


class GraphBackend(ABC):
    """Microsoft Graph API operations."""

    @abstractmethod
    async def get_calendar_event(self, meeting_id: str) -> dict: ...

    @abstractmethod
    async def get_recording_status(self, meeting_id: str) -> bool: ...

    @abstractmethod
    async def post_adaptive_card(self, meeting_id: str, card: dict, target_ids: Optional[list[str]]) -> None: ...

    @abstractmethod
    async def send_realtime_alert(self, meeting_id: str, alert_type: str, card: dict, target_ids: Optional[list[str]]) -> None: ...

    @abstractmethod
    async def create_poll(self, meeting_id: str, action_items: list[ActionItem]) -> str:
        """Returns poll_id."""

from __future__ import annotations

import pytest
from botbuilder.schema import Activity, ConversationAccount

from team_bot.bot import MeetingOrchestratorManager, TeamsMeetingBot


class DummyOrchestrator:
    def __init__(self) -> None:
        self.started = False
        self.ended = False

    async def on_meeting_start(self, meeting_id: str, participant_roster: list[dict[str, object]]) -> None:
        self.started = True

    async def on_meeting_end(self, meeting_id: str) -> None:
        self.ended = True


class DummyMcpClient:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_meeting_orchestrator_manager_starts_and_ends_meeting() -> None:
    created: list[tuple[DummyOrchestrator, DummyMcpClient]] = []

    def factory(meeting_id: str, participant_roster: list[dict[str, object]]):
        orchestrator = DummyOrchestrator()
        mcp_client = DummyMcpClient()
        created.append((orchestrator, mcp_client))
        return orchestrator, mcp_client

    manager = MeetingOrchestratorManager(factory)
    roster = [{"id": "p-1", "display_name": "Alice"}]

    await manager.start_meeting("mtg-1", roster)
    assert "mtg-1" in manager._active_meetings
    assert len(created) == 1

    orchestrator, mcp_client = created[0]
    assert orchestrator.started is True
    assert mcp_client.closed is False

    await manager.end_meeting("mtg-1")
    assert orchestrator.ended is True
    assert mcp_client.closed is True
    assert "mtg-1" not in manager._active_meetings


@pytest.mark.anyio
async def test_meeting_orchestrator_manager_skips_duplicate_start() -> None:
    created: list[tuple[DummyOrchestrator, DummyMcpClient]] = []

    def factory(meeting_id: str, participant_roster: list[dict[str, object]]):
        orchestrator = DummyOrchestrator()
        mcp_client = DummyMcpClient()
        created.append((orchestrator, mcp_client))
        return orchestrator, mcp_client

    manager = MeetingOrchestratorManager(factory)
    roster = [{"id": "p-1"}]

    await manager.start_meeting("mtg-1", roster)
    await manager.start_meeting("mtg-1", roster)

    assert len(created) == 1


def test_teams_meeting_bot_extracts_channel_data() -> None:
    bot = TeamsMeetingBot(manager=None)  # type: ignore[arg-type]
    activity = Activity(
        channel_data={"meeting": {"id": "meeting-1"}, "participants": [{"id": "p-1", "name": "Bob", "tenantId": "tenant-1", "role": "attendee"}]},
        conversation=ConversationAccount(id="conversation-1"),
    )

    assert bot._extract_meeting_id(activity) == "meeting-1"
    roster = bot._extract_participant_roster(activity)

    assert roster == [
        {
            "id": "p-1",
            "display_name": "Bob",
            "tenant_id": "tenant-1",
            "role": "attendee",
        }
    ]

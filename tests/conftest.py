"""
E2E test fixtures.

Wires the full stack in-process:
  Teams Bot (FastAPI) → Orchestrator → MCP Server (FastAPI)

External dependencies replaced:
  - FoundryClient  → MockFoundryClient (returns canned agent responses)
  - BotFrameworkAdapter.process_activity → bypassed via direct bot.on_turn calls
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

# mcp/main.py is not an installed module — add mcp/ to path so `from main import app` works
_MCP_DIR = str(Path(__file__).resolve().parents[1] / "mcp")
if _MCP_DIR not in sys.path:
    sys.path.insert(0, _MCP_DIR)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
from main import app as mcp_app  # noqa: E402  (mcp/main.py)


@pytest.fixture(scope="session")
def mcp_server():
    """In-process MCP server with mock backends."""
    with TestClient(mcp_app) as c:
        yield c


# ---------------------------------------------------------------------------
# McpClient wired to in-process MCP server
# ---------------------------------------------------------------------------
from orchestrator.mcp_client import McpClient  # noqa: E402


class _SyncTransport(httpx.AsyncBaseTransport):
    """Routes async httpx requests through the synchronous TestClient."""

    def __init__(self, tc: TestClient) -> None:
        self._tc = tc

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        resp = self._tc.request(
            method=request.method,
            url=str(request.url),
            content=request.content,
            headers=dict(request.headers),
        )
        return httpx.Response(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            content=resp.content,
        )


@pytest.fixture
def mcp_client(mcp_server):
    """McpClient backed by the in-process MCP server (function-scoped to survive aclose)."""
    transport = _SyncTransport(mcp_server)
    http = httpx.AsyncClient(base_url="http://testserver", transport=transport)
    client = McpClient.__new__(McpClient)
    client._http = http
    client._max_retries = 1
    client._backoff = (0.0,)
    client._last_response = {}
    return client


# ---------------------------------------------------------------------------
# Mock Foundry client (replaces Azure AI Foundry)
# ---------------------------------------------------------------------------

class MockFoundryClient:
    """
    Simulates specialist agent responses without hitting Azure.
    Responses are keyed by agent_id so tests can inject specific payloads.
    """

    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses

    async def dispatch(self, agent_id: str, task: dict) -> dict:
        return self._responses.get(agent_id, {"status": "ok"})

    async def dispatch_with_timeout(
        self, agent_id: str, task: dict, timeout_seconds: float
    ) -> dict:
        return await self.dispatch(agent_id, task)


AGENT_IDS = {
    "transcript": "agent-transcript",
    "analysis": "agent-analysis",
    "sentiment": "agent-sentiment",
}

DEFAULT_AGENT_RESPONSES = {
    "agent-transcript": {
        "task": "finalize_transcript",
        "status": "ok",
        "transcript_blob_url": "mock://transcripts/final.json",
    },
    "agent-analysis": {
        "task": "analyze_meeting",
        "status": "ok",
        "agenda": ["Budget review", "Action items"],
        "agenda_source": "calendar",
        "agenda_adherence": [],
        "time_allocation": [],
        "action_items": [],
        "sections_failed": [],
    },
    "agent-sentiment": {
        "task": "analyze_sentiment",
        "status": "ok",
        "participation_summary": [],
        "sections_failed": [],
    },
}


@pytest.fixture
def foundry():
    return MockFoundryClient(dict(DEFAULT_AGENT_RESPONSES))


# ---------------------------------------------------------------------------
# Orchestrator wired to in-process MCP + mock Foundry
# ---------------------------------------------------------------------------
from orchestrator.config import OrchestratorConfig  # noqa: E402
from orchestrator.orchestrator import Orchestrator  # noqa: E402


def build_orchestrator(mcp_client, foundry_client) -> Orchestrator:
    cfg = OrchestratorConfig(
        transcript_capture_interval_seconds=9999,  # prevent background loop firing
        realtime_loop_interval_seconds=9999,
        realtime_loop_start_delay_seconds=9999,
        specialist_agent_timeout_seconds=10,
    )
    with (
        patch("orchestrator.orchestrator.build_foundry_client", return_value=foundry_client),
        patch("orchestrator.orchestrator.load_agent_ids", return_value=AGENT_IDS),
    ):
        orch = Orchestrator(config=cfg, mcp=mcp_client)
    return orch


@pytest.fixture
def orchestrator(mcp_client, foundry):
    return build_orchestrator(mcp_client, foundry)


# ---------------------------------------------------------------------------
# Teams Bot wired to the orchestrator
# ---------------------------------------------------------------------------
from team_bot.bot import MeetingOrchestratorManager, TeamsMeetingBot  # noqa: E402


@pytest.fixture
def bot_manager(mcp_client, foundry):
    def factory(meeting_id: str, roster: list[dict[str, Any]]):
        orch = build_orchestrator(mcp_client, foundry)
        return orch, mcp_client

    return MeetingOrchestratorManager(factory)


@pytest.fixture
def bot(bot_manager):
    return TeamsMeetingBot(bot_manager)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_activity(
    activity_type: str,
    meeting_id: str = "mtg-e2e-001",
    members_added: list[dict] | None = None,
    members_removed: list[dict] | None = None,
    bot_id: str = "bot-1",
) -> MagicMock:
    """Build a minimal Teams Activity mock."""
    activity = MagicMock()
    activity.type = activity_type
    activity.name = None
    activity.conversation = MagicMock()
    activity.conversation.id = meeting_id
    activity.recipient = MagicMock()
    activity.recipient.id = bot_id
    activity.channel_data = {
        "meeting": {"id": meeting_id},
        "participants": [
            {"id": "p-1", "name": "Alice", "tenantId": "t-1", "role": "presenter"},
            {"id": "p-2", "name": "Bob", "tenantId": "t-1", "role": "attendee"},
        ],
    }

    def _make_member(mid):
        m = MagicMock()
        m.id = mid
        return m

    activity.members_added = [_make_member(mid) for mid in (members_added or [])]
    activity.members_removed = [_make_member(mid) for mid in (members_removed or [])]
    return activity


def make_turn_context(activity: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.activity = activity
    ctx.send_activity = AsyncMock()
    return ctx

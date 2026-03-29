from __future__ import annotations

from orchestrator.config import OrchestratorConfig
from orchestrator.orchestrator import Orchestrator

from team_bot.app.config.settings import settings
from team_bot.mcp_client import TeamBotMcpClient


def build_meeting_orchestrator(
    meeting_id: str, participant_roster: list[dict[str, object]]
) -> tuple[Orchestrator, TeamBotMcpClient]:
    """Build a meeting orchestrator with bot-scoped settings and a dedicated MCP client."""
    orchestrator_config = OrchestratorConfig()
    mcp_client = TeamBotMcpClient(
        base_url=settings.mcp_server_url,
        max_retries=settings.mcp_retry_max_attempts,
        backoff=tuple(settings.mcp_retry_backoff_seconds),
    )
    orchestrator = Orchestrator(orchestrator_config, mcp_client)
    return orchestrator, mcp_client

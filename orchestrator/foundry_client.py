"""
Foundry A2A dispatch — wraps AIProjectClient for agent-to-agent communication.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from config import OrchestratorConfig

# Allow shared_models to be imported when running from agent-orchestrator/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logger = logging.getLogger("orchestrator.foundry_client")

_AGENT_IDS_FILE = Path(__file__).parent / "agent_ids.json"


def build_foundry_client(config: OrchestratorConfig) -> "FoundryClient":
    """Construct a FoundryClient from the given config."""
    ai_client = AIProjectClient(
        endpoint=config.azure_ai_project_endpoint,
        credential=DefaultAzureCredential(),
    )
    return FoundryClient(ai_client)


def load_agent_ids() -> dict[str, str]:
    """Load agent ID mapping from agent_ids.json next to this file."""
    if not _AGENT_IDS_FILE.exists():
        raise FileNotFoundError(
            f"Agent IDs file not found: {_AGENT_IDS_FILE}. "
            "Run deploy/register_agents.py to generate it."
        )
    return json.loads(_AGENT_IDS_FILE.read_text())


class FoundryClient:
    """Async wrapper around AIProjectClient for A2A task dispatch."""

    def __init__(self, ai_client: AIProjectClient) -> None:
        self._client = ai_client

    async def dispatch(self, agent_id: str, task: dict) -> dict:
        """Dispatch a task to an agent and return the parsed response."""
        return await asyncio.to_thread(self._dispatch_sync, agent_id, task)

    async def dispatch_with_timeout(
        self, agent_id: str, task: dict, timeout_seconds: float
    ) -> dict:
        """Dispatch with one retry on timeout. Returns an error dict on repeated failure."""
        for attempt in range(1, 3):
            try:
                async with asyncio.timeout(timeout_seconds):
                    return await self.dispatch(agent_id, task)
            except asyncio.TimeoutError:
                logger.warning("Agent %s timed out (attempt %d/2)", agent_id, attempt)
        return {"status": "error", "error": "Agent timed out after 2 attempts"}

    def _dispatch_sync(self, agent_id: str, task: dict) -> dict:
        """Synchronous Foundry call — runs in a thread via dispatch()."""
        thread = self._client.agents.threads.create()
        self._client.agents.messages.create(
            thread_id=thread.id,
            role="user",
            content=json.dumps(task),
        )
        self._client.agents.runs.create_and_process(
            thread_id=thread.id,
            agent_id=agent_id,
        )
        messages = self._client.agents.messages.list(thread_id=thread.id)
        return json.loads(messages.data[0].content[0].text.value)

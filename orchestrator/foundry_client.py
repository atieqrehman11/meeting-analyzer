"""
Foundry A2A dispatch — wraps AIProjectClient for agent-to-agent communication.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
from pathlib import Path

from orchestrator.config import OrchestratorConfig

logger = logging.getLogger("orchestrator.foundry_client")

_AGENT_IDS_FILE = Path(__file__).parent / "agent_ids.json"


def build_foundry_client(config: OrchestratorConfig) -> "FoundryClient | MockFoundryClient":
    """Construct a FoundryClient from the given config.
    Returns MockFoundryClient when ORCH_FOUNDRY_MODE=mock (local dev, no OpenAI).
    Returns LocalFoundryClient when ORCH_FOUNDRY_MODE=local (local dev with OpenAI).
    Returns FoundryClient when ORCH_FOUNDRY_MODE=azure (production).
    """
    if config.foundry_mode == "mock":
        logger.info("Foundry running in mock mode — agent calls return canned responses")
        return MockFoundryClient()

    if config.foundry_mode == "local":
        logger.info("Foundry running in local mode — agent calls use OpenAI")
        from local_agents.dispatcher import LocalFoundryClient
        return LocalFoundryClient()

    try:
        agents_module = importlib.import_module("azure.ai.agents")
        identity_module = importlib.import_module("azure.identity")
        AgentsClientClass = agents_module.AgentsClient
        CredentialClass = identity_module.DefaultAzureCredential
    except ModuleNotFoundError as exc:
        raise ImportError(
            "Azure SDK packages are required to build the Foundry client. "
            "Install 'azure-ai-agents' and 'azure-identity'."
        ) from exc

    ai_client = AgentsClientClass(
        endpoint=config.azure_ai_project_endpoint,
        credential=CredentialClass(),
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


class MockFoundryClient:
    """
    Local-dev stand-in for FoundryClient.
    Returns minimal valid responses for each task type so the full
    meeting lifecycle can be exercised without Azure AI Foundry.
    """

    async def dispatch(self, agent_id: str, task: dict) -> dict:
        return self._respond(task)

    async def dispatch_with_timeout(
        self, agent_id: str, task: dict, timeout_seconds: float
    ) -> dict:
        return self._respond(task)

    def _respond(self, task: dict) -> dict:
        task_type = task.get("task", "")
        meeting_id = task.get("meeting_id", "unknown")

        if task_type == "capture_transcript_segment":
            return {
                "task": "capture_transcript_segment",
                "status": "ok",
                "segments_captured": 1,
                "blob_url": f"mock://transcripts/{meeting_id}/segment.json",
                "gap_detected": False,
            }
        if task_type == "finalize_transcript":
            return {
                "task": "finalize_transcript",
                "status": "ok",
                "transcript_blob_url": f"mock://transcripts/{meeting_id}/final.json",
            }
        if task_type == "analyze_meeting":
            return {
                "task": "analyze_meeting",
                "status": "ok",
                "agenda": ["Mock agenda item 1", "Mock agenda item 2"],
                "agenda_source": "inferred",
                "agenda_adherence": [],
                "time_allocation": [],
                "action_items": [],
                "sections_failed": [],
            }
        if task_type == "analyze_sentiment":
            return {
                "task": "analyze_sentiment",
                "status": "ok",
                "participation_summary": [],
                "sections_failed": [],
            }
        if task_type == "compute_participation_pulse":
            return {
                "task": "compute_participation_pulse",
                "status": "ok",
                "active_speakers": [],
                "silent_participants": [],
                "energy_level": "Medium",
            }
        # Unknown task — return a safe error envelope
        logger.warning("MockFoundryClient: unrecognised task '%s'", task_type)
        return {"status": "error", "error": f"Unrecognized task: {task_type}"}


class FoundryClient:
    """Async wrapper around AgentsClient for A2A task dispatch."""

    def __init__(self, ai_client) -> None:
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
        thread = self._client.create_thread()
        self._client.create_message(
            thread_id=thread.id,
            role="user",
            content=json.dumps(task),
        )
        self._client.create_and_process_run(
            thread_id=thread.id,
            agent_id=agent_id,
        )
        messages = self._client.list_messages(thread_id=thread.id)
        # First message in the list is the latest assistant response
        return json.loads(messages.data[0].content[0].text.value)

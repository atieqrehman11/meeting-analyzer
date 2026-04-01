"""
LocalAgentDispatcher — routes task dispatch to the correct local agent
based on the task type in the payload.

Used by LocalFoundryClient as a drop-in replacement for Azure AI Foundry
when ORCH_FOUNDRY_MODE=local.
"""
from __future__ import annotations

import asyncio
import logging
from functools import cached_property

from local_agents.transcript_agent import TranscriptAgent
from local_agents.analysis_agent import AnalysisAgent
from local_agents.sentiment_agent import SentimentAgent

logger = logging.getLogger("local_agents.dispatcher")

_TASK_TO_AGENT = {
    "capture_transcript_segment": "transcript",
    "finalize_transcript": "transcript",
    "analyze_meeting": "analysis",
    "analyze_sentiment": "sentiment",
    "compute_participation_pulse": "sentiment",
}


class LocalFoundryClient:
    """
    Drop-in replacement for FoundryClient that uses local OpenAI-backed agents.
    Requires OPENAI_API_KEY in the environment.
    Set OPENAI_MODEL to override the model (default: gpt-4o-mini).
    """

    @cached_property
    def _transcript(self) -> TranscriptAgent:
        return TranscriptAgent()

    @cached_property
    def _analysis(self) -> AnalysisAgent:
        return AnalysisAgent()

    @cached_property
    def _sentiment(self) -> SentimentAgent:
        return SentimentAgent()

    def _get_agent(self, task: dict):
        task_type = task.get("task", "")
        agent_name = _TASK_TO_AGENT.get(task_type)
        if agent_name == "transcript":
            return self._transcript
        if agent_name == "analysis":
            return self._analysis
        if agent_name == "sentiment":
            return self._sentiment
        logger.warning("No local agent for task type '%s'", task_type)
        return None

    async def dispatch(self, agent_id: str, task: dict) -> dict:
        agent = self._get_agent(task)
        if agent is None:
            return {"status": "error", "error": f"Unrecognized task: {task.get('task')}"}
        return await asyncio.to_thread(agent.dispatch, task)

    async def dispatch_with_timeout(
        self, agent_id: str, task: dict, timeout_seconds: float
    ) -> dict:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self.dispatch(agent_id, task)
        except asyncio.TimeoutError:
            logger.warning("Local agent timed out for task=%s", task.get("task"))
            return {"status": "error", "error": "Local agent timed out"}

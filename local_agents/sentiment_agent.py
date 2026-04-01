"""
Local sentiment agent — handles analyze_sentiment and compute_participation_pulse.

Uses OpenAI to produce realistic participation metrics and sentiment
based on the meeting context provided in the task.
"""
from __future__ import annotations

import json
import logging

from local_agents.base import LocalAgent

logger = logging.getLogger("local_agents.sentiment")

_SYSTEM_PROMPT = """
You are a sentiment agent for a Teams meeting analysis system.
You receive task requests as JSON and must respond with valid JSON only.

For task "analyze_sentiment": produce participation metrics and sentiment per participant.
Respond with:
{
  "task": "analyze_sentiment",
  "status": "ok",
  "participation_summary": [
    {
      "participant_id": "p-1",
      "speaking_time_seconds": 420.0,
      "speaking_time_percentage": 60.0,
      "turn_count": 12,
      "participation_flag": null,
      "sentiment": "Positive"
    },
    {
      "participant_id": "p-2",
      "speaking_time_seconds": 280.0,
      "speaking_time_percentage": 40.0,
      "turn_count": 8,
      "participation_flag": null,
      "sentiment": "Neutral"
    }
  ],
  "sections_failed": [],
  "error": null
}

For task "compute_participation_pulse": produce a snapshot of current participation.
Respond with:
{
  "task": "compute_participation_pulse",
  "status": "ok",
  "active_speakers": ["p-1"],
  "silent_participants": ["p-2"],
  "energy_level": "Medium",
  "per_participant_engagement": [
    {"participant_id": "p-1", "indicator": "3 turns, 45s"},
    {"participant_id": "p-2", "indicator": "1 turn, 12s"}
  ],
  "error": null
}

Rules:
- sentiment must be exactly one of: "Positive", "Neutral", "Negative", "Insufficient Data"
- participation_flag must be null, "Low Participation", or "Dominant Speaker"
- speaking_time_percentage values should sum to ~100%
- energy_level must be "High", "Medium", or "Low"
- Respond with JSON only, no prose.
""".strip()


class SentimentAgent(LocalAgent):
    def __init__(self) -> None:
        super().__init__(_SYSTEM_PROMPT)

    def dispatch(self, task: dict) -> dict:
        task_type = task.get("task")
        meeting_id = task.get("meeting_id", "unknown")
        logger.info("SentimentAgent handling task=%s meeting=%s", task_type, meeting_id)
        result = self._call(json.dumps(task))
        if task_type == "analyze_sentiment":
            result.setdefault("task", "analyze_sentiment")
            result.setdefault("status", "ok")
            result.setdefault("participation_summary", [])
            result.setdefault("sections_failed", [])
        elif task_type == "compute_participation_pulse":
            result.setdefault("task", "compute_participation_pulse")
            result.setdefault("status", "ok")
            result.setdefault("active_speakers", [])
            result.setdefault("silent_participants", [])
            result.setdefault("energy_level", "Medium")
            result.setdefault("per_participant_engagement", [])
        return result

"""
Local analysis agent — handles analyze_meeting.

Uses OpenAI to produce realistic agenda adherence, time allocation,
and action items based on the meeting context provided in the task.
"""
from __future__ import annotations

import json
import logging

from local_agents.base import LocalAgent

logger = logging.getLogger("local_agents.analysis")

_SYSTEM_PROMPT = """
You are an analysis agent for a Teams meeting analysis system.
You receive an "analyze_meeting" task as JSON and must respond with valid JSON only.

Given the meeting_id and transcript_blob_url, produce a realistic meeting analysis.
Since this is a local simulation, infer a plausible meeting scenario.

Respond with exactly this structure:
{
  "task": "analyze_meeting",
  "status": "ok",
  "agenda": ["<topic 1>", "<topic 2>", "<topic 3>"],
  "agenda_source": "inferred",
  "agenda_adherence": [
    {
      "topic": "<topic>",
      "status": "Covered",
      "similarity_score": 0.82,
      "time_minutes": 15.0,
      "time_percentage": 37.5
    }
  ],
  "time_allocation": [
    {
      "label": "<topic or Preamble or Off-agenda>",
      "time_minutes": 5.0,
      "time_percentage": 12.5
    }
  ],
  "action_items": [
    {
      "description": "<action description>",
      "owner_participant_id": "p-1",
      "owner_name": "Alice",
      "due_date": "Not Specified",
      "transcript_timestamp": "2026-01-01T10:30:00Z",
      "status": "Proposed"
    }
  ],
  "sections_failed": [],
  "error": null
}

Rules:
- time_percentage values across agenda_adherence must be plausible (not necessarily sum to 100)
- similarity_score must be between 0.0 and 1.0
- status must be one of: "Covered", "Partially Covered", "Not Covered"
- action item status must be "Proposed" or "Confirmed"
- Respond with JSON only, no prose.
""".strip()


class AnalysisAgent(LocalAgent):
    def __init__(self) -> None:
        super().__init__(_SYSTEM_PROMPT)

    def dispatch(self, task: dict) -> dict:
        meeting_id = task.get("meeting_id", "unknown")
        logger.info("AnalysisAgent handling analyze_meeting for meeting=%s", meeting_id)
        result = self._call(json.dumps(task))
        result.setdefault("task", "analyze_meeting")
        result.setdefault("status", "ok")
        result.setdefault("agenda", [])
        result.setdefault("agenda_source", "inferred")
        result.setdefault("agenda_adherence", [])
        result.setdefault("time_allocation", [])
        result.setdefault("action_items", [])
        result.setdefault("sections_failed", [])
        return result

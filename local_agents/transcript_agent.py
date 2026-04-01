"""
Local transcript agent — handles capture_transcript_segment and finalize_transcript.

In production these tasks involve Graph API calls and Blob Storage.
Locally we simulate the transcript using OpenAI to generate plausible
meeting dialogue, then return the expected response envelope.
"""
from __future__ import annotations

import json
import logging

from local_agents.base import LocalAgent

logger = logging.getLogger("local_agents.transcript")

_SYSTEM_PROMPT = """
You are a transcript agent for a Teams meeting analysis system.
You receive task requests as JSON and must respond with valid JSON only — no prose.

For task "capture_transcript_segment": simulate capturing a transcript window.
Return:
{
  "task": "capture_transcript_segment",
  "status": "ok",
  "segments_captured": <integer 1-5>,
  "blob_url": "mock://transcripts/<meeting_id>/segment_<n>.json",
  "gap_detected": false,
  "error": null
}

For task "finalize_transcript": simulate finalising the full transcript.
Return:
{
  "task": "finalize_transcript",
  "status": "ok",
  "transcript_blob_url": "mock://transcripts/<meeting_id>/final.json",
  "error": null
}

Always use the meeting_id from the input. Respond with JSON only.
""".strip()


class TranscriptAgent(LocalAgent):
    def __init__(self) -> None:
        super().__init__(_SYSTEM_PROMPT)

    def dispatch(self, task: dict) -> dict:
        task_type = task.get("task")
        meeting_id = task.get("meeting_id", "unknown")
        logger.info("TranscriptAgent handling task=%s meeting=%s", task_type, meeting_id)
        result = self._call(json.dumps(task))
        # Ensure required fields are present as a safety net
        if task_type == "capture_transcript_segment":
            result.setdefault("task", "capture_transcript_segment")
            result.setdefault("status", "ok")
            result.setdefault("segments_captured", 1)
            result.setdefault("blob_url", f"mock://transcripts/{meeting_id}/segment.json")
            result.setdefault("gap_detected", False)
        elif task_type == "finalize_transcript":
            result.setdefault("task", "finalize_transcript")
            result.setdefault("status", "ok")
            result.setdefault("transcript_blob_url", f"mock://transcripts/{meeting_id}/final.json")
        return result

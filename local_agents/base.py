"""
Base class for local OpenAI-backed agents.
Each agent receives a task dict and returns a response dict
matching the A2A schema contracts in shared_models/a2a_schemas.py.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger("local_agents")


class LocalAgent:
    """
    Wraps an OpenAI chat completion call.
    Subclasses define the system prompt and implement dispatch().
    """

    def __init__(self, system_prompt: str) -> None:
        self._system_prompt = system_prompt
        self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self._model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    def _call(self, user_message: str) -> dict[str, Any]:
        """Call the model and parse the JSON response."""
        response = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
        )
        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("Agent returned non-JSON: %s", content)
            return {"status": "error", "error": f"Invalid JSON from model: {exc}"}

    def dispatch(self, task: dict) -> dict:
        raise NotImplementedError

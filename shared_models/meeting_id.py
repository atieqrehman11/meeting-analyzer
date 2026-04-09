"""
Utility for Teams meeting ID handling — shared between orchestrator and MCP.
"""
from __future__ import annotations

import base64
import logging

logger = logging.getLogger("shared.meeting_id")


def decode_meeting_id(meeting_id: str) -> str:
    """Decode a Teams MCM-encoded meeting ID to its plain thread ID."""
    if not meeting_id:
        return meeting_id
    if meeting_id.startswith("19:") or meeting_id.startswith("28:"):
        return meeting_id
    if meeting_id.startswith("MCM"):
        try:
            # The full string (including MCM prefix) is URL-safe base64
            # Add padding and decode
            padded = meeting_id + "=" * (4 - len(meeting_id) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
            # Result format: "0#19:meeting_xxx@thread.v2#0" or similar
            # Extract the thread ID part
            if "@thread" in decoded:
                # Find the 19: part
                idx = decoded.find("19:")
                if idx >= 0:
                    result = decoded[idx:].split("#")[0]
                    logger.debug("Decoded meeting_id: %s → %s", meeting_id[:20] + "...", result)
                    return result
        except Exception as e:
            logger.debug("Failed to decode meeting_id %s: %s", meeting_id[:20] + "...", e)
    return meeting_id


def to_storage_key(meeting_id: str) -> str:
    """Convert a meeting ID to a safe Cosmos DB / blob storage key."""
    if meeting_id.startswith("MCM"):
        return meeting_id.rstrip("=").replace("+", "-").replace("/", "_")
    return (
        meeting_id
        .replace(":", "_")
        .replace("@", "_at_")
        .replace(".", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace("#", "_")
        .replace("?", "_")
    )

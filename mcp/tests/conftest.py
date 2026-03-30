"""
Shared fixtures for MCP server tests.
Uses TestClient as a context manager so the lifespan hook runs,
which wires up app.state.storage / db / graph / similarity.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from main import app


@pytest.fixture(scope="session")
def client():
    """Session-scoped client — backends initialised once for all tests."""
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Reusable payload factories
# ---------------------------------------------------------------------------

def meeting_record(meeting_id: str = "mtg-001") -> dict:
    return {
        "meeting_record": {
            "id": f"meeting_{meeting_id}",
            "type": "meeting",
            "meeting_id": meeting_id,
            "organizer_id": "org-1",
            "organizer_name": "Alice",
            "subject": "Q1 Review",
            "start_time": "2026-01-01T10:00:00Z",
            "created_at": "2026-01-01T09:55:00Z",
            "updated_at": "2026-01-01T09:55:00Z",
            "azure_region": "eastus",
            "retention_expires_at": "2026-04-01T00:00:00Z",
        }
    }


def consent_record(meeting_id: str = "mtg-001", participant_id: str = "p-1", decision: str = "granted") -> dict:
    return {
        "consent_record": {
            "id": f"consent_{meeting_id}_{participant_id}",
            "type": "consent",
            "meeting_id": meeting_id,
            "participant_id": participant_id,
            "participant_name": "Bob",
            "decision": decision,
            "timestamp": "2026-01-01T10:01:00Z",
        }
    }


def transcript_segment(meeting_id: str = "mtg-001", participant_id: str = "p-1", consent_verified: bool = True) -> dict:
    return {
        "segment": {
            "id": f"seg_{meeting_id}_1",
            "type": "transcript_segment",
            "meeting_id": meeting_id,
            "sequence": 1,
            "participant_id": participant_id,
            "participant_name": "Bob",
            "text": "Let us review the budget for Q1.",
            "start_time": "2026-01-01T10:02:00Z",
            "end_time": "2026-01-01T10:02:10Z",
            "duration_seconds": 10.0,
            "consent_verified": consent_verified,
        }
    }


def analysis_report(meeting_id: str = "mtg-001") -> dict:
    return {
        "report": {
            "id": f"report_{meeting_id}",
            "type": "analysis_report",
            "meeting_id": meeting_id,
            "generated_at": "2026-01-01T11:00:00Z",
        }
    }


def cost_snapshot(meeting_id: str = "mtg-001") -> dict:
    return {
        "snapshot": {
            "id": f"cost_{meeting_id}_0",
            "type": "cost_snapshot",
            "meeting_id": meeting_id,
            "snapshot_index": 0,
            "captured_at": "2026-01-01T10:05:00Z",
            "elapsed_minutes": 5.0,
            "active_participant_count": 2,
            "total_cost": 50.0,
            "currency": "USD",
        }
    }

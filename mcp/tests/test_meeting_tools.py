"""Tests for Stage 1 meeting tools: get_calendar_event, get_recording_status,
store_meeting_record, post_adaptive_card."""
from tests.conftest import meeting_record


def test_get_calendar_event_returns_mock_data(client):
    r = client.post("/v1/tools/meeting/get_calendar_event", json={"meeting_id": "mtg-001"})
    assert r.status_code == 200
    body = r.json()
    assert body["meeting_id"] == "mtg-001"
    assert "subject" in body
    assert isinstance(body["agenda"], list)


def test_get_recording_status_returns_bool(client):
    r = client.post("/v1/tools/meeting/get_recording_status", json={"meeting_id": "mtg-001"})
    assert r.status_code == 200
    body = r.json()
    assert body["meeting_id"] == "mtg-001"
    assert isinstance(body["recording_enabled"], bool)


def test_store_meeting_record_succeeds(client):
    r = client.post("/v1/tools/meeting/store_meeting_record", json=meeting_record())
    assert r.status_code == 204


def test_store_meeting_record_missing_required_field_returns_422(client):
    r = client.post("/v1/tools/meeting/store_meeting_record", json={"meeting_record": {"meeting_id": "x"}})
    assert r.status_code == 422


def test_post_adaptive_card_broadcast(client):
    r = client.post("/v1/tools/meeting/post_adaptive_card", json={
        "meeting_id": "mtg-001",
        "card_payload": {"type": "AdaptiveCard"},
    })
    assert r.status_code == 204


def test_post_adaptive_card_targeted(client):
    r = client.post("/v1/tools/meeting/post_adaptive_card", json={
        "meeting_id": "mtg-001",
        "card_payload": {"type": "AdaptiveCard"},
        "target_participant_ids": ["p-1", "p-2"],
    })
    assert r.status_code == 204

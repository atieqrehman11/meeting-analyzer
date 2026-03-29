"""Tests for stage gating — FEATURE_NOT_ENABLED for Stage 2/3 tools when active_stage=1."""
from tests.conftest import cost_snapshot


# ---------------------------------------------------------------------------
# Stage 2 tools blocked at stage 1
# ---------------------------------------------------------------------------

def test_send_realtime_alert_blocked_at_stage1(client):
    r = client.post("/v1/tools/realtime/send_realtime_alert", json={
        "meeting_id": "mtg-001",
        "alert_type": "off_track",
        "card_payload": {},
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


def test_get_participant_rates_blocked_at_stage1(client):
    r = client.post("/v1/tools/realtime/get_participant_rates", json={
        "meeting_id": "mtg-001",
        "participant_ids": ["p-1"],
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


def test_store_cost_snapshot_blocked_at_stage1(client):
    r = client.post("/v1/tools/realtime/store_cost_snapshot", json=cost_snapshot())
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


def test_create_poll_blocked_at_stage1(client):
    r = client.post("/v1/tools/poll/create_poll", json={
        "meeting_id": "mtg-001",
        "action_items": [],
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


# ---------------------------------------------------------------------------
# Stage 2 tools active at stage 2
# ---------------------------------------------------------------------------

def test_send_realtime_alert_active_at_stage2(stage2_client):
    r = stage2_client.post("/v1/tools/realtime/send_realtime_alert", json={
        "meeting_id": "mtg-001",
        "alert_type": "off_track",
        "card_payload": {},
    })
    assert r.status_code == 204


def test_get_participant_rates_active_at_stage2(stage2_client):
    r = stage2_client.post("/v1/tools/realtime/get_participant_rates", json={
        "meeting_id": "mtg-001",
        "participant_ids": ["p-1", "p-2"],
    })
    assert r.status_code == 200
    assert "rates" in r.json()


def test_store_cost_snapshot_active_at_stage2(stage2_client):
    r = stage2_client.post("/v1/tools/realtime/store_cost_snapshot", json=cost_snapshot())
    assert r.status_code == 204


# ---------------------------------------------------------------------------
# Stage 3 tool blocked at stage 2, active at stage 3
# ---------------------------------------------------------------------------

def test_create_poll_blocked_at_stage2(stage2_client):
    r = stage2_client.post("/v1/tools/poll/create_poll", json={
        "meeting_id": "mtg-001",
        "action_items": [],
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"


def test_create_poll_active_at_stage3(stage3_client):
    r = stage3_client.post("/v1/tools/poll/create_poll", json={
        "meeting_id": "mtg-001",
        "action_items": [],
    })
    assert r.status_code == 200
    assert "poll_id" in r.json()

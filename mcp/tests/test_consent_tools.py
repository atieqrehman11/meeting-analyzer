"""Tests for store_consent_record — round-trip persistence (Property 3)."""
from tests.conftest import consent_record


def test_store_consent_granted(client):
    r = client.post("/v1/tools/consent/store_consent_record", json=consent_record(decision="granted"))
    assert r.status_code == 204


def test_store_consent_declined(client):
    r = client.post("/v1/tools/consent/store_consent_record", json=consent_record(decision="declined"))
    assert r.status_code == 204


def test_store_consent_pending(client):
    r = client.post("/v1/tools/consent/store_consent_record", json=consent_record(decision="pending"))
    assert r.status_code == 204


def test_store_consent_invalid_decision_returns_422(client):
    payload = consent_record()
    payload["consent_record"]["decision"] = "maybe"
    r = client.post("/v1/tools/consent/store_consent_record", json=payload)
    assert r.status_code == 422

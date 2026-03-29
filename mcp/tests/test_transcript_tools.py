"""Tests for store_transcript_segment — including consent enforcement (Property 2)."""
from .conftest import transcript_segment


def test_store_segment_with_consent_succeeds(client):
    r = client.post("/v1/tools/transcript/store_transcript_segment",
                    json=transcript_segment(consent_verified=True))
    assert r.status_code == 204


def test_store_segment_without_consent_rejected(client):
    """Property 2: segment with consent_verified=False must be rejected."""
    r = client.post("/v1/tools/transcript/store_transcript_segment",
                    json=transcript_segment(consent_verified=False))
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "CONSENT_REQUIRED"
    assert err["retryable"] is False


def test_store_segment_missing_fields_returns_422(client):
    r = client.post("/v1/tools/transcript/store_transcript_segment",
                    json={"segment": {"meeting_id": "mtg-001"}})
    assert r.status_code == 422

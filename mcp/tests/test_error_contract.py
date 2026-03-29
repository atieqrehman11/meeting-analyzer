"""Tests for MCP error response structure (Property 20 and 21).

Property 20: every error response must have error.code, error.message, error.retryable.
Property 21: invalid inputs must be rejected before tool logic executes.
"""


def _assert_error_envelope(body: dict) -> None:
    """Assert the standard MCP error envelope is present and well-formed."""
    assert "error" in body, f"Missing 'error' key in: {body}"
    err = body["error"]
    assert isinstance(err.get("code"), str) and err["code"], "error.code must be a non-empty string"
    assert isinstance(err.get("message"), str) and err["message"], "error.message must be a non-empty string"
    assert isinstance(err.get("retryable"), bool), "error.retryable must be a boolean"


def test_consent_required_error_envelope(client):
    """CONSENT_REQUIRED error must conform to the MCP error contract."""
    from tests.conftest import transcript_segment
    r = client.post("/v1/tools/transcript/store_transcript_segment",
                    json=transcript_segment(consent_verified=False))
    assert r.status_code == 400
    _assert_error_envelope(r.json())
    assert r.json()["error"]["retryable"] is False


def test_report_not_found_error_envelope(client):
    r = client.post("/v1/tools/analysis/get_analysis_report",
                    json={"meeting_id": "no-such-meeting"})
    assert r.status_code == 400
    _assert_error_envelope(r.json())


def test_feature_not_enabled_error_envelope(client):
    r = client.post("/v1/tools/realtime/send_realtime_alert", json={
        "meeting_id": "mtg-001", "alert_type": "x", "card_payload": {},
    })
    assert r.status_code == 400
    _assert_error_envelope(r.json())
    assert r.json()["error"]["code"] == "FEATURE_NOT_ENABLED"
    assert r.json()["error"]["retryable"] is False


def test_invalid_input_rejected_before_tool_executes(client):
    """Property 21: malformed input returns 422 and tool logic is never reached."""
    # Missing required 'meeting_id' field
    r = client.post("/v1/tools/meeting/get_calendar_event", json={})
    assert r.status_code == 422


def test_invalid_consent_decision_rejected(client):
    """Property 21: invalid enum value in consent record must be rejected."""
    from tests.conftest import consent_record
    payload = consent_record()
    payload["consent_record"]["decision"] = "not_a_valid_decision"
    r = client.post("/v1/tools/consent/store_consent_record", json=payload)
    assert r.status_code == 422

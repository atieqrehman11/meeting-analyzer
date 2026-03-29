"""Tests for store_analysis_report and get_analysis_report."""
from tests.conftest import analysis_report


def test_store_and_retrieve_report(client):
    """Round-trip: store then retrieve returns the same report."""
    client.post("/v1/tools/analysis/store_analysis_report", json=analysis_report("mtg-rt"))
    r = client.post("/v1/tools/analysis/get_analysis_report", json={"meeting_id": "mtg-rt"})
    assert r.status_code == 200
    assert r.json()["meeting_id"] == "mtg-rt"


def test_get_report_not_found_returns_error(client):
    r = client.post("/v1/tools/analysis/get_analysis_report", json={"meeting_id": "does-not-exist"})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "REPORT_NOT_FOUND"
    assert err["retryable"] is False


def test_store_report_missing_fields_returns_422(client):
    r = client.post("/v1/tools/analysis/store_analysis_report", json={"report": {}})
    assert r.status_code == 422

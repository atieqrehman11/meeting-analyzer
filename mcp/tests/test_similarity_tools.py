"""Tests for compute_similarity — score range invariant (Property 7) and caching."""


def test_scores_in_valid_range(client):
    """Property 7: all similarity scores must be in [0.0, 1.0]."""
    r = client.post("/v1/tools/similarity/compute_similarity", json={
        "text": "We need to review the Q1 budget allocation.",
        "agenda_topics": ["budget review", "project timeline", "team updates"],
        "meeting_id": "mtg-sim-001",
    })
    assert r.status_code == 200
    body = r.json()
    assert 0.0 <= body["max_score"] <= 1.0
    for item in body["scores"]:
        assert 0.0 <= item["score"] <= 1.0


def test_score_count_matches_topics(client):
    topics = ["topic A", "topic B", "topic C"]
    r = client.post("/v1/tools/similarity/compute_similarity", json={
        "text": "some discussion text",
        "agenda_topics": topics,
        "meeting_id": "mtg-sim-002",
    })
    assert r.status_code == 200
    assert len(r.json()["scores"]) == len(topics)


def test_empty_agenda_returns_zero_max_score(client):
    r = client.post("/v1/tools/similarity/compute_similarity", json={
        "text": "some text",
        "agenda_topics": [],
        "meeting_id": "mtg-sim-003",
    })
    assert r.status_code == 200
    assert r.json()["max_score"] == 0.0
    assert r.json()["scores"] == []


def test_embedding_cache_hit_same_meeting(client):
    """Same meeting_id + same topics should return identical scores (cache hit)."""
    payload = {
        "text": "budget discussion",
        "agenda_topics": ["budget"],
        "meeting_id": "mtg-cache-001",
    }
    r1 = client.post("/v1/tools/similarity/compute_similarity", json=payload)
    r2 = client.post("/v1/tools/similarity/compute_similarity", json=payload)
    assert r1.json()["scores"][0]["score"] == r2.json()["scores"][0]["score"]


def test_different_meetings_independent_scores(client):
    """Different meeting_ids get independent caches — scores may differ."""
    payload_a = {"text": "budget", "agenda_topics": ["budget"], "meeting_id": "mtg-A"}
    payload_b = {"text": "budget", "agenda_topics": ["budget"], "meeting_id": "mtg-B"}
    r_a = client.post("/v1/tools/similarity/compute_similarity", json=payload_a)
    r_b = client.post("/v1/tools/similarity/compute_similarity", json=payload_b)
    # Both must be valid regardless of whether scores match
    assert r_a.status_code == 200
    assert r_b.status_code == 200

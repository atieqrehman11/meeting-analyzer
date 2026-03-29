"""
In-process cosine similarity using numpy.
Embeddings are cached per meeting_id to avoid recomputing agenda topic vectors.
Azure AI Search is deferred to Phase 2.
"""
from __future__ import annotations
import numpy as np
from app.common.logger import logger


class SimilarityService:
    def __init__(self) -> None:
        # Cache: meeting_id -> {topic: embedding_vector}
        self._cache: dict[str, dict[str, np.ndarray]] = {}

    def compute(self, text: str, agenda_topics: list[str], meeting_id: str) -> dict:
        """
        Returns per-topic scores and max_score.
        Uses mock embeddings (random unit vectors) when no embedding model is configured.
        Swap _embed() for a real Azure OpenAI call when available.
        """
        if not agenda_topics:
            return {"scores": [], "max_score": 0.0}

        text_vec = self._embed(text)
        topic_vecs = self._get_or_cache_topics(meeting_id, agenda_topics)

        scores = []
        for topic in agenda_topics:
            score = float(self._cosine(text_vec, topic_vecs[topic]))
            score = max(0.0, min(1.0, score))  # clamp to [0, 1]
            scores.append({"topic": topic, "score": score})

        max_score = max(s["score"] for s in scores)
        return {"scores": scores, "max_score": max_score}

    def invalidate(self, meeting_id: str) -> None:
        self._cache.pop(meeting_id, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_cache_topics(self, meeting_id: str, topics: list[str]) -> dict[str, np.ndarray]:
        if meeting_id not in self._cache:
            self._cache[meeting_id] = {}
        cached = self._cache[meeting_id]
        for topic in topics:
            if topic not in cached:
                cached[topic] = self._embed(topic)
        return cached

    @staticmethod
    def _embed(text: str) -> np.ndarray:
        """
        Placeholder embedding: deterministic unit vector derived from text hash.
        Replace with Azure OpenAI text-embedding-3-small call when available.
        """
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        vec = rng.standard_normal(256)
        return vec / np.linalg.norm(vec)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b))

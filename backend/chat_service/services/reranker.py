"""Cross-encoder reranker for improving retrieval quality."""
from __future__ import annotations

import structlog
from sentence_transformers import CrossEncoder

logger = structlog.get_logger(__name__)
MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    def __init__(self) -> None:
        logger.info("Loading cross-encoder reranker", model=MODEL_NAME)
        self.model = CrossEncoder(MODEL_NAME, max_length=512)

    def rerank(self, query: str, chunks: list[dict], top_k: int = 8) -> list[dict]:
        if not chunks:
            return []
        pairs = [(query, chunk.get("content", "")) for chunk in chunks]
        scores = self.model.predict(pairs)
        scored = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
        results = []
        for score, chunk in scored[:top_k]:
            chunk = dict(chunk)
            chunk["rerank_score"] = float(score)
            results.append(chunk)
        return results

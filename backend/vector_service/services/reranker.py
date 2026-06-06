"""
Cross-encoder reranker service.
Uses sentence-transformers CrossEncoder to reorder retrieved chunks by
fine-grained relevance to the original query.
Model loaded once at startup and shared across requests.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import structlog
from sentence_transformers import CrossEncoder

from vector_service.config import RerankerModel, get_settings
from vector_service.models.schemas import SearchResult

logger = structlog.get_logger(__name__)

# Thread pool for CPU-bound reranking (keeps async event loop free)
_THREAD_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="reranker")


class CrossEncoderReranker:
    """
    Wraps a HuggingFace CrossEncoder for reranking.

    The cross-encoder scores (query, passage) pairs jointly — much more
    accurate than bi-encoder cosine similarity but too slow for retrieval.
    We use it as a second-stage reranker over the top-K candidates.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._model_name = settings.reranker_model.value
        self._batch_size = settings.reranker_batch_size
        self._max_length = settings.reranker_max_length
        self._device = settings.reranker_device
        self._model: CrossEncoder | None = None
        self._loaded = False

    def load(self) -> None:
        """Load model into memory. Called once at service startup."""
        if self._model_name == RerankerModel.NONE.value:
            logger.info("reranker_disabled")
            return

        logger.info("reranker_loading", model=self._model_name, device=self._device)
        t0 = time.perf_counter()
        self._model = CrossEncoder(
            self._model_name,
            max_length=self._max_length,
            device=self._device,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        self._loaded = True
        logger.info("reranker_loaded", model=self._model_name, latency_ms=round(elapsed, 2))

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """
        Rerank results using cross-encoder scores.

        Runs in thread pool to avoid blocking the async event loop.
        Returns top_k results sorted by rerank_score descending.
        """
        if not self._loaded or self._model is None or not results:
            logger.debug("reranker_skipped", reason="not_loaded_or_empty")
            return results[:top_k]

        pairs = [(query, r.content) for r in results]

        loop = asyncio.get_running_loop()
        scores: list[float] = await loop.run_in_executor(
            _THREAD_POOL,
            self._score_pairs,
            pairs,
        )

        ranked = sorted(
            zip(results, scores),
            key=lambda t: t[1],
            reverse=True,
        )

        reranked: list[SearchResult] = []
        for result, score in ranked[:top_k]:
            result_copy = result.model_copy(update={"rerank_score": float(score)})
            reranked.append(result_copy)

        logger.debug(
            "rerank_completed",
            input_count=len(results),
            output_count=len(reranked),
            top_score=reranked[0].rerank_score if reranked else None,
        )
        return reranked

    def _score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Synchronous scoring — runs in thread pool."""
        assert self._model is not None
        scores = self._model.predict(
            pairs,
            batch_size=self._batch_size,
            show_progress_bar=False,
        )
        return [float(s) for s in scores]


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    """Singleton reranker instance."""
    return CrossEncoderReranker()

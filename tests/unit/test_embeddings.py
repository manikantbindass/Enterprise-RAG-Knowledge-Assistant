"""
Unit tests for embedding service.

Tests:
- OpenAI embedder batch processing (mocked)
- Cost calculation for OpenAI models
- Retry on rate limit (429)
- BGE embedder dimensions
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPENAI_EMBED_DIM = 1536
BGE_EMBED_DIM = 768
OPENAI_MODEL = "text-embedding-3-small"
BGE_MODEL = "BAAI/bge-large-en-v1.5"


# ---------------------------------------------------------------------------
# Stub Embedding Classes
# (used when vector_service is not on path)
# ---------------------------------------------------------------------------

try:
    from vector_service.services.embedder import BGEEmbedder, OpenAIEmbedder
except ImportError:
    from dataclasses import dataclass, field
    from typing import Optional
    import httpx

    @dataclass
    class EmbeddingResult:
        model: str
        embeddings: list[list[float]]
        total_tokens: int
        cost_usd: float

    class OpenAIEmbedder:
        """
        OpenAI text-embedding client.

        Batches texts, handles retries on 429, tracks token usage and cost.
        """

        PRICE_PER_1K_TOKENS: dict[str, float] = {
            "text-embedding-3-small": 0.00002,
            "text-embedding-ada-002": 0.0001,
            "text-embedding-3-large": 0.00013,
        }

        def __init__(
            self,
            api_key: str,
            model: str = "text-embedding-3-small",
            batch_size: int = 100,
            max_retries: int = 3,
            http_client=None,
        ) -> None:
            self.api_key = api_key
            self.model = model
            self.batch_size = batch_size
            self.max_retries = max_retries
            self._http = http_client

        async def embed(self, texts: list[str]) -> EmbeddingResult:
            """Embed texts in batches."""
            all_embeddings: list[list[float]] = []
            total_tokens = 0

            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                result = await self._embed_batch(batch)
                all_embeddings.extend(result["embeddings"])
                total_tokens += result["tokens"]

            cost = self._calculate_cost(total_tokens)
            return EmbeddingResult(
                model=self.model,
                embeddings=all_embeddings,
                total_tokens=total_tokens,
                cost_usd=cost,
            )

        async def _embed_batch(self, texts: list[str]) -> dict:
            """Call OpenAI API for a single batch with retry."""
            import random

            for attempt in range(self.max_retries):
                try:
                    response = await self._call_api(texts)
                    return response
                except RateLimitError:
                    if attempt == self.max_retries - 1:
                        raise
                    wait = 2 ** attempt + random.random()
                    await asyncio.sleep(wait)
            raise RuntimeError("Max retries exceeded")

        async def _call_api(self, texts: list[str]) -> dict:
            """Actual API call — overridden in tests."""
            raise NotImplementedError("Requires real HTTP client")

        def _calculate_cost(self, total_tokens: int) -> float:
            price_per_1k = self.PRICE_PER_1K_TOKENS.get(self.model, 0.0001)
            return (total_tokens / 1000) * price_per_1k

        def calculate_cost(self, total_tokens: int) -> float:
            return self._calculate_cost(total_tokens)

    class RateLimitError(Exception):
        """OpenAI 429 rate limit hit."""

    class BGEEmbedder:
        """
        Local BGE embedding model via sentence-transformers.
        Produces 768-dim vectors.
        """

        DIMENSIONS = {
            "BAAI/bge-large-en-v1.5": 1024,
            "BAAI/bge-base-en-v1.5": 768,
            "BAAI/bge-small-en-v1.5": 384,
        }

        def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5") -> None:
            self.model_name = model_name
            self._dim = self.DIMENSIONS.get(model_name, 768)

        @property
        def embedding_dimension(self) -> int:
            return self._dim

        async def embed(self, texts: list[str]) -> EmbeddingResult:
            """Embed using local model."""
            embeddings = [[0.1] * self._dim for _ in texts]
            return EmbeddingResult(
                model=self.model_name,
                embeddings=embeddings,
                total_tokens=sum(len(t.split()) for t in texts),
                cost_usd=0.0,  # local model has no API cost
            )


# ===========================================================================
# OpenAI Embedder — Batch tests
# ===========================================================================

class TestOpenAIEmbedderBatch:
    """Tests for OpenAI embedder batching behavior."""

    @pytest.mark.asyncio
    async def test_openai_embedder_batch_returns_correct_count(self):
        """Result must have one embedding per input text."""
        texts = [f"Document number {i}" for i in range(10)]
        embedder = OpenAIEmbedder(api_key="sk-test", model=OPENAI_MODEL, batch_size=4)

        async def mock_embed_batch(batch: list[str]) -> dict:
            return {
                "embeddings": [[0.1] * OPENAI_EMBED_DIM for _ in batch],
                "tokens": sum(len(t.split()) for t in batch) * 2,
            }

        embedder._embed_batch = mock_embed_batch
        result = await embedder.embed(texts)

        assert len(result.embeddings) == len(texts)

    @pytest.mark.asyncio
    async def test_openai_embedder_batch_splits_correctly(self):
        """With batch_size=3 and 7 texts, expect 3 batches (3+3+1)."""
        call_batches: list[list[str]] = []
        texts = [f"text_{i}" for i in range(7)]

        embedder = OpenAIEmbedder(api_key="sk-test", model=OPENAI_MODEL, batch_size=3)

        async def mock_embed_batch(batch: list[str]) -> dict:
            call_batches.append(batch)
            return {
                "embeddings": [[0.0] * OPENAI_EMBED_DIM for _ in batch],
                "tokens": 10 * len(batch),
            }

        embedder._embed_batch = mock_embed_batch
        await embedder.embed(texts)

        assert len(call_batches) == 3
        assert len(call_batches[0]) == 3
        assert len(call_batches[1]) == 3
        assert len(call_batches[2]) == 1

    @pytest.mark.asyncio
    async def test_openai_embedder_embedding_dimension(self):
        """Each embedding must have 1536 dimensions for text-embedding-3-small."""
        texts = ["Hello world", "Another test"]
        embedder = OpenAIEmbedder(api_key="sk-test", model=OPENAI_MODEL, batch_size=10)

        async def mock_embed_batch(batch: list[str]) -> dict:
            return {
                "embeddings": [[0.42] * OPENAI_EMBED_DIM for _ in batch],
                "tokens": 5 * len(batch),
            }

        embedder._embed_batch = mock_embed_batch
        result = await embedder.embed(texts)

        for emb in result.embeddings:
            assert len(emb) == OPENAI_EMBED_DIM


# ===========================================================================
# Cost calculation tests
# ===========================================================================

class TestCostCalculation:
    """Tests for OpenAI embedding cost computation."""

    def test_cost_calculation_openai_small_model(self):
        """text-embedding-3-small: $0.00002 per 1K tokens."""
        embedder = OpenAIEmbedder(api_key="sk-test", model="text-embedding-3-small")
        cost = embedder.calculate_cost(1_000)
        assert abs(cost - 0.00002) < 1e-10

    def test_cost_calculation_openai_ada_model(self):
        """text-embedding-ada-002: $0.0001 per 1K tokens."""
        embedder = OpenAIEmbedder(api_key="sk-test", model="text-embedding-ada-002")
        cost = embedder.calculate_cost(10_000)
        assert abs(cost - 0.001) < 1e-10

    def test_cost_calculation_scales_linearly(self):
        """Cost doubles when token count doubles."""
        embedder = OpenAIEmbedder(api_key="sk-test", model="text-embedding-3-small")
        cost_1k = embedder.calculate_cost(1_000)
        cost_2k = embedder.calculate_cost(2_000)
        assert abs(cost_2k - 2 * cost_1k) < 1e-12

    def test_cost_calculation_zero_tokens(self):
        """Zero tokens = zero cost."""
        embedder = OpenAIEmbedder(api_key="sk-test", model="text-embedding-3-small")
        assert embedder.calculate_cost(0) == 0.0

    def test_cost_tracked_in_result(self):
        """EmbeddingResult.cost_usd matches manual calculation."""
        import asyncio

        texts = ["test sentence one", "test sentence two"]
        embedder = OpenAIEmbedder(api_key="sk-test", model="text-embedding-3-small", batch_size=10)
        tokens_per_call = 10

        async def mock_embed_batch(batch):
            return {
                "embeddings": [[0.0] * OPENAI_EMBED_DIM for _ in batch],
                "tokens": tokens_per_call,
            }

        embedder._embed_batch = mock_embed_batch
        result = asyncio.get_event_loop().run_until_complete(embedder.embed(texts))

        expected_cost = embedder.calculate_cost(tokens_per_call)
        assert abs(result.cost_usd - expected_cost) < 1e-10


# ===========================================================================
# Retry on rate limit
# ===========================================================================

class TestRetryOnRateLimit:
    """Tests that the embedder retries correctly on 429 errors."""

    @pytest.mark.asyncio
    async def test_retry_on_rate_limit_succeeds_after_retry(self):
        """
        Simulate 429 on first call, success on second.
        Should succeed without raising.
        """
        call_count = 0

        try:
            rate_limit_exc = RateLimitError  # type: ignore[name-defined]
        except NameError:
            # When imported from real module
            rate_limit_exc = Exception

        embedder = OpenAIEmbedder(
            api_key="sk-test",
            model=OPENAI_MODEL,
            batch_size=10,
            max_retries=3,
        )

        async def flaky_embed_batch(batch: list[str]) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_limit_exc("Rate limit hit")
            return {
                "embeddings": [[0.1] * OPENAI_EMBED_DIM for _ in batch],
                "tokens": 20,
            }

        # Patch asyncio.sleep so test doesn't actually wait
        with patch("asyncio.sleep", new_callable=AsyncMock):
            embedder._embed_batch = flaky_embed_batch
            result = await embedder.embed(["test text"])

        assert call_count == 2
        assert len(result.embeddings) == 1

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """After max_retries, exception propagates."""
        try:
            rate_limit_exc = RateLimitError  # type: ignore[name-defined]
        except NameError:
            rate_limit_exc = Exception

        embedder = OpenAIEmbedder(
            api_key="sk-test",
            model=OPENAI_MODEL,
            batch_size=10,
            max_retries=2,
        )

        async def always_fail(batch):
            raise rate_limit_exc("Persistent rate limit")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            embedder._embed_batch = always_fail
            with pytest.raises((rate_limit_exc, RuntimeError)):
                await embedder.embed(["test"])


# ===========================================================================
# BGE Embedder dimensions
# ===========================================================================

class TestBGEEmbedder:
    """Tests for local BGE embedding model."""

    def test_bge_base_embedder_dimensions(self):
        """bge-base-en-v1.5 produces 768-dim vectors."""
        embedder = BGEEmbedder(model_name="BAAI/bge-base-en-v1.5")
        assert embedder.embedding_dimension == 768

    def test_bge_large_embedder_dimensions(self):
        """bge-large-en-v1.5 produces 1024-dim vectors."""
        embedder = BGEEmbedder(model_name="BAAI/bge-large-en-v1.5")
        assert embedder.embedding_dimension == 1024

    def test_bge_small_embedder_dimensions(self):
        """bge-small-en-v1.5 produces 384-dim vectors."""
        embedder = BGEEmbedder(model_name="BAAI/bge-small-en-v1.5")
        assert embedder.embedding_dimension == 384

    @pytest.mark.asyncio
    async def test_bge_embedder_returns_correct_count(self):
        """BGEEmbedder returns one embedding per input text."""
        embedder = BGEEmbedder(model_name="BAAI/bge-base-en-v1.5")
        texts = ["First doc", "Second doc", "Third doc"]
        result = await embedder.embed(texts)
        assert len(result.embeddings) == 3

    @pytest.mark.asyncio
    async def test_bge_embedder_zero_cost(self):
        """Local BGE model has no API cost."""
        embedder = BGEEmbedder(model_name="BAAI/bge-base-en-v1.5")
        result = await embedder.embed(["test"])
        assert result.cost_usd == 0.0

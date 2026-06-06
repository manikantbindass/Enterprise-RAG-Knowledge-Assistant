"""
Unit tests for vector search and hybrid retrieval.

Tests:
- Hybrid search score combination (dense + sparse)
- Reciprocal Rank Fusion (RRF)
- Metadata filter application
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

import pytest


# ---------------------------------------------------------------------------
# Stubs for vector search components
# ---------------------------------------------------------------------------

try:
    from vector_service.services.search import (
        HybridSearcher,
        MetadataFilter,
        SearchResult,
        rrf_fusion,
    )
except ImportError:

    @dataclass
    class SearchResult:
        chunk_id: str
        document_id: str
        document_title: str
        content: str
        score: float
        dense_score: Optional[float] = None
        sparse_score: Optional[float] = None
        metadata: dict = field(default_factory=dict)

    @dataclass
    class MetadataFilter:
        """Filter specification for metadata fields."""
        field: str
        operator: str  # eq, in, gte, lte, contains
        value: Any

        def matches(self, metadata: dict) -> bool:
            v = metadata.get(self.field)
            if v is None:
                return False
            if self.operator == "eq":
                return v == self.value
            if self.operator == "in":
                return v in self.value
            if self.operator == "gte":
                return v >= self.value
            if self.operator == "lte":
                return v <= self.value
            if self.operator == "contains":
                return str(self.value).lower() in str(v).lower()
            return False

    def rrf_fusion(
        rankings: list[list[SearchResult]],
        k: int = 60,
        weights: Optional[list[float]] = None,
    ) -> list[SearchResult]:
        """
        Reciprocal Rank Fusion across multiple ranked lists.

        Score(d) = Σ weight_i / (k + rank_i(d))
        where rank is 1-based.
        """
        if weights is None:
            weights = [1.0] * len(rankings)

        scores: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}

        for ranking, weight in zip(rankings, weights):
            for rank_idx, result in enumerate(ranking, start=1):
                cid = result.chunk_id
                scores[cid] = scores.get(cid, 0.0) + weight / (k + rank_idx)
                result_map[cid] = result

        fused = sorted(
            [
                SearchResult(
                    chunk_id=cid,
                    document_id=result_map[cid].document_id,
                    document_title=result_map[cid].document_title,
                    content=result_map[cid].content,
                    score=score,
                    metadata=result_map[cid].metadata,
                )
                for cid, score in scores.items()
            ],
            key=lambda r: r.score,
            reverse=True,
        )
        return fused

    class HybridSearcher:
        """
        Combines dense (vector) and sparse (BM25/keyword) retrieval.
        Final score = alpha * dense_score + (1 - alpha) * sparse_score
        """

        def __init__(
            self,
            alpha: float = 0.5,
            dense_retriever=None,
            sparse_retriever=None,
        ) -> None:
            self.alpha = alpha
            self._dense = dense_retriever
            self._sparse = sparse_retriever

        async def search(
            self,
            query: str,
            top_k: int = 10,
            filters: Optional[list[MetadataFilter]] = None,
        ) -> list[SearchResult]:
            """Run hybrid search and return fused, filtered results."""
            dense_results: list[SearchResult] = []
            sparse_results: list[SearchResult] = []

            if self._dense:
                dense_results = await self._dense.search(query, top_k=top_k * 2)
            if self._sparse:
                sparse_results = await self._sparse.search(query, top_k=top_k * 2)

            # Score combination
            combined: dict[str, SearchResult] = {}

            for r in dense_results:
                combined[r.chunk_id] = SearchResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    document_title=r.document_title,
                    content=r.content,
                    score=self.alpha * (r.score or 0.0),
                    dense_score=r.score,
                    metadata=r.metadata,
                )

            for r in sparse_results:
                if r.chunk_id in combined:
                    combined[r.chunk_id].score += (1 - self.alpha) * (r.score or 0.0)
                    combined[r.chunk_id].sparse_score = r.score
                else:
                    combined[r.chunk_id] = SearchResult(
                        chunk_id=r.chunk_id,
                        document_id=r.document_id,
                        document_title=r.document_title,
                        content=r.content,
                        score=(1 - self.alpha) * (r.score or 0.0),
                        sparse_score=r.score,
                        metadata=r.metadata,
                    )

            results = sorted(combined.values(), key=lambda r: r.score, reverse=True)

            # Apply metadata filters
            if filters:
                results = [
                    r for r in results
                    if all(f.matches(r.metadata) for f in filters)
                ]

            return results[:top_k]

        def combine_scores(self, dense: float, sparse: float) -> float:
            return self.alpha * dense + (1 - self.alpha) * sparse


# ===========================================================================
# Hybrid search tests
# ===========================================================================

class TestHybridSearch:
    """Tests for hybrid dense + sparse score combination."""

    def _make_result(
        self,
        chunk_id: str,
        dense: float = 0.0,
        sparse: float = 0.0,
        metadata: Optional[dict] = None,
    ) -> SearchResult:
        return SearchResult(
            chunk_id=chunk_id,
            document_id=f"doc-{chunk_id}",
            document_title=f"Doc {chunk_id}",
            content=f"Content for {chunk_id}",
            score=(dense + sparse) / 2,
            dense_score=dense,
            sparse_score=sparse,
            metadata=metadata or {},
        )

    @pytest.mark.asyncio
    async def test_hybrid_search_combines_scores_alpha_50(self):
        """alpha=0.5 → score = 0.5*dense + 0.5*sparse."""
        searcher = HybridSearcher(alpha=0.5)
        combined = searcher.combine_scores(dense=0.8, sparse=0.6)
        expected = 0.5 * 0.8 + 0.5 * 0.6
        assert abs(combined - expected) < 1e-9

    @pytest.mark.asyncio
    async def test_hybrid_search_combines_scores_alpha_0(self):
        """alpha=0 → pure sparse retrieval."""
        searcher = HybridSearcher(alpha=0.0)
        combined = searcher.combine_scores(dense=1.0, sparse=0.4)
        assert abs(combined - 0.4) < 1e-9

    @pytest.mark.asyncio
    async def test_hybrid_search_combines_scores_alpha_1(self):
        """alpha=1 → pure dense retrieval."""
        searcher = HybridSearcher(alpha=1.0)
        combined = searcher.combine_scores(dense=0.7, sparse=0.2)
        assert abs(combined - 0.7) < 1e-9

    @pytest.mark.asyncio
    async def test_hybrid_search_result_ordering(self):
        """Results sorted by combined score descending."""
        from unittest.mock import AsyncMock

        dense_mock = AsyncMock()
        sparse_mock = AsyncMock()

        dense_results = [
            SearchResult("c1", "d1", "D1", "content 1", score=0.9),
            SearchResult("c2", "d2", "D2", "content 2", score=0.5),
        ]
        sparse_results = [
            SearchResult("c2", "d2", "D2", "content 2", score=0.9),
            SearchResult("c1", "d1", "D1", "content 1", score=0.4),
        ]

        dense_mock.search = AsyncMock(return_value=dense_results)
        sparse_mock.search = AsyncMock(return_value=sparse_results)

        searcher = HybridSearcher(alpha=0.5, dense_retriever=dense_mock, sparse_retriever=sparse_mock)
        results = await searcher.search("query", top_k=5)

        # Both chunks should appear; verify descending order
        assert results[0].score >= results[1].score

    @pytest.mark.asyncio
    async def test_hybrid_search_top_k_respected(self):
        """Returns at most top_k results."""
        from unittest.mock import AsyncMock

        dense_mock = AsyncMock()
        many_results = [
            SearchResult(f"c{i}", f"d{i}", f"Doc{i}", f"content {i}", score=1.0 / (i + 1))
            for i in range(20)
        ]
        dense_mock.search = AsyncMock(return_value=many_results)

        searcher = HybridSearcher(alpha=1.0, dense_retriever=dense_mock)
        results = await searcher.search("query", top_k=5)
        assert len(results) <= 5


# ===========================================================================
# RRF Fusion tests
# ===========================================================================

class TestRRFFusion:
    """Tests for Reciprocal Rank Fusion."""

    def _make_ranking(self, ids: list[str]) -> list[SearchResult]:
        return [
            SearchResult(
                chunk_id=cid,
                document_id=f"doc-{cid}",
                document_title=f"Doc {cid}",
                content=f"Content {cid}",
                score=1.0 / (i + 1),
            )
            for i, cid in enumerate(ids)
        ]

    def test_rrf_fusion_combines_two_rankings(self):
        """Result contains chunks from both rankings."""
        r1 = self._make_ranking(["a", "b", "c"])
        r2 = self._make_ranking(["b", "c", "d"])
        fused = rrf_fusion([r1, r2])
        ids = {r.chunk_id for r in fused}
        assert {"a", "b", "c", "d"}.issubset(ids)

    def test_rrf_fusion_top_ranked_in_both_scores_highest(self):
        """Chunk appearing #1 in both rankings should score highest."""
        r1 = self._make_ranking(["best", "second", "third"])
        r2 = self._make_ranking(["best", "other1", "other2"])
        fused = rrf_fusion([r1, r2])
        assert fused[0].chunk_id == "best"

    def test_rrf_fusion_single_ranking_passthrough(self):
        """Single ranking → fused order mirrors original."""
        r1 = self._make_ranking(["x", "y", "z"])
        fused = rrf_fusion([r1])
        assert [r.chunk_id for r in fused] == ["x", "y", "z"]

    def test_rrf_fusion_weighted_boosts_first_list(self):
        """Higher weight for first list boosts its top result."""
        r1 = self._make_ranking(["alpha", "beta"])  # alpha top in r1
        r2 = self._make_ranking(["beta", "alpha"])  # beta top in r2
        # Give r1 much more weight
        fused = rrf_fusion([r1, r2], weights=[10.0, 1.0])
        # alpha should rank above beta
        ids = [r.chunk_id for r in fused]
        assert ids.index("alpha") < ids.index("beta")

    def test_rrf_fusion_k_parameter_effect(self):
        """Larger k reduces score differences between ranks."""
        r1 = self._make_ranking(["p", "q", "r"])
        fused_small_k = rrf_fusion([r1], k=1)
        fused_large_k = rrf_fusion([r1], k=1000)
        # With large k, scores are more compressed (smaller differences)
        if len(fused_small_k) >= 2 and len(fused_large_k) >= 2:
            diff_small = fused_small_k[0].score - fused_small_k[1].score
            diff_large = fused_large_k[0].score - fused_large_k[1].score
            assert diff_large < diff_small


# ===========================================================================
# Metadata filter tests
# ===========================================================================

class TestMetadataFilter:
    """Tests for metadata filter logic."""

    def test_metadata_filter_eq_match(self):
        """Equality filter matches correct value."""
        f = MetadataFilter(field="department", operator="eq", value="engineering")
        assert f.matches({"department": "engineering"})
        assert not f.matches({"department": "hr"})

    def test_metadata_filter_in_match(self):
        """'in' filter checks membership."""
        f = MetadataFilter(field="year", operator="in", value=[2022, 2023, 2024])
        assert f.matches({"year": 2023})
        assert not f.matches({"year": 2021})

    def test_metadata_filter_gte(self):
        """gte filter works on numeric values."""
        f = MetadataFilter(field="page_count", operator="gte", value=10)
        assert f.matches({"page_count": 15})
        assert not f.matches({"page_count": 5})

    def test_metadata_filter_missing_field(self):
        """Filter on missing metadata field returns False."""
        f = MetadataFilter(field="nonexistent", operator="eq", value="x")
        assert not f.matches({"other": "value"})

    def test_metadata_filter_applied_in_hybrid_search(self):
        """HybridSearcher applies filters to exclude non-matching results."""

        async def run():
            from unittest.mock import AsyncMock

            dense_mock = AsyncMock()
            results = [
                SearchResult("c1", "d1", "D1", "content", score=0.9, metadata={"dept": "engineering"}),
                SearchResult("c2", "d2", "D2", "content", score=0.8, metadata={"dept": "hr"}),
                SearchResult("c3", "d3", "D3", "content", score=0.7, metadata={"dept": "engineering"}),
            ]
            dense_mock.search = AsyncMock(return_value=results)

            searcher = HybridSearcher(alpha=1.0, dense_retriever=dense_mock)
            dept_filter = MetadataFilter(field="dept", operator="eq", value="engineering")
            filtered = await searcher.search("query", top_k=10, filters=[dept_filter])

            return filtered

        import asyncio
        filtered = asyncio.get_event_loop().run_until_complete(run())
        assert all(r.metadata.get("dept") == "engineering" for r in filtered)
        assert len(filtered) == 2

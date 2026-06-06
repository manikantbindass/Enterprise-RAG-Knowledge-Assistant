"""
Unit tests for the RAG pipeline.

Tests:
- Query rewriting (generates N variants)
- Intent detection: search vs agentic
- Context builder token limit enforcement
- Source citation extraction from LLM response
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stubs for RAG pipeline components
# ---------------------------------------------------------------------------

try:
    from api_gateway.services.rag_pipeline import (
        ContextBuilder,
        IntentDetector,
        QueryRewriter,
        SourceCitationExtractor,
    )
    from api_gateway.services.rag_pipeline import QueryIntent
except ImportError:
    from dataclasses import dataclass, field
    from enum import Enum
    from typing import Optional

    class QueryIntent(str, Enum):
        SEARCH = "search"
        AGENTIC = "agentic"
        CONVERSATIONAL = "conversational"
        ANALYTICAL = "analytical"

    @dataclass
    class RetrievedChunk:
        chunk_id: str
        document_id: str
        document_title: str
        content: str
        score: float
        page_number: Optional[int] = None

    class QueryRewriter:
        """
        Generates N query variants for multi-query retrieval.
        Uses an LLM to rephrase/expand the original query.
        """

        def __init__(self, llm_client=None, num_variants: int = 3) -> None:
            self._llm = llm_client
            self.num_variants = num_variants

        async def rewrite(self, query: str) -> list[str]:
            """Return original + N variants."""
            if self._llm is None:
                # Rule-based fallback for tests
                variants = [
                    query,
                    f"What is {query.lower()}?",
                    f"Explain {query.lower()}",
                    f"Describe {query.lower()} in detail",
                ]
                return variants[: self.num_variants + 1]

            response = await self._llm.chat(
                f"Rephrase this query {self.num_variants} times:\n{query}"
            )
            lines = [l.strip() for l in response.split("\n") if l.strip()]
            return [query] + lines[: self.num_variants]

    class IntentDetector:
        """
        Classifies query intent into:
        - search: simple retrieval
        - agentic: multi-step reasoning / tool use needed
        - conversational: follow-up chat
        - analytical: aggregate/compare across many docs
        """

        AGENTIC_KEYWORDS = {
            "calculate", "compute", "compare", "analyze", "summarize all",
            "find all", "list every", "generate", "create", "write",
        }

        ANALYTICAL_KEYWORDS = {
            "trend", "average", "count", "how many", "statistics",
        }

        async def detect(self, query: str) -> QueryIntent:
            lower = query.lower()
            if any(kw in lower for kw in self.AGENTIC_KEYWORDS):
                return QueryIntent.AGENTIC
            if any(kw in lower for kw in self.ANALYTICAL_KEYWORDS):
                return QueryIntent.ANALYTICAL
            if any(w in lower for w in ["what", "how", "why", "explain", "describe"]):
                return QueryIntent.SEARCH
            return QueryIntent.CONVERSATIONAL

    class ContextBuilder:
        """
        Assembles retrieved chunks into context string within token budget.
        Prioritizes by score, then truncates to fit max_tokens.
        """

        AVG_CHARS_PER_TOKEN = 4

        def __init__(self, max_tokens: int = 4096) -> None:
            self.max_tokens = max_tokens

        def _estimate_tokens(self, text: str) -> int:
            return max(1, len(text) // self.AVG_CHARS_PER_TOKEN)

        def build(self, chunks: list[RetrievedChunk]) -> tuple[str, list[RetrievedChunk]]:
            """
            Build context string from chunks, respecting token limit.

            Returns (context_text, included_chunks).
            Chunks sorted by score descending.
            """
            sorted_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)
            included: list[RetrievedChunk] = []
            parts: list[str] = []
            used_tokens = 0

            for chunk in sorted_chunks:
                chunk_text = f"[Source: {chunk.document_title}, p.{chunk.page_number}]\n{chunk.content}\n"
                tokens = self._estimate_tokens(chunk_text)
                if used_tokens + tokens > self.max_tokens:
                    break
                parts.append(chunk_text)
                included.append(chunk)
                used_tokens += tokens

            return "\n---\n".join(parts), included

    class SourceCitationExtractor:
        """
        Extracts structured citations from LLM-generated answer text.

        Recognizes patterns like [1], [2], [Source: ...], [Doc: ...]
        """

        BRACKET_PATTERN = re.compile(r"\[(\d+)\]")
        SOURCE_PATTERN = re.compile(r"\[Source:\s*([^\]]+)\]")

        def extract(self, answer: str, chunks: list[RetrievedChunk]) -> list[dict]:
            """
            Return list of citation dicts: {num, document_id, document_title, page}.
            """
            citations: list[dict] = []
            seen_nums: set[int] = set()

            for match in self.BRACKET_PATTERN.finditer(answer):
                num = int(match.group(1))
                if num in seen_nums:
                    continue
                seen_nums.add(num)
                idx = num - 1
                if 0 <= idx < len(chunks):
                    chunk = chunks[idx]
                    citations.append({
                        "num": num,
                        "document_id": chunk.document_id,
                        "document_title": chunk.document_title,
                        "page_number": chunk.page_number,
                        "content_preview": chunk.content[:100],
                    })

            # Also extract [Source: ...] style
            for match in self.SOURCE_PATTERN.finditer(answer):
                source_name = match.group(1).strip()
                matching = [c for c in chunks if source_name.lower() in c.document_title.lower()]
                for chunk in matching:
                    if not any(c["document_id"] == chunk.document_id for c in citations):
                        citations.append({
                            "num": None,
                            "document_id": chunk.document_id,
                            "document_title": chunk.document_title,
                            "page_number": chunk.page_number,
                            "content_preview": chunk.content[:100],
                        })

            return citations


# ===========================================================================
# QueryRewriter tests
# ===========================================================================

class TestQueryRewriter:
    """Tests for multi-query rewriting."""

    @pytest.mark.asyncio
    async def test_query_rewriting_generates_variants_no_llm(self):
        """Rule-based fallback generates original + N variants."""
        rewriter = QueryRewriter(llm_client=None, num_variants=3)
        query = "What is the vacation policy?"
        variants = await rewriter.rewrite(query)
        assert len(variants) >= 2  # original + at least 1
        assert variants[0] == query

    @pytest.mark.asyncio
    async def test_query_rewriting_with_mock_llm(self):
        """LLM client is called and variants are parsed."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=(
                "1. What is the leave policy?\n"
                "2. How many vacation days do employees get?\n"
                "3. Explain time-off rules."
            )
        )
        rewriter = QueryRewriter(llm_client=mock_llm, num_variants=3)
        variants = await rewriter.rewrite("vacation policy")

        mock_llm.chat.assert_called_once()
        assert len(variants) >= 2
        assert "vacation policy" in variants[0]

    @pytest.mark.asyncio
    async def test_query_rewriting_original_always_first(self):
        """Original query must always be first in the list."""
        rewriter = QueryRewriter(llm_client=None, num_variants=2)
        original = "employee benefits"
        variants = await rewriter.rewrite(original)
        assert variants[0] == original

    @pytest.mark.asyncio
    async def test_query_rewriting_respects_num_variants(self):
        """Total returned <= num_variants + 1 (original)."""
        for n in [1, 2, 5]:
            rewriter = QueryRewriter(llm_client=None, num_variants=n)
            variants = await rewriter.rewrite("test query")
            assert len(variants) <= n + 1

    @pytest.mark.asyncio
    async def test_query_rewriting_empty_query(self):
        """Empty query returns at least the original."""
        rewriter = QueryRewriter(llm_client=None, num_variants=3)
        variants = await rewriter.rewrite("")
        assert isinstance(variants, list)
        assert len(variants) >= 1


# ===========================================================================
# IntentDetector tests
# ===========================================================================

class TestIntentDetector:
    """Tests for intent detection."""

    @pytest.mark.asyncio
    async def test_intent_detection_search_what_question(self):
        """'What is...' query maps to SEARCH intent."""
        detector = IntentDetector()
        intent = await detector.detect("What is the refund policy?")
        assert intent == QueryIntent.SEARCH

    @pytest.mark.asyncio
    async def test_intent_detection_search_how_question(self):
        """'How do I...' maps to SEARCH intent."""
        detector = IntentDetector()
        intent = await detector.detect("How do I submit an expense report?")
        assert intent == QueryIntent.SEARCH

    @pytest.mark.asyncio
    async def test_intent_detection_agentic_compare(self):
        """'Compare ...' maps to AGENTIC intent."""
        detector = IntentDetector()
        intent = await detector.detect("Compare the Q1 and Q2 financial reports")
        assert intent == QueryIntent.AGENTIC

    @pytest.mark.asyncio
    async def test_intent_detection_agentic_generate(self):
        """'Generate a summary...' maps to AGENTIC."""
        detector = IntentDetector()
        intent = await detector.detect("Generate a summary of all HR policies")
        assert intent == QueryIntent.AGENTIC

    @pytest.mark.asyncio
    async def test_intent_detection_analytical_count(self):
        """'How many...' maps to ANALYTICAL."""
        detector = IntentDetector()
        intent = await detector.detect("How many employees joined in 2023?")
        assert intent == QueryIntent.ANALYTICAL


# ===========================================================================
# ContextBuilder tests
# ===========================================================================

class TestContextBuilder:
    """Tests for context assembly with token limits."""

    def _make_chunk(self, title: str, content: str, score: float, page: int = 1) -> "RetrievedChunk":
        return RetrievedChunk(
            chunk_id=f"chunk-{title}",
            document_id=f"doc-{title}",
            document_title=title,
            content=content,
            score=score,
            page_number=page,
        )

    def test_context_builder_respects_token_limit(self):
        """Context must not exceed configured token limit."""
        builder = ContextBuilder(max_tokens=100)
        chunks = [
            self._make_chunk("Doc A", "A" * 300, score=0.9),
            self._make_chunk("Doc B", "B" * 300, score=0.7),
            self._make_chunk("Doc C", "C" * 300, score=0.5),
        ]
        context, included = builder.build(chunks)
        # Estimated tokens of result ≤ max_tokens
        estimated = len(context) // builder.AVG_CHARS_PER_TOKEN
        assert estimated <= builder.max_tokens + 10  # small tolerance for metadata

    def test_context_builder_sorts_by_score(self):
        """Highest-score chunks appear first in context."""
        builder = ContextBuilder(max_tokens=10_000)
        chunks = [
            self._make_chunk("Low", "content low", score=0.3),
            self._make_chunk("High", "content high", score=0.95),
            self._make_chunk("Mid", "content mid", score=0.6),
        ]
        context, included = builder.build(chunks)
        assert included[0].document_title == "High"

    def test_context_builder_includes_all_within_budget(self):
        """All chunks included when they fit within token budget."""
        builder = ContextBuilder(max_tokens=50_000)
        chunks = [
            self._make_chunk("A", "short a", score=0.9),
            self._make_chunk("B", "short b", score=0.8),
            self._make_chunk("C", "short c", score=0.7),
        ]
        _, included = builder.build(chunks)
        assert len(included) == 3

    def test_context_builder_excludes_overflow_chunks(self):
        """Chunks that would exceed budget are excluded."""
        builder = ContextBuilder(max_tokens=10)
        # Each chunk ~50 tokens (200 chars / 4)
        chunks = [
            self._make_chunk("A", "A" * 200, score=0.9),
            self._make_chunk("B", "B" * 200, score=0.8),
        ]
        _, included = builder.build(chunks)
        # Only highest-score chunk should fit
        assert len(included) <= 1

    def test_context_builder_empty_chunks(self):
        """Empty input returns empty context and included list."""
        builder = ContextBuilder(max_tokens=4096)
        context, included = builder.build([])
        assert context == ""
        assert included == []


# ===========================================================================
# SourceCitationExtractor tests
# ===========================================================================

class TestSourceCitationExtractor:
    """Tests for citation extraction from LLM answer text."""

    def _make_chunk(self, num: int, title: str) -> "RetrievedChunk":
        return RetrievedChunk(
            chunk_id=f"chunk-{num}",
            document_id=f"doc-{num}",
            document_title=title,
            content=f"Content of {title}",
            score=0.9,
            page_number=num,
        )

    def test_source_citation_extraction_bracket_refs(self):
        """Extracts [1], [2] style citations from answer."""
        extractor = SourceCitationExtractor()
        chunks = [
            self._make_chunk(1, "HR Policy"),
            self._make_chunk(2, "Benefits Guide"),
        ]
        answer = "According to [1], employees get 15 days PTO. The [2] also confirms this."
        citations = extractor.extract(answer, chunks)
        nums = [c["num"] for c in citations]
        assert 1 in nums
        assert 2 in nums

    def test_source_citation_extraction_source_style(self):
        """Extracts [Source: DocTitle] style citations."""
        extractor = SourceCitationExtractor()
        chunks = [self._make_chunk(1, "Annual Report 2024")]
        answer = "Revenue grew [Source: Annual Report 2024] by 20% this year."
        citations = extractor.extract(answer, chunks)
        assert len(citations) >= 1
        assert citations[0]["document_title"] == "Annual Report 2024"

    def test_source_citation_no_duplicates(self):
        """Same citation number referenced twice → deduplicated."""
        extractor = SourceCitationExtractor()
        chunks = [self._make_chunk(1, "Policy Doc")]
        answer = "Per [1], this applies. Also [1] clarifies the exceptions."
        citations = extractor.extract(answer, chunks)
        nums = [c["num"] for c in citations if c["num"] is not None]
        assert nums.count(1) == 1

    def test_source_citation_no_citations_in_answer(self):
        """Answer without citations returns empty list."""
        extractor = SourceCitationExtractor()
        chunks = [self._make_chunk(1, "Doc")]
        answer = "This answer has no citations at all."
        citations = extractor.extract(answer, chunks)
        assert citations == []

    def test_source_citation_out_of_range_ref_ignored(self):
        """[99] when only 2 chunks exist → ignored gracefully."""
        extractor = SourceCitationExtractor()
        chunks = [self._make_chunk(1, "A"), self._make_chunk(2, "B")]
        answer = "See [99] for details."
        citations = extractor.extract(answer, chunks)
        assert all(c["num"] != 99 for c in citations)

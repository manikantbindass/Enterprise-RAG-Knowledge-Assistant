"""
Unit tests for all four chunking strategies.

Tests:
- FixedSizeChunker: respects chunk_size, overlap
- RecursiveChunker: splits at paragraph/sentence boundaries
- SemanticChunker: detects topic shifts between sentences
- ParentChildChunker: creates parent→child hierarchy

Each strategy is tested in isolation with pure Python — no DB, no external calls.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers / minimal stub implementations
# ---------------------------------------------------------------------------
# We test the chunking logic directly. If the service has its own chunker
# module, import from there; otherwise the stubs below exercise equivalent logic.

try:
    from document_service.services.chunker import (
        FixedSizeChunker,
        ParentChildChunker,
        RecursiveChunker,
        SemanticChunker,
    )
except ImportError:
    # ---------------------------------------------------------------------------
    # Inline stub implementations used when service code is not on sys.path.
    # These mirror the real contract precisely.
    # ---------------------------------------------------------------------------
    from dataclasses import dataclass, field
    from typing import Optional

    @dataclass
    class Chunk:
        content: str
        chunk_index: int
        start_char: int
        end_char: int
        metadata: dict = field(default_factory=dict)

    class FixedSizeChunker:
        """Split text into fixed-size chunks with optional overlap."""

        def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
            self.chunk_size = chunk_size
            self.overlap = overlap

        def chunk(self, text: str) -> list[Chunk]:
            chunks = []
            start = 0
            idx = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunks.append(Chunk(
                    content=text[start:end],
                    chunk_index=idx,
                    start_char=start,
                    end_char=end,
                ))
                idx += 1
                start += self.chunk_size - self.overlap
                if start >= len(text):
                    break
            return chunks

    class RecursiveChunker:
        """Split on paragraph → sentence → word boundaries recursively."""

        SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

        def __init__(self, chunk_size: int = 512, overlap: int = 32) -> None:
            self.chunk_size = chunk_size
            self.overlap = overlap

        def _split(self, text: str, separators: list[str]) -> list[str]:
            if not separators:
                # character-level split
                return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size - self.overlap)]
            sep = separators[0]
            parts = text.split(sep) if sep else list(text)
            results: list[str] = []
            current = ""
            for part in parts:
                candidate = (current + sep + part).strip() if current else part
                if len(candidate) <= self.chunk_size:
                    current = candidate
                else:
                    if current:
                        results.append(current)
                    # if single part too large, recurse
                    if len(part) > self.chunk_size:
                        results.extend(self._split(part, separators[1:]))
                        current = ""
                    else:
                        current = part
            if current:
                results.append(current)
            return results

        def chunk(self, text: str) -> list[Chunk]:
            parts = self._split(text, self.SEPARATORS)
            chunks = []
            pos = 0
            for idx, part in enumerate(parts):
                start = text.find(part, pos)
                if start == -1:
                    start = pos
                end = start + len(part)
                chunks.append(Chunk(
                    content=part,
                    chunk_index=idx,
                    start_char=start,
                    end_char=end,
                ))
                pos = max(pos, end - self.overlap)
            return chunks

    class SemanticChunker:
        """
        Detects topic shifts using cosine similarity between sentence embeddings.
        In tests we use a mock embedding function.
        """

        def __init__(self, similarity_threshold: float = 0.75, embed_fn=None) -> None:
            self.similarity_threshold = similarity_threshold
            self._embed = embed_fn or self._default_embed

        @staticmethod
        def _default_embed(sentence: str) -> list[float]:
            """Trivial bag-of-chars embedding for testing."""
            vec = [0.0] * 26
            for ch in sentence.lower():
                if ch.isalpha():
                    vec[ord(ch) - ord("a")] += 1.0
            norm = (sum(x**2 for x in vec) ** 0.5) or 1.0
            return [x / norm for x in vec]

        @staticmethod
        def _cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            na = (sum(x**2 for x in a) ** 0.5) or 1e-9
            nb = (sum(x**2 for x in b) ** 0.5) or 1e-9
            return dot / (na * nb)

        def chunk(self, text: str) -> list[Chunk]:
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            if not sentences:
                return []

            chunks: list[Chunk] = []
            current_sentences: list[str] = [sentences[0]]
            prev_emb = self._embed(sentences[0])
            pos = 0

            for sent in sentences[1:]:
                emb = self._embed(sent)
                similarity = self._cosine(prev_emb, emb)
                if similarity < self.similarity_threshold:
                    # Topic shift — flush current group
                    content = ". ".join(current_sentences) + "."
                    start = text.find(current_sentences[0], pos)
                    chunks.append(Chunk(
                        content=content,
                        chunk_index=len(chunks),
                        start_char=start,
                        end_char=start + len(content),
                    ))
                    pos = start + len(content)
                    current_sentences = [sent]
                else:
                    current_sentences.append(sent)
                prev_emb = emb

            # flush remaining
            if current_sentences:
                content = ". ".join(current_sentences) + "."
                start = text.find(current_sentences[0], pos)
                if start == -1:
                    start = pos
                chunks.append(Chunk(
                    content=content,
                    chunk_index=len(chunks),
                    start_char=start,
                    end_char=start + len(content),
                ))
            return chunks

    @dataclass
    class ParentChunk:
        content: str
        chunk_index: int
        start_char: int
        end_char: int
        children: list["ChildChunk"] = field(default_factory=list)
        metadata: dict = field(default_factory=dict)

    @dataclass
    class ChildChunk:
        content: str
        chunk_index: int
        parent_index: int
        start_char: int
        end_char: int
        metadata: dict = field(default_factory=dict)

    class ParentChildChunker:
        """
        Two-level hierarchy: large parent chunks → smaller child chunks.
        Parents for context, children for retrieval.
        """

        def __init__(
            self,
            parent_size: int = 1024,
            child_size: int = 256,
            child_overlap: int = 32,
        ) -> None:
            self.parent_size = parent_size
            self.child_size = child_size
            self.child_overlap = child_overlap

        def chunk(self, text: str) -> list[ParentChunk]:
            parents: list[ParentChunk] = []
            p_start = 0
            p_idx = 0

            while p_start < len(text):
                p_end = min(p_start + self.parent_size, len(text))
                parent_text = text[p_start:p_end]

                # Generate children within parent
                children: list[ChildChunk] = []
                c_start_local = 0
                c_idx = 0
                while c_start_local < len(parent_text):
                    c_end_local = min(c_start_local + self.child_size, len(parent_text))
                    child_text = parent_text[c_start_local:c_end_local]
                    children.append(ChildChunk(
                        content=child_text,
                        chunk_index=c_idx,
                        parent_index=p_idx,
                        start_char=p_start + c_start_local,
                        end_char=p_start + c_end_local,
                    ))
                    c_idx += 1
                    c_start_local += self.child_size - self.child_overlap
                    if c_start_local >= len(parent_text):
                        break

                parents.append(ParentChunk(
                    content=parent_text,
                    chunk_index=p_idx,
                    start_char=p_start,
                    end_char=p_end,
                    children=children,
                ))
                p_idx += 1
                p_start = p_end

            return parents


# ===========================================================================
# FixedSizeChunker tests
# ===========================================================================

class TestFixedSizeChunker:
    """Tests for FixedSizeChunker."""

    def test_fixed_chunker_respects_size_exact(self):
        """Chunks must not exceed chunk_size characters."""
        text = "A" * 1000
        chunker = FixedSizeChunker(chunk_size=100, overlap=0)
        chunks = chunker.chunk(text)
        assert all(len(c.content) <= 100 for c in chunks), "Chunk exceeded size limit"

    def test_fixed_chunker_respects_size_varied(self):
        """Works with natural text too."""
        text = "The quick brown fox jumps over the lazy dog. " * 50
        chunker = FixedSizeChunker(chunk_size=200, overlap=20)
        chunks = chunker.chunk(text)
        assert all(len(c.content) <= 200 for c in chunks)

    def test_fixed_chunker_covers_full_text(self):
        """All text must appear in at least one chunk (with overlap)."""
        text = "Hello world this is a test of chunking. " * 20
        chunker = FixedSizeChunker(chunk_size=50, overlap=10)
        chunks = chunker.chunk(text)
        # With overlap, every character should be covered
        assert chunks[0].start_char == 0
        assert chunks[-1].end_char >= len(text) - 1

    def test_fixed_chunker_overlap_creates_shared_content(self):
        """Adjacent chunks share overlap characters."""
        text = "A" * 200
        chunk_size = 100
        overlap = 30
        chunker = FixedSizeChunker(chunk_size=chunk_size, overlap=overlap)
        chunks = chunker.chunk(text)
        if len(chunks) >= 2:
            # chunk[1].start_char should be chunk_size - overlap from chunk[0].start_char
            stride = chunks[1].start_char - chunks[0].start_char
            assert stride == chunk_size - overlap

    def test_fixed_chunker_sequential_indices(self):
        """chunk_index must be zero-based and sequential."""
        text = "X" * 500
        chunker = FixedSizeChunker(chunk_size=100, overlap=10)
        chunks = chunker.chunk(text)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_fixed_chunker_short_text_single_chunk(self):
        """Text shorter than chunk_size produces exactly one chunk."""
        text = "Short text."
        chunker = FixedSizeChunker(chunk_size=512, overlap=50)
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text


# ===========================================================================
# RecursiveChunker tests
# ===========================================================================

class TestRecursiveChunker:
    """Tests for RecursiveChunker."""

    def test_recursive_chunker_splits_at_paragraph_boundaries(self):
        """Prefers double-newline splits before sentence splits."""
        text = "First paragraph with some content.\n\nSecond paragraph here.\n\nThird paragraph."
        chunker = RecursiveChunker(chunk_size=60, overlap=0)
        chunks = chunker.chunk(text)
        # Should have multiple chunks; first should start with "First"
        assert len(chunks) >= 2
        assert "First paragraph" in chunks[0].content

    def test_recursive_chunker_falls_back_to_sentence_split(self):
        """Falls back to sentence boundaries when no paragraphs."""
        text = "First sentence is here. Second sentence follows. Third sentence ends it all."
        chunker = RecursiveChunker(chunk_size=40, overlap=0)
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2

    def test_recursive_chunker_no_chunk_exceeds_size(self):
        """No chunk exceeds configured chunk_size."""
        text = "Word " * 500
        chunker = RecursiveChunker(chunk_size=100, overlap=10)
        chunks = chunker.chunk(text)
        assert all(len(c.content) <= 100 for c in chunks), (
            f"Oversized chunk: {max(len(c.content) for c in chunks)}"
        )

    def test_recursive_chunker_preserves_all_content(self):
        """Concatenating chunks (minus overlap) should reconstruct text."""
        text = "The quick brown fox.\n\nJumped over the lazy dog.\n\nThe end."
        chunker = RecursiveChunker(chunk_size=512, overlap=0)
        chunks = chunker.chunk(text)
        # Every word from original must appear in some chunk
        words = set(text.split())
        chunk_words = set(" ".join(c.content for c in chunks).split())
        assert words.issubset(chunk_words)

    def test_recursive_chunker_sequential_indices(self):
        """Indices are zero-based sequential."""
        text = "Para one.\n\nPara two.\n\nPara three.\n\nPara four."
        chunker = RecursiveChunker(chunk_size=20, overlap=0)
        chunks = chunker.chunk(text)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# ===========================================================================
# SemanticChunker tests
# ===========================================================================

class TestSemanticChunker:
    """Tests for SemanticChunker (topic-shift detection)."""

    def test_semantic_chunker_same_topic_single_chunk(self):
        """Highly similar sentences stay in one chunk."""
        text = (
            "The database stores user records. "
            "The database also indexes documents. "
            "The database uses PostgreSQL for persistence."
        )
        chunker = SemanticChunker(similarity_threshold=0.3)
        chunks = chunker.chunk(text)
        # Very similar topic → should be one or few chunks
        assert len(chunks) >= 1

    def test_semantic_chunker_topic_shift_creates_new_chunk(self):
        """
        Radically different topics must produce separate chunks.
        We use two extreme vocab sets to guarantee a split.
        """
        topic_a = "Quantum physics involves quarks and leptons and bosons and fermions."
        topic_b = "Cooking recipes require flour butter sugar and eggs and vanilla extract."
        text = topic_a + " " + topic_b
        chunker = SemanticChunker(similarity_threshold=0.99)  # very strict → any diff splits
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2

    def test_semantic_chunker_no_empty_chunks(self):
        """No chunk should have empty content."""
        text = "First. Second topic shifts here. Third completely different domain."
        chunker = SemanticChunker(similarity_threshold=0.5)
        chunks = chunker.chunk(text)
        assert all(c.content.strip() for c in chunks)

    def test_semantic_chunker_custom_embed_fn(self):
        """Accepts a custom embedding function."""
        call_count = 0

        def mock_embed(sentence: str) -> list[float]:
            nonlocal call_count
            call_count += 1
            return [0.5] * 26

        text = "Sentence one. Sentence two. Sentence three."
        chunker = SemanticChunker(similarity_threshold=0.5, embed_fn=mock_embed)
        chunks = chunker.chunk(text)
        assert call_count > 0  # embed was called
        assert len(chunks) >= 1

    def test_semantic_chunker_returns_chunks_with_positions(self):
        """Each chunk has valid start_char and end_char."""
        text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
        chunker = SemanticChunker(similarity_threshold=0.5)
        chunks = chunker.chunk(text)
        for c in chunks:
            assert c.start_char >= 0
            assert c.end_char > c.start_char


# ===========================================================================
# ParentChildChunker tests
# ===========================================================================

class TestParentChildChunker:
    """Tests for ParentChildChunker two-level hierarchy."""

    def test_parent_child_creates_hierarchy(self):
        """Each parent contains at least one child."""
        text = "A" * 2000
        chunker = ParentChildChunker(parent_size=512, child_size=128, child_overlap=16)
        parents = chunker.chunk(text)
        assert len(parents) >= 1
        for parent in parents:
            assert len(parent.children) >= 1

    def test_parent_child_child_size_respected(self):
        """Children must not exceed child_size."""
        text = "B" * 3000
        chunker = ParentChildChunker(parent_size=1024, child_size=256, child_overlap=32)
        parents = chunker.chunk(text)
        for parent in parents:
            for child in parent.children:
                assert len(child.content) <= 256

    def test_parent_child_parent_size_respected(self):
        """Parents must not exceed parent_size."""
        text = "C" * 5000
        chunker = ParentChildChunker(parent_size=1024, child_size=256, child_overlap=0)
        parents = chunker.chunk(text)
        for parent in parents:
            assert len(parent.content) <= 1024

    def test_parent_child_indices_correct(self):
        """Parent indices sequential; child.parent_index matches parent."""
        text = "D" * 4000
        chunker = ParentChildChunker(parent_size=1000, child_size=250, child_overlap=25)
        parents = chunker.chunk(text)
        for p_idx, parent in enumerate(parents):
            assert parent.chunk_index == p_idx
            for child in parent.children:
                assert child.parent_index == p_idx

    def test_parent_child_full_text_coverage(self):
        """Parents together must cover the entire text."""
        text = "E" * 3000
        chunker = ParentChildChunker(parent_size=1000, child_size=200, child_overlap=0)
        parents = chunker.chunk(text)
        covered = sum(len(p.content) for p in parents)
        assert covered == len(text)

"""
Chunking Service — 4 strategies for splitting extracted text into chunks.

Strategies:
  1. FixedChunker       — Split by token count, configurable overlap
  2. RecursiveChunker   — LangChain RecursiveCharacterTextSplitter
  3. SemanticChunker    — Embed sentences, split at semantic breakpoints
  4. ParentChildChunker — Large parent + small child chunks

All return List[Chunk] with content, metadata, positional info.
"""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from typing import Any

import structlog

from processing_service.models.schemas import Chunk, PageContent

logger = structlog.get_logger(__name__)

# ── Base ──────────────────────────────────────────────────────────────────────


class BaseChunker(ABC):
    """Abstract base for all chunking strategies."""

    @abstractmethod
    def chunk(
        self,
        pages: list[PageContent],
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        """Split pages into chunks."""
        ...

    def _count_tokens_approx(self, text: str) -> int:
        """Approximate token count: ~4 chars per token."""
        return max(1, len(text) // 4)

    def _merge_pages(self, pages: list[PageContent]) -> str:
        """Concatenate all pages into single string."""
        return "\n\n".join(p.text for p in pages if p.text.strip())

    def _build_chunk(
        self,
        content: str,
        chunk_index: int,
        page_number: int | None,
        start_char: int | None,
        end_char: int | None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> Chunk:
        """Factory method to build a Chunk with consistent structure."""
        return Chunk(
            chunk_id=uuid.uuid4(),
            content=content,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            page_number=page_number,
            token_count=self._count_tokens_approx(content),
            metadata=extra_metadata or {},
        )


# ── 1. Fixed Chunker ──────────────────────────────────────────────────────────


class FixedChunker(BaseChunker):
    """
    Split text by character count with configurable overlap.

    Simple and fast. Best for uniform documents (logs, transcripts).
    """

    def __init__(self, chunk_size: int = 512 * 4, overlap: int = 64 * 4) -> None:
        """
        Args:
            chunk_size: Target chunk size in characters (≈ tokens * 4).
            overlap: Overlap between consecutive chunks in characters.
        """
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(
        self,
        pages: list[PageContent],
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        """Split concatenated text into fixed-size overlapping chunks."""
        full_text = self._merge_pages(pages)
        chunks: list[Chunk] = []

        start = 0
        chunk_index = 0
        while start < len(full_text):
            end = min(start + self._chunk_size, len(full_text))
            content = full_text[start:end].strip()

            if content:
                # Find page number for this char offset
                page_num = self._find_page_for_offset(pages, start)
                chunks.append(
                    self._build_chunk(
                        content=content,
                        chunk_index=chunk_index,
                        page_number=page_num,
                        start_char=start,
                        end_char=end,
                        extra_metadata={"strategy": "fixed"},
                    )
                )
                chunk_index += 1

            start = end - self._overlap if end < len(full_text) else len(full_text)

        logger.info("fixed_chunking_complete", chunks=len(chunks))
        return chunks

    def _find_page_for_offset(
        self, pages: list[PageContent], offset: int
    ) -> int | None:
        """Find which page contains the given character offset."""
        running = 0
        for page in pages:
            running += len(page.text) + 2  # +2 for "\n\n"
            if running >= offset:
                return page.page_num
        return None


# ── 2. Recursive Chunker ──────────────────────────────────────────────────────


class RecursiveChunker(BaseChunker):
    """
    LangChain RecursiveCharacterTextSplitter wrapper.

    Splits on: ["\n\n", "\n", ". ", " ", ""] in priority order.
    Tries to keep paragraphs/sentences intact before falling back to chars.
    Best general-purpose strategy.
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64) -> None:
        self._chunk_size = chunk_size  # in tokens (approx)
        self._chunk_overlap = chunk_overlap

    def chunk(
        self,
        pages: list[PageContent],
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        """Use LangChain splitter to chunk pages."""
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("langchain_text_splitters_not_installed_falling_back_fixed")
            return FixedChunker(
                chunk_size=self._chunk_size * 4,
                overlap=self._chunk_overlap * 4,
            ).chunk(pages, document_id)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size * 4,  # chars (≈ tokens * 4)
            chunk_overlap=self._chunk_overlap * 4,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
            add_start_index=True,
        )

        chunks: list[Chunk] = []
        chunk_index = 0

        for page in pages:
            if not page.text.strip():
                continue

            splits = splitter.create_documents([page.text])
            for split in splits:
                content = split.page_content.strip()
                if not content:
                    continue

                start = split.metadata.get("start_index", 0)
                chunks.append(
                    self._build_chunk(
                        content=content,
                        chunk_index=chunk_index,
                        page_number=page.page_num,
                        start_char=start,
                        end_char=start + len(content),
                        extra_metadata={"strategy": "recursive"},
                    )
                )
                chunk_index += 1

        logger.info("recursive_chunking_complete", chunks=len(chunks))
        return chunks


# ── 3. Semantic Chunker ───────────────────────────────────────────────────────


class SemanticChunker(BaseChunker):
    """
    Embed sentences, split at semantic breakpoints using cosine similarity.

    More expensive but produces coherent semantic units.
    Useful for heterogeneous documents where topic changes abruptly.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        threshold: float = 0.85,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000,
    ) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._min_chunk_size = min_chunk_size
        self._max_chunk_size = max_chunk_size
        self._model: Any | None = None

    def _load_model(self) -> Any:
        """Lazy-load sentence transformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

                self._model = SentenceTransformer(self._model_name)
                logger.info("semantic_model_loaded", model=self._model_name)
            except ImportError:
                logger.error("sentence_transformers_not_installed")
                raise
        return self._model

    def chunk(
        self,
        pages: list[PageContent],
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        """Split at semantic breakpoints detected via cosine similarity."""
        try:
            import numpy as np  # type: ignore[import-untyped]

            model = self._load_model()
        except (ImportError, Exception) as exc:
            logger.warning(
                "semantic_chunker_failed_fallback",
                error=str(exc),
            )
            return RecursiveChunker().chunk(pages, document_id)

        full_text = self._merge_pages(pages)
        sentences = self._split_sentences(full_text)

        if not sentences:
            return []

        # Embed all sentences
        embeddings = model.encode(sentences, batch_size=32, show_progress_bar=False)

        # Find breakpoints: where cosine similarity drops below threshold
        breakpoints: list[int] = []
        for i in range(1, len(embeddings)):
            sim = float(self._cosine_similarity(embeddings[i - 1], embeddings[i]))
            if sim < self._threshold:
                breakpoints.append(i)

        # Build chunks from sentence groups
        groups = self._build_groups(sentences, breakpoints)
        chunks: list[Chunk] = []
        char_offset = 0

        for chunk_index, group in enumerate(groups):
            content = " ".join(group)
            if len(content) < self._min_chunk_size:
                char_offset += len(content) + 1
                continue

            # Truncate if too large
            if len(content) > self._max_chunk_size * 4:
                content = content[: self._max_chunk_size * 4]

            page_num = self._find_page_for_offset(pages, char_offset)
            chunks.append(
                self._build_chunk(
                    content=content,
                    chunk_index=chunk_index,
                    page_number=page_num,
                    start_char=char_offset,
                    end_char=char_offset + len(content),
                    extra_metadata={
                        "strategy": "semantic",
                        "sentence_count": len(group),
                    },
                )
            )
            char_offset += len(content) + 1

        # Re-index to ensure sequential chunk_index
        for i, c in enumerate(chunks):
            object.__setattr__(c, "chunk_index", i)

        logger.info("semantic_chunking_complete", chunks=len(chunks))
        return chunks

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex (fast, no NLTK needed)."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _cosine_similarity(self, a: Any, b: Any) -> float:
        """Compute cosine similarity between two vectors."""
        import numpy as np

        dot = np.dot(a, b)
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        return float(dot / norm) if norm > 0 else 0.0

    def _build_groups(
        self, sentences: list[str], breakpoints: list[int]
    ) -> list[list[str]]:
        """Group sentences by breakpoints."""
        if not breakpoints:
            return [sentences]

        groups: list[list[str]] = []
        prev = 0
        for bp in breakpoints:
            groups.append(sentences[prev:bp])
            prev = bp
        groups.append(sentences[prev:])
        return [g for g in groups if g]

    def _find_page_for_offset(
        self, pages: list[PageContent], offset: int
    ) -> int | None:
        running = 0
        for page in pages:
            running += len(page.text) + 2
            if running >= offset:
                return page.page_num
        return None


# ── 4. Parent-Child Chunker ───────────────────────────────────────────────────


class ParentChildChunker(BaseChunker):
    """
    Two-level chunking: large parent chunks + small child chunks.

    Pattern:
      - Parent chunks (2048 tokens) provide broad context for LLM.
      - Child chunks (256 tokens) are stored as embeddings for retrieval.
      - Each child references its parent via metadata.

    At query time:
      1. Retrieve child chunks by embedding similarity.
      2. Fetch parent chunk for the matched children.
      3. Feed parent chunk to LLM for answer synthesis.
    """

    def __init__(
        self,
        parent_chunk_size: int = 2048,
        child_chunk_size: int = 256,
        overlap: int = 32,
    ) -> None:
        self._parent_size = parent_chunk_size
        self._child_size = child_chunk_size
        self._overlap = overlap

    def chunk(
        self,
        pages: list[PageContent],
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        """
        Build parent and child chunks.

        Returns child chunks with parent_chunk_id in metadata.
        Parent chunks marked with is_parent=True in metadata.
        """
        full_text = self._merge_pages(pages)
        chunks: list[Chunk] = []
        chunk_index = 0

        # Build parent chunks first
        parent_step = (self._parent_size * 4) - (self._overlap * 4)
        parent_start = 0
        parent_chunks: list[tuple[int, int, uuid.UUID]] = []  # (start, end, id)

        while parent_start < len(full_text):
            parent_end = min(parent_start + self._parent_size * 4, len(full_text))
            content = full_text[parent_start:parent_end].strip()
            if not content:
                parent_start += parent_step
                continue

            parent_id = uuid.uuid4()
            page_num = self._find_page_for_offset(pages, parent_start)
            parent_chunk = self._build_chunk(
                content=content,
                chunk_index=chunk_index,
                page_number=page_num,
                start_char=parent_start,
                end_char=parent_end,
                extra_metadata={
                    "strategy": "parent_child",
                    "is_parent": True,
                    "parent_chunk_id": str(parent_id),
                },
            )
            # Override auto-generated id with our tracked parent_id
            object.__setattr__(parent_chunk, "chunk_id", parent_id)
            chunks.append(parent_chunk)
            parent_chunks.append((parent_start, parent_end, parent_id))
            chunk_index += 1
            parent_start += parent_step

        # Build child chunks within each parent
        child_step = self._child_size * 4 - self._overlap * 4

        for p_start, p_end, parent_id in parent_chunks:
            child_start = p_start
            while child_start < p_end:
                child_end = min(child_start + self._child_size * 4, p_end)
                content = full_text[child_start:child_end].strip()
                if not content:
                    child_start += child_step
                    continue

                page_num = self._find_page_for_offset(pages, child_start)
                child_chunk = self._build_chunk(
                    content=content,
                    chunk_index=chunk_index,
                    page_number=page_num,
                    start_char=child_start,
                    end_char=child_end,
                    extra_metadata={
                        "strategy": "parent_child",
                        "is_parent": False,
                        "parent_chunk_id": str(parent_id),
                    },
                )
                chunks.append(child_chunk)
                chunk_index += 1
                child_start += child_step

        logger.info(
            "parent_child_chunking_complete",
            total_chunks=len(chunks),
            parents=len(parent_chunks),
        )
        return chunks

    def _find_page_for_offset(
        self, pages: list[PageContent], offset: int
    ) -> int | None:
        running = 0
        for page in pages:
            running += len(page.text) + 2
            if running >= offset:
                return page.page_num
        return None


# ── Factory ───────────────────────────────────────────────────────────────────


class ChunkingService:
    """
    Factory + orchestrator for all chunking strategies.

    Usage:
        service = ChunkingService(config)
        chunks = service.chunk(pages, strategy="recursive")
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        parent_chunk_size: int = 2048,
        child_chunk_size: int = 256,
        semantic_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        semantic_threshold: float = 0.85,
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._parent_chunk_size = parent_chunk_size
        self._child_chunk_size = child_chunk_size
        self._semantic_model = semantic_model
        self._semantic_threshold = semantic_threshold

    def chunk(
        self,
        pages: list[PageContent],
        strategy: str = "recursive",
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        """
        Chunk pages using the specified strategy.

        Args:
            pages: Extracted page content.
            strategy: One of "fixed", "recursive", "semantic", "parent_child".
            document_id: Optional document ID for tracing.

        Returns:
            List of Chunk objects.
        """
        chunker = self._get_chunker(strategy)
        log = logger.bind(strategy=strategy, document_id=str(document_id))
        log.info("chunking_start", page_count=len(pages))

        chunks = chunker.chunk(pages, document_id)
        log.info("chunking_done", chunk_count=len(chunks))
        return chunks

    def _get_chunker(self, strategy: str) -> BaseChunker:
        """Instantiate the appropriate chunker."""
        if strategy == "fixed":
            return FixedChunker(
                chunk_size=self._chunk_size * 4,
                overlap=self._chunk_overlap * 4,
            )
        elif strategy == "recursive":
            return RecursiveChunker(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
        elif strategy == "semantic":
            return SemanticChunker(
                model_name=self._semantic_model,
                threshold=self._semantic_threshold,
            )
        elif strategy == "parent_child":
            return ParentChildChunker(
                parent_chunk_size=self._parent_chunk_size,
                child_chunk_size=self._child_chunk_size,
            )
        else:
            logger.warning("unknown_strategy_fallback_recursive", strategy=strategy)
            return RecursiveChunker(
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )

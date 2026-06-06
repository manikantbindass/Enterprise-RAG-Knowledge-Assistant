"""Citation extractor — maps [1],[2] references in answer to source chunks."""
from __future__ import annotations

import re


class CitationExtractor:
    def extract(self, answer: str, chunks: list[dict]) -> list[dict]:
        """
        Find citation markers [N] in the answer and return referenced chunks.
        Returns list of {chunk_id, doc_id, doc_filename, page_number, relevance_score, excerpt}
        """
        cited_indices: set[int] = set()
        for match in re.finditer(r'\[(\d+)\]', answer):
            idx = int(match.group(1))
            if 1 <= idx <= len(chunks):
                cited_indices.add(idx - 1)  # 0-indexed

        if not cited_indices:
            # Return top 3 chunks if no explicit citations
            cited_indices = set(range(min(3, len(chunks))))

        sources = []
        for i in sorted(cited_indices):
            if i < len(chunks):
                chunk = chunks[i]
                content = chunk.get("content", "")
                excerpt = content[:200] + "..." if len(content) > 200 else content
                sources.append({
                    "citation_number": i + 1,
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "doc_filename": chunk.get("doc_filename", "Unknown"),
                    "page_number": chunk.get("page_number"),
                    "relevance_score": chunk.get("score", 0.0),
                    "excerpt": excerpt,
                })

        return sources

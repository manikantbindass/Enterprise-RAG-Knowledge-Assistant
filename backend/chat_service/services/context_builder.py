"""Context builder — assembles retrieved chunks into LLM-ready context string."""
from __future__ import annotations

import tiktoken

ENCODING = tiktoken.get_encoding("cl100k_base")


class ContextBuilder:
    def build(self, chunks: list[dict], max_tokens: int = 6000) -> str:
        """
        Build context string from reranked chunks.
        Deduplicates content, respects token limit, adds source markers.
        """
        seen_content: set[str] = set()
        context_parts: list[str] = []
        total_tokens = 0

        for i, chunk in enumerate(chunks, start=1):
            content = chunk.get("content", "").strip()
            if not content or content in seen_content:
                continue
            seen_content.add(content)

            doc_name = chunk.get("doc_filename", "Unknown Document")
            page = chunk.get("page_number", "")
            page_str = f" (Page {page})" if page else ""
            header = f"[{i}] {doc_name}{page_str}"
            entry = f"{header}\n{content}"

            chunk_tokens = len(ENCODING.encode(entry))
            if total_tokens + chunk_tokens > max_tokens:
                break

            context_parts.append(entry)
            total_tokens += chunk_tokens

        return "\n\n---\n\n".join(context_parts)

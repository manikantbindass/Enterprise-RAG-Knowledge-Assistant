"""Query rewriter — generates multiple query variants for better retrieval."""
from __future__ import annotations

import structlog
from services.llm_service import LLMService

logger = structlog.get_logger(__name__)


class QueryRewriter:
    def __init__(self) -> None:
        self.llm = LLMService()

    async def rewrite(self, query: str, history: list[dict]) -> list[str]:
        """Generate 3 alternative query phrasings + HyDE variant."""
        system_prompt = (
            "You are a query rewriting assistant. Given a user query, generate 3 alternative "
            "phrasings that capture the same intent but use different words. "
            "Return ONLY a JSON array of strings, e.g. [\"query1\", \"query2\", \"query3\"]."
        )
        messages = [{"role": "user", "content": f"Original query: {query}"}]

        text = ""
        async for chunk in self.llm.stream(provider="openai", messages=messages, system_prompt=system_prompt):
            text += chunk.get("content", "")

        import json, re
        try:
            match = re.search(r'\[.*?\]', text, re.DOTALL)
            if match:
                variants = json.loads(match.group())
                return [query] + [v for v in variants if isinstance(v, str)][:3]
        except Exception:
            pass
        return [query]

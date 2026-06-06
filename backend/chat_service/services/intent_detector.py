"""Intent detector — classifies user query intent."""
from __future__ import annotations

from typing import Literal

import structlog
from services.llm_service import LLMService

logger = structlog.get_logger(__name__)
IntentType = Literal["search", "summarize", "compare", "agentic", "chit_chat"]


class IntentDetector:
    def __init__(self) -> None:
        self.llm = LLMService()

    async def detect(self, query: str) -> IntentType:
        system_prompt = (
            "Classify the user query into one of these intents:\n"
            "- search: Looking for specific information\n"
            "- summarize: Wants a summary of a document or topic\n"
            "- compare: Comparing two or more items\n"
            "- agentic: Multi-step research or complex analysis\n"
            "- chit_chat: Casual conversation not requiring document search\n\n"
            "Return ONLY the intent label, nothing else."
        )
        messages = [{"role": "user", "content": query}]
        text = ""
        async for chunk in self.llm.stream(provider="openai", messages=messages, system_prompt=system_prompt):
            text += chunk.get("content", "")
        intent = text.strip().lower().split()[0] if text.strip() else "search"
        valid = {"search", "summarize", "compare", "agentic", "chit_chat"}
        return intent if intent in valid else "search"  # type: ignore

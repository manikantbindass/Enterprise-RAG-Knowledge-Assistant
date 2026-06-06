"""
RAG Pipeline — LangGraph StateGraph implementation
Query → Rewrite → Intent → Retrieve → Rerank → Context → LLM → Cite
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Literal, TypedDict

import httpx
import structlog
import tiktoken
from langgraph.graph import END, StateGraph

from config import ChatConfig
from services.llm_service import LLMService
from services.query_rewriter import QueryRewriter
from services.intent_detector import IntentDetector
from services.context_builder import ContextBuilder
from services.citation_extractor import CitationExtractor

logger = structlog.get_logger(__name__)
config = ChatConfig()
tokenizer = tiktoken.get_encoding("cl100k_base")


class RAGState(TypedDict):
    query: str
    rewritten_queries: list[str]
    intent: Literal["search", "summarize", "compare", "agentic", "chit_chat"]
    retrieved_chunks: list[dict]
    reranked_chunks: list[dict]
    context: str
    answer: str
    sources: list[dict]
    conversation_history: list[dict]
    org_id: str
    user_id: str
    llm_provider: str
    filters: dict
    tokens_used: int
    cost: float
    error: str | None


class RAGPipeline:
    def __init__(self, reranker: Any = None) -> None:
        self.reranker = reranker
        self.llm_service = LLMService()
        self.query_rewriter = QueryRewriter()
        self.intent_detector = IntentDetector()
        self.context_builder = ContextBuilder()
        self.citation_extractor = CitationExtractor()
        self._graph = self._build_graph()

    def _build_graph(self) -> Any:
        graph = StateGraph(RAGState)

        graph.add_node("rewrite_query", self._node_rewrite)
        graph.add_node("detect_intent", self._node_detect_intent)
        graph.add_node("retrieve", self._node_retrieve)
        graph.add_node("rerank", self._node_rerank)
        graph.add_node("build_context", self._node_build_context)
        graph.add_node("generate_answer", self._node_generate_answer)
        graph.add_node("extract_sources", self._node_extract_sources)

        graph.set_entry_point("rewrite_query")
        graph.add_edge("rewrite_query", "detect_intent")
        graph.add_conditional_edges(
            "detect_intent",
            self._route_by_intent,
            {"search": "retrieve", "chit_chat": "generate_answer"},
        )
        graph.add_edge("retrieve", "rerank")
        graph.add_edge("rerank", "build_context")
        graph.add_edge("build_context", "generate_answer")
        graph.add_edge("generate_answer", "extract_sources")
        graph.add_edge("extract_sources", END)

        return graph.compile()

    def _route_by_intent(self, state: RAGState) -> str:
        if state["intent"] == "chit_chat":
            return "chit_chat"
        return "search"

    async def _node_rewrite(self, state: RAGState) -> dict:
        try:
            rewritten = await self.query_rewriter.rewrite(
                query=state["query"],
                history=state["conversation_history"][-6:],  # last 3 turns
            )
            return {"rewritten_queries": rewritten}
        except Exception as e:
            logger.warning("Query rewrite failed, using original", error=str(e))
            return {"rewritten_queries": [state["query"]]}

    async def _node_detect_intent(self, state: RAGState) -> dict:
        try:
            intent = await self.intent_detector.detect(state["query"])
            return {"intent": intent}
        except Exception:
            return {"intent": "search"}

    async def _node_retrieve(self, state: RAGState) -> dict:
        """Multi-query retrieval via vector service."""
        all_chunks: list[dict] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = [
                client.post(
                    f"{config.vector_service_url}/search",
                    json={
                        "query": q,
                        "org_id": state["org_id"],
                        "top_k": 10,
                        "filters": state["filters"],
                        "search_type": "hybrid",
                    },
                )
                for q in state["rewritten_queries"][:3]
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

        for resp in responses:
            if isinstance(resp, Exception):
                logger.warning("Retrieval request failed", error=str(resp))
                continue
            if resp.status_code == 200:
                chunks = resp.json().get("results", [])
                for chunk in chunks:
                    if chunk["chunk_id"] not in seen_ids:
                        seen_ids.add(chunk["chunk_id"])
                        all_chunks.append(chunk)

        # Sort by score descending
        all_chunks.sort(key=lambda x: x.get("score", 0), reverse=True)
        return {"retrieved_chunks": all_chunks[:20]}

    async def _node_rerank(self, state: RAGState) -> dict:
        chunks = state["retrieved_chunks"]
        if not chunks or not self.reranker:
            return {"reranked_chunks": chunks[:10]}
        try:
            reranked = await asyncio.to_thread(
                self.reranker.rerank,
                query=state["query"],
                chunks=chunks,
                top_k=8,
            )
            return {"reranked_chunks": reranked}
        except Exception as e:
            logger.warning("Reranking failed", error=str(e))
            return {"reranked_chunks": chunks[:8]}

    async def _node_build_context(self, state: RAGState) -> dict:
        context = self.context_builder.build(
            chunks=state["reranked_chunks"],
            max_tokens=config.max_context_tokens,
        )
        return {"context": context}

    async def _node_generate_answer(self, state: RAGState) -> dict:
        # Build messages
        system_prompt = (
            "You are an expert Enterprise Knowledge Assistant. "
            "Answer questions accurately using ONLY the provided context. "
            "If the context does not contain sufficient information, say so clearly. "
            "Always cite your sources using [1], [2] notation.\n\n"
            f"CONTEXT:\n{state.get('context', '')}"
        )

        messages = []
        for turn in state["conversation_history"][-6:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": state["query"]})

        answer = ""
        tokens = 0
        cost = 0.0

        async for chunk in self.llm_service.stream(
            provider=state["llm_provider"],
            messages=messages,
            system_prompt=system_prompt,
        ):
            answer += chunk.get("content", "")
            tokens += chunk.get("tokens", 0)
            cost += chunk.get("cost", 0.0)

        return {"answer": answer, "tokens_used": tokens, "cost": cost}

    async def _node_extract_sources(self, state: RAGState) -> dict:
        sources = self.citation_extractor.extract(
            answer=state["answer"],
            chunks=state["reranked_chunks"],
        )
        return {"sources": sources}

    async def stream(
        self,
        query: str,
        conversation_history: list[dict],
        org_id: str,
        user_id: str,
        llm_provider: str = "openai",
        filters: dict | None = None,
    ) -> AsyncIterator[dict]:
        """Execute RAG pipeline and yield SSE events."""
        initial_state: RAGState = {
            "query": query,
            "rewritten_queries": [],
            "intent": "search",
            "retrieved_chunks": [],
            "reranked_chunks": [],
            "context": "",
            "answer": "",
            "sources": [],
            "conversation_history": conversation_history,
            "org_id": org_id,
            "user_id": user_id,
            "llm_provider": llm_provider,
            "filters": filters or {},
            "tokens_used": 0,
            "cost": 0.0,
            "error": None,
        }

        try:
            # Run up to generate_answer (pre-LLM)
            state = initial_state.copy()
            state = await self._node_rewrite(state)
            state.update(await self._node_detect_intent(state))
            state.update(await self._node_retrieve(state))
            state.update(await self._node_rerank(state))
            state.update(await self._node_build_context(state))

            # Stream LLM tokens
            system_prompt = (
                "You are an expert Enterprise Knowledge Assistant. "
                "Answer questions accurately using ONLY the provided context. "
                "If context is insufficient, say so. "
                "Cite sources as [1], [2].\n\n"
                f"CONTEXT:\n{state['context']}"
            )
            messages = [
                {"role": t["role"], "content": t["content"]}
                for t in conversation_history[-6:]
            ]
            messages.append({"role": "user", "content": query})

            full_answer = ""
            total_tokens = 0
            total_cost = 0.0

            async for chunk in self.llm_service.stream(
                provider=llm_provider,
                messages=messages,
                system_prompt=system_prompt,
            ):
                token = chunk.get("content", "")
                if token:
                    full_answer += token
                    yield {"type": "token", "content": token}
                total_tokens += chunk.get("tokens", 0)
                total_cost += chunk.get("cost", 0.0)

            # Extract and yield sources
            sources = self.citation_extractor.extract(
                answer=full_answer,
                chunks=state["reranked_chunks"],
            )
            yield {"type": "sources", "content": sources}
            yield {"type": "metadata", "tokens_used": total_tokens, "cost": total_cost}

        except Exception as e:
            logger.error("RAG pipeline error", error=str(e), exc_info=True)
            yield {"type": "error", "content": f"RAG pipeline error: {str(e)}"}

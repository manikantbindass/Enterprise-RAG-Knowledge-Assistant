"""
Embedding Service — Multi-provider embedder with cost tracking and retry
"""
from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)

# Pricing per 1M tokens (USD)
COST_PER_1M_TOKENS = {
    "text-embedding-3-large": 0.13,
    "text-embedding-3-small": 0.02,
    "text-embedding-ada-002": 0.10,
    "nomic-embed-text": 0.0,
}


class BaseEmbedder(ABC):
    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def estimate_cost(self, texts: list[str]) -> float:
        ...


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, api_key: str, model: str = "text-embedding-3-large") -> None:
        import openai
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Truncate texts exceeding token limit
        truncated = [t[:8000] for t in texts]
        response = await self.client.embeddings.create(model=self.model, input=truncated)
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    def estimate_cost(self, texts: list[str]) -> float:
        total_chars = sum(len(t) for t in texts)
        approx_tokens = total_chars / 4
        rate = COST_PER_1M_TOKENS.get(self.model, 0.13)
        return (approx_tokens / 1_000_000) * rate


class AzureOpenAIEmbedder(BaseEmbedder):
    def __init__(self, api_key: str, endpoint: str, deployment: str, api_version: str) -> None:
        import openai
        self.client = openai.AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self.deployment = deployment

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        truncated = [t[:8000] for t in texts]
        response = await self.client.embeddings.create(model=self.deployment, input=truncated)
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]

    def estimate_cost(self, texts: list[str]) -> float:
        total_chars = sum(len(t) for t in texts)
        return (total_chars / 4 / 1_000_000) * 0.13


class BGEEmbedder(BaseEmbedder):
    def __init__(self, model_name: str = "BAAI/bge-large-en-v1.5") -> None:
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = await asyncio.to_thread(
            self.model.encode,
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def estimate_cost(self, texts: list[str]) -> float:
        return 0.0  # Local model, no API cost


class OllamaEmbedder(BaseEmbedder):
    def __init__(self, base_url: str, model: str = "nomic-embed-text") -> None:
        import httpx
        self.client = httpx.AsyncClient(base_url=base_url, timeout=60.0)
        self.model = model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = []
        for text in texts:
            resp = await self.client.post("/api/embeddings", json={"model": self.model, "prompt": text})
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        return embeddings

    def estimate_cost(self, texts: list[str]) -> float:
        return 0.0


class EmbeddingService:
    """Factory + orchestrator for all embedding providers."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self._embedders: dict[str, BaseEmbedder] = {}

    def _get_embedder(self, provider: str) -> BaseEmbedder:
        if provider not in self._embedders:
            if provider == "openai":
                self._embedders[provider] = OpenAIEmbedder(
                    api_key=self.config.openai_api_key,
                    model=self.config.openai_embedding_model,
                )
            elif provider == "azure":
                self._embedders[provider] = AzureOpenAIEmbedder(
                    api_key=self.config.azure_openai_api_key,
                    endpoint=self.config.azure_openai_endpoint,
                    deployment=self.config.azure_openai_embedding_deployment,
                    api_version=self.config.azure_openai_api_version,
                )
            elif provider == "bge":
                self._embedders[provider] = BGEEmbedder(self.config.bge_model_name)
            elif provider == "ollama":
                self._embedders[provider] = OllamaEmbedder(
                    base_url=self.config.ollama_base_url,
                    model=self.config.ollama_embedding_model,
                )
            else:
                raise ValueError(f"Unknown embedding provider: {provider}")
        return self._embedders[provider]

    async def embed_texts(
        self,
        texts: list[str],
        provider: str | None = None,
        batch_size: int | None = None,
    ) -> tuple[list[list[float]], float]:
        """
        Embed texts in batches. Returns (embeddings, total_cost).
        """
        provider = provider or self.config.default_embedding_provider
        batch_size = batch_size or self.config.embedding_batch_size
        embedder = self._get_embedder(provider)

        all_embeddings: list[list[float]] = []
        total_cost = 0.0

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            cost = embedder.estimate_cost(batch)
            embeddings = await embedder.embed_batch(batch)
            all_embeddings.extend(embeddings)
            total_cost += cost
            logger.info(
                "Batch embedded",
                batch_num=i // batch_size + 1,
                batch_size=len(batch),
                provider=provider,
                cost=cost,
            )

        return all_embeddings, total_cost

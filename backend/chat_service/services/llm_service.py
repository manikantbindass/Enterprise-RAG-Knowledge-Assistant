"""
LLM Service — provider abstraction layer.

All providers implement AsyncIterator[str] streaming via stream_generate().
Cost is calculated per provider per token using published pricing.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

import httpx
import structlog
from anthropic import AsyncAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_community.llms.ollama import Ollama
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from openai import AsyncAzureOpenAI, AsyncOpenAI

from chat_service.config import LLMProvider, get_settings

logger = structlog.get_logger(__name__)


# ── Cost tables (USD per 1M tokens) ───────────────────────────────────────

_OPENAI_COSTS: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}
_ANTHROPIC_COSTS: dict[str, dict[str, float]] = {
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
}


def _calc_cost(model: str, input_tokens: int, output_tokens: int, table: dict) -> float:
    if model not in table:
        return 0.0
    rates = table[model]
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


# ── Base provider ──────────────────────────────────────────────────────────


class BaseLLMProvider(ABC):
    """Abstract base — all providers must implement this interface."""

    @abstractmethod
    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas as they stream from the LLM."""
        ...

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        """Non-streaming generate. Returns (text, input_tokens, output_tokens)."""
        ...

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0


# ── OpenAI provider ────────────────────────────────────────────────────────


class OpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._max_tokens = settings.openai_max_tokens
        self._temperature = settings.openai_temperature

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=max_tokens or self._max_tokens,
            temperature=temperature if temperature is not None else self._temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            max_tokens=max_tokens or self._max_tokens,
            temperature=self._temperature,
            stream=False,
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return content, usage.prompt_tokens, usage.completion_tokens

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return _calc_cost(self._model, input_tokens, output_tokens, _OPENAI_COSTS)


# ── Anthropic provider ─────────────────────────────────────────────────────


class AnthropicProvider(BaseLLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        self._max_tokens = settings.anthropic_max_tokens

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system_prompt,
            messages=messages,
            temperature=temperature if temperature is not None else 0.2,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system_prompt,
            messages=messages,
        )
        content = resp.content[0].text if resp.content else ""
        return content, resp.usage.input_tokens, resp.usage.output_tokens

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return _calc_cost(self._model, input_tokens, output_tokens, _ANTHROPIC_COSTS)


# ── Azure OpenAI provider ──────────────────────────────────────────────────


class AzureOpenAIProvider(BaseLLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_deployment
        self._max_tokens = settings.openai_max_tokens
        self._temperature = settings.openai_temperature

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        stream = await self._client.chat.completions.create(
            model=self._deployment,
            messages=full_messages,
            max_tokens=max_tokens or self._max_tokens,
            temperature=temperature if temperature is not None else self._temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        resp = await self._client.chat.completions.create(
            model=self._deployment,
            messages=full_messages,
            max_tokens=max_tokens or self._max_tokens,
            stream=False,
        )
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        return content, usage.prompt_tokens, usage.completion_tokens


# ── Ollama provider ────────────────────────────────────────────────────────


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM via REST API — no third-party SDK dependency."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model
        self._timeout = settings.ollama_timeout

    async def stream_generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        payload = {
            "model": self._model,
            "messages": full_messages,
            "stream": True,
            "options": {
                "temperature": temperature if temperature is not None else 0.2,
                **({"num_predict": max_tokens} if max_tokens else {}),
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def generate(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> tuple[str, int, int]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        payload = {
            "model": self._model,
            "messages": full_messages,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
        content = data.get("message", {}).get("content", "")
        eval_count = data.get("eval_count", 0)
        prompt_eval_count = data.get("prompt_eval_count", 0)
        return content, prompt_eval_count, eval_count


# ── Factory ────────────────────────────────────────────────────────────────


class LLMService:
    """
    Provider factory + thin router.
    Instantiate providers lazily and cache per provider name.
    """

    _instances: dict[str, BaseLLMProvider] = {}

    @classmethod
    def get_provider(cls, provider_name: str | None = None) -> BaseLLMProvider:
        settings = get_settings()
        name = provider_name or settings.default_llm_provider.value

        if name not in cls._instances:
            if name == LLMProvider.OPENAI:
                cls._instances[name] = OpenAIProvider()
            elif name == LLMProvider.ANTHROPIC:
                cls._instances[name] = AnthropicProvider()
            elif name == LLMProvider.AZURE_OPENAI:
                cls._instances[name] = AzureOpenAIProvider()
            elif name == LLMProvider.OLLAMA:
                cls._instances[name] = OllamaProvider()
            else:
                raise ValueError(f"Unknown LLM provider: {name!r}")

        return cls._instances[name]

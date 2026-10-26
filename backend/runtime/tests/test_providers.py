import asyncio
import json

import httpx
import pytest
from backend.runtime import providers


@pytest.mark.parametrize("provider", ["openai", "ollama"])
def test_provider_wire_format(provider, monkeypatch):
    monkeypatch.setenv("RAG_PROVIDER", provider)
    monkeypatch.setenv("RAG_MODEL", "configured-test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")
    original_client = httpx.AsyncClient

    def handler(request):
        body = json.loads(request.content)
        assert body["stream"] and body["model"] == "configured-test-model"
        assert body["messages"][0]["role"] == "system"
        assert "evidence" in body["messages"][-1]["content"]
        if provider == "openai":
            assert request.headers["authorization"] == "Bearer test-key-not-a-real-secret"
            return httpx.Response(
                200,
                text='data: {"choices":[{"delta":{"content":"Hello [1]"}}]}\n\ndata: [DONE]\n\n',
            )
        assert request.url.path == "/api/chat"
        return httpx.Response(
            200,
            text='{"message":{"content":"Hello [1]"},"done":false}\n{"message":{"content":""},"done":true}\n',
        )

    monkeypatch.setattr(
        providers.httpx,
        "AsyncClient",
        lambda **kw: original_client(transport=httpx.MockTransport(handler), **kw),
    )

    async def run():
        return [
            token async for token in providers.generate("Question", [{"excerpt": "Evidence"}], [])
        ]

    assert asyncio.run(run()) == ["Hello [1]"]


def test_truncated_provider_stream_is_not_success(monkeypatch):
    monkeypatch.setenv("RAG_PROVIDER", "openai")
    monkeypatch.setenv("RAG_MODEL", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, text='data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n'
        )
    )
    monkeypatch.setattr(
        providers.httpx, "AsyncClient", lambda **kw: original_client(transport=transport, **kw)
    )

    async def run():
        return [
            token async for token in providers.generate("Question", [{"excerpt": "Evidence"}], [])
        ]

    with pytest.raises(ValueError, match="without a completed answer"):
        asyncio.run(run())

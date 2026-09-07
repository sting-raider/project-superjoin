from __future__ import annotations

import io
import json
import urllib.error
from dataclasses import replace
from typing import Any, Self

from app import providers
from app.config import settings


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_role_endpoints_and_keys_are_independent(monkeypatch) -> None:
    configured = replace(
        settings,
        ai_base_url="",
        ai_api_key="",
        extraction_base_url="http://extract.example/v1",
        extraction_api_key="extract-key",
        extraction_model="qwen2.5-7b-instruct",
        extraction_max_output_tokens=77,
        extraction_timeout_seconds=13,
        reasoning_base_url="",
        reasoning_api_key="",
        reasoning_model="",
        vision_base_url="",
        vision_api_key="",
        vision_model="",
        embedding_base_url="http://embed.example/v1",
        embedding_api_key="embed-key",
        embedding_model="nomic-embed-text",
        embedding_dimensions=2,
        embedding_timeout_seconds=17,
    )
    monkeypatch.setattr(providers, "settings", configured)
    calls: list[tuple[str, str, int, dict[str, Any]]] = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        calls.append((request.full_url, request.headers["Authorization"], timeout, payload))
        if request.full_url.endswith("/embeddings"):
            return _Response({"data": [{"embedding": [3.0, 4.0]}], "usage": {"prompt_tokens": 4}})
        return _Response({"choices": [{"message": {"content": json.dumps({"claims": []})}}], "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    assert providers.available("extraction") is True
    assert providers.available("reasoning") is False
    assert providers.available("embedding") is True
    assert providers.available() is True

    chat = providers.structured_chat("extraction", "system", "user")
    vector = providers.embed("claim text")

    assert chat.data == {"claims": []}
    assert chat.model == configured.extraction_model
    assert vector.data["data"][0]["embedding"] == [3.0, 4.0]
    assert calls[0][0] == "http://extract.example/v1/chat/completions"
    assert calls[0][1] == "Bearer extract-key"
    assert calls[0][2] == 13
    assert calls[0][3]["max_tokens"] == 77
    assert calls[1][0] == "http://embed.example/v1/embeddings"
    assert calls[1][1] == "Bearer embed-key"
    assert calls[1][2] == 17
    assert calls[1][3]["dimensions"] == 2


def test_arbitrary_compatible_endpoint_supports_local_and_azure_style_auth(monkeypatch) -> None:
    configured = replace(
        settings,
        ai_base_url="",
        ai_api_key="",
        extraction_base_url="http://ollama.local/v1",
        extraction_api_key="",
        extraction_model="llama3.1:8b",
        extraction_structured_output_mode="none",
        extraction_timeout_seconds=7,
        vision_base_url="https://azure.example",
        vision_api_key="azure-secret",
        vision_model="vision-deployment",
        vision_chat_path="/openai/deployments/vision-deployment/chat/completions?api-version=2024-10-21",
        vision_auth_header="api-key",
        vision_auth_scheme="",
        vision_send_model=False,
    )
    monkeypatch.setattr(providers, "settings", configured)
    calls: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        calls.append((request.full_url, dict(request.headers), payload))
        return _Response({"choices": [{"message": {"content": json.dumps({"claims": []})}}]})

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    assert providers.available("extraction") is True
    assert providers.structured_chat("extraction", "system", "user").model == "llama3.1:8b"
    assert providers.available("vision") is True
    providers.vision_chat("system", "user", b"image")

    assert calls[0][0] == "http://ollama.local/v1/chat/completions"
    assert "Authorization" not in calls[0][1]
    assert calls[0][2]["model"] == "llama3.1:8b"
    assert calls[1][0].endswith("api-version=2024-10-21")
    assert calls[1][1]["Api-key"] == "azure-secret"
    assert "model" not in calls[1][2]


def test_empty_role_configuration_does_not_enable_shared_provider(monkeypatch) -> None:
    configured = replace(
        settings,
        ai_base_url="",
        ai_api_key="",
        extraction_base_url="",
        extraction_api_key="",
        reasoning_base_url="",
        reasoning_api_key="",
        vision_base_url="",
        vision_api_key="",
        embedding_base_url="",
        embedding_api_key="",
    )
    monkeypatch.setattr(providers, "settings", configured)
    assert providers.available() is False
    assert providers.available("extraction") is False
    assert providers.available("embedding") is False


def test_transient_provider_failure_uses_retry_after_without_silent_fallback(monkeypatch) -> None:
    configured = replace(
        settings,
        extraction_base_url="http://retry.example/v1",
        extraction_api_key="retry-key",
        extraction_model="custom-retry-model",
        provider_retry_attempts=2,
        provider_retry_backoff_seconds=0.01,
    )
    monkeypatch.setattr(providers, "settings", configured)
    calls: list[int] = []
    sleeps: list[float] = []

    def fake_urlopen(request, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limited",
                {"Retry-After": "0"},
                io.BytesIO(b'{"error":"slow down"}'),
            )
        return _Response({"choices": [{"message": {"content": json.dumps({"claims": []})}}]})

    monkeypatch.setattr(providers.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(providers.time, "sleep", lambda delay: sleeps.append(delay))
    result = providers.structured_chat("extraction", "system", "user")
    assert result.data == {"claims": []}
    assert calls == [90, 90]
    assert len(sleeps) == 1
    assert 0.0 <= sleeps[0] <= 0.25

from __future__ import annotations

import json
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
        extraction_max_output_tokens=77,
        reasoning_base_url="",
        reasoning_api_key="",
        vision_base_url="",
        vision_api_key="",
        embedding_base_url="http://embed.example/v1",
        embedding_api_key="embed-key",
        embedding_dimensions=2,
        ai_timeout_seconds=13,
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
    assert chat.model == settings.extraction_model
    assert vector.data["data"][0]["embedding"] == [3.0, 4.0]
    assert calls[0][0] == "http://extract.example/v1/chat/completions"
    assert calls[0][1] == "Bearer extract-key"
    assert calls[0][2] == 13
    assert calls[0][3]["max_tokens"] == 77
    assert calls[1][0] == "http://embed.example/v1/embeddings"
    assert calls[1][1] == "Bearer embed-key"
    assert calls[1][3]["dimensions"] == 2


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

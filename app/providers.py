from __future__ import annotations

import base64
import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import settings


@dataclass(frozen=True)
class ProviderResult:
    data: Any
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float = 0.0
    latency_ms: int = 0
    cached: bool = False


class ProviderError(RuntimeError):
    pass


def _role_config(role: str) -> tuple[str, str]:
    values = {
        "extraction": (settings.extraction_base_url, settings.extraction_api_key),
        "reasoning": (settings.reasoning_base_url, settings.reasoning_api_key),
        "vision": (settings.vision_base_url, settings.vision_api_key),
        "embedding": (settings.embedding_base_url, settings.embedding_api_key),
        "embeddings": (settings.embedding_base_url, settings.embedding_api_key),
    }
    return values.get(role, (settings.ai_base_url, settings.ai_api_key))


def available(role: str | None = None) -> bool:
    if role:
        base_url, api_key = _role_config(role)
        return bool(base_url and api_key)
    return any(available(name) for name in ("extraction", "reasoning", "vision", "embedding"))


def _post(path: str, payload: dict[str, Any], model: str, role: str) -> ProviderResult:
    base_url, api_key = _role_config(role)
    if not base_url or not api_key:
        raise ProviderError(f"No OpenAI-compatible {role} provider configured")
    url = f"{base_url}{path}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=settings.ai_timeout_seconds) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError(str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    if path == "/embeddings":
        parsed = raw
    else:
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            parsed = content
    usage = raw.get("usage") or {}
    input_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("completion_tokens")
    estimated_cost = ((input_tokens or max(1, len(body) // 4)) / 1_000_000) * settings.ai_input_price_per_million + ((output_tokens or 1200) / 1_000_000) * settings.ai_output_price_per_million
    return ProviderResult(
        data=parsed,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=round(estimated_cost, 6),
        latency_ms=elapsed,
    )


def structured_chat(role: str, system: str, user: str, model: str | None = None, max_output_tokens: int = 1200) -> ProviderResult:
    chosen = model or {
        "extraction": settings.extraction_model,
        "reasoning": settings.reasoning_model,
        "vision": settings.vision_model,
    }.get(role, settings.reasoning_model)
    payload = {
        "model": chosen,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": max_output_tokens,
    }
    mode = getattr(settings, f"{role}_structured_output_mode", "json_object")
    if mode and mode != "none":
        payload["response_format"] = {"type": mode}
    if max_output_tokens == 1200:
        max_output_tokens = getattr(settings, f"{role}_max_output_tokens", max_output_tokens)
        payload["max_tokens"] = max_output_tokens
    return _post("/chat/completions", payload, chosen, role)


def vision_chat(system: str, user: str, image_bytes: bytes, model: str | None = None, max_output_tokens: int = 1200) -> ProviderResult:
    chosen = model or settings.vision_model
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": chosen,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}]},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
    }
    if settings.vision_structured_output_mode and settings.vision_structured_output_mode != "none":
        payload["response_format"] = {"type": settings.vision_structured_output_mode}
    if max_output_tokens == 1200:
        max_output_tokens = settings.vision_max_output_tokens
        payload["max_tokens"] = max_output_tokens
    return _post("/chat/completions", payload, chosen, "vision")


def embed(text: str, model: str | None = None) -> ProviderResult:
    chosen = model or settings.embedding_model
    payload = {"model": chosen, "input": text, "dimensions": settings.embedding_dimensions}
    return _post("/embeddings", payload, chosen, "embedding")


def input_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

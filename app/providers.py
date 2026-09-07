from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
import base64
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


def available() -> bool:
    return bool(settings.ai_base_url and settings.ai_api_key)


def _post(path: str, payload: dict[str, Any], model: str) -> ProviderResult:
    if not available():
        raise ProviderError("No OpenAI-compatible provider configured")
    url = f"{settings.ai_base_url}{path}"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise ProviderError(str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    choice = (raw.get("choices") or [{}])[0]
    message = choice.get("message", {})
    content = message.get("content", "")
    usage = raw.get("usage") or {}
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    try:
        parsed = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        parsed = content
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


def structured_chat(role: str, system: str, user: str, model: str | None = None) -> ProviderResult:
    chosen = model or {
        "extraction": settings.extraction_model,
        "reasoning": settings.reasoning_model,
        "vision": settings.vision_model,
    }.get(role, settings.reasoning_model)
    payload = {
        "model": chosen,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    return _post("/chat/completions", payload, chosen)


def vision_chat(system: str, user: str, image_bytes: bytes, model: str | None = None) -> ProviderResult:
    chosen = model or settings.vision_model
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": chosen,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}]},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    return _post("/chat/completions", payload, chosen)


def embed(text: str, model: str | None = None) -> ProviderResult:
    chosen = model or settings.embedding_model
    payload = {"model": chosen, "input": text, "dimensions": settings.embedding_dimensions}
    return _post("/embeddings", payload, chosen)


def input_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

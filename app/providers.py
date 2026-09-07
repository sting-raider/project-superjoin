from __future__ import annotations

import base64
import hashlib
import json
import random
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
    endpoint: str | None = None


class ProviderError(RuntimeError):
    """A configured provider failed or does not support the requested lane."""


_ROLE_FIELDS: dict[str, dict[str, str]] = {
    "extraction": {
        "base_url": "extraction_base_url",
        "api_key": "extraction_api_key",
        "model": "extraction_model",
        "timeout": "extraction_timeout_seconds",
        "max_output_tokens": "extraction_max_output_tokens",
        "structured_output_mode": "extraction_structured_output_mode",
        "path": "extraction_chat_path",
        "auth_header": "extraction_auth_header",
        "auth_scheme": "extraction_auth_scheme",
        "send_model": "extraction_send_model",
    },
    "reasoning": {
        "base_url": "reasoning_base_url",
        "api_key": "reasoning_api_key",
        "model": "reasoning_model",
        "timeout": "reasoning_timeout_seconds",
        "max_output_tokens": "reasoning_max_output_tokens",
        "structured_output_mode": "reasoning_structured_output_mode",
        "path": "reasoning_chat_path",
        "auth_header": "reasoning_auth_header",
        "auth_scheme": "reasoning_auth_scheme",
        "send_model": "reasoning_send_model",
    },
    "vision": {
        "base_url": "vision_base_url",
        "api_key": "vision_api_key",
        "model": "vision_model",
        "timeout": "vision_timeout_seconds",
        "max_output_tokens": "vision_max_output_tokens",
        "structured_output_mode": "vision_structured_output_mode",
        "path": "vision_chat_path",
        "auth_header": "vision_auth_header",
        "auth_scheme": "vision_auth_scheme",
        "send_model": "vision_send_model",
    },
    "embedding": {
        "base_url": "embedding_base_url",
        "api_key": "embedding_api_key",
        "model": "embedding_model",
        "timeout": "embedding_timeout_seconds",
        "path": "embedding_path",
        "auth_header": "embedding_auth_header",
        "auth_scheme": "embedding_auth_scheme",
        "send_model": "embedding_send_model",
    },
}


def _canonical_role(role: str) -> str:
    return "embedding" if role == "embeddings" else role


def _role_config(role: str) -> dict[str, Any]:
    canonical = _canonical_role(role)
    fields = _ROLE_FIELDS.get(canonical)
    if not fields:
        return {
            "base_url": settings.ai_base_url,
            "api_key": settings.ai_api_key,
            "model": "",
            "timeout": settings.ai_timeout_seconds,
            "max_output_tokens": 1200,
            "structured_output_mode": "none",
            "path": "/chat/completions",
            "auth_header": "Authorization",
            "auth_scheme": "Bearer",
            "send_model": True,
        }
    return {key: getattr(settings, attribute) for key, attribute in fields.items()}


def available(role: str | None = None) -> bool:
    """Return whether a role has enough configuration to attempt a call.

    API keys are optional so local Ollama/vLLM endpoints can be used. Remote
    services that require credentials return an explicit provider error rather
    than being hidden by a provider-specific allowlist.
    """

    if role:
        config = _role_config(role)
        return bool(config["base_url"] and config["model"])
    return any(available(name) for name in _ROLE_FIELDS)


def _endpoint(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = str(config.get("api_key") or "")
    if api_key:
        header = str(config.get("auth_header") or "Authorization")
        scheme = str(config.get("auth_scheme") or "")
        headers[header] = f"{scheme} {api_key}".strip()
    return headers


def _post(operation: str, payload: dict[str, Any], model: str, role: str, fallback_output_tokens: int | None = None) -> ProviderResult:
    config = _role_config(role)
    base_url = str(config["base_url"] or "")
    if not base_url:
        raise ProviderError(f"No OpenAI-compatible {role} base URL configured")
    if not model:
        raise ProviderError(f"No {role} model configured")
    path = str(config["path"])
    url = _endpoint(base_url, path)
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=_headers(config), method="POST")
    started = time.perf_counter()
    attempts = max(1, int(getattr(settings, "provider_retry_attempts", 1)))
    raw = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=int(config["timeout"])) as response:
                raw = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except (AttributeError, OSError, UnicodeError):  # pragma: no cover - defensive for unusual transports
                detail = str(exc)
            transient = exc.code == 429 or exc.code >= 500
            if not transient or attempt + 1 >= attempts:
                raise ProviderError(f"{role} provider HTTP {exc.code}: {detail}") from exc
            retry_after = _retry_after_seconds(exc)
            base = float(getattr(settings, "provider_retry_backoff_seconds", 0.25))
            delay = retry_after if retry_after is not None else base * (2**attempt)
            time.sleep(max(0.0, delay + random.uniform(0.0, min(base, 0.25))))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ProviderError(f"{role} provider request failed: {exc}") from exc
    if raw is None:  # pragma: no cover - loop either returns or raises
        raise ProviderError(f"{role} provider returned no response")
    elapsed = int((time.perf_counter() - started) * 1000)
    if operation == "embedding":
        parsed = raw
    else:
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content", choice.get("text", ""))
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if isinstance(content, dict):
            parsed = content
        else:
            try:
                parsed = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                parsed = content
    usage = raw.get("usage") or {}
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    estimated_cost = (
        ((input_tokens or max(1, len(body) // 4)) / 1_000_000) * settings.ai_input_price_per_million
        + ((output_tokens or fallback_output_tokens or config.get("max_output_tokens", 1200)) / 1_000_000)
        * settings.ai_output_price_per_million
    )
    return ProviderResult(
        data=parsed,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=round(estimated_cost, 6),
        latency_ms=elapsed,
        endpoint=url,
    )


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def structured_chat(role: str, system: str, user: str, model: str | None = None, max_output_tokens: int = 1200) -> ProviderResult:
    config = _role_config(role)
    chosen = model or str(config["model"] or "")
    output_limit = max_output_tokens if max_output_tokens != 1200 else int(config["max_output_tokens"])
    payload: dict[str, Any] = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "max_tokens": output_limit,
    }
    if config["send_model"]:
        payload["model"] = chosen
    mode = str(config["structured_output_mode"] or "none")
    if mode != "none":
        payload["response_format"] = {"type": mode}
    return _post("chat", payload, chosen, role, output_limit)


def vision_chat(system: str, user: str, image_bytes: bytes, model: str | None = None, max_output_tokens: int = 1200) -> ProviderResult:
    config = _role_config("vision")
    chosen = model or str(config["model"] or "")
    output_limit = max_output_tokens if max_output_tokens != 1200 else int(config["max_output_tokens"])
    encoded = base64.b64encode(image_bytes).decode("ascii")
    payload: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}]},
        ],
        "temperature": 0,
        "max_tokens": output_limit,
    }
    if config["send_model"]:
        payload["model"] = chosen
    mode = str(config["structured_output_mode"] or "none")
    if mode != "none":
        payload["response_format"] = {"type": mode}
    return _post("chat", payload, chosen, "vision", output_limit)


def embed(text: str, model: str | None = None) -> ProviderResult:
    config = _role_config("embedding")
    chosen = model or str(config["model"] or "")
    payload: dict[str, Any] = {"input": text}
    if config["send_model"]:
        payload["model"] = chosen
    if settings.embedding_include_dimensions:
        payload["dimensions"] = settings.embedding_dimensions
    return _post("embedding", payload, chosen, "embedding")


def input_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

from __future__ import annotations

import base64
import hashlib
import json
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
    attempts: int = 1
    finish_reason: str | None = None

    @property
    def truncated(self) -> bool:
        return str(self.finish_reason or "").casefold() in {
            "length",
            "max_tokens",
            "max_output_tokens",
        }


class ProviderError(RuntimeError):
    """A configured provider failed or does not support the requested lane."""

    def __init__(self, message: str, *, attempts: int = 1) -> None:
        super().__init__(message)
        self.attempts = max(1, int(attempts))


def public_endpoint(value: str) -> str:
    """Return endpoint identity without URL credentials or query parameters."""

    raw = str(value or "")
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return raw.split("?", 1)[0].split("#", 1)[0]
    if not parsed.scheme or not parsed.netloc:
        return raw.split("?", 1)[0].split("#", 1)[0]
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


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
        "concurrency": "extraction_concurrency",
        "extra_body_json": "extraction_extra_body_json",
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
        "concurrency": "reasoning_concurrency",
        "extra_body_json": "reasoning_extra_body_json",
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
        "concurrency": "vision_concurrency",
        "extra_body_json": "vision_extra_body_json",
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
        "concurrency": "embedding_concurrency",
        "extra_body_json": "embedding_extra_body_json",
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
            "concurrency": 1,
        }
    return {key: getattr(settings, attribute) for key, attribute in fields.items()}


def provider_identity(role: str, model: str | None = None) -> str:
    """Return a nonsecret cache identity for one compatible provider lane."""

    canonical = _canonical_role(role)
    config = _role_config(canonical)
    chosen_model = model or str(config.get("model") or "")
    shape = [
        canonical,
        str(config.get("base_url") or ""),
        str(config.get("path") or ""),
        chosen_model,
        str(config.get("auth_header") or ""),
        str(config.get("auth_scheme") or ""),
        str(config.get("send_model")),
        str(config.get("structured_output_mode") or ""),
        str(config.get("extra_body_json") or ""),
    ]
    if canonical == "embedding":
        shape.extend(
            [
                str(settings.embedding_dimensions),
                str(settings.embedding_include_dimensions),
                str(settings.embedding_task_type),
            ]
        )
    else:
        shape.extend([str(config.get("max_output_tokens") or "")])
    return input_hash("provider-config-v1", *shape)


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


def _merge_extra_body(payload: dict[str, Any], config: dict[str, Any], role: str) -> None:
    """Merge deployment-specific OpenAI-compatible fields from configuration."""

    raw = str(config.get("extra_body_json") or "").strip()
    if not raw:
        return
    try:
        extra = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{role} extra body is not valid JSON: {exc}") from exc
    if not isinstance(extra, dict):
        raise ProviderError(f"{role} extra body must be a JSON object")
    payload.update(extra)


_role_slots_lock = threading.Lock()
_role_slots: dict[tuple[str, int], threading.BoundedSemaphore] = {}
_role_cooldown_until: dict[str, float] = {}


def _role_slot(role: str, limit: int) -> threading.BoundedSemaphore:
    key = (_canonical_role(role), max(1, limit))
    with _role_slots_lock:
        return _role_slots.setdefault(key, threading.BoundedSemaphore(key[1]))


def _wait_for_role_cooldown(role: str) -> None:
    with _role_slots_lock:
        remaining = _role_cooldown_until.get(_canonical_role(role), 0.0) - time.monotonic()
    if remaining > 0:
        time.sleep(min(remaining, 30.0))


def _note_role_rate_limit(role: str, delay: float) -> None:
    until = time.monotonic() + max(0.0, min(delay, 30.0))
    with _role_slots_lock:
        canonical = _canonical_role(role)
        _role_cooldown_until[canonical] = max(
            _role_cooldown_until.get(canonical, 0.0), until
        )


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
    attempts_used = 0
    slot = _role_slot(role, int(config.get("concurrency") or 1))
    with slot:
        for attempt in range(attempts):
            attempts_used = attempt + 1
            _wait_for_role_cooldown(role)
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
                    raise ProviderError(f"{role} provider HTTP {exc.code}: {detail}", attempts=attempts_used) from exc
                retry_after = _retry_after_seconds(exc)
                if exc.code == 429 or exc.code >= 500:
                    delay = retry_after if retry_after is not None else float(
                        getattr(settings, "provider_retry_backoff_seconds", 0.5)
                    ) * (2**attempt)
                    _note_role_rate_limit(role, delay)
                _sleep_before_retry(attempt, retry_after)
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt + 1 >= attempts:
                    raise ProviderError(f"{role} provider request failed: {exc}", attempts=attempts_used) from exc
                _sleep_before_retry(attempt)
            except json.JSONDecodeError as exc:
                raise ProviderError(f"{role} provider returned invalid JSON: {exc}", attempts=attempts_used) from exc
    if raw is None:  # pragma: no cover - loop either returns or raises
        raise ProviderError(f"{role} provider returned no response", attempts=attempts_used)
    elapsed = int((time.perf_counter() - started) * 1000)
    finish_reason = None
    if operation == "embedding":
        parsed = raw
    else:
        choice = (raw.get("choices") or [{}])[0]
        finish_reason = choice.get("finish_reason")
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
    per_attempt_cost = (
        ((input_tokens or max(1, len(body) // 4)) / 1_000_000) * settings.ai_input_price_per_million
        + ((output_tokens or fallback_output_tokens or config.get("max_output_tokens", 1200)) / 1_000_000)
        * settings.ai_output_price_per_million
    )
    return ProviderResult(
        data=parsed,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=round(per_attempt_cost * attempts_used, 6),
        latency_ms=elapsed,
        endpoint=public_endpoint(url),
        attempts=attempts_used,
        finish_reason=str(finish_reason) if finish_reason is not None else None,
    )


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _sleep_before_retry(attempt: int, retry_after: float | None = None) -> None:
    base = float(getattr(settings, "provider_retry_backoff_seconds", 0.5))
    delay = retry_after if retry_after is not None else base * (2**attempt)
    time.sleep(max(0.0, delay + random.uniform(0.0, min(base, 0.25))))


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
    _merge_extra_body(payload, config, role)
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
    _merge_extra_body(payload, config, "vision")
    return _post("chat", payload, chosen, "vision", output_limit)


def embed(text: str | list[str], model: str | None = None) -> ProviderResult:
    config = _role_config("embedding")
    chosen = model or str(config["model"] or "")
    payload: dict[str, Any] = {"input": text}
    if config["send_model"]:
        payload["model"] = chosen
    if settings.embedding_include_dimensions:
        payload["dimensions"] = settings.embedding_dimensions
    _merge_extra_body(payload, config, "embedding")
    return _post("embedding", payload, chosen, "embedding")


def input_hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

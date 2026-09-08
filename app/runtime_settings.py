"""Validated, process-local provider configuration.

API keys live only on the in-memory Settings object. They are never written to
SQLite, returned by an API, or included in provider/cache identities.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from .config import settings
from .providers import ProviderError, validate_provider_base_url


class ProviderRoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = Field(default=None, max_length=2048)
    api_key: SecretStr | None = None
    clear_api_key: bool = False
    model: str | None = Field(default=None, max_length=512)
    path: str | None = Field(default=None, max_length=2048)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    max_output_tokens: int | None = Field(default=None, ge=1, le=131072)
    concurrency: int | None = Field(default=None, ge=1, le=64)
    structured_output_mode: str | None = Field(default=None, max_length=64)
    auth_header: str | None = Field(default=None, max_length=128)
    auth_scheme: str | None = Field(default=None, max_length=128)
    send_model: bool | None = None
    extra_body_json: str | None = Field(default=None, max_length=32768)
    dimensions: int | None = Field(default=None, ge=1, le=65536)
    include_dimensions: bool | None = None
    task_type: str | None = Field(default=None, max_length=128)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("path must be origin-relative and begin with /")
        if "#" in value:
            raise ValueError("path cannot contain a fragment")
        return value

    @field_validator("auth_header")
    @classmethod
    def validate_auth_header(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9-]+", value):
            raise ValueError("auth_header must be a valid HTTP header name")
        return value

    @field_validator("structured_output_mode")
    @classmethod
    def validate_output_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in {"none", "json_object", "json_schema"}:
            raise ValueError("structured_output_mode must be none, json_object, or json_schema")
        return value

    @field_validator("extra_body_json")
    @classmethod
    def validate_extra_body(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("extra_body_json must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise TypeError("extra_body_json must contain a JSON object")
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


_ROLE_ATTRIBUTES: dict[str, dict[str, str]] = {
    "extraction": {
        "base_url": "extraction_base_url",
        "api_key": "extraction_api_key",
        "model": "extraction_model",
        "path": "extraction_chat_path",
        "timeout_seconds": "extraction_timeout_seconds",
        "max_output_tokens": "extraction_max_output_tokens",
        "concurrency": "extraction_concurrency",
        "structured_output_mode": "extraction_structured_output_mode",
        "auth_header": "extraction_auth_header",
        "auth_scheme": "extraction_auth_scheme",
        "send_model": "extraction_send_model",
        "extra_body_json": "extraction_extra_body_json",
    },
    "reasoning": {
        "base_url": "reasoning_base_url",
        "api_key": "reasoning_api_key",
        "model": "reasoning_model",
        "path": "reasoning_chat_path",
        "timeout_seconds": "reasoning_timeout_seconds",
        "max_output_tokens": "reasoning_max_output_tokens",
        "concurrency": "reasoning_concurrency",
        "structured_output_mode": "reasoning_structured_output_mode",
        "auth_header": "reasoning_auth_header",
        "auth_scheme": "reasoning_auth_scheme",
        "send_model": "reasoning_send_model",
        "extra_body_json": "reasoning_extra_body_json",
    },
    "vision": {
        "base_url": "vision_base_url",
        "api_key": "vision_api_key",
        "model": "vision_model",
        "path": "vision_chat_path",
        "timeout_seconds": "vision_timeout_seconds",
        "max_output_tokens": "vision_max_output_tokens",
        "concurrency": "vision_concurrency",
        "structured_output_mode": "vision_structured_output_mode",
        "auth_header": "vision_auth_header",
        "auth_scheme": "vision_auth_scheme",
        "send_model": "vision_send_model",
        "extra_body_json": "vision_extra_body_json",
    },
    "embeddings": {
        "base_url": "embedding_base_url",
        "api_key": "embedding_api_key",
        "model": "embedding_model",
        "path": "embedding_path",
        "timeout_seconds": "embedding_timeout_seconds",
        "concurrency": "embedding_concurrency",
        "auth_header": "embedding_auth_header",
        "auth_scheme": "embedding_auth_scheme",
        "send_model": "embedding_send_model",
        "extra_body_json": "embedding_extra_body_json",
        "dimensions": "embedding_dimensions",
        "include_dimensions": "embedding_include_dimensions",
        "task_type": "embedding_task_type",
    },
}

_update_lock = threading.Lock()


def apply_provider_update(role: str, update: ProviderRoleUpdate) -> None:
    attributes = _ROLE_ATTRIBUTES.get(role)
    if not attributes:
        raise ProviderError(f"Unknown provider role: {role}")
    supplied = update.model_fields_set
    if "base_url" in supplied and update.base_url:
        validate_provider_base_url(update.base_url.strip().rstrip("/"))
    values = update.model_dump(exclude_unset=True, exclude={"api_key", "clear_api_key"})
    with _update_lock:
        for field_name, value in values.items():
            attribute = attributes.get(field_name)
            if attribute:
                object.__setattr__(
                    settings,
                    attribute,
                    value.strip().rstrip("/") if field_name == "base_url" else value,
                )
        if update.api_key is not None:
            object.__setattr__(
                settings,
                attributes["api_key"],
                update.api_key.get_secret_value(),
            )
        elif update.clear_api_key:
            object.__setattr__(settings, attributes["api_key"], "")


def provider_presets() -> list[dict[str, Any]]:
    """Return endpoint conveniences only; models and credentials stay arbitrary."""

    return [
        {"id": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1"},
        {"id": "azure", "label": "Azure OpenAI", "base_url": "", "auth_header": "api-key", "auth_scheme": "", "send_model": False},
        {"id": "openrouter", "label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1"},
        {"id": "together", "label": "Together", "base_url": "https://api.together.xyz/v1"},
        {"id": "groq", "label": "Groq", "base_url": "https://api.groq.com/openai/v1"},
        {"id": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com"},
        {"id": "nvidia", "label": "NVIDIA NIM", "base_url": "https://integrate.api.nvidia.com/v1"},
        {"id": "ollama", "label": "Ollama / local vLLM", "base_url": "http://localhost:11434/v1"},
        {"id": "custom", "label": "Custom endpoint", "base_url": ""},
    ]

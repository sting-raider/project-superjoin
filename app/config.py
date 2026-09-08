from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return (value if value else default).strip().rstrip("/")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "demo")
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/project_superjoin.sqlite3"))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
    ai_base_url: str = _env("AI_BASE_URL")
    ai_api_key: str = _env("AI_API_KEY")
    extraction_base_url: str = _env("EXTRACTION_BASE_URL", _env("AI_BASE_URL"))
    extraction_api_key: str = _env("EXTRACTION_API_KEY", _env("AI_API_KEY"))
    reasoning_base_url: str = _env("REASONING_BASE_URL", _env("AI_BASE_URL"))
    reasoning_api_key: str = _env("REASONING_API_KEY", _env("AI_API_KEY"))
    vision_base_url: str = _env("VISION_BASE_URL", _env("AI_BASE_URL"))
    vision_api_key: str = _env("VISION_API_KEY", _env("AI_API_KEY"))
    embedding_base_url: str = _env("EMBEDDING_BASE_URL", _env("AI_BASE_URL"))
    embedding_api_key: str = _env("EMBEDDING_API_KEY", _env("AI_API_KEY"))
    # Model names are deliberately unset by default. Every deployment chooses
    # its own model identifier, including local Ollama/vLLM models.
    extraction_model: str = _env("EXTRACTION_MODEL")
    reasoning_model: str = _env("REASONING_MODEL")
    vision_model: str = _env("VISION_MODEL")
    embedding_model: str = _env("EMBEDDING_MODEL")
    embedding_dimensions: int = _int_env("EMBEDDING_DIMENSIONS", 768)
    embedding_include_dimensions: bool = _bool_env("EMBEDDING_INCLUDE_DIMENSIONS", True)
    ai_timeout_seconds: int = _int_env("AI_TIMEOUT_SECONDS", 90)
    extraction_timeout_seconds: int = _int_env("EXTRACTION_TIMEOUT_SECONDS", ai_timeout_seconds)
    reasoning_timeout_seconds: int = _int_env("REASONING_TIMEOUT_SECONDS", ai_timeout_seconds)
    vision_timeout_seconds: int = _int_env("VISION_TIMEOUT_SECONDS", ai_timeout_seconds)
    embedding_timeout_seconds: int = _int_env("EMBEDDING_TIMEOUT_SECONDS", ai_timeout_seconds)
    extraction_max_output_tokens: int = _int_env("EXTRACTION_MAX_OUTPUT_TOKENS", 1200)
    reasoning_max_output_tokens: int = _int_env("REASONING_MAX_OUTPUT_TOKENS", 1200)
    vision_max_output_tokens: int = _int_env("VISION_MAX_OUTPUT_TOKENS", 1200)
    extraction_concurrency: int = _int_env("EXTRACTION_CONCURRENCY", 2)
    extraction_batch_pages: int = _int_env("EXTRACTION_BATCH_PAGES", 6)
    extraction_batch_chars: int = _int_env("EXTRACTION_BATCH_CHARS", 24000)
    extraction_hint_limit: int = _int_env("EXTRACTION_HINT_LIMIT", 24)
    extraction_claims_per_batch: int = _int_env("EXTRACTION_CLAIMS_PER_BATCH", 8)
    reasoning_concurrency: int = _int_env("REASONING_CONCURRENCY", 2)
    relationship_candidate_limit: int = _int_env("RELATIONSHIP_CANDIDATE_LIMIT", 12)
    relationship_semantic_limit: int = _int_env("RELATIONSHIP_SEMANTIC_LIMIT", 24)
    vision_concurrency: int = _int_env("VISION_CONCURRENCY", 2)
    embedding_concurrency: int = _int_env("EMBEDDING_CONCURRENCY", 2)
    embedding_batch_size: int = _int_env("EMBEDDING_BATCH_SIZE", 128)
    extraction_structured_output_mode: str = _env("EXTRACTION_STRUCTURED_OUTPUT_MODE", "json_object")
    reasoning_structured_output_mode: str = _env("REASONING_STRUCTURED_OUTPUT_MODE", "json_object")
    vision_structured_output_mode: str = _env("VISION_STRUCTURED_OUTPUT_MODE", "json_object")
    embedding_task_type: str = _env("EMBEDDING_TASK_TYPE", "retrieval_document")
    extraction_chat_path: str = _env("EXTRACTION_CHAT_PATH", "/chat/completions")
    reasoning_chat_path: str = _env("REASONING_CHAT_PATH", "/chat/completions")
    vision_chat_path: str = _env("VISION_CHAT_PATH", "/chat/completions")
    embedding_path: str = _env("EMBEDDING_PATH", "/embeddings")
    extraction_auth_header: str = _env("EXTRACTION_AUTH_HEADER", "Authorization")
    reasoning_auth_header: str = _env("REASONING_AUTH_HEADER", "Authorization")
    vision_auth_header: str = _env("VISION_AUTH_HEADER", "Authorization")
    embedding_auth_header: str = _env("EMBEDDING_AUTH_HEADER", "Authorization")
    extraction_auth_scheme: str = _env("EXTRACTION_AUTH_SCHEME", "Bearer")
    reasoning_auth_scheme: str = _env("REASONING_AUTH_SCHEME", "Bearer")
    vision_auth_scheme: str = _env("VISION_AUTH_SCHEME", "Bearer")
    embedding_auth_scheme: str = _env("EMBEDDING_AUTH_SCHEME", "Bearer")
    extraction_send_model: bool = _bool_env("EXTRACTION_SEND_MODEL", True)
    reasoning_send_model: bool = _bool_env("REASONING_SEND_MODEL", True)
    vision_send_model: bool = _bool_env("VISION_SEND_MODEL", True)
    embedding_send_model: bool = _bool_env("EMBEDDING_SEND_MODEL", True)
    provider_retry_attempts: int = _int_env("AI_RETRY_ATTEMPTS", 2)
    provider_retry_backoff_seconds: float = _float_env("AI_RETRY_BACKOFF_SECONDS", 0.25)
    ai_budget_usd: float = float(os.getenv("AI_BUDGET_USD", "20"))
    ai_input_price_per_million: float = float(os.getenv("AI_INPUT_PRICE_PER_MILLION", "0.35"))
    ai_output_price_per_million: float = float(os.getenv("AI_OUTPUT_PRICE_PER_MILLION", "0.53"))
    max_pdf_mb: int = int(os.getenv("MAX_PDF_MB", "100"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "2000"))

    def ensure_dirs(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

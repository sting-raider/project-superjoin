from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return (value if value else default).strip().rstrip("/")


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
    extraction_model: str = os.getenv("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    reasoning_model: str = os.getenv("REASONING_MODEL", "gemini-3.8-flash")
    vision_model: str = os.getenv("VISION_MODEL", "gemini-3.8-flash")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
    ai_timeout_seconds: int = int(os.getenv("AI_TIMEOUT_SECONDS", "90"))
    extraction_max_output_tokens: int = int(os.getenv("EXTRACTION_MAX_OUTPUT_TOKENS", "1200"))
    reasoning_max_output_tokens: int = int(os.getenv("REASONING_MAX_OUTPUT_TOKENS", "1200"))
    vision_max_output_tokens: int = int(os.getenv("VISION_MAX_OUTPUT_TOKENS", "1200"))
    ai_budget_usd: float = float(os.getenv("AI_BUDGET_USD", "20"))
    ai_input_price_per_million: float = float(os.getenv("AI_INPUT_PRICE_PER_MILLION", "0.35"))
    ai_output_price_per_million: float = float(os.getenv("AI_OUTPUT_PRICE_PER_MILLION", "0.53"))
    max_pdf_mb: int = int(os.getenv("MAX_PDF_MB", "100"))
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "2000"))

    def ensure_dirs(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

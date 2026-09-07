from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "demo")
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/project_superjoin.sqlite3"))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "data/uploads"))
    demo_mode: bool = os.getenv("DEMO_MODE", "true").lower() in {"1", "true", "yes", "on"}
    ai_base_url: str = os.getenv("AI_BASE_URL", "").rstrip("/")
    ai_api_key: str = os.getenv("AI_API_KEY", "")
    extraction_model: str = os.getenv("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    reasoning_model: str = os.getenv("REASONING_MODEL", "gemini-3.8-flash")
    vision_model: str = os.getenv("VISION_MODEL", "gemini-3.8-flash")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
    ai_budget_usd: float = float(os.getenv("AI_BUDGET_USD", "20"))

    def ensure_dirs(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()


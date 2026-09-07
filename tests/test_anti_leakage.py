from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.demo_data import (
    DEMO_CASES,
    DEMO_CLAIMS,
    DEMO_DOCUMENTS,
    DEMO_RELATIONSHIPS,
    DEMO_WORKSPACES,
)

CORE_PRODUCTION_MODULES = (
    "parser.py",
    "pipeline.py",
    "registry.py",
    "knowledge.py",
    "normalization.py",
    "main.py",
    "seed.py",
)
FRONTEND_PRODUCTION_FILES = ("web/src/main.jsx",)

# These are identifiers from the supplied evaluation corpus. Domain terms such
# as revenue remain valid open-vocabulary outputs, but production code may not
# branch on the corpus's named subjects, case IDs, or expected relationship cues.
FORBIDDEN_CORPUS_MARKERS = (
    "delhivery",
    "india macroeconomy",
    "suvir suren sujan",
    "first advance estimate",
    "second advance estimate",
    "clm-delhivery",
    "clm-rbi",
    "clm-imf",
    "case-corroboration",
)


def test_production_reasoning_is_starter_corpus_blind() -> None:
    app_dir = Path(__file__).parents[1] / "app"
    root = app_dir.parents[0]
    production_files = [app_dir / filename for filename in CORE_PRODUCTION_MODULES]
    production_files.extend(root / filename for filename in FRONTEND_PRODUCTION_FILES)
    production = "\n".join(path.read_text(encoding="utf-8").casefold() for path in production_files)
    for filename in CORE_PRODUCTION_MODULES:
        source = (app_dir / filename).read_text(encoding="utf-8").casefold()
        leaked = [marker for marker in FORBIDDEN_CORPUS_MARKERS if marker in source]
        assert not leaked, f"{filename} contains starter-corpus markers: {leaked}"
    for filename in FRONTEND_PRODUCTION_FILES:
        source = (root / filename).read_text(encoding="utf-8").casefold()
        leaked = [marker for marker in FORBIDDEN_CORPUS_MARKERS if marker in source]
        assert not leaked, f"{filename} contains starter-corpus markers: {leaked}"

    # Keep the hand-selected markers above readable, but also derive a second
    # guard from the recorded demo metadata. This catches newly added IDs,
    # values, predicates, subjects, relationship explanations, and case labels
    # without copying the metadata into the production test itself.
    records = (*DEMO_WORKSPACES, *DEMO_DOCUMENTS, *DEMO_CLAIMS, *DEMO_RELATIONSHIPS, *DEMO_CASES)
    distinctive_keys = {
        "id",
        "workspace_id",
        "document_id",
        "claim_a",
        "claim_b",
        "relationship_id",
        "subject",
        "predicate",
        "raw_value",
        "normalized_value",
        "scope",
        "name",
        "publisher",
        "source_url",
        "title",
        "description",
        "reason",
    }
    generic_metadata_values = {"consolidated", "director"}
    derived: set[str] = set()
    for record in records:
        for key, value in record.items():
            if key in distinctive_keys and isinstance(value, str):
                marker = value.strip().casefold()
                if len(marker) >= 6 and marker not in generic_metadata_values:
                    derived.add(marker)
            if key == "evidence" and isinstance(value, dict):
                for nested_key in ("document", "text"):
                    nested = value.get(nested_key)
                    if isinstance(nested, str) and len(nested.strip()) >= 12:
                        derived.add(nested.strip().casefold())
    leaked_derived = sorted(marker for marker in derived if marker in production)
    assert not leaked_derived, f"production source contains recorded demo metadata: {leaked_derived}"


def test_live_app_initializes_without_demo_artifact_modules(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    live_root = tmp_path / "live-copy"
    shutil.copytree(
        root / "app",
        live_root / "app",
        ignore=shutil.ignore_patterns("demo_data.py", "seed.py", "__pycache__"),
    )
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(live_root),
            "DEMO_MODE": "false",
            "DATABASE_PATH": str(tmp_path / "live.sqlite3"),
            "UPLOAD_DIR": str(tmp_path / "uploads"),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import app; from app.db import init_db; init_db(); print(app.title)"],
        cwd=live_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Project SuperJoin" in result.stdout


def test_runtime_provider_configuration_has_no_gemini_specific_logic() -> None:
    root = Path(__file__).parents[1]
    runtime_files = [
        *(root / "app").glob("*.py"),
        root / ".env.example",
        root / "compose.yaml",
        root / "web" / "src" / "main.jsx",
    ]
    leaked = [str(path.relative_to(root)) for path in runtime_files if "gemini" in path.read_text(encoding="utf-8").casefold()]
    assert not leaked, f"runtime provider surface contains Gemini-specific markers: {leaked}"

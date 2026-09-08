import os
import subprocess
import sys
from pathlib import Path

CORE_PRODUCTION_MODULES = (
    "parser.py", "pipeline.py", "registry.py", "knowledge.py", "normalization.py", "main.py",
)
FRONTEND_PRODUCTION_FILES = ("web/src/main.jsx",)

# Named subjects, fixed claim IDs, and case labels from the supplied evaluation
# corpus may live in eval fixtures, but never in runtime decision paths.
FORBIDDEN_CORPUS_MARKERS = (
    "delhivery", "india macroeconomy", "suvir suren sujan", "first advance estimate",
    "second advance estimate", "clm-delhivery", "clm-rbi", "clm-imf", "case-corroboration",
)


def test_production_reasoning_is_starter_corpus_blind() -> None:
    root = Path(__file__).parents[1]
    production_files = [root / "app" / name for name in CORE_PRODUCTION_MODULES]
    production_files.extend(root / name for name in FRONTEND_PRODUCTION_FILES)
    for path in production_files:
        source = path.read_text(encoding="utf-8").casefold()
        leaked = [marker for marker in FORBIDDEN_CORPUS_MARKERS if marker in source]
        assert not leaked, f"{path.relative_to(root)} contains starter-corpus markers: {leaked}"


def test_runtime_has_no_seed_or_replay_modules() -> None:
    root = Path(__file__).parents[1]
    assert not (root / "app" / "demo_data.py").exists()
    assert not (root / "app" / "seed.py").exists()
    production = "\n".join(
        path.read_text(encoding="utf-8").casefold()
        for path in [*(root / "app").glob("*.py"), root / "web" / "src" / "main.jsx"]
    )
    assert "/api/v1/demo" not in production
    assert "recorded demo replay" not in production


def test_fresh_process_initializes_with_zero_workspaces(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    database = tmp_path / "fresh.sqlite3"
    env = os.environ.copy()
    env.update({"PYTHONPATH": str(root), "DATABASE_PATH": str(database), "UPLOAD_DIR": str(tmp_path / "uploads")})
    code = "from app.db import connect,init_db; init_db(); c=connect(); print(c.execute('select count(*) from workspaces').fetchone()[0]); c.close()"
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"


def test_runtime_provider_configuration_has_no_gemini_specific_logic() -> None:
    root = Path(__file__).parents[1]
    runtime_files = [
        *(root / "app").glob("*.py"), root / ".env.example", root / "compose.yaml",
        root / "web" / "src" / "main.jsx",
    ]
    leaked = [str(path.relative_to(root)) for path in runtime_files if "gemini" in path.read_text(encoding="utf-8").casefold()]
    assert not leaked, f"runtime provider surface contains Gemini-specific markers: {leaked}"

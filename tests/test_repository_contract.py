from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_project_name_and_required_readme_sections_are_present() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# Project SuperJoin")
    for heading in (
        "## Setup and Run Instructions",
        "## Video Demo",
        "## Approach",
        "## Limitations and Next Steps",
        "## Additional Notes",
    ):
        assert heading in readme

    production_files = [
        path
        for path in (ROOT / "app").glob("*.py")
    ] + [ROOT / "web" / "src" / "main.jsx"]
    assert all("factledger" not in path.read_text(encoding="utf-8").casefold() for path in production_files)


def test_tracked_tree_contains_no_local_secrets_or_generated_runtime_data() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    forbidden_suffixes = (
        ".env",
        ".sqlite3",
        ".db",
        ".pyc",
    )
    forbidden_parts = ("/data/", "/uploads/", "/tmp/", "/node_modules/", "/dist/")
    tracked = [line.replace("\\", "/") for line in result.stdout.splitlines() if line]
    assert not [path for path in tracked if path.endswith(forbidden_suffixes)]
    assert not [path for path in tracked if any(part in f"/{path}/" for part in forbidden_parts)]
    assert not [path for path in tracked if Path(path).name in {".env", ".env.local"}]


def test_provider_configuration_contract_is_wired_through_compose() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    for role in ("EXTRACTION", "REASONING", "VISION", "EMBEDDING"):
        for field in ("BASE_URL", "API_KEY", "MODEL", "TIMEOUT_SECONDS"):
            variable = f"{role}_{field}"
            assert f"{variable}=" in env_example
            assert variable in compose
    assert "project_superjoin_data" in compose
    assert "neo4j" not in compose.casefold()
    for variable in (
        "AI_TIMEOUT_SECONDS",
        "AI_INPUT_PRICE_PER_MILLION",
        "AI_OUTPUT_PRICE_PER_MILLION",
        "AI_BUDGET_USD",
        "MAX_PDF_MB",
        "MAX_PDF_PAGES",
    ):
        assert f"{variable}=" in env_example
        assert variable in compose

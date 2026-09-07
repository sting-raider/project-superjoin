"""Check that the tracked tree is safe to package before a public release.

The check deliberately does not decide whether a publisher granted permission.
It verifies the repository-side half of that decision: source documents and
recordings are absent, generated runtime storage is not tracked, and the
rights audit still declares the release gate. A local evaluator can supply
source files outside Git and run the application without weakening this check.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs" / "DATASET_REDISTRIBUTION.md"

_SOURCE_SUFFIXES = {".pdf", ".mp4", ".mov", ".webm"}
_GENERATED_PARTS = {
    "data",
    "tmp",
    "uploads",
    ".extracted",
    "node_modules",
    "dist",
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def check() -> dict[str, Any]:
    paths = tracked_files()
    source_artifacts = [
        path
        for path in paths
        if Path(path).suffix.casefold() in _SOURCE_SUFFIXES
    ]
    generated_runtime = [
        path
        for path in paths
        if set(Path(path).parts) & _GENERATED_PARTS
    ]
    audit = AUDIT.read_text(encoding="utf-8")
    gate_phrases = (
        "do not commit source PDFs",
        "written permission",
        "unresolved",
    )
    missing_gate_phrases = [phrase for phrase in gate_phrases if phrase not in audit]
    return {
        "status": "clean" if not source_artifacts and not generated_runtime and not missing_gate_phrases else "blocked",
        "tracked_source_artifacts": source_artifacts,
        "tracked_generated_runtime": generated_runtime,
        "missing_rights_gate_phrases": missing_gate_phrases,
        "publication_permission": "not established; source-specific review remains required",
    }


def main() -> int:
    report = check()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())

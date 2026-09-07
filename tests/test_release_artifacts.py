from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_release_preflight_keeps_unapproved_source_material_out_of_git() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_artifacts.py")],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "clean"
    assert report["tracked_source_artifacts"] == []
    assert report["tracked_generated_runtime"] == []
    assert report["missing_rights_gate_phrases"] == []
    assert "not established" in report["publication_permission"]

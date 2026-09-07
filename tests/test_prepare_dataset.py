import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "prepare_dataset.py"
SPEC = importlib.util.spec_from_file_location("prepare_dataset", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
_match_candidate = MODULE._match_candidate


def test_manifest_title_matches_hyphenated_archive_filename() -> None:
    candidates = [
        Path("01-acme-prospectus-2026-excerpt.pdf"),
        Path("02-acme-annual-report-fy26-excerpt.pdf"),
        Path("03-acme-q4-fy26-earnings-presentation.pdf"),
    ]
    assert _match_candidate("Acme Annual Report FY26", candidates) == candidates[1]
    assert _match_candidate("Acme Prospectus 2026", candidates) == candidates[0]

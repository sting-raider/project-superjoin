from __future__ import annotations

from pathlib import Path

CORE_PRODUCTION_MODULES = (
    "parser.py",
    "pipeline.py",
    "registry.py",
    "knowledge.py",
    "normalization.py",
    "main.py",
    "seed.py",
)

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
    for filename in CORE_PRODUCTION_MODULES:
        source = (app_dir / filename).read_text(encoding="utf-8").casefold()
        leaked = [marker for marker in FORBIDDEN_CORPUS_MARKERS if marker in source]
        assert not leaked, f"{filename} contains starter-corpus markers: {leaked}"

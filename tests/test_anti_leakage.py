from __future__ import annotations

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
    production = "\n".join(
        (app_dir / filename).read_text(encoding="utf-8").casefold()
        for filename in CORE_PRODUCTION_MODULES
    )
    for filename in CORE_PRODUCTION_MODULES:
        source = (app_dir / filename).read_text(encoding="utf-8").casefold()
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

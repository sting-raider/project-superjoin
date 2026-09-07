from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_dataset_rights_audit_covers_every_starter_source_and_keeps_release_gate() -> None:
    audit = (ROOT / "docs" / "DATASET_REDISTRIBUTION.md").read_text(encoding="utf-8")
    for source in (
        "Delhivery prospectus",
        "Delhivery annual report",
        "Delhivery earnings presentation",
        "Economic Survey",
        "RBI Annual Report",
        "IMF Article IV report",
    ):
        assert source in audit
    for policy_url in (
        "https://www.delhivery.com/terms-and-conditions",
        "https://www.indiabudget.gov.in/budget2023-24/website-policies.php",
        "https://www.imf.org/en/about/copyright-and-terms",
    ):
        assert policy_url in audit
    assert "not cleared" in audit
    assert "unresolved" in audit
    assert "do not commit source PDFs" in audit
    assert "written permission" in audit

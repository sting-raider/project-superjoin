from app.pipeline import _claim_id


def test_claim_identity_is_stable_and_workspace_scoped() -> None:
    item = {"subject": "India", "predicate": "real_gdp_growth", "raw_value": "6.5%", "period": "FY26", "modality": "forecast", "scope": None}
    evidence = {"pdf_page": 3, "text": "India real GDP growth is projected at 6.5% in FY26."}
    first = _claim_id("india-macro", "doc-a", item, evidence)
    second = _claim_id("india-macro", "doc-a", item, evidence)
    other_workspace = _claim_id("delhivery", "doc-a", item, evidence)
    assert first == second
    assert first != other_workspace

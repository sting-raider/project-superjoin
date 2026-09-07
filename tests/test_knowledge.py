import json

from app.knowledge import compare_claim_pair


def _claim(**overrides):
    value = {
        "subject": "India",
        "predicate": "real_gdp_growth",
        "period": "FY25",
        "modality": "estimate",
        "value_type": "percentage",
        "normalized_value": "0.064",
        "evidence_json": json.dumps({"text": "first advance estimate"}),
    }
    value.update(overrides)
    return value


def test_vintage_difference_reconciles_instead_of_calling_it_false() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _claim(normalized_value="0.064"),
        _claim(normalized_value="0.065", evidence_json=json.dumps({"text": "second advance estimate"})),
    )
    assert relationship == "RECONCILES"


def test_role_ending_event_supersedes_prior_role() -> None:
    relationship, _, _, _ = compare_claim_pair(
        _claim(subject="Suvir Suren Sujan", predicate="director_role", period="2022-05-14", value_type="semantic", normalized_value="director", evidence_json=json.dumps({"text": "director"})),
        _claim(subject="Suvir Suren Sujan", predicate="director_role", period="2023-08-24", value_type="semantic", normalized_value="ceased", evidence_json=json.dumps({"text": "resigned"})),
    )
    assert relationship == "SUPERSEDES"

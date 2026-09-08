from decimal import Decimal

from app.normalization import (
    compare_numeric,
    normalize_modality,
    normalize_period_label,
    parse_interval,
    parse_numeric,
    parse_period,
)


def test_indian_money_units_normalize_to_base_amount() -> None:
    parsed = parse_numeric("₹8,142 crore")
    assert parsed["normalized"] == "81420000000"
    assert parsed["currency"] == "INR"
    assert parsed["value_type"] == "money"


def test_open_currency_and_scale_vocabulary() -> None:
    assert parse_numeric("€1.25 billion")["normalized"] == "1250000000"
    assert parse_numeric("£2 trillion")["currency"] == "GBP"


def test_percentage_is_stored_as_fraction() -> None:
    parsed = parse_numeric("6.4 per cent")
    assert parsed["normalized"] == "0.064"
    assert parsed["value_type"] == "percentage"


def test_parenthetical_negative() -> None:
    parsed = parse_numeric("(404)")
    assert Decimal(parsed["normalized"]) == Decimal(-404)


def test_fiscal_periods_are_stable() -> None:
    assert parse_period("for the year ended March 31, 2024") == "FY2024"
    assert parse_period("FY 2025/26 projection") == "FY2025/26"
    assert normalize_period_label("FY24") == "FY2023/24"
    assert normalize_period_label("Q1 FY 23") == "Q1FY2022/23"
    for spelling in ("FY26", "FY2025-26", "FY2025/26", "2025-26", "2025/26", "2025–26"):
        assert normalize_period_label(spelling) == "FY2025/26"
    assert normalize_period_label("FY2026/27") == "FY2026/27"
    assert normalize_period_label("nine months ended December 31, 2024") == "nine months ended December 31, 2024"


def test_source_modalities_have_a_stable_generic_vocabulary() -> None:
    assert normalize_modality("ASSERTED") == "reported"
    assert normalize_modality("actual") == "reported"
    assert normalize_modality("projected") == "forecast"
    assert normalize_modality("management_guidance") == "management_guidance"
    assert normalize_modality("asserted", "Demand is projected at 42 units next year.") == "forecast"
    assert normalize_modality("reported", "The first advance estimate is 42 units.") == "first_estimate"
    assert normalize_modality("asserted", "The second advance estimate is 43 units.") == "revised_estimate"


def test_rounding_comparison_is_explicit() -> None:
    assert compare_numeric("81415380000", "81420000000", 2, 0) == "rounding-compatible"
    assert compare_numeric("0.064", "0.065", 3, 3) == "different"
    assert compare_numeric("0.064", "0.065") == "different"
    assert compare_numeric("100", "110") == "different"
    assert compare_numeric("0.065", "0.066", 1, 1, percentage=True) == "different"


def test_percentage_points_and_basis_points_keep_distinct_semantics() -> None:
    assert parse_numeric("25 basis points")["normalized"] == "0.0025"
    points = parse_numeric("1.5 percentage points")
    assert points["normalized"] == "1.5"
    assert points["value_type"] == "percentage_points"


def test_missing_and_bound_values_are_not_silently_zero() -> None:
    assert parse_numeric("N/A")["value_type"] == "missing"
    bounded = parse_numeric("<= 6.5%")
    assert bounded["operator"] == "<="
    assert bounded["normalized"] == "0.065"


def test_explicit_date_interval_does_not_infer_publication_time() -> None:
    assert parse_interval("effective 2023-08-24 through 2024-03-31") == {
        "start": "2023-08-24",
        "end": "2024-03-31",
        "basis": "explicit-iso-range",
    }

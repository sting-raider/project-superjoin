from decimal import Decimal

from app.normalization import compare_numeric, parse_interval, parse_numeric, parse_period


def test_indian_money_units_normalize_to_base_amount() -> None:
    parsed = parse_numeric("₹8,142 crore")
    assert parsed["normalized"] == "81420000000"
    assert parsed["currency"] == "INR"


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


def test_rounding_comparison_is_explicit() -> None:
    assert compare_numeric("81415380000", "81420000000", 2, 0) == "rounding-compatible"
    assert compare_numeric("0.064", "0.065", 3, 3) == "different"
    assert compare_numeric("0.064", "0.065") == "different"
    assert compare_numeric("100", "110") == "different"


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

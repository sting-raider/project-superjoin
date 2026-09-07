from decimal import Decimal

from app.normalization import compare_numeric, parse_numeric, parse_period


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
    assert Decimal(parsed["normalized"]) == Decimal("-404")


def test_fiscal_periods_are_stable() -> None:
    assert parse_period("for the year ended March 31, 2024") == "FY2024"
    assert parse_period("FY 2025/26 projection") == "FY2025/26"


def test_rounding_comparison_is_explicit() -> None:
    assert compare_numeric("81415380000", "81420000000", 2, 0) == "rounding-compatible"
    assert compare_numeric("0.064", "0.065", 3, 3) == "different"


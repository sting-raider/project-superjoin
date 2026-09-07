from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

MONEY_SYMBOLS = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}
SCALE_FACTORS = {
    "thousand": Decimal(1000),
    "k": Decimal(1000),
    "lakh": Decimal(100000),
    "lac": Decimal(100000),
    "crore": Decimal(10000000),
    "cr": Decimal(10000000),
    "million": Decimal(1000000),
    "mn": Decimal(1000000),
    "billion": Decimal(1000000000),
    "bn": Decimal(1000000000),
    "trillion": Decimal(1000000000000),
}
MISSING_VALUES = {"", "-", "—", "–", "n/a", "na", "nil", "none", "not available", "not meaningful", "nm"}


def _decimal(value: str) -> Decimal | None:
    cleaned = value.replace(",", "").replace(" ", "").replace("−", "-").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def parse_numeric(raw: str) -> dict[str, Any]:
    """Parse a financial-looking scalar while retaining the display trace."""
    original = raw.strip()
    if original.lower() in MISSING_VALUES:
        return {"raw": original, "normalized": None, "value_type": "missing", "unit": None, "trace": ["missing-token"]}
    is_percentage = bool(re.search(r"%|per cent|percent", original, flags=re.IGNORECASE))
    is_percentage_points = bool(re.search(r"percentage\s*points?|pp\b", original, flags=re.IGNORECASE))
    is_basis_points = bool(re.search(r"basis\s*points?|\bbps?\b", original, flags=re.IGNORECASE))
    numbers = re.findall(r"(?:\(|[-−+])?\s*\d[\d,]*(?:\.\d+)?\s*\)?", original)
    values = [v for v in (_decimal(n) for n in numbers) if v is not None]
    if not values:
        return {"raw": original, "normalized": None, "value_type": "text", "trace": []}
    value = values[0]
    unit = None
    currency = None
    lower = original.lower()
    for key, factor in SCALE_FACTORS.items():
        if re.search(rf"\b{re.escape(key)}\b", lower):
            value *= factor
            unit = key
            break
    for token, code in MONEY_SYMBOLS.items():
        if token in lower:
            currency = code
            break
    if is_basis_points:
        normalized = value / Decimal(10000)
        value_type = "rate"
        display_unit = "bps"
    elif is_percentage and not is_percentage_points:
        normalized = value / Decimal(100)
        value_type = "percentage"
        display_unit = "%"
    elif is_percentage_points:
        normalized = value
        value_type = "percentage_points"
        display_unit = "pp"
    else:
        normalized = value
        value_type = "money" if currency else "number"
        display_unit = currency or unit
    if len(values) > 1 and re.search(r"-|to|–", original, flags=re.IGNORECASE):
        end = values[1]
        if is_basis_points:
            end /= Decimal(10000)
        elif is_percentage and not is_percentage_points:
            end /= Decimal(100)
        elif unit:
            end *= SCALE_FACTORS[unit]
        normalized_value: str | list[str] = [decimal_string(normalized) or "", decimal_string(end) or ""]
        value_type = "range"
    else:
        normalized_value = decimal_string(normalized)
    return {
        "raw": original,
        "normalized": normalized_value,
        "value_type": value_type,
        "unit": display_unit,
        "currency": currency,
        "precision": _precision(original),
        "operator": _bound_operator(original),
        "trace": [
            "parse-number",
            *([f"scale:{unit}"] if unit else []),
            *(["percent-to-fraction"] if is_percentage and not is_percentage_points else []),
            *(["basis-points-to-fraction"] if is_basis_points else []),
            *(["percentage-points-preserved"] if is_percentage_points else []),
            *([f"bound:{_bound_operator(original)}"] if _bound_operator(original) else []),
        ],
    }


def _bound_operator(raw: str) -> str | None:
    match = re.match(r"\s*(<=|>=|<|>|≤|≥)", raw)
    if not match:
        return None
    return {"≤": "<=", "≥": ">="}.get(match.group(1), match.group(1))


def _precision(raw: str) -> int | None:
    match = re.search(r"\d[\d,]*(?:\.(\d+))?", raw)
    return len(match.group(1)) if match and match.group(1) else 0 if match else None


def parse_period(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text.upper())
    for pattern in (r"FY20\d{2}(?:/\d{2})?", r"20\d{2}/\d{2}", r"Q[1-4]FY(?:20)?\d{2}"):
        match = re.search(pattern, compact)
        if match:
            value = match.group(0)
            return value.replace("Q", "Q")
    match = re.search(r"(?:YEAR|ENDED|ASAT).*?(20\d{2})", text, flags=re.IGNORECASE)
    return f"FY{match.group(1)}" if match else None


def parse_interval(text: str) -> dict[str, str | None]:
    """Return explicit effective/publication date hints without inventing dates."""

    iso_dates = re.findall(r"\b20\d{2}-\d{2}-\d{2}\b", text)
    if len(iso_dates) >= 2:
        return {"start": iso_dates[0], "end": iso_dates[1], "basis": "explicit-iso-range"}
    if len(iso_dates) == 1:
        return {"start": iso_dates[0], "end": iso_dates[0], "basis": "explicit-iso-date"}
    return {"start": None, "end": None, "basis": None}


def infer_modality(text: str) -> str | None:
    lower = text.lower()
    for keyword, modality in (
        ("projected", "forecast"),
        ("projection", "forecast"),
        ("forecast", "forecast"),
        ("guidance", "guidance"),
        ("estimate", "estimate"),
        ("actual", "actual"),
    ):
        if keyword in lower:
            return modality
    return None


def compare_numeric(a: str | None, b: str | None, precision_a: int | None = None, precision_b: int | None = None) -> str:
    if a is None or b is None:
        return "unknown"
    try:
        left, right = Decimal(a), Decimal(b)
    except InvalidOperation:
        return "unknown"
    if left == right:
        return "equal"
    # A source precision of zero is common when one document reports a rounded
    # whole-unit value (for example, INR crore) while another reports the same
    # fact in base currency.  Treat positive precision values as significant
    # digit hints and compare the resulting values proportionally.  This keeps
    # large-unit rounding compatible without making small percentages fuzzy.
    precisions = [p for p in (precision_a, precision_b) if p is not None and p >= 0]
    if precisions:
        scale = max(abs(left), abs(right), Decimal(1))
        significant_places = max(precisions)
        tolerance = scale * (Decimal(10) ** -significant_places) / 2
    else:
        scale = max(abs(left), abs(right))
        tolerance = Decimal("0.0005") if scale <= 1 else Decimal("0.5")
    return "rounding-compatible" if abs(left - right) <= tolerance else "different"

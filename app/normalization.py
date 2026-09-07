from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


MONEY_SYMBOLS = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "$": "USD", "usd": "USD"}
SCALE_FACTORS = {
    "thousand": Decimal("1000"),
    "k": Decimal("1000"),
    "lakh": Decimal("100000"),
    "lac": Decimal("100000"),
    "crore": Decimal("10000000"),
    "cr": Decimal("10000000"),
    "million": Decimal("1000000"),
    "mn": Decimal("1000000"),
    "billion": Decimal("1000000000"),
    "bn": Decimal("1000000000"),
}


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
    is_percentage = bool(re.search(r"%|per cent|percent", original, flags=re.I))
    numbers = re.findall(r"(?:\(|-)?\s*\d[\d,]*(?:\.\d+)?\s*\)?", original)
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
    if is_percentage:
        normalized = value / Decimal("100")
        value_type = "percentage"
        display_unit = "%"
    else:
        normalized = value
        value_type = "number"
        display_unit = currency or unit
    if len(values) > 1 and re.search(r"-|to|–", original, flags=re.I):
        end = values[1]
        if is_percentage:
            end /= Decimal("100")
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
        "trace": ["parse-number", *( [f"scale:{unit}"] if unit else []), *( ["percent-to-fraction"] if is_percentage else [])],
    }


def _precision(raw: str) -> int | None:
    match = re.search(r"\d[\d,]*(?:\.(\d+))?", raw)
    return len(match.group(1)) if match and match.group(1) else 0 if match else None


def parse_period(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text.upper())
    for pattern in (r"FY20\d{2}(?:/\d{2})?", r"20\d{2}/\d{2}", r"Q[1-4]FY20\d{2}"):
        match = re.search(pattern, compact)
        if match:
            value = match.group(0)
            return value.replace("Q", "Q")
    match = re.search(r"(?:YEAR|ENDED|ASAT).*?(20\d{2})", text, flags=re.I)
    return f"FY{match.group(1)}" if match else None


def infer_modality(text: str) -> str | None:
    lower = text.lower()
    for keyword, modality in (
        ("first advance estimate", "estimate"),
        ("second advance estimate", "estimate"),
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
    precisions = [p for p in (precision_a, precision_b) if p and p > 0]
    significant_places = max(precisions, default=0)
    scale = max(abs(left), abs(right), Decimal("1"))
    tolerance = scale * (Decimal(10) ** -significant_places) / 2
    return "rounding-compatible" if abs(left - right) <= tolerance else "different"

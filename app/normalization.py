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


def normalize_period_label(value: str | None) -> str | None:
    """Canonicalize explicit fiscal-year spellings to their start/end identity.

    ``FY26`` conventionally names the fiscal year ending in 2026, while
    ``FY2025/26`` and ``2025-26`` spell out the same interval.  Keeping the
    complete interval prevents the former from being confused with
    ``FY2026/27`` and makes cross-source comparisons deterministic.
    """

    if value is None or not str(value).strip():
        return None
    compact = re.sub(r"\s+", "", str(value).upper()).replace("–", "-").replace("—", "-")
    quarter = ""
    quarter_match = re.match(r"Q([1-4])", compact)
    if quarter_match:
        quarter = f"Q{quarter_match.group(1)}"
        compact = compact[quarter_match.end() :]
    compact = compact.removeprefix("FY")
    short = re.fullmatch(r"(\d{2})", compact)
    if short:
        end_year = 2000 + int(short.group(1))
        return f"{quarter}FY{end_year - 1}/{end_year % 100:02d}"
    single = re.fullmatch(r"(20\d{2})", compact)
    if single:
        end_year = int(single.group(1))
        return f"{quarter}FY{end_year - 1}/{end_year % 100:02d}"
    interval = re.fullmatch(r"(20\d{2})[-/](\d{2}|20\d{2})", compact)
    if interval:
        start_year = int(interval.group(1))
        raw_end = interval.group(2)
        end_year = int(raw_end) if len(raw_end) == 4 else (start_year // 100) * 100 + int(raw_end)
        if end_year == start_year + 1:
            return f"{quarter}FY{start_year}/{end_year % 100:02d}"
    return str(value).strip()


def normalize_modality(value: str | None, evidence_text: str | None = None) -> str | None:
    """Map provider wording to a small, explainable source-context taxonomy."""

    if value is None or not str(value).strip():
        return None
    key = re.sub(r"[^a-z]+", "_", str(value).casefold()).strip("_")
    aliases = {
        "asserted": "reported",
        "actual": "reported",
        "historical": "reported",
        "estimate": "estimated",
        "projection": "forecast",
        "projected": "forecast",
        "forecasted": "forecast",
        "mandatory": "required",
    }
    normalized = aliases.get(key, key)
    # Providers sometimes return a generic assertion label even though the
    # cited sentence states a more precise forecast or estimate status.  The
    # source wording is authoritative in that narrow case.
    if normalized in {"reported", "observed"} and evidence_text:
        evidence = re.sub(r"\s+", " ", evidence_text.casefold())
        if re.search(r"\b(?:first advance estimate|initial estimate)\b", evidence):
            return "first_estimate"
        if re.search(r"\b(?:second advance estimate|revised estimate|updated estimate)\b", evidence):
            return "revised_estimate"
        if re.search(r"\b(?:forecast(?:ed)?|project(?:ed|ion)|expected to)\b", evidence):
            return "forecast"
        if re.search(r"\b(?:estimate|estimated|preliminary)\b", evidence):
            return "estimated"
    return normalized


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

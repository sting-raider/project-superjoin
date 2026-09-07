from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any

import pdfplumber

from .normalization import infer_modality, parse_numeric, parse_period
from .security import security_flags


@dataclass
class ParsedPage:
    index: int
    width: float
    height: float
    text: str
    words: list[dict[str, Any]]
    quality_score: float
    flags: list[str]


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    sha256: str
    parser: str
    parser_version: str


def _quality(text: str, words: list[dict[str, Any]], page: Any) -> tuple[float, list[str]]:
    flags: list[str] = []
    stripped = text.strip()
    if len(stripped) < 80:
        flags.append("low-native-text")
    if "\ufffd" in text or "\x00" in text:
        flags.append("suspicious-glyphs")
    if not words:
        flags.append("no-word-geometry")
    density = len(stripped) / max(float(page.width * page.height), 1.0)
    if density < 0.00012:
        flags.append("sparse-page")
    score = 0.98
    score -= 0.22 * len([f for f in flags if f in {"low-native-text", "no-word-geometry"}])
    score -= 0.08 * len([f for f in flags if f not in {"low-native-text", "no-word-geometry"}])
    return max(0.05, min(1.0, score)), flags


def parse_pdf(data: bytes) -> ParsedDocument:
    pages: list[ParsedPage] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False) or []
            score, flags = _quality(text, words, page)
            pages.append(ParsedPage(index, float(page.width), float(page.height), text, words, score, flags))
    return ParsedDocument(pages, hashlib.sha256(data).hexdigest(), "pdfplumber", getattr(pdfplumber, "__version__", "unknown"))


def evidence_for(page: ParsedPage, start: int, end: int, excerpt: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", excerpt).strip()
    match_words = [word for word in page.words if normalized[:24].lower() in word.get("text", "").lower()]
    bbox = None
    if match_words:
        bbox = [
            min(float(word["x0"]) for word in match_words),
            min(float(word["top"]) for word in match_words),
            max(float(word["x1"]) for word in match_words),
            max(float(word["bottom"]) for word in match_words),
        ]
    return {
        "pdf_page": page.index + 1,
        "printed_page": _printed_page(normalized),
        "text": normalized[:1000],
        "start": start,
        "end": end,
        "bbox": bbox,
        "precision": "word-region" if bbox else "page-only",
        "parser": "pdfplumber",
        "quality_flags": page.flags,
    }


def _printed_page(text: str) -> str | None:
    matches = re.findall(r"(?:page\s+|\s)(\d{1,4})\s*$", text, flags=re.IGNORECASE)
    return matches[-1] if matches else None


def candidate_claims(page: ParsedPage) -> list[dict[str, Any]]:
    """High-recall deterministic candidates used with or without a model key."""
    text = page.text
    candidates: list[dict[str, Any]] = []
    patterns = [
        (r"(?P<label>revenue(?: from services| from operations| from contracts with customers| from customers)?)\D{0,100}(?P<value>(?:₹|Rs\.?|INR|\$)?\s*\(?[\d,]+(?:\.\d+)?\)?\s*(?:crore|cr|million|mn|billion|bn|%|per cent|percent)?)", "financial_metric"),
        (r"(?P<label>real gross domestic product(?: \(GDP\))?|real GDP growth|GDP growth)\D{0,100}(?P<value>\(?\d+(?:\.\d+)?\)?\s*(?:%|per cent|percent))", "macro_metric"),
        (r"(?P<label>EBITDA(?: margin)?|Adjusted EBITDA)\D{0,100}(?P<value>(?:₹|Rs\.?|INR)?\s*\(?[\d,]+(?:\.\d+)?\)?\s*(?:crore|cr|million|mn|billion|bn|%|per cent|percent)?)", "financial_metric"),
    ]
    for pattern, category in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw_value = match.group("value").strip()
            parsed = parse_numeric(raw_value)
            context_start = max(0, match.start() - 180)
            context_end = min(len(text), match.end() + 260)
            excerpt = re.sub(r"\s+", " ", text[context_start:context_end]).strip()
            flags = security_flags(excerpt)
            candidates.append({
                "subject": _subject(text),
                "predicate": re.sub(r"\s+", " ", match.group("label")).strip().lower().replace(" ", "_"),
                "raw_value": raw_value,
                "normalized_value": parsed.get("normalized"),
                "value_type": parsed.get("value_type", "text"),
                "unit": parsed.get("unit") or parsed.get("currency"),
                "precision": parsed.get("precision"),
                "normalization_trace": parsed.get("trace", []),
                "period": parse_period(excerpt),
                "modality": infer_modality(excerpt),
                "scope": "consolidated" if "consolidated" in excerpt.lower() else None,
                "evidence": {**evidence_for(page, context_start, context_end, excerpt), "security_flags": flags},
                "security_flags": flags,
                "category": category,
            })
    semantic_patterns = [
        (r"(?P<name>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,5}).{0,100}(?:resigned|ceased to be|appointed as).{0,100}(?P<role>director)", "director_role"),
    ]
    for pattern, predicate in semantic_patterns:
        for match in re.finditer(pattern, text):
            context_start = max(0, match.start() - 80)
            context_end = min(len(text), match.end() + 180)
            excerpt = re.sub(r"\s+", " ", text[context_start:context_end]).strip()
            flags = security_flags(excerpt)
            candidates.append({
                "subject": match.group("name").strip(),
                "predicate": predicate,
                "raw_value": excerpt,
                "normalized_value": excerpt,
                "value_type": "semantic",
                "unit": None,
                "period": parse_period(excerpt),
                "modality": "actual",
                "scope": None,
                "evidence": {**evidence_for(page, context_start, context_end, excerpt), "security_flags": flags},
                "security_flags": flags,
                "category": "semantic",
            })
    return _dedupe_candidates(candidates)


def _subject(text: str) -> str:
    for candidate in ("Delhivery", "India", "Indian economy"):
        if candidate.lower() in text.lower():
            return candidate
    return "Document subject"


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result = []
    for candidate in candidates:
        key = (candidate["subject"], candidate["predicate"], str(candidate["raw_value"]), candidate["period"])
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result

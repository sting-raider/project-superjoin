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
    """Domain-neutral numeric hints for the semantic extraction lane.

    These hints are deliberately open-vocabulary. They improve grounding and
    provide a limited offline fallback, but they never define which predicates
    the model may discover.
    """
    text = page.text
    candidates: list[dict[str, Any]] = []
    value_pattern = re.compile(
        r"(?P<value>(?:₹|Rs\.?|INR|USD|EUR|GBP|\$|€|£)?\s*\(?[-+]?\d[\d,]*(?:\.\d+)?\)?"
        r"\s*(?:trillion|billion|million|thousand|crore|lakh|bn|mn|cr|k|%|per\s+cent|percent|bps)?)",
        flags=re.IGNORECASE,
    )
    offset = 0
    for line in text.splitlines(keepends=True):
        compact_line = re.sub(r"\s+", " ", line).strip()
        if not compact_line or not re.search(r"[A-Za-z]", compact_line):
            offset += len(line)
            continue
        for match in value_pattern.finditer(line):
            raw_value = match.group("value").strip()
            if not _useful_numeric_hint(raw_value, compact_line):
                continue
            parsed = parse_numeric(raw_value)
            context_start = max(0, offset + match.start() - 180)
            context_end = min(len(text), offset + match.end() + 260)
            excerpt = re.sub(r"\s+", " ", text[context_start:context_end]).strip()
            label = _open_vocabulary_label(line[: match.start()])
            if not label:
                continue
            flags = security_flags(excerpt)
            candidates.append({
                "subject": "Document subject",
                "predicate": label,
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
                "category": "open_numeric_hint",
            })
        offset += len(line)
    return _dedupe_candidates(candidates)


def _open_vocabulary_label(prefix: str) -> str | None:
    words = re.findall(r"[A-Za-z][A-Za-z0-9&'/-]*", prefix)
    if not words:
        return None
    label = "_".join(words[-8:]).casefold().replace("-", "_").replace("/", "_")
    return re.sub(r"_+", "_", label).strip("_") or None


def _useful_numeric_hint(raw_value: str, line: str) -> bool:
    """Reject isolated page/year tokens while retaining arbitrary metrics."""

    has_measure = bool(
        re.search(
            r"(?:₹|Rs\.?|INR|USD|EUR|GBP|\$|€|£|trillion|billion|million|thousand|crore|lakh|bn|mn|cr|%|per\s+cent|percent|bps)",
            raw_value,
            flags=re.IGNORECASE,
        )
    )
    digits = re.sub(r"\D", "", raw_value)
    if has_measure:
        return True
    if len(digits) == 4 and digits.startswith(("19", "20")):
        return False
    return len(line.split()) >= 3 and bool(re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]", line))


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result = []
    for candidate in candidates:
        key = (candidate["subject"], candidate["predicate"], str(candidate["raw_value"]), candidate["period"])
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result

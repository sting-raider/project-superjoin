from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import pdfplumber

from .config import settings
from .normalization import infer_modality, parse_numeric, parse_period
from .parser_routing import requires_local_ocr
from .security import security_flags

logger = logging.getLogger(__name__)


@dataclass
class ParsedBlock:
    id: str
    kind: str
    text: str
    bbox: list[float] | None
    start: int
    end: int


@dataclass
class ParsedPage:
    index: int
    width: float
    height: float
    text: str
    words: list[dict[str, Any]]
    quality_score: float
    flags: list[str]
    blocks: list[ParsedBlock] = field(default_factory=list)
    disposition: str = "native"
    parser: str = "unknown"
    parser_version: str = "unknown"
    parser_config_hash: str = ""


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    sha256: str
    parser: str
    parser_version: str
    parser_config_hash: str = ""


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


def parse_pdf(data: bytes, backend: str | None = None) -> ParsedDocument:
    """Parse a PDF through the configured native-first backend.

    LiteParse is the production default. Its complexity metadata routes only
    pages with a genuinely unusable native text layer through bounded local
    OCR. pdfplumber remains available as an explicit operational fallback.
    """

    selected = (backend or settings.parser_backend).strip().lower()
    if selected == "pdfplumber":
        return _parse_pdfplumber(data)
    if selected != "liteparse":
        raise ValueError(f"Unsupported parser backend: {selected}")
    try:
        return _parse_liteparse(data)
    except Exception as exc:  # noqa: BLE001 - explicit operational fallback boundary
        # A parser backend failure must not make an otherwise valid upload
        # unusable. The selected backend and config remain visible in the
        # resulting parser identity and therefore cannot reuse its checkpoints.
        logger.warning("LiteParse failed; using pdfplumber fallback: %s", exc)
        return _parse_pdfplumber(data, parser_name="pdfplumber-fallback")


def _parse_pdfplumber(data: bytes, parser_name: str = "pdfplumber") -> ParsedDocument:
    pages: list[ParsedPage] = []
    config_hash = _parser_config_hash(parser_name, {})
    parser_version = getattr(pdfplumber, "__version__", "unknown")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for index, page in enumerate(pdf.pages):
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            words = page.extract_words(x_tolerance=1, y_tolerance=3, keep_blank_chars=False) or []
            score, flags = _quality(text, words, page)
            disposition = (
                "vision-required"
                if {"low-native-text", "no-word-geometry"}.intersection(flags)
                else "native"
            )
            pages.append(
                ParsedPage(
                    index,
                    float(page.width),
                    float(page.height),
                    text,
                    words,
                    score,
                    flags,
                    disposition=disposition,
                    parser=parser_name,
                    parser_version=parser_version,
                    parser_config_hash=config_hash,
                )
            )
    return ParsedDocument(
        pages,
        hashlib.sha256(data).hexdigest(),
        parser_name,
        parser_version,
        config_hash,
    )


def _parse_liteparse(data: bytes) -> ParsedDocument:
    from liteparse import LiteParse

    native_options = {
        "ocr_enabled": False,
        "output_format": "text",
        "quiet": True,
        "include_complexity": True,
        "extract_blocks": True,
        "extract_text_metadata": True,
        "emit_word_boxes": True,
        "pool_size": max(1, settings.parser_pool_size),
        "parse_timeout": max(1, settings.parser_timeout_seconds),
    }
    native_parser = LiteParse(**native_options)
    try:
        native_parser.warm_up()
        result = native_parser.parse(data)
    finally:
        native_parser.close()

    ocr_numbers: list[int] = []
    if settings.local_ocr_enabled:
        for page in result.pages:
            complexity = page.complexity
            reasons = list(complexity.reasons if complexity else [])
            if requires_local_ocr(
                reasons,
                native_text_length=len(page.text.strip()),
                is_garbled=bool(complexity and complexity.is_garbled),
            ):
                ocr_numbers.append(page.page_num)
    ocr_pages = _liteparse_ocr_pages(data, ocr_numbers)
    parser_version = _package_version("liteparse")
    config = {
        "backend": "liteparse",
        "version": parser_version,
        "pool_size": settings.parser_pool_size,
        "timeout_seconds": settings.parser_timeout_seconds,
        "local_ocr_enabled": settings.local_ocr_enabled,
        "ocr_language": settings.local_ocr_language,
        "ocr_dpi": settings.local_ocr_dpi,
        "ocr_slice_pages": settings.local_ocr_slice_pages,
    }
    config_hash = _parser_config_hash("liteparse", config)
    pages: list[ParsedPage] = []
    for native_page in result.pages:
        page = ocr_pages.get(native_page.page_num) or native_page
        locally_ocrd = native_page.page_num in ocr_pages and bool(page.text.strip())
        was_candidate = native_page.page_num in ocr_numbers
        disposition = (
            "local-ocr"
            if locally_ocrd
            else "vision-required"
            if was_candidate
            else "native"
        )
        text, blocks = _liteparse_layout(page, native_page.page_num)
        words = _liteparse_words(page)
        reasons = list(
            native_page.complexity.reasons if native_page.complexity else []
        )
        flags = [f"complexity:{reason}" for reason in reasons]
        if len(text.strip()) < 80:
            flags.append("low-native-text")
        if not words:
            flags.append("no-word-geometry")
        if locally_ocrd:
            flags.append("local-ocr")
        score = 0.96
        if disposition == "local-ocr":
            score = 0.82
        elif disposition == "vision-required":
            score = 0.35
        page_parser = "liteparse-local-ocr" if locally_ocrd else "liteparse"
        pages.append(
            ParsedPage(
                index=native_page.page_num - 1,
                width=float(page.width),
                height=float(page.height),
                text=text,
                words=words,
                quality_score=score,
                flags=flags,
                blocks=blocks,
                disposition=disposition,
                parser=page_parser,
                parser_version=parser_version,
                parser_config_hash=config_hash,
            )
        )
    return ParsedDocument(
        pages,
        hashlib.sha256(data).hexdigest(),
        "liteparse",
        parser_version,
        config_hash,
    )


def _liteparse_ocr_pages(data: bytes, page_numbers: list[int]) -> dict[int, Any]:
    if not page_numbers:
        return {}
    from liteparse import LiteParse

    recovered: dict[int, Any] = {}
    slice_size = max(1, settings.local_ocr_slice_pages)
    for start in range(0, len(page_numbers), slice_size):
        page_slice = page_numbers[start : start + slice_size]
        parser = LiteParse(
            ocr_enabled=True,
            ocr_language=settings.local_ocr_language,
            target_pages=",".join(str(number) for number in page_slice),
            dpi=max(72, settings.local_ocr_dpi),
            output_format="text",
            quiet=True,
            num_workers=max(1, min(settings.local_ocr_workers, len(page_slice))),
            emit_word_boxes=True,
            extract_blocks=True,
            continue_on_page_error=True,
            pool_size=1,
            parse_timeout=max(1, settings.parser_timeout_seconds),
        )
        try:
            parser.warm_up()
            parsed = parser.parse(data)
            recovered.update(
                {
                    page.page_num: page
                    for page in parsed.pages
                    if page.text and page.text.strip()
                }
            )
        except Exception as exc:  # noqa: BLE001 - an OCR slice may fail independently
            # Unrecovered pages remain explicitly vision-required.
            logger.warning("LiteParse OCR failed for pages %s: %s", page_slice, exc)
            continue
        finally:
            parser.close()
    return recovered


def _liteparse_words(page: Any) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for item in page.text_items or []:
        for word in item.words or []:
            words.append(
                {
                    "text": str(word.text),
                    "x0": float(word.x),
                    "top": float(word.y),
                    "x1": float(word.x + word.width),
                    "bottom": float(word.y + word.height),
                }
            )
    return words


def _liteparse_layout(page: Any, page_number: int) -> tuple[str, list[ParsedBlock]]:
    parts: list[str] = []
    blocks: list[ParsedBlock] = []
    for index, block in enumerate(page.blocks or []):
        block_text = _liteparse_block_text(block).strip()
        if not block_text:
            continue
        if parts:
            parts.append("\n\n")
        start = sum(len(part) for part in parts)
        parts.append(block_text)
        end = start + len(block_text)
        blocks.append(
            ParsedBlock(
                id=str(block.id or f"p{page_number}-b{index}"),
                kind=str(block.kind or "text"),
                text=block_text,
                bbox=_liteparse_bbox(block.bbox),
                start=start,
                end=end,
            )
        )
    text = "".join(parts)
    return (text or str(page.text or ""), blocks)


def _liteparse_block_text(block: Any) -> str:
    if block.text:
        return str(block.text)
    if block.lines:
        return "\n".join(str(line) for line in block.lines)
    rows: list[str] = []
    if block.header:
        rows.append(" | ".join(str(cell.text) for cell in block.header))
    rows.extend(
        " | ".join(str(cell.text) for cell in row) for row in (block.rows or [])
    )
    return "\n".join(rows)


def _liteparse_bbox(rect: Any) -> list[float] | None:
    if rect is None:
        return None
    return [
        float(rect.x),
        float(rect.y),
        float(rect.x + rect.width),
        float(rect.y + rect.height),
    ]


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _parser_config_hash(backend: str, config: dict[str, Any]) -> str:
    payload = json.dumps(
        {"backend": backend, **config}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def evidence_for(page: ParsedPage, start: int, end: int, excerpt: str) -> dict[str, Any]:
    normalized = re.sub(r"\s+", " ", excerpt).strip()
    overlapping_blocks = [
        block for block in page.blocks if block.start < end and start < block.end
    ]
    bbox = _union_bbox([block.bbox for block in overlapping_blocks])
    match_tokens = set(re.findall(r"[a-z0-9]+", normalized.casefold())[:12])
    match_words = [
        word
        for word in page.words
        if str(word.get("text") or "").casefold() in match_tokens
    ]
    if bbox is None and match_words:
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
        "parser": page.parser,
        "quality_flags": page.flags,
    }


def _union_bbox(boxes: list[list[float] | None]) -> list[float] | None:
    present = [box for box in boxes if box is not None]
    if not present:
        return None
    return [
        min(box[0] for box in present),
        min(box[1] for box in present),
        max(box[2] for box in present),
        max(box[3] for box in present),
    ]


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
            if _overlaps_date(line, match.start(), match.end()):
                continue
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
    # Prefer the final metric phrase in a sentence or table row. This is an
    # intentionally shallow hint normalizer: the semantic extractor remains
    # responsible for discovering and naming claims.
    prefix = re.split(r"[,;|]", prefix)[-1]
    words = re.findall(r"[A-Za-z][A-Za-z0-9&'/-]*", prefix)
    if not words:
        return None
    cue_words = {
        "and",
        "are",
        "ended",
        "has",
        "have",
        "is",
        "reported",
        "shows",
        "stood",
        "was",
        "were",
        "with",
    }
    for index in range(len(words) - 1, -1, -1):
        if words[index].casefold() in cue_words and index < len(words) - 1:
            words = words[index + 1 :]
            break
    while words and words[-1].casefold() in {"at", "by", "effective", "for", "in", "of", "on", "to"}:
        words.pop()
    words = [word for word in words if not re.fullmatch(r"(?:fy)?\d{2,4}", word, flags=re.IGNORECASE)]
    if not words or not any(len(word) >= 3 for word in words):
        return None
    label = "_".join(words[-8:]).casefold().replace("-", "_").replace("/", "_")
    return re.sub(r"_+", "_", label).strip("_") or None


def _overlaps_date(line: str, start: int, end: int) -> bool:
    date_patterns = (
        r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+\d{1,2}(?:,\s*\d{4})?\b",
    )
    return any(
        match.start() < end and start < match.end()
        for pattern in date_patterns
        for match in re.finditer(pattern, line, flags=re.IGNORECASE)
    )


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

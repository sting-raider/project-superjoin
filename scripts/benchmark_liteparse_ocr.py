"""Measure bounded selective LiteParse OCR after the native fast path."""

from __future__ import annotations

import argparse
import json
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

from app.parser_routing import requires_local_ocr


def _ranges(numbers: list[int]) -> list[list[int]]:
    return [numbers[index : index + 8] for index in range(0, len(numbers), 8)]


def _expression(numbers: list[int]) -> str:
    return ",".join(str(number) for number in numbers)


def benchmark_file(path: Path, timeout_seconds: float) -> dict[str, Any]:
    from liteparse import LiteParse

    native_parser = LiteParse(
        ocr_enabled=False,
        output_format="text",
        quiet=True,
        include_complexity=True,
        emit_word_boxes=True,
        pool_size=1,
        parse_timeout=timeout_seconds,
    )
    try:
        native_parser.warm_up()
        started = time.perf_counter()
        native = native_parser.parse(path.read_bytes())
        native_seconds = time.perf_counter() - started
    finally:
        native_parser.close()
    candidates = [
        page.page_num
        for page in native.pages
        if page.complexity
        and requires_local_ocr(
            page.complexity.reasons,
            native_text_length=page.complexity.text_length,
            is_garbled=page.complexity.is_garbled,
        )
    ]
    ocr_pages: dict[int, Any] = {}
    errors: list[dict[str, Any]] = []
    ocr_seconds = 0.0
    for page_slice in _ranges(candidates):
        parser = LiteParse(
            ocr_enabled=True,
            ocr_language="eng",
            target_pages=_expression(page_slice),
            dpi=150,
            output_format="text",
            quiet=True,
            num_workers=min(2, len(page_slice)),
            emit_word_boxes=True,
            continue_on_page_error=True,
            pool_size=1,
            parse_timeout=timeout_seconds,
        )
        try:
            parser.warm_up()
            started = time.perf_counter()
            result = parser.parse(path.read_bytes())
            ocr_seconds += time.perf_counter() - started
            ocr_pages.update({page.page_num: page for page in result.pages})
            errors.extend(
                {"page": error.page_num, "error": error.message}
                for error in result.page_errors
            )
        except Exception as exc:  # noqa: BLE001 - benchmark records backend failures
            errors.append({"pages": page_slice, "error": str(exc)[:500]})
        finally:
            parser.close()
    recovered = [
        number
        for number in candidates
        if number in ocr_pages and bool(ocr_pages[number].text.strip())
    ]
    remaining = [number for number in candidates if number not in recovered]
    return {
        "file": path.name,
        "pages": native.num_pages,
        "native_seconds": round(native_seconds, 6),
        "native_characters": sum(len(page.text) for page in native.pages),
        "ocr_candidate_pages": candidates,
        "ocr_slices": len(_ranges(candidates)),
        "ocr_seconds": round(ocr_seconds, 6),
        "ocr_pages_returned": sorted(ocr_pages),
        "ocr_pages_recovered": recovered,
        "ocr_characters": sum(len(ocr_pages[number].text) for number in recovered),
        "ocr_positioned_items": sum(
            len(ocr_pages[number].text_items) for number in recovered
        ),
        "remaining_vision_pages": remaining,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    report = {
        "schema_version": "1.0",
        "benchmark": "liteparse-selective-local-ocr",
        "liteparse_version": version("liteparse"),
        "slice_page_limit": 8,
        "mode": "native first; OCR only quality-routed page slices; vision absent",
        "files": [benchmark_file(path, args.timeout_seconds) for path in args.paths],
    }
    report["wall_seconds"] = round(time.perf_counter() - started, 6)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()

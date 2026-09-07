"""Bounded native parser comparison for locally supplied PDFs.

This benchmark never downloads or publishes a source file. It records native
text/word counts, page timing, rendering support, and peak Python allocations;
source-verified grounding scores are supplied separately when annotations are
available.
"""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from pathlib import Path
from typing import Any

import pdfplumber


def _pdfplumber(path: Path, page_limit: int | None) -> dict[str, Any]:
    started = time.perf_counter()
    pages = 0
    chars = 0
    words = 0
    empty = 0
    tracemalloc.start()
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:page_limit]:
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            pages += 1
            chars += len(text)
            words += len(page.extract_words(x_tolerance=1, y_tolerance=3) or [])
            empty += int(not text.strip())
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"backend": "pdfplumber", "version": getattr(pdfplumber, "__version__", "unknown"), "pages": pages, "characters": chars, "words": words, "empty_pages": empty, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "peak_python_bytes": peak}


def _pymupdf(path: Path, page_limit: int | None) -> dict[str, Any]:
    try:
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            import fitz  # type: ignore
    except ImportError:
        return {"backend": "pymupdf", "available": False, "reason": "PyMuPDF is not installed for this local benchmark."}
    started = time.perf_counter()
    pages = chars = words = empty = 0
    tracemalloc.start()
    document = fitz.open(path)
    try:
        for page in list(document)[:page_limit]:
            text = page.get_text("text") or ""
            pages += 1
            chars += len(text)
            words += len(page.get_text("words") or [])
            empty += int(not text.strip())
    finally:
        document.close()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"backend": "pymupdf", "version": getattr(fitz, "VersionBind", "unknown"), "available": True, "pages": pages, "characters": chars, "words": words, "empty_pages": empty, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "peak_python_bytes": peak, "license_note": "AGPL or commercial; do not add to runtime without a project-license decision."}


def _pypdfium2(path: Path, page_limit: int | None) -> dict[str, Any]:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return {"backend": "pypdfium2-render", "available": False}
    started = time.perf_counter()
    document = pdfium.PdfDocument(str(path))
    pages = min(len(document), page_limit or len(document))
    for index in range(pages):
        page = document[index]
        bitmap = page.render(scale=0.25)
        bitmap.close()
        page.close()
    document.close()
    return {"backend": "pypdfium2-render", "version": getattr(pdfium, "__version__", "unknown"), "available": True, "pages": pages, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2), "note": "Rendering backend; layout/text metrics come from pdfplumber."}


def benchmark(paths: list[Path], page_limit: int | None) -> dict[str, Any]:
    files = []
    for path in paths:
        files.append({"file": path.name, "bytes": path.stat().st_size, "results": [_pdfplumber(path, page_limit), _pymupdf(path, page_limit), _pypdfium2(path, page_limit)]})
    return {"benchmark": "parser-selection-v1", "page_limit": page_limit, "files": files, "decision": {"runtime_primary": "pdfplumber", "reason": "Retain the compatible pdfplumber stack until the complete six-document source-verified comparison and licensing review are available; PyMuPDF remains a local comparison candidate only."}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--page-limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = benchmark(args.paths, args.page_limit)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()

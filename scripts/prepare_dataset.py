"""Prepare a local starter corpus without publishing third-party PDFs.

The preparation step is intentionally conservative: it accepts a local
directory or archive, computes file hashes and page counts, and fails when a
manifest entry cannot be matched. It never downloads a replacement document
or changes the tracked manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "datasets" / "starter" / "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _page_count(path: Path) -> int | None:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(path), strict=False).pages)
    except Exception:  # noqa: BLE001 - optional parser must not block manifest creation
        return None


def _files(input_path: Path, scratch: Path) -> list[Path]:
    if input_path.is_dir():
        return list(input_path.rglob("*.pdf"))
    if input_path.suffix.lower() == ".zip":
        scratch.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(input_path) as archive:
            archive.extractall(scratch)
        return list(scratch.rglob("*.pdf"))
    if input_path.suffix.lower() == ".pdf":
        return [input_path]
    raise SystemExit(f"Unsupported input: {input_path}")


def prepare(input_path: Path, output_dir: Path) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    candidates = _files(input_path, output_dir / ".extracted")
    output: dict[str, Any] = {
        "manifest_version": manifest["manifest_version"],
        "project": "Project SuperJoin",
        "input": str(input_path.resolve()),
        "verified": False,
        "documents": [],
    }
    if not candidates:
        raise SystemExit("No PDF files found in the supplied input")
    for item in manifest["documents"]:
        title_tokens = {token.lower() for token in item["title"].replace("–", " ").split() if len(token) > 3}
        matches = [path for path in candidates if title_tokens & {token.lower() for token in path.stem.replace("_", " ").split()}]
        if len(matches) != 1:
            output["documents"].append({"id": item["id"], "status": "unmatched", "matches": [str(path) for path in matches]})
            continue
        path = matches[0]
        output["documents"].append({"id": item["id"], "status": "prepared", "path": str(path.resolve()), "sha256": _sha256(path), "page_count": _page_count(path), "expected_pages": item["expected_pages"]})
    output["verified"] = len(output["documents"]) == len(manifest["documents"]) and all(
        entry["status"] == "prepared" and entry["page_count"] in (None, entry["expected_pages"])
        for entry in output["documents"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "prepared-manifest.json"
    destination.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "starter")
    args = parser.parse_args()
    result = prepare(args.input, args.output)
    print(json.dumps(result, indent=2))
    if not result["verified"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

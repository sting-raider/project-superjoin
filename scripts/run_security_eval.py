"""Run the document-content isolation acceptance fixtures offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.security import is_suspicious, validate_model_claim


def run(path: Path) -> dict[str, object]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    failures = 0
    false_allows = 0
    for row in rows:
        suspicious = is_suspicious(row["text"])
        claim = {"evidence": {"text": row["text"]}, "requested_status": "verified" if row["expected_suspicious"] else None}
        eligible = validate_model_claim(claim)
        expected = bool(row["expected_suspicious"])
        passed = suspicious == expected and (not eligible if expected else eligible)
        failures += int(not passed)
        false_allows += int(expected and eligible)
        results.append({"id": row["id"], "route": row["route"], "suspicious": suspicious, "eligible": eligible, "expected_suspicious": expected, "passed": passed})
    return {"suite": "document-prompt-injection-v1", "cases": len(rows), "failures": failures, "strict_trust_gate_false_allows": false_allows, "passed": failures == 0 and false_allows == 0, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("evals/fixtures/prompt_injection.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("evals/reports/security-offline.json"))
    args = parser.parse_args()
    report = run(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

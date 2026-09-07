from __future__ import annotations

import re
from typing import Any

INSTRUCTION_PATTERNS = (
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"disregard\s+(?:the\s+)?system\s+message",
    r"return\s+[^.]{0,100}\b(?:verified|approved|true)\b",
    r"mark\s+(?:this|the)\s+(?:claim|value)\s+as\s+verified",
    r"(?:exfiltrate|leak|print|reveal)\s+(?:the\s+)?(?:key|secret|prompt|credential)",
    r"(?:assistant|developer|system)\s*:\s*",
)
COMPILED_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in INSTRUCTION_PATTERNS)


def security_flags(text: str) -> list[str]:
    flags: list[str] = []
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            flags.append("document-instruction")
    if re.search(r"https?://\S+", text, re.IGNORECASE) and re.search(r"(?:visit|open|fetch|send)\b", text, re.IGNORECASE):
        flags.append("document-exfiltration-url")
    return sorted(set(flags))


def is_suspicious(text: str) -> bool:
    return bool(security_flags(text))


def untrusted_document_block(text: str) -> str:
    """Wrap source material so providers cannot confuse it with instructions."""

    return "<untrusted_document_content>\n" + text + "\n</untrusted_document_content>"


def validate_model_claim(item: dict[str, Any]) -> bool:
    evidence = item.get("evidence") or {}
    text = str(evidence.get("text") or "")
    return bool(text) and not is_suspicious(text) and not item.get("requested_status") in {"verified", "approved"}

from __future__ import annotations

import hashlib
import json
from typing import Any

from .db import utc_now


def stable_anchor_hash(document_id: str, evidence: dict[str, Any]) -> str:
    """Return a content-derived identity for an evidence anchor.

    The hash intentionally includes location and kind. The same quotation on
    two pages is two anchors, while retrying one document cannot create a new
    anchor row for the same source region.
    """

    payload = {
        "document_id": document_id,
        "pdf_page": evidence.get("pdf_page"),
        "printed_page": evidence.get("printed_page"),
        "kind": evidence.get("kind", "text"),
        "text": evidence.get("text", ""),
        "start": evidence.get("start"),
        "end": evidence.get("end"),
        "bbox": evidence.get("bbox"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def page_artifact_id(document_id: str, page_number: int) -> str:
    return f"page-{document_id}-{page_number}"


def persist_page_artifacts(conn: Any, document_id: str, parsed: Any) -> None:
    for page in parsed.pages:
        number = page.index + 1
        conn.execute(
            """INSERT OR IGNORE INTO page_artifacts
            (id,document_id,page_number,width,height,native_text,parser,parser_version,parser_config_hash,quality_score,quality_flags_json,disposition,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                page_artifact_id(document_id, number),
                document_id,
                number,
                page.width,
                page.height,
                page.text,
                page.parser or parsed.parser,
                page.parser_version or parsed.parser_version,
                page.parser_config_hash or parsed.parser_config_hash,
                page.quality_score,
                json.dumps(page.flags),
                page.disposition,
                utc_now(),
            ),
        )
        conn.execute(
            """UPDATE page_artifacts SET width=?,height=?,native_text=?,parser=?,parser_version=?,parser_config_hash=?,quality_score=?,quality_flags_json=?,disposition=?
            WHERE id=?""",
            (
                page.width,
                page.height,
                page.text,
                page.parser or parsed.parser,
                page.parser_version or parsed.parser_version,
                page.parser_config_hash or parsed.parser_config_hash,
                page.quality_score,
                json.dumps(page.flags),
                page.disposition,
                page_artifact_id(document_id, number),
            ),
        )


def persist_anchor(conn: Any, document_id: str, evidence: dict[str, Any]) -> str:
    anchor_hash = stable_anchor_hash(document_id, evidence)
    anchor_id = f"anchor-{anchor_hash[:20]}"
    conn.execute(
        """INSERT OR IGNORE INTO evidence_anchors
        (id,document_id,page_artifact_id,pdf_page,printed_page,kind,text,start_offset,end_offset,bbox_json,precision,parser,anchor_hash,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            anchor_id,
            document_id,
            page_artifact_id(document_id, int(evidence.get("pdf_page") or 1)),
            int(evidence.get("pdf_page") or 1),
            evidence.get("printed_page"),
            evidence.get("kind", "text"),
            str(evidence.get("text") or ""),
            evidence.get("start"),
            evidence.get("end"),
            json.dumps(evidence.get("bbox")) if evidence.get("bbox") is not None else None,
            evidence.get("precision", "page-only"),
            evidence.get("parser"),
            anchor_hash,
            utc_now(),
        ),
    )
    return anchor_id


def persist_interpretation(conn: Any, claim: dict[str, Any], claim_id: str, created_at: str) -> str:
    interpretation_id = f"interp-{claim_id}-1"
    conn.execute(
        """INSERT OR IGNORE INTO claim_interpretations
        (id,claim_id,version,subject,predicate,normalized_value,value_type,unit,period,modality,scope,normalization_trace_json,entity_status,predicate_status,eligibility,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            interpretation_id,
            claim_id,
            1,
            str(claim.get("subject") or "Document subject"),
            str(claim.get("predicate") or "unknown_predicate"),
            _storage_scalar(claim.get("normalized_value")),
            str(claim.get("value_type") or "text"),
            _storage_scalar(claim.get("unit")),
            _storage_scalar(claim.get("period")),
            _storage_scalar(claim.get("modality")),
            _storage_scalar(claim.get("scope")),
            json.dumps(claim.get("normalization_trace") or [], ensure_ascii=False),
            "unresolved",
            "unresolved",
            "eligible" if claim.get("evidence") else "quarantined",
            created_at,
        ),
    )
    return interpretation_id


def _storage_scalar(value: Any) -> str | int | float | None:
    """Keep heterogeneous provider fields inspectable without leaking containers to SQLite."""

    if value is None or isinstance(value, (str, int, float)):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

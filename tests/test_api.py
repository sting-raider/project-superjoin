import os
from pathlib import Path

os.environ["DATABASE_PATH"] = str(Path("tmp") / "test-api.sqlite3")
os.environ["UPLOAD_DIR"] = str(Path("tmp") / "test-uploads")
os.environ["DEMO_MODE"] = "true"

from fastapi.testclient import TestClient

from app.main import app


def test_demo_health_and_required_cases() -> None:
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        cases = client.get("/api/v1/cases").json()["items"]
        assert [case["number"] for case in cases] == [1, 2, 3, 4]


def test_strict_resolver_blocks_contested_forecast() -> None:
    with TestClient(app) as client:
        result = client.get("/api/v1/resolve", params={"workspace_id": "india-macro", "subject": "India", "predicate": "real_gdp_growth", "period": "FY26"})
        payload = result.json()
        assert payload["decision"] == "block"
        assert payload["safe_to_use"] is False


def test_dynamic_registries_are_visible_without_overmerging() -> None:
    with TestClient(app) as client:
        entities = client.get("/api/v1/entities", params={"workspace_id": "delhivery"}).json()["items"]
        predicates = client.get("/api/v1/predicates", params={"workspace_id": "delhivery"}).json()["items"]
        assert {item["canonical_name"] for item in entities} >= {"Delhivery", "Suvir Suren Sujan"}
        keys = {item["key"] for item in predicates}
        assert "revenue_from_services" in keys
        assert "revenue_from_contracts_with_customers" in keys


def test_fact_inspector_keeps_both_revenue_evidence_anchors() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/facts/fact-delhivery-revenue-fy24")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["fact"]["evidence"]) == 2
        assert {claim["id"] for claim in payload["claims"]} >= {
            "clm-delhivery-revenue-annual",
            "clm-delhivery-revenue-presentation",
        }
        assert {anchor["claim_id"] for anchor in payload["anchors"]} >= {
            "clm-delhivery-revenue-annual",
            "clm-delhivery-revenue-presentation",
        }


def test_resolver_requires_period_for_temporal_role_history() -> None:
    with TestClient(app) as client:
        result = client.post("/api/v1/resolve", json={"workspace_id": "delhivery", "subject": "Suvir Suren Sujan", "predicate": "director_role"})
        assert result.status_code == 200
        assert result.json()["decision"] == "needs_context"


def test_human_preference_is_explicit_and_revision_bound() -> None:
    with TestClient(app) as client:
        review = client.post("/api/v1/reviews", json={"workspace_id": "india-macro", "fact_id": "fact-india-gdp-fy26", "action": "prefer", "rationale": "Use the RBI forecast for this named scenario."})
        assert review.status_code == 200
        result = client.post("/api/v1/resolve", json={"workspace_id": "india-macro", "subject": "India", "predicate": "real_gdp_growth", "period": "FY26", "policy": "human_preference"})
        assert result.json()["decision"] == "allow"
        assert "HUMAN_PREFERENCE" in result.json()["reason_codes"]


def test_upload_rejects_non_pdf_signature() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/documents", files={"file": ("notes.txt", b"not a pdf", "text/plain")}, data={"workspace_id": "delhivery"})
        assert response.status_code == 400


def test_lexical_search_returns_claims_with_retrieval_metadata() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/search", params={"workspace_id": "india-macro", "q": "GDP FY26", "limit": 10})
        assert response.status_code == 200
        payload = response.json()
        assert payload["lanes"]["lexical"] >= 1
        assert payload["items"][0]["workspace_id"] == "india-macro"


def test_read_models_and_exports_are_available() -> None:
    with TestClient(app) as client:
        workspace = client.get("/api/v1/workspaces/delhivery")
        assert workspace.status_code == 200
        assert workspace.json()["workspace"]["id"] == "delhivery"
        claim = client.get("/api/v1/claims/clm-delhivery-revenue-annual")
        assert claim.status_code == 200
        assert claim.json()["anchors"]
        assert claim.json()["interpretations"][0]["entity_status"] == "resolved"
        history = client.get("/api/v1/facts/fact-delhivery-revenue-fy24/history")
        assert history.status_code == 200
        assert history.json()["items"]
        csv_export = client.get("/api/v1/exports/facts?workspace_id=delhivery&format=csv")
        assert csv_export.status_code == 200
        assert "subject,predicate" in csv_export.text
        xlsx_export = client.get("/api/v1/exports/facts?workspace_id=delhivery&format=xlsx")
        assert xlsx_export.status_code == 200
        assert xlsx_export.content[:2] == b"PK"


def test_settings_exposes_nonsecret_independent_role_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/settings")
        assert response.status_code == 200
        payload = response.json()
        assert payload["project"] == "Project SuperJoin"
        assert payload["roles"]["extraction"]["model"]
        assert payload["roles"]["embeddings"]["dimensions"] == 768
        assert payload["roles"]["vision"]["structured_output_mode"] == "json_object"
        assert payload["configured_roles"] == {"extraction": False, "reasoning": False, "vision": False, "embeddings": False}


def test_document_archive_and_reactivate_are_auditable() -> None:
    with TestClient(app) as client:
        archive = client.post("/api/v1/documents/delhivery-annual/archive")
        assert archive.status_code == 200
        assert archive.json()["document"]["status"] == "archived"
        blocked = client.get("/api/v1/resolve", params={"workspace_id": "delhivery", "subject": "Delhivery", "predicate": "revenue_from_services", "period": "FY24"}).json()
        assert blocked["decision"] == "block"
        reactivate = client.post("/api/v1/documents/delhivery-annual/reactivate")
        assert reactivate.status_code == 200
        assert reactivate.json()["document"]["status"] == "complete"
        allowed = client.get("/api/v1/resolve", params={"workspace_id": "delhivery", "subject": "Delhivery", "predicate": "revenue_from_services", "period": "FY24"}).json()
        assert allowed["decision"] == "allow"
        changes = client.get("/api/v1/changes", params={"workspace_id": "delhivery"}).json()["items"]
        assert any(change["kind"] == "document_archived" for change in changes)


def test_workspace_create_slugifies_and_rejects_duplicate() -> None:
    with TestClient(app) as client:
        created = client.post("/api/v1/workspaces", json={"name": "New Advisory Corpus", "description": "test"})
        assert created.status_code == 201
        assert created.json()["id"] == "new-advisory-corpus"
        duplicate = client.post("/api/v1/workspaces", json={"name": "New Advisory Corpus"})
        assert duplicate.status_code == 409

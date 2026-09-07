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

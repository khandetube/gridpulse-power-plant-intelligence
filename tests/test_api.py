from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_project_discloses_no_live_telemetry():
    response = client.get("/api/v1/project")
    assert response.status_code == 200
    payload = response.json()
    assert payload["live_telemetry_connected"] is False
    assert payload["dispatch_system_connected"] is False


def test_source_registry_has_records_and_labels_unverified_leads():
    response = client.get("/api/v1/sources")
    assert response.status_code == 200
    records = response.json()
    assert len(records) >= 1
    assert all(record["verification_status"] in {"unverified", "reviewed", "verified"} for record in records)


def test_source_filter():
    response = client.get("/api/v1/sources?status=unverified")
    assert response.status_code == 200
    assert all(record["verification_status"] == "unverified" for record in response.json())

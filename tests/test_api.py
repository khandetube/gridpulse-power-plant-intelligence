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



def _observation(record_id: str, value: float = 10) -> dict:
    return {
        "record_id": record_id,
        "plant": "Example plant",
        "metric": "net_generation",
        "value": value,
        "unit": "MWh",
        "period_start": "2026-01-01",
        "period_end": "2026-01-01",
        "scope": "unit",
        "source_id": "SRC-TEST",
        "verification_status": "reviewed",
    }


def test_observation_analytics_endpoint_returns_grouped_statistics():
    response = client.post(
        "/api/v1/analytics/observations",
        json={"records": [_observation("a", 10), _observation("b", 20)]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["observation_count"] == 2
    assert payload["groups"][0]["mean"] == 15
    assert payload["groups"][0]["unit"] == "MWh"
    assert "not alarms" in payload["limitations"][0]


def test_observation_analytics_rejects_duplicate_ids():
    response = client.post(
        "/api/v1/analytics/observations",
        json={"records": [_observation("same"), _observation("same", 20)]},
    )
    assert response.status_code == 422


def test_observation_analytics_rejects_reversed_period():
    row = _observation("a")
    row["period_start"] = "2026-02-01"
    row["period_end"] = "2026-01-01"
    response = client.post("/api/v1/analytics/observations", json={"records": [row]})
    assert response.status_code == 422


def test_observation_analytics_rejects_non_finite_value():
    response = client.post(
        "/api/v1/analytics/observations",
        json={"records": [_observation("a", "NaN")]},
    )
    assert response.status_code == 422

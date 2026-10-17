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
        "source_id": "SRC-001",
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



def test_persisted_observation_ingest_and_query(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "api.db"))
    first = client.post(
        "/api/v1/observations",
        json={"records": [_observation("persist-1", 12.5), _observation("persist-2", 20)]},
    )
    assert first.status_code == 201
    assert first.json()["inserted_count"] == 2
    queried = client.get("/api/v1/observations?metric=net_generation&limit=1")
    assert queried.status_code == 200
    assert queried.json()["total"] == 2
    assert len(queried.json()["records"]) == 1


def test_persisted_observation_duplicate_batch_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "atomic.db"))
    assert client.post(
        "/api/v1/observations",
        json={"records": [_observation("persist-existing")]},
    ).status_code == 201
    response = client.post(
        "/api/v1/observations",
        json={"records": [_observation("persist-new"), _observation("persist-existing", 20)]},
    )
    assert response.status_code == 409
    records = client.get("/api/v1/observations").json()["records"]
    assert [record["record_id"] for record in records] == ["persist-existing"]



def _maintenance_event(event_id: str, start: str = "2026-01-01T08:00:00+03:30") -> dict:
    return {
        "event_id": event_id,
        "plant": "Example plant",
        "equipment": "GT-1",
        "event_type": "inspection",
        "start_time": start,
        "end_time": "2026-01-01T10:00:00+03:30",
        "timezone": "Asia/Tehran",
        "source_id": "SRC-001",
        "verification_status": "unverified",
        "notes": "API test event",
    }


def test_maintenance_event_ingest_normalizes_times_and_queries(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "maintenance.db"))
    response = client.post(
        "/api/v1/maintenance/events",
        json={"records": [_maintenance_event("maint-1")]},
    )
    assert response.status_code == 201
    assert response.json()["inserted_count"] == 1
    assert "not necessarily equipment downtime" in response.json()["duration_semantics"]
    query = client.get("/api/v1/maintenance/events?plant=Example%20plant")
    assert query.status_code == 200
    assert query.json()["total"] == 1
    assert query.json()["records"][0]["start_time"].endswith("+00:00")


def test_maintenance_api_rejects_timestamps_without_timezone(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "maintenance-invalid.db"))
    response = client.post(
        "/api/v1/maintenance/events",
        json={"records": [_maintenance_event("bad-time", "2026-01-01T08:00:00")]},
    )
    assert response.status_code == 422


def test_maintenance_api_rejects_reversed_times(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "maintenance-reversed.db"))
    event = _maintenance_event("bad-order")
    event["start_time"] = "2026-01-01T11:00:00+03:30"
    response = client.post("/api/v1/maintenance/events", json={"records": [event]})
    assert response.status_code == 422


def test_maintenance_api_rejects_duplicate_ids_and_duplicate_persisted_events(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "maintenance-duplicates.db"))
    repeated = _maintenance_event("duplicate")
    bad_batch = client.post(
        "/api/v1/maintenance/events",
        json={"records": [repeated, repeated]},
    )
    assert bad_batch.status_code == 422
    assert client.post(
        "/api/v1/maintenance/events",
        json={"records": [repeated]},
    ).status_code == 201
    repeated_response = client.post(
        "/api/v1/maintenance/events",
        json={"records": [repeated]},
    )
    assert repeated_response.status_code == 409



def test_maintenance_summary_endpoint_returns_grouped_elapsed_time(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "maintenance-summary.db"))
    first = _maintenance_event("summary-1")
    second = _maintenance_event("summary-2")
    second["event_type"] = "corrective"
    second["equipment"] = "ST-1"
    second["start_time"] = "2026-01-02T08:00:00+03:30"
    second["end_time"] = "2026-01-02T11:00:00+03:30"
    inserted = client.post(
        "/api/v1/maintenance/events",
        json={"records": [first, second]},
    )
    assert inserted.status_code == 201
    summary = client.get("/api/v1/maintenance/summary?plant=Example%20plant")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_events"] == 2
    assert len(payload["by_equipment"]) == 2
    assert "not equipment downtime" in payload["duration_semantics"]



def test_observation_ingest_rejects_unregistered_source_id(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "unknown-source.db"))
    row = _observation("unknown-source")
    row["source_id"] = "SRC-NOT-REGISTERED"
    response = client.post("/api/v1/observations", json={"records": [row]})
    assert response.status_code == 422
    assert "unknown_source_ids" in str(response.json()["detail"])


def test_maintenance_ingest_rejects_unregistered_source_id(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "unknown-maint-source.db"))
    row = _maintenance_event("unknown-maint-source")
    row["source_id"] = "SRC-NOT-REGISTERED"
    response = client.post("/api/v1/maintenance/events", json={"records": [row]})
    assert response.status_code == 422



def test_data_quality_endpoint_reports_persisted_observation_coverage(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "quality-api.db"))
    response = client.post(
        "/api/v1/observations",
        json={"records": [_observation("quality-1"), _observation("quality-2", 20)]},
    )
    assert response.status_code == 201
    report = client.get("/api/v1/analytics/data-quality")
    assert report.status_code == 200
    payload = report.json()
    assert payload["overview"]["total_records"] == 2
    assert payload["verification_status_counts"] == {"reviewed": 2}
    assert payload["overview"]["source_count"] == 1



def test_engineering_generation_performance_endpoint_returns_formula_results():
    response = client.post(
        "/api/v1/engineering/generation-performance",
        json={
            "plant": "Example plant",
            "period_start": "2026-01-01",
            "period_end": "2026-01-01",
            "net_generation_mwh": 100,
            "fuel_thermal_input_mwh": 250,
            "net_capacity_mw": 50,
            "period_hours": 4,
            "source_id": "SRC-001",
            "verification_status": "unverified",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["net_efficiency_percent"] == 40
    assert payload["net_heat_rate_kj_per_kwh"] == 9000
    assert payload["capacity_factor_percent"] == 50
    assert payload["verification_status"] == "unverified"


def test_engineering_endpoint_rejects_unknown_source_and_bad_capacity():
    base = {
        "plant": "Example plant",
        "period_start": "2026-01-01",
        "period_end": "2026-01-01",
        "net_generation_mwh": 100,
        "fuel_thermal_input_mwh": 250,
        "net_capacity_mw": 50,
        "period_hours": 4,
        "source_id": "SRC-001",
        "verification_status": "unverified",
    }
    bad_capacity = {**base, "net_capacity_mw": 0}
    assert client.post("/api/v1/engineering/generation-performance", json=bad_capacity).status_code == 422
    bad_source = {**base, "source_id": "SRC-DOES-NOT-EXIST"}
    assert client.post("/api/v1/engineering/generation-performance", json=bad_source).status_code == 422

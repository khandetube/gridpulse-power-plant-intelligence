import csv
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from gridpulse import main
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


def test_ml_anomaly_endpoint_flags_candidates_and_preserves_limitations():
    from datetime import date, timedelta

    start = date(2026, 1, 1)
    values = [100, 101, 99, 102, 100, 98, 101, 99, 100, 1000]
    records = []
    for index, value in enumerate(values):
        row = _observation(f"ml-{index}", value)
        row["period_start"] = (start + timedelta(days=index)).isoformat()
        row["period_end"] = row["period_start"]
        records.append(row)

    response = client.post(
        "/api/v1/analytics/anomalies?contamination=0.1",
        json={"records": records},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["algorithm"] == "scikit-learn IsolationForest"
    assert payload["observation_count"] == 10
    assert payload["flagged_count"] >= 1
    assert "not alarms" in payload["limitations"][0]


def test_ml_anomaly_endpoint_rejects_too_few_observations():
    response = client.post(
        "/api/v1/analytics/anomalies",
        json={"records": [_observation(str(index), index + 1) for index in range(7)]},
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


def test_observation_csv_export_preserves_status_and_supports_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "export.db"))
    response = client.post(
        "/api/v1/observations",
        json={"records": [_observation("export-1", 12.5), {**_observation("export-2", 20), "metric": "fuel_input"}]},
    )
    assert response.status_code == 201

    exported = client.get("/api/v1/observations/export.csv?metric=net_generation&status=reviewed")
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert exported.headers["content-disposition"].endswith('filename="gridpulse-observations.csv"')
    assert exported.headers["x-gridpulse-export-total"] == "1"
    assert exported.headers["x-gridpulse-export-returned"] == "1"
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert len(rows) == 1
    assert rows[0]["record_id"] == "export-1"
    assert rows[0]["metric"] == "net_generation"
    assert rows[0]["value"] == "12.5"
    assert rows[0]["verification_status"] == "reviewed"
    assert "export-2" not in exported.text


def test_observation_csv_export_rejects_reversed_date_filter():
    response = client.get(
        "/api/v1/observations/export.csv?start_date=2026-02-01&end_date=2026-01-01"
    )
    assert response.status_code == 422


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



def test_audit_api_returns_observation_ingest_event(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "audit-api.db"))
    response = client.post(
        "/api/v1/observations",
        json={"records": [_observation("audited-1")]},
    )
    assert response.status_code == 201
    audit = client.get("/api/v1/audit/events?entity_type=observation&entity_id=audited-1")
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["total"] == 1
    assert payload["events"][0]["entity_id"] == "audited-1"
    assert payload["events"][0]["source_id"] == "SRC-001"



def test_api_key_guard_protects_versioned_api_when_configured(monkeypatch):
    monkeypatch.setenv("GRIDPULSE_API_KEY", "test-only-secret")
    missing = client.get("/api/v1/project")
    assert missing.status_code == 401
    wrong = client.get("/api/v1/project", headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401
    valid = client.get("/api/v1/project", headers={"X-API-Key": "test-only-secret"})
    assert valid.status_code == 200
    assert client.get("/health").status_code == 200


def test_readiness_endpoint_reports_healthy_dependencies(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "ready.sqlite3"))
    response = client.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"] == {"source_registry": "ok", "database": "ok"}


def test_readiness_endpoint_returns_503_when_source_registry_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "not-ready.sqlite3"))
    monkeypatch.setattr(main, "SOURCE_REGISTRY", tmp_path / "missing-source-registry.csv")
    response = client.get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["source_registry"] == "unavailable"
    assert payload["checks"]["database"] == "ok"


def test_system_diagnostics_reports_safe_dependency_and_record_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "diagnostics.sqlite3"))
    response = client.post(
        "/api/v1/observations",
        json={"records": [_observation("diag-1"), _observation("diag-2", 20)]},
    )
    assert response.status_code == 201

    diagnostics = client.get("/api/v1/system/diagnostics")
    assert diagnostics.status_code == 200
    payload = diagnostics.json()
    assert payload["status"] == "ok"
    assert payload["checks"] == {"source_registry": "ok", "database": "ok"}
    assert payload["stored_record_counts"]["observations"] == 2
    assert payload["stored_record_counts"]["audit_events"] == 2
    assert payload["registered_source_count"] >= 1
    assert payload["capabilities"]["live_plant_telemetry"] is False
    assert payload["capabilities"]["storage_backend"] == "sqlite"
    assert payload["capabilities"]["storage_path_explicitly_configured"] is True
    assert payload["capabilities"]["storage_durability"] == "deployment_volume_unverified"
    assert "persistent_storage" not in payload["capabilities"]
    assert "database_path" not in payload


def test_observation_csv_export_paginates_and_reports_total(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "export-pages.db"))
    inserted = client.post(
        "/api/v1/observations",
        json={"records": [_observation("page-1", 1), _observation("page-2", 2), _observation("page-3", 3)]},
    )
    assert inserted.status_code == 201

    first = client.get("/api/v1/observations/export.csv?limit=2&offset=0")
    second = client.get("/api/v1/observations/export.csv?limit=2&offset=2")
    assert first.status_code == second.status_code == 200
    assert first.headers["x-gridpulse-export-total"] == "3"
    assert first.headers["x-gridpulse-export-returned"] == "2"
    assert second.headers["x-gridpulse-export-total"] == "3"
    assert second.headers["x-gridpulse-export-returned"] == "1"
    assert [row["record_id"] for row in csv.DictReader(StringIO(first.text))] == ["page-1", "page-2"]
    assert [row["record_id"] for row in csv.DictReader(StringIO(second.text))] == ["page-3"]


def test_observation_csv_export_neutralizes_formula_like_text_cells(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "export-formula.db"))
    malicious = {
        **_observation("formula-1"),
        "metric": "=HYPERLINK(\"https://example.invalid\",\"open\")",
    }
    inserted = client.post("/api/v1/observations", json={"records": [malicious]})
    assert inserted.status_code == 201

    exported = client.get("/api/v1/observations/export.csv")
    assert exported.status_code == 200
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert rows[0]["metric"].startswith("'=")
    # The numerical measurement remains numeric rather than being escaped as text.
    assert rows[0]["value"] == "10.0"


def test_production_api_fails_closed_without_key(monkeypatch):
    monkeypatch.setenv("GRIDPULSE_ENV", "production")
    monkeypatch.delenv("GRIDPULSE_API_KEY", raising=False)
    response = client.get("/api/v1/project")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_api_requires_constant_time_checked_key_when_configured(monkeypatch):
    monkeypatch.setenv("GRIDPULSE_ENV", "production")
    monkeypatch.setenv("GRIDPULSE_API_KEY", "test-only-long-random-key")
    denied = client.get("/api/v1/project")
    assert denied.status_code == 401
    allowed = client.get(
        "/api/v1/project", headers={"X-API-Key": "test-only-long-random-key"}
    )
    assert allowed.status_code == 200


def test_api_rejects_oversized_declared_request_body(monkeypatch):
    monkeypatch.setenv("GRIDPULSE_ENV", "production")
    monkeypatch.setenv("GRIDPULSE_API_KEY", "test-only-long-random-key")
    response = client.post(
        "/api/v1/observations",
        content=b"{}",
        headers={
            "X-API-Key": "test-only-long-random-key",
            "Content-Type": "application/json",
            "Content-Length": str(5 * 1024 * 1024 + 1),
        },
    )
    assert response.status_code == 413



def test_unit_conversion_api_converts_compatible_engineering_units():
    response = client.post(
        "/api/v1/analytics/units/convert",
        json={"value": 1.25, "from_unit": "MW", "to_unit": "kW"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["converted_value"] == pytest.approx(1250.0)
    assert payload["library"] == "Pint"


def test_unit_conversion_api_rejects_incompatible_dimensions():
    response = client.post(
        "/api/v1/analytics/units/convert",
        json={"value": 1, "from_unit": "MW", "to_unit": "MWh"},
    )
    assert response.status_code == 422
    assert "dimensionally incompatible" in response.json()["detail"]



def test_time_series_api_returns_stl_components():
    from datetime import date, timedelta

    start = date(2026, 1, 1)
    values = [100 + index * 0.5 + [0, 2, -1, 1, -2, 0, 1][index % 7] for index in range(21)]
    records = []
    for index, value in enumerate(values):
        row = _observation(f"stl-{index:03d}", value)
        row["period_start"] = (start + timedelta(days=index)).isoformat()
        row["period_end"] = row["period_start"]
        records.append(row)

    response = client.post("/api/v1/analytics/time-series?period=7", json={"records": records})
    assert response.status_code == 200
    payload = response.json()
    assert payload["method"] == "statsmodels STL with robust fitting"
    assert payload["observation_count"] == 21
    assert len(payload["observations"]) == 21
    assert "trend" in payload["observations"][0]
    assert "seasonal" in payload["observations"][0]


def test_time_series_api_rejects_insufficient_observations():
    response = client.post(
        "/api/v1/analytics/time-series?period=7",
        json={"records": [_observation(f"short-{i}", i + 1) for i in range(13)]},
    )
    assert response.status_code == 422

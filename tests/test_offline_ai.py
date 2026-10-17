from gridpulse.offline_ai import analyze_offline


def row(record_id, value, day, status="reviewed"):
    return {
        "record_id": record_id,
        "plant": "Demo plant",
        "metric": "net_generation",
        "value": value,
        "unit": "MWh",
        "period_start": day,
        "period_end": day,
        "scope": "plant",
        "source_id": "SRC-001",
        "verification_status": status,
    }


def test_offline_analysis_is_deterministic_and_groups_units():
    records = [
        row("r1", 10, "2026-01-01"),
        row("r2", 11, "2026-01-02"),
        row("r3", 9, "2026-01-03"),
        row("r4", 10, "2026-01-04"),
        row("r5", 100, "2026-01-05", "unverified"),
    ]
    first = analyze_offline(records)
    second = analyze_offline(records)
    assert first == second
    assert first["network_access"] is False
    assert first["group_count"] == 1
    assert first["anomaly_candidates"][0]["record_id"] == "r5"
    assert first["anomaly_candidates"][0]["review_required"] is True
    assert first["anomaly_candidates"][0]["verification_status"] == "unverified"


def test_offline_analysis_reports_invalid_records_without_crashing():
    valid = row("r1", 10, "2026-01-01")
    invalid = row("r2", float("nan"), "2026-01-02")
    result = analyze_offline([valid, invalid])
    assert result["analyzed_count"] == 1
    assert result["invalid_or_skipped_count"] == 1
    assert result["invalid_or_skipped_records"][0]["reason"] == "value_not_finite_number"


def test_offline_analysis_requires_minimum_four_points_for_outlier_flags():
    result = analyze_offline([row("r1", 10, "2026-01-01"), row("r2", 100, "2026-01-02")])
    assert result["anomaly_candidates"] == []
    assert result["groups"][0]["trend_per_day"] == 90


def test_offline_analysis_api_status_and_analysis():
    from fastapi.testclient import TestClient

    from gridpulse.main import app

    client = TestClient(app)
    status = client.get("/api/v1/ai/status")
    assert status.status_code == 200
    assert status.json()["network_access"] is False
    response = client.post("/api/v1/ai/analyze", json={"records": [row("api-1", 1, "2026-01-01")]})
    assert response.status_code == 200
    assert response.json()["mode"] == "offline_deterministic_statistics"

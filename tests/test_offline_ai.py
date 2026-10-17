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


def test_offline_cli_reads_local_json_and_writes_report(tmp_path, monkeypatch):
    import json
    import sys

    from gridpulse.offline_ai import main

    source = tmp_path / "input.json"
    output = tmp_path / "report.json"
    source.write_text(json.dumps({"records": [row("cli-1", 3, "2026-01-01")]}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["gridpulse-offline-ai", str(source), "--output", str(output)])
    assert main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "offline_deterministic_statistics"
    assert report["analyzed_count"] == 1


def test_local_language_model_is_disabled_without_a_model_file(monkeypatch, tmp_path):
    from gridpulse.local_llm import LocalModelUnavailable, generate_local_answer, local_model_status

    monkeypatch.setenv("GRIDPULSE_LOCAL_MODEL_PATH", str(tmp_path / "missing.gguf"))
    status = local_model_status()
    assert status["ready"] is False
    assert status["network_access"] is False
    try:
        generate_local_answer("Summarize the observations")
    except LocalModelUnavailable as exc:
        assert "No local model file" in str(exc)
    else:
        raise AssertionError("Missing local model must not silently use a remote service")


def test_local_language_model_rejects_oversized_context(monkeypatch, tmp_path):
    from gridpulse.local_llm import generate_local_answer

    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"test")
    monkeypatch.setenv("GRIDPULSE_LOCAL_MODEL_PATH", str(model_file))
    try:
        generate_local_answer("Summarize", [{"x": index} for index in range(21)])
    except ValueError as exc:
        assert "20 context records" in str(exc)
    else:
        raise AssertionError("Oversized context must be rejected")

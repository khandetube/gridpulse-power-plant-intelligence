from fastapi.testclient import TestClient

from gridpulse.data_quality import assess_data_quality
from gridpulse.main import app


def row(record_id, value, start, end=None, *, unit="MW", scope="unit", source="SRC-1", status="verified"):
    return {
        "record_id": record_id,
        "plant": "Plant-A",
        "metric": "load",
        "value": value,
        "unit": unit,
        "period_start": start,
        "period_end": end or start,
        "scope": scope,
        "source_id": source,
        "verification_status": status,
    }


def test_data_quality_detects_duplicate_conflict_and_missing_provenance():
    records = [row("r1", 10, "2026-01-01"), row("r1", 12, "2026-01-01"), row("r2", 11, "2026-01-02", source="")]
    result = assess_data_quality(records)
    assert result["engine"] == "gridpulse-data-quality-v1"
    assert result["evidence_coverage_score"] < 100
    kinds = {item["kind"] for item in result["issues"]}
    assert "duplicate_record_id_conflict" in kinds
    assert "missing_source_id" in kinds


def test_data_quality_detects_unit_scope_mismatch_without_converting():
    records = [row("r1", 10, "2026-01-01"), row("r2", 11, "2026-01-02", unit="kW", scope="feeder")]
    result = assess_data_quality(records)
    kinds = {item["kind"] for item in result["issues"]}
    assert "unit_mismatch" in kinds
    assert "scope_mismatch" in kinds


def test_data_quality_detects_overlap_gap_and_irregular_sampling():
    records = [
        row("r1", 10, "2026-01-01", "2026-01-03"),
        row("r2", 11, "2026-01-03", "2026-01-04"),
        row("r3", 12, "2026-01-07"),
        row("r4", 13, "2026-01-08"),
        row("r5", 14, "2026-01-10"),
    ]
    result = assess_data_quality(records)
    kinds = {item["kind"] for item in result["issues"]}
    assert "overlapping_reporting_period" in kinds
    assert "temporal_gap" in kinds
    assert "irregular_sampling" in kinds


def test_data_quality_is_deterministic_and_scores_full_clean_evidence():
    records = [row("a", 1, "2026-01-01"), row("b", 2, "2026-01-02")]
    first = assess_data_quality(records)
    second = assess_data_quality(records)
    assert first == second
    assert first["data_quality_score"] == 100
    assert first["evidence_coverage_score"] == 100
    assert first["issue_count"] == 0
    assert first["audit"]["input_sha256"] == second["audit"]["input_sha256"]
    assert len(first["audit"]["input_sha256"]) == 64
    assert first["audit"]["issues_sha256"] == second["audit"]["issues_sha256"]
    assert first["audit"]["reproducible"] is True


def test_data_quality_input_fingerprint_changes_when_evidence_changes():
    original = assess_data_quality([row("a", 1, "2026-01-01")])
    changed = assess_data_quality([row("a", 2, "2026-01-01")])
    assert original["audit"]["input_sha256"] != changed["audit"]["input_sha256"]


def test_data_quality_handles_empty_input_explicitly():
    result = assess_data_quality([])
    assert result["input_record_count"] == 0
    assert result["data_quality_score"] == 0
    assert result["evidence_coverage_score"] == 0


def test_data_quality_api_endpoint_returns_scores_and_issues():
    client = TestClient(app)
    response = client.post("/api/v1/ai/data-quality", json={"records": [row("api-1", 5, "2026-01-01")]})
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "gridpulse-data-quality-v1"
    assert payload["data_quality_score"] == 100
    assert payload["evidence_coverage_score"] == 100


def test_data_quality_handles_non_object_records_and_flags_invalid_numeric_values():
    records = [row("bad-number", "not-a-number", "2026-01-01"), None]
    result = assess_data_quality(records)
    kinds = {item["kind"] for item in result["issues"]}
    assert "invalid_numeric_value" in kinds
    assert "invalid_record" in kinds
    assert result["input_record_count"] == 2
    assert result["coverage_components"]["finite_numeric_value"] == 0

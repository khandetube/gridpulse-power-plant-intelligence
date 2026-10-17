from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def plan(plan_id="TP-1"):
    return {
        "plan_id": plan_id,
        "title": "Generator acceptance test",
        "plant": "Test plant",
        "objective": "Verify measured output against the approved acceptance criterion.",
        "method_reference": "TEST-METHOD-001",
        "revision": "1.0",
        "status": "ready",
        "source_id": "SRC-001",
        "verification_status": "reviewed",
        "notes": "Fixture only",
    }


def case(case_id="TC-1"):
    return {
        "case_id": case_id,
        "plan_id": "TP-1",
        "title": "Net generation check",
        "parameter": "net_generation",
        "unit": "MWh",
        "acceptance_min": 90,
        "acceptance_max": 110,
        "acceptance_text": "Measured value within approved bounds.",
        "method_reference": "TEST-METHOD-001",
        "instrument_reference": "CAL-REF-001",
        "baseline_value": 100,
        "notes": "Fixture only",
    }


def execution(execution_id="TE-1", value=100):
    return {
        "execution_id": execution_id,
        "case_id": "TC-1",
        "executed_at": "2026-01-01T10:00:00Z",
        "measured_value": value,
        "measured_unit": "MWh",
        "result": "pass",
        "operator": "test-operator",
        "evidence_reference": "evidence://test-1",
        "source_id": "SRC-001",
        "verification_status": "reviewed",
        "approval_status": "pending",
        "notes": "Fixture only",
    }


def test_testing_lifecycle_and_acceptance_evaluation(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "testing.db"))
    assert client.post("/api/v1/testing/plans", json=plan()).status_code == 201
    assert client.post("/api/v1/testing/cases", json=case()).status_code == 201
    passed = client.post("/api/v1/testing/executions", json=execution())
    assert passed.status_code == 201
    assert passed.json()["result"] == "pass"
    failed = client.post("/api/v1/testing/executions", json=execution("TE-2", 130))
    assert failed.status_code == 201
    assert failed.json()["result"] == "fail"
    assert len(client.get("/api/v1/testing/cases?plan_id=TP-1").json()["records"]) == 1
    assert len(client.get("/api/v1/testing/executions?case_id=TC-1").json()["records"]) == 2


def test_testing_rejects_unknown_source_and_missing_parent_records(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "testing-invalid.db"))
    bad = plan("TP-BAD")
    bad["source_id"] = "SRC-NOT-REGISTERED"
    assert client.post("/api/v1/testing/plans", json=bad).status_code == 422
    assert client.post("/api/v1/testing/cases", json=case("NO-PLAN")).status_code == 409
    assert client.post("/api/v1/testing/executions", json=execution("NO-CASE")).status_code == 422


def test_testing_rejects_reversed_acceptance_bounds(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "testing-bounds.db"))
    invalid = case("TC-BAD")
    invalid["acceptance_min"] = 10
    invalid["acceptance_max"] = 5
    assert client.post("/api/v1/testing/cases", json=invalid).status_code == 422

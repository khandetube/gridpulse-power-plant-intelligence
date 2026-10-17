from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def asset(asset_id="wo-asset"):
    return {
        "asset_id": asset_id, "plant": "Test plant", "name": asset_id,
        "asset_type": "pump", "parent_asset_id": None, "manufacturer": "Example",
        "model": "P-1", "serial_number": asset_id, "criticality": "high",
        "lifecycle_state": "active", "commissioning_date": "2026-01-01",
        "rated_capacity_mw": 1, "source_id": "SRC-001",
        "verification_status": "reviewed", "notes": "Test fixture only",
    }


def work_order(work_order_id="WO-1"):
    return {
        "work_order_id": work_order_id, "asset_id": "wo-asset",
        "origin_type": "manual", "origin_id": "", "title": "Inspect pump seal",
        "description": "Fixture work order, not a real plant instruction.",
        "priority": "high", "owner": "test-maintainer",
        "planned_start": "2026-10-20T08:00:00Z", "planned_end": "2026-10-20T12:00:00Z",
        "estimated_labor_hours": 4, "parts_materials": "seal kit",
        "before_evidence": "evidence://fixture/before", "source_id": "SRC-001",
    }


def test_work_order_lifecycle_requires_completion_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "work-orders.db"))
    assert client.post("/api/v1/assets", json=asset()).status_code == 201
    created = client.post("/api/v1/work-orders", json=work_order())
    assert created.status_code == 201
    assert created.json()["status"] == "proposed"

    approved = client.patch("/api/v1/work-orders/WO-1", json={
        "status": "approved", "source_id": "SRC-001"
    })
    assert approved.status_code == 200
    started = client.patch("/api/v1/work-orders/WO-1", json={
        "status": "in_progress", "source_id": "SRC-001"
    })
    assert started.status_code == 200

    incomplete = client.patch("/api/v1/work-orders/WO-1", json={
        "status": "completed", "source_id": "SRC-001"
    })
    assert incomplete.status_code == 422

    completed = client.patch("/api/v1/work-orders/WO-1", json={
        "status": "completed", "completion_summary": "Fixture task completed",
        "after_evidence": "evidence://fixture/after", "source_id": "SRC-001"
    })
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    verified = client.patch("/api/v1/work-orders/WO-1", json={
        "status": "verified", "verification_status": "verified", "source_id": "SRC-001"
    })
    assert verified.status_code == 200
    assert verified.json()["status"] == "verified"

    audit = client.get("/api/v1/work-orders/WO-1/audit")
    assert audit.status_code == 200
    assert audit.json()["total"] == 5
    assert audit.json()["events"][-1]["to_status"] == "verified"


def test_work_order_rejects_bad_origin_source_and_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "work-orders-validation.db"))
    assert client.post("/api/v1/assets", json=asset()).status_code == 201

    bad_source = work_order("WO-BAD-SOURCE")
    bad_source["source_id"] = "SRC-NOT-REGISTERED"
    assert client.post("/api/v1/work-orders", json=bad_source).status_code == 422

    bad_origin = work_order("WO-BAD-ORIGIN")
    bad_origin["origin_type"] = "inspection"
    bad_origin["origin_id"] = "missing-inspection"
    assert client.post("/api/v1/work-orders", json=bad_origin).status_code == 409

    assert client.post("/api/v1/work-orders", json=work_order()).status_code == 201
    invalid = client.patch("/api/v1/work-orders/WO-1", json={
        "status": "verified", "verification_status": "verified", "source_id": "SRC-001"
    })
    assert invalid.status_code == 409
    assert client.get("/api/v1/work-orders/no-such-order").status_code == 404

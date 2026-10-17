from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def asset(asset_id="inspection-asset"):
    return {
        "asset_id": asset_id,
        "plant": "Test plant",
        "name": asset_id,
        "asset_type": "pump",
        "parent_asset_id": None,
        "manufacturer": "Example",
        "model": "P-1",
        "serial_number": asset_id,
        "criticality": "high",
        "lifecycle_state": "active",
        "commissioning_date": "2026-01-01",
        "rated_capacity_mw": 1,
        "source_id": "SRC-001",
        "verification_status": "reviewed",
        "notes": "Test fixture only",
    }


def inspection(inspection_id="INSP-1", asset_id="inspection-asset"):
    return {
        "inspection_id": inspection_id,
        "asset_id": asset_id,
        "inspection_type": "visual",
        "inspected_at": "2026-10-17T10:00:00Z",
        "inspector": "test-inspector",
        "condition_rating": "monitor",
        "findings": "Fixture finding; not real plant data.",
        "recommendation": "Review during planned maintenance.",
        "evidence_reference": "evidence://fixture/inspection-1",
        "method_reference": "TEST-METHOD-001",
        "source_id": "SRC-001",
        "verification_status": "unverified",
        "approval_status": "pending",
        "next_due_at": "2026-11-17T10:00:00Z",
        "notes": "Automated test fixture",
    }


def test_inspection_create_filter_and_review_audit(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "inspections.db"))
    assert client.post("/api/v1/assets", json=asset()).status_code == 201

    created = client.post("/api/v1/inspections", json=inspection())
    assert created.status_code == 201
    assert created.json()["condition_rating"] == "monitor"

    listing = client.get("/api/v1/inspections?condition_rating=monitor&limit=10")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["records"][0]["inspection_id"] == "INSP-1"

    reviewed = client.patch("/api/v1/inspections/INSP-1", json={
        "findings": "Reviewed finding",
        "condition_rating": "degraded",
        "verification_status": "reviewed",
        "approval_status": "reviewed",
        "source_id": "SRC-001",
    })
    assert reviewed.status_code == 200
    assert reviewed.json()["condition_rating"] == "degraded"
    assert reviewed.json()["findings"] == "Reviewed finding"


def test_inspection_validates_source_timestamps_and_asset(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "inspections-validation.db"))
    assert client.post("/api/v1/assets", json=asset()).status_code == 201

    bad_source = inspection("INSP-BAD-SOURCE")
    bad_source["source_id"] = "SRC-NOT-REGISTERED"
    assert client.post("/api/v1/inspections", json=bad_source).status_code == 422

    naive_timestamp = inspection("INSP-NAIVE")
    naive_timestamp["inspected_at"] = "2026-10-17T10:00:00"
    assert client.post("/api/v1/inspections", json=naive_timestamp).status_code == 422

    missing_asset = inspection("INSP-MISSING", "no-such-asset")
    assert client.post("/api/v1/inspections", json=missing_asset).status_code == 409


def test_inspection_duplicate_and_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "inspections-404.db"))
    assert client.post("/api/v1/assets", json=asset()).status_code == 201
    assert client.post("/api/v1/inspections", json=inspection()).status_code == 201
    assert client.post("/api/v1/inspections", json=inspection()).status_code == 409
    assert client.get("/api/v1/inspections/no-such-inspection").status_code == 404
    assert client.patch("/api/v1/inspections/no-such-inspection", json={
        "source_id": "SRC-001", "approval_status": "approved"
    }).status_code == 404

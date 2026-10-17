from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def asset(asset_id: str, parent_asset_id: str | None = None) -> dict:
    return {
        "asset_id": asset_id,
        "plant": "Test plant",
        "name": asset_id,
        "asset_type": "test_unit",
        "parent_asset_id": parent_asset_id,
        "manufacturer": "Example",
        "model": "M1",
        "serial_number": asset_id,
        "criticality": "high",
        "lifecycle_state": "active",
        "commissioning_date": "2026-01-01",
        "rated_capacity_mw": 10,
        "source_id": "SRC-001",
        "verification_status": "reviewed",
        "notes": "test fixture",
    }


def test_asset_crud_hierarchy_and_delete_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "assets.db"))
    assert client.post("/api/v1/assets", json=asset("root")).status_code == 201
    child = client.post("/api/v1/assets", json=asset("child", "root"))
    assert child.status_code == 201
    assert child.json()["commissioning_date"] == "2026-01-01"

    listing = client.get("/api/v1/assets?plant=Test%20plant")
    assert listing.status_code == 200
    assert listing.json()["total"] == 2

    hierarchy = client.get("/api/v1/assets/hierarchy?plant=Test%20plant")
    assert hierarchy.status_code == 200
    assert hierarchy.json()["hierarchy"][0]["children"][0]["asset_id"] == "child"

    assert client.patch("/api/v1/assets/child", json={"criticality": "critical"}).status_code == 200
    blocked = client.delete("/api/v1/assets/root")
    assert blocked.status_code == 409
    assert client.delete("/api/v1/assets/child").status_code == 200
    assert client.delete("/api/v1/assets/root").status_code == 200


def test_asset_requires_registered_source_and_duplicate_id_is_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "assets-source.db"))
    unknown = asset("unknown")
    unknown["source_id"] = "SRC-NOT-REGISTERED"
    assert client.post("/api/v1/assets", json=unknown).status_code == 422
    assert client.post("/api/v1/assets", json=asset("dup")).status_code == 201
    assert client.post("/api/v1/assets", json=asset("dup")).status_code == 409


def test_asset_parent_validation_and_cycle_prevention(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "assets-cycle.db"))
    assert client.post("/api/v1/assets", json=asset("a")).status_code == 201
    assert client.post("/api/v1/assets", json=asset("b", "a")).status_code == 201
    assert client.post("/api/v1/assets", json=asset("missing-parent", "does-not-exist")).status_code == 409
    assert client.patch("/api/v1/assets/a", json={"parent_asset_id": "b"}).status_code == 409
    assert client.patch("/api/v1/assets/b", json={"parent_asset_id": "b"}).status_code == 409


def test_asset_not_found_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "assets-404.db"))
    assert client.get("/api/v1/assets/no-such-asset").status_code == 404
    assert client.patch("/api/v1/assets/no-such-asset", json={"name": "x"}).status_code == 404
    assert client.delete("/api/v1/assets/no-such-asset").status_code == 404

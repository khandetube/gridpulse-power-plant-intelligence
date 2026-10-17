from fastapi.testclient import TestClient

from gridpulse.main import app

client = TestClient(app)


def plan(plan_id="TURN-1"):
    return {
        "plan_id": plan_id,
        "title": "Test turnaround plan",
        "scope": "Automated test fixtures only; not a real outage plan.",
        "source_id": "SRC-001",
        "tasks": [
            {"task_id": "TASK-A", "title": "Preparation", "duration_hours": 2, "crew": "crew-a", "depends_on": []},
            {"task_id": "TASK-B", "title": "Inspection after preparation", "duration_hours": 3, "crew": "crew-b", "depends_on": ["TASK-A"]},
            {"task_id": "TASK-C", "title": "Independent test", "duration_hours": 4, "crew": "crew-c", "depends_on": []},
        ],
    }


def test_turnaround_dependency_schedule_and_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "turnarounds.db"))
    created = client.post("/api/v1/turnarounds/plans", json=plan())
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["task_count"] == 3
    assert body["total_labor_hours_estimate"] == 9
    assert body["critical_path_hours_estimate"] == 5

    approved = client.patch("/api/v1/turnarounds/plans/TURN-1", json={
        "status": "approved", "source_id": "SRC-001"
    })
    assert approved.status_code == 200
    started = client.patch("/api/v1/turnarounds/plans/TURN-1", json={
        "status": "in_progress", "source_id": "SRC-001"
    })
    assert started.status_code == 200

    blocked = client.patch("/api/v1/turnarounds/plans/TURN-1/tasks/TASK-B",
                           params={"status": "ready", "source_id": "SRC-001"})
    assert blocked.status_code == 409

    first_done = client.patch("/api/v1/turnarounds/plans/TURN-1/tasks/TASK-A",
                              params={"status": "completed", "source_id": "SRC-001"})
    assert first_done.status_code == 200
    second_ready = client.patch("/api/v1/turnarounds/plans/TURN-1/tasks/TASK-B",
                                params={"status": "ready", "source_id": "SRC-001"})
    assert second_ready.status_code == 200

    cannot_close = client.patch("/api/v1/turnarounds/plans/TURN-1", json={
        "status": "closed", "source_id": "SRC-001"
    })
    assert cannot_close.status_code == 409

    audit = client.get("/api/v1/turnarounds/plans/TURN-1/audit")
    assert audit.status_code == 200
    assert audit.json()["total"] == 2


def test_turnaround_rejects_cycles_unknown_dependencies_and_duplicate_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_DB_PATH", str(tmp_path / "turnarounds-validation.db"))
    cyclic = plan("TURN-CYCLE")
    cyclic["tasks"][0]["depends_on"] = ["TASK-B"]
    assert client.post("/api/v1/turnarounds/plans", json=cyclic).status_code == 422

    missing = plan("TURN-MISSING")
    missing["tasks"][0]["depends_on"] = ["DOES-NOT-EXIST"]
    assert client.post("/api/v1/turnarounds/plans", json=missing).status_code == 422

    duplicate = plan("TURN-DUPLICATE")
    duplicate["tasks"][1]["task_id"] = "TASK-A"
    assert client.post("/api/v1/turnarounds/plans", json=duplicate).status_code == 422

    bad_source = plan("TURN-BAD-SOURCE")
    bad_source["source_id"] = "SRC-NOT-REGISTERED"
    assert client.post("/api/v1/turnarounds/plans", json=bad_source).status_code == 422
    assert client.get("/api/v1/turnarounds/plans/not-found").status_code == 404

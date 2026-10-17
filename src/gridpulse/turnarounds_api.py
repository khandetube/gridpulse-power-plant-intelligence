"""Turnaround planning API with dependency validation and guarded plan lifecycle."""
from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from gridpulse.assets import AssetStore

router = APIRouter(prefix="/api/v1/turnarounds", tags=["turnaround-planning"])
PlanStatus = Literal["draft", "approved", "in_progress", "on_hold", "closed", "cancelled"]


def db_path() -> Path:
    return Path(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))


def source_is_registered(source_id: str) -> bool:
    root = Path(os.environ.get("GRIDPULSE_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
    registry = root / "source_registry.csv"
    if not registry.is_file():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    try:
        with registry.open("r", encoding="utf-8", newline="") as handle:
            return source_id in {r.get("source_id", "").strip() for r in csv.DictReader(handle)}
    except (OSError, csv.Error) as exc:
        raise HTTPException(status_code=503, detail="Source registry cannot be read") from exc


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    AssetStore(path)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS turnaround_plans (
        plan_id TEXT PRIMARY KEY, title TEXT NOT NULL, scope TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('draft','approved','in_progress','on_hold','closed','cancelled')),
        source_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    db.execute("""CREATE TABLE IF NOT EXISTS turnaround_tasks (
        task_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, asset_id TEXT, title TEXT NOT NULL,
        duration_hours REAL NOT NULL CHECK(duration_hours > 0), crew TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','ready','in_progress','completed','blocked')),
        source_id TEXT NOT NULL, FOREIGN KEY(plan_id) REFERENCES turnaround_plans(plan_id),
        FOREIGN KEY(asset_id) REFERENCES assets(asset_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS turnaround_dependencies (
        plan_id TEXT NOT NULL, task_id TEXT NOT NULL, depends_on_task_id TEXT NOT NULL,
        PRIMARY KEY(task_id, depends_on_task_id),
        FOREIGN KEY(plan_id) REFERENCES turnaround_plans(plan_id),
        FOREIGN KEY(task_id) REFERENCES turnaround_tasks(task_id),
        FOREIGN KEY(depends_on_task_id) REFERENCES turnaround_tasks(task_id),
        CHECK(task_id <> depends_on_task_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS turnaround_audit_events (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL, action TEXT NOT NULL,
        from_status TEXT, to_status TEXT, source_id TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    db.execute("""CREATE TABLE IF NOT EXISTS turnaround_task_audit_events (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL, task_id TEXT NOT NULL,
        from_status TEXT, to_status TEXT NOT NULL, source_id TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_turnaround_tasks_plan_status ON turnaround_tasks(plan_id,status)")
    return db


class TaskInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=128)
    asset_id: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    duration_hours: float = Field(gt=0, le=100000, allow_inf_nan=False)
    crew: str = Field(default="unassigned", min_length=1, max_length=200)
    depends_on: list[str] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_dependencies(self):
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("depends_on entries must be unique")
        return self


class TurnaroundPlanInput(BaseModel):
    plan_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    scope: str = Field(min_length=1, max_length=6000)
    source_id: str = Field(min_length=1, max_length=128)
    tasks: list[TaskInput] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_dependency_graph(self):
        ids = [task.task_id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task_id values must be unique within a plan")
        known = set(ids)
        graph = {task.task_id: task.depends_on for task in self.tasks}
        for task_id, dependencies in graph.items():
            missing = set(dependencies) - known
            if missing:
                raise ValueError(f"task {task_id} references unknown dependencies: {sorted(missing)}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("task dependency graph contains a cycle")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in ids:
            visit(node)
        return self


class TurnaroundPlanUpdate(BaseModel):
    status: PlanStatus
    source_id: str = Field(min_length=1, max_length=128)


TRANSITIONS = {
    "draft": {"approved", "cancelled"},
    "approved": {"in_progress", "cancelled"},
    "in_progress": {"on_hold", "closed"},
    "on_hold": {"in_progress", "cancelled"},
    "closed": set(),
    "cancelled": set(),
}


@router.post("/plans", status_code=201)
def create_turnaround_plan(request: TurnaroundPlanInput) -> dict[str, object]:
    if not source_is_registered(request.source_id):
        raise HTTPException(status_code=422, detail="source_id is not registered")
    payload = request.model_dump()
    try:
        with connect() as db:
            for task in payload["tasks"]:
                if task["asset_id"] and db.execute("SELECT 1 FROM assets WHERE asset_id=?", (task["asset_id"],)).fetchone() is None:
                    raise HTTPException(status_code=409, detail=f"asset_id does not exist for task {task['task_id']}")
            db.execute("INSERT INTO turnaround_plans(plan_id,title,scope,status,source_id) VALUES (?,?,?,'draft',?)",
                       (payload["plan_id"], payload["title"], payload["scope"], payload["source_id"]))
            for task in payload["tasks"]:
                db.execute("""INSERT INTO turnaround_tasks(task_id,plan_id,asset_id,title,duration_hours,crew,status,source_id)
                              VALUES (?,?,?,?,?,?,'pending',?)""",
                           (task["task_id"], payload["plan_id"], task["asset_id"], task["title"],
                            task["duration_hours"], task["crew"], payload["source_id"]))
            for task in payload["tasks"]:
                db.execute("INSERT INTO turnaround_task_audit_events(plan_id,task_id,from_status,to_status,source_id) VALUES (?,?,?,?,?)",
                           (payload["plan_id"], task["task_id"], None, "pending", payload["source_id"]))
            for task in payload["tasks"]:
                for dependency in task["depends_on"]:
                    db.execute("INSERT INTO turnaround_dependencies(plan_id,task_id,depends_on_task_id) VALUES (?,?,?)",
                               (payload["plan_id"], task["task_id"], dependency))
            db.execute("INSERT INTO turnaround_audit_events(plan_id,action,from_status,to_status,source_id) VALUES (?,?,?,?,?)",
                       (payload["plan_id"], "created", None, "draft", payload["source_id"]))
            return _plan_payload(db, payload["plan_id"])
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="plan_id or task_id already exists, or a database constraint failed") from exc


def _plan_payload(db: sqlite3.Connection, plan_id: str) -> dict[str, object]:
    plan = db.execute("SELECT * FROM turnaround_plans WHERE plan_id=?", (plan_id,)).fetchone()
    tasks = db.execute("SELECT * FROM turnaround_tasks WHERE plan_id=? ORDER BY task_id", (plan_id,)).fetchall()
    task_rows = []
    for row in tasks:
        item = dict(row)
        item["depends_on"] = [r["depends_on_task_id"] for r in db.execute(
            "SELECT depends_on_task_id FROM turnaround_dependencies WHERE task_id=? ORDER BY depends_on_task_id",
            (item["task_id"],)).fetchall()]
        task_rows.append(item)
    critical_path_hours = _critical_path(task_rows)
    return {**dict(plan), "task_count": len(task_rows), "total_labor_hours_estimate": round(sum(t["duration_hours"] for t in task_rows), 3),
            "critical_path_hours_estimate": round(critical_path_hours, 3), "tasks": task_rows,
            "schedule_note": "Duration estimates assume sequential dependencies and unlimited resources; resource constraints and calendar scheduling are not modeled."}


def _critical_path(tasks: list[dict[str, object]]) -> float:
    durations = {str(t["task_id"]): float(t["duration_hours"]) for t in tasks}
    dependencies = {str(t["task_id"]): [str(x) for x in t["depends_on"]] for t in tasks}
    cache: dict[str, float] = {}

    def finish(task_id: str) -> float:
        if task_id not in cache:
            cache[task_id] = durations[task_id] + max((finish(dep) for dep in dependencies[task_id]), default=0.0)
        return cache[task_id]
    return max((finish(task_id) for task_id in durations), default=0.0)


@router.get("/plans")
def list_turnaround_plans(status: PlanStatus | None = None,
                          limit: int = Query(default=100, ge=1, le=1000),
                          offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    where = " WHERE status=?" if status else ""
    params: list[object] = [status] if status else []
    with connect() as db:
        total = db.execute("SELECT COUNT(*) FROM turnaround_plans" + where, params).fetchone()[0]
        rows = db.execute("SELECT plan_id FROM turnaround_plans" + where + " ORDER BY created_at DESC LIMIT ? OFFSET ?",
                          [*params, limit, offset]).fetchall()
        return {"total": total, "limit": limit, "offset": offset,
                "records": [_plan_payload(db, row["plan_id"]) for row in rows]}


@router.get("/plans/{plan_id}")
def get_turnaround_plan(plan_id: str) -> dict[str, object]:
    with connect() as db:
        if db.execute("SELECT 1 FROM turnaround_plans WHERE plan_id=?", (plan_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Turnaround plan not found")
        return _plan_payload(db, plan_id)


@router.patch("/plans/{plan_id}")
def update_turnaround_plan(plan_id: str, request: TurnaroundPlanUpdate) -> dict[str, object]:
    if not source_is_registered(request.source_id):
        raise HTTPException(status_code=422, detail="source_id is not registered")
    with connect() as db:
        row = db.execute("SELECT * FROM turnaround_plans WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Turnaround plan not found")
        before = row["status"]
        if request.status != before and request.status not in TRANSITIONS[before]:
            raise HTTPException(status_code=409, detail=f"Invalid plan transition: {before} -> {request.status}")
        if request.status == "approved":
            task_count = db.execute("SELECT COUNT(*) FROM turnaround_tasks WHERE plan_id=?", (plan_id,)).fetchone()[0]
            if task_count < 1:
                raise HTTPException(status_code=422, detail="Cannot approve a plan without tasks")
        if request.status == "closed":
            incomplete = db.execute("SELECT COUNT(*) FROM turnaround_tasks WHERE plan_id=? AND status<>'completed'", (plan_id,)).fetchone()[0]
            if incomplete:
                raise HTTPException(status_code=409, detail="Cannot close turnaround while tasks remain incomplete")
        db.execute("UPDATE turnaround_plans SET status=?,source_id=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE plan_id=?",
                   (request.status, request.source_id, plan_id))
        db.execute("INSERT INTO turnaround_audit_events(plan_id,action,from_status,to_status,source_id) VALUES (?,?,?,?,?)",
                   (plan_id, "status_changed", before, request.status, request.source_id))
        return _plan_payload(db, plan_id)


@router.patch("/plans/{plan_id}/tasks/{task_id}")
def update_turnaround_task(plan_id: str, task_id: str,
                           status: Literal["pending", "ready", "in_progress", "completed", "blocked"],
                           source_id: str = Query(min_length=1, max_length=128)) -> dict[str, object]:
    if not source_is_registered(source_id):
        raise HTTPException(status_code=422, detail="source_id is not registered")
    with connect() as db:
        plan = db.execute("SELECT status FROM turnaround_plans WHERE plan_id=?", (plan_id,)).fetchone()
        task = db.execute("SELECT * FROM turnaround_tasks WHERE task_id=? AND plan_id=?", (task_id, plan_id)).fetchone()
        if plan is None or task is None:
            raise HTTPException(status_code=404, detail="Plan or task not found")
        if plan["status"] not in {"approved", "in_progress", "on_hold"}:
            raise HTTPException(status_code=409, detail="Tasks can only be updated for an approved or active plan")
        allowed_transitions = {
            "pending": {"ready", "blocked"},
            "ready": {"in_progress", "blocked", "pending"},
            "in_progress": {"completed", "blocked"},
            "blocked": {"pending", "ready"},
            "completed": set(),
        }
        if status != task["status"] and status not in allowed_transitions[task["status"]]:
            raise HTTPException(status_code=409, detail=f"Invalid task transition: {task['status']} -> {status}")
        dependencies = db.execute("SELECT depends_on_task_id FROM turnaround_dependencies WHERE task_id=?", (task_id,)).fetchall()
        if status in {"ready", "in_progress", "completed"}:
            incomplete = [r["depends_on_task_id"] for r in dependencies if db.execute(
                "SELECT status FROM turnaround_tasks WHERE task_id=?", (r["depends_on_task_id"],)).fetchone()["status"] != "completed"]
            if incomplete:
                raise HTTPException(status_code=409, detail={"message": "Dependencies must be completed first", "blocked_by": incomplete})
        db.execute("UPDATE turnaround_tasks SET status=?,source_id=? WHERE task_id=? AND plan_id=?",
                   (status, source_id, task_id, plan_id))
        db.execute("INSERT INTO turnaround_task_audit_events(plan_id,task_id,from_status,to_status,source_id) VALUES (?,?,?,?,?)",
                   (plan_id, task_id, task["status"], status, source_id))
        return _plan_payload(db, plan_id)


@router.get("/plans/{plan_id}/tasks/{task_id}/audit")
def list_turnaround_task_audit(plan_id: str, task_id: str,
                               limit: int = Query(default=100, ge=1, le=1000),
                               offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    with connect() as db:
        if db.execute("SELECT 1 FROM turnaround_tasks WHERE plan_id=? AND task_id=?", (plan_id, task_id)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Plan task not found")
        total = db.execute("SELECT COUNT(*) FROM turnaround_task_audit_events WHERE plan_id=? AND task_id=?",
                           (plan_id, task_id)).fetchone()[0]
        rows = db.execute("SELECT * FROM turnaround_task_audit_events WHERE plan_id=? AND task_id=? ORDER BY audit_id LIMIT ? OFFSET ?",
                          (plan_id, task_id, limit, offset)).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "events": [dict(r) for r in rows]}


@router.get("/plans/{plan_id}/audit")
def list_turnaround_audit(plan_id: str, limit: int = Query(default=100, ge=1, le=1000),
                          offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    with connect() as db:
        if db.execute("SELECT 1 FROM turnaround_plans WHERE plan_id=?", (plan_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Turnaround plan not found")
        total = db.execute("SELECT COUNT(*) FROM turnaround_audit_events WHERE plan_id=?", (plan_id,)).fetchone()[0]
        rows = db.execute("SELECT * FROM turnaround_audit_events WHERE plan_id=? ORDER BY audit_id LIMIT ? OFFSET ?",
                          (plan_id, limit, offset)).fetchall()
        return {"total": total, "limit": limit, "offset": offset, "events": [dict(r) for r in rows]}

"""Traceable maintenance work orders linked to assets, inspections, and FMEA."""
from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from gridpulse.assets import AssetStore

router = APIRouter(prefix="/api/v1/work-orders", tags=["maintenance-work-orders"])
Status = Literal["proposed", "approved", "in_progress", "on_hold", "completed", "verified", "cancelled"]
Priority = Literal["low", "medium", "high", "urgent"]
Origin = Literal["manual", "inspection", "fmea"]


def database_path() -> Path:
    return Path(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))


def source_registered(source_id: str) -> bool:
    registry = Path(os.environ.get("GRIDPULSE_DATA_DIR", Path(__file__).resolve().parents[2] / "data")) / "source_registry.csv"
    if not registry.is_file():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    try:
        with registry.open("r", encoding="utf-8", newline="") as handle:
            return source_id in {row.get("source_id", "").strip() for row in csv.DictReader(handle)}
    except (OSError, csv.Error) as exc:
        raise HTTPException(status_code=503, detail="Source registry cannot be read") from exc


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    AssetStore(path)
    from gridpulse.fmea import FMEAStore
    from gridpulse.inspections import InspectionStore
    InspectionStore(path)
    FMEAStore(path)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("""CREATE TABLE IF NOT EXISTS work_orders (
        work_order_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL,
        origin_type TEXT NOT NULL CHECK(origin_type IN ('manual','inspection','fmea')),
        origin_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
        priority TEXT NOT NULL CHECK(priority IN ('low','medium','high','urgent')),
        status TEXT NOT NULL CHECK(status IN ('proposed','approved','in_progress','on_hold','completed','verified','cancelled')),
        owner TEXT NOT NULL, planned_start TEXT, planned_end TEXT, estimated_labor_hours REAL,
        parts_materials TEXT NOT NULL, completion_summary TEXT NOT NULL,
        before_evidence TEXT NOT NULL, after_evidence TEXT NOT NULL,
        source_id TEXT NOT NULL, verification_status TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        FOREIGN KEY(asset_id) REFERENCES assets(asset_id))""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_asset_status ON work_orders(asset_id,status)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_work_orders_priority_status ON work_orders(priority,status)")
    db.execute("""CREATE TABLE IF NOT EXISTS work_order_audit_events (
        audit_id INTEGER PRIMARY KEY AUTOINCREMENT, work_order_id TEXT NOT NULL,
        action TEXT NOT NULL, from_status TEXT, to_status TEXT,
        source_id TEXT NOT NULL,
        recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    return db


class WorkOrderInput(BaseModel):
    work_order_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    origin_type: Origin = "manual"
    origin_id: str = Field(default="", max_length=128)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=6000)
    priority: Priority = "medium"
    owner: str = Field(min_length=1, max_length=200)
    planned_start: str | None = Field(default=None, max_length=40)
    planned_end: str | None = Field(default=None, max_length=40)
    estimated_labor_hours: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    parts_materials: str = Field(default="", max_length=6000)
    before_evidence: str = Field(default="", max_length=2000)
    source_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_origin_and_schedule(self):
        if self.origin_type != "manual" and not self.origin_id:
            raise ValueError("origin_id is required for inspection/FMEA work orders")
        if self.planned_start and self.planned_end and self.planned_end < self.planned_start:
            raise ValueError("planned_end must not precede planned_start (ISO-8601 strings)")
        return self


class WorkOrderUpdate(BaseModel):
    status: Status | None = None
    priority: Priority | None = None
    owner: str | None = Field(default=None, min_length=1, max_length=200)
    planned_start: str | None = Field(default=None, max_length=40)
    planned_end: str | None = Field(default=None, max_length=40)
    estimated_labor_hours: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    parts_materials: str | None = Field(default=None, max_length=6000)
    completion_summary: str | None = Field(default=None, max_length=6000)
    before_evidence: str | None = Field(default=None, max_length=2000)
    after_evidence: str | None = Field(default=None, max_length=2000)
    verification_status: Literal["unverified", "reviewed", "verified"] | None = None
    source_id: str = Field(min_length=1, max_length=128)


TRANSITIONS = {
    "proposed": {"approved", "cancelled"},
    "approved": {"in_progress", "cancelled"},
    "in_progress": {"on_hold", "completed"},
    "on_hold": {"in_progress", "cancelled"},
    "completed": {"verified"},
    "verified": set(),
    "cancelled": set(),
}


@router.post("", status_code=201)
def create_work_order(request: WorkOrderInput) -> dict[str, object]:
    if not source_registered(request.source_id):
        raise HTTPException(status_code=422, detail="source_id is not registered")
    data = request.model_dump()
    try:
        with connect() as db:
            if db.execute("SELECT 1 FROM assets WHERE asset_id=?", (data["asset_id"],)).fetchone() is None:
                raise HTTPException(status_code=409, detail="asset_id does not exist")
            if data["origin_type"] == "inspection":
                origin = db.execute("SELECT asset_id FROM inspections WHERE inspection_id=?", (data["origin_id"],)).fetchone()
                if origin is None or origin["asset_id"] != data["asset_id"]:
                    raise HTTPException(status_code=409, detail="inspection origin must exist and belong to the same asset")
            if data["origin_type"] == "fmea":
                origin = db.execute("SELECT asset_id FROM failure_modes WHERE failure_mode_id=?", (data["origin_id"],)).fetchone()
                if origin is None or origin["asset_id"] != data["asset_id"]:
                    raise HTTPException(status_code=409, detail="FMEA origin must exist and belong to the same asset")
            db.execute("""INSERT INTO work_orders
                (work_order_id,asset_id,origin_type,origin_id,title,description,priority,status,owner,
                 planned_start,planned_end,estimated_labor_hours,parts_materials,completion_summary,
                 before_evidence,after_evidence,source_id,verification_status)
                VALUES (?,?,?,?,?,?,?,'proposed',?,?,?,?,?,'',?,'',?,'unverified')""",
                (data["work_order_id"],data["asset_id"],data["origin_type"],data["origin_id"],data["title"],
                 data["description"],data["priority"],data["owner"],data["planned_start"],data["planned_end"],
                 data["estimated_labor_hours"],data["parts_materials"],data["before_evidence"],data["source_id"]))
            db.execute("INSERT INTO work_order_audit_events(work_order_id,action,from_status,to_status,source_id) VALUES (?,?,?,?,?)",
                       (data["work_order_id"],"created",None,"proposed",data["source_id"]))
            return dict(db.execute("SELECT * FROM work_orders WHERE work_order_id=?", (data["work_order_id"],)).fetchone())
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="work_order_id already exists or violates a database constraint") from exc


@router.get("")
def list_work_orders(asset_id: str | None = Query(default=None, max_length=128),
                     status: Status | None = None, priority: Priority | None = None,
                     origin_type: Origin | None = None,
                     limit: int = Query(default=100, ge=1, le=1000),
                     offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    clauses, params = [], []
    for column, value in (("asset_id",asset_id),("status",status),("priority",priority),("origin_type",origin_type)):
        if value is not None:
            clauses.append(column+"=?")
            params.append(value)
    where = " WHERE "+" AND ".join(clauses) if clauses else ""
    with connect() as db:
        total = db.execute("SELECT COUNT(*) FROM work_orders"+where,params).fetchone()[0]
        rows = db.execute("SELECT * FROM work_orders"+where+" ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC LIMIT ? OFFSET ?",[*params,limit,offset]).fetchall()
    return {"total":total,"limit":limit,"offset":offset,"records":[dict(row) for row in rows],
            "note":"Work orders are planning records; they do not authorize equipment operation or return-to-service."}


@router.get("/{work_order_id}")
def get_work_order(work_order_id: str) -> dict[str, object]:
    with connect() as db:
        row = db.execute("SELECT * FROM work_orders WHERE work_order_id=?", (work_order_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Work order not found")
    return dict(row)


@router.patch("/{work_order_id}")
def update_work_order(work_order_id: str, request: WorkOrderUpdate) -> dict[str, object]:
    data = request.model_dump(exclude_unset=True)
    source_id = data.pop("source_id")
    if not source_registered(source_id):
        raise HTTPException(status_code=422, detail="source_id is not registered")
    with connect() as db:
        row = db.execute("SELECT * FROM work_orders WHERE work_order_id=?", (work_order_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Work order not found")
        before = dict(row)
        new_status = data.get("status", before["status"])
        if new_status != before["status"] and new_status not in TRANSITIONS[before["status"]]:
            raise HTTPException(status_code=409, detail=f"Invalid status transition: {before['status']} -> {new_status}")
        merged = {**before, **data}
        if merged["planned_start"] and merged["planned_end"] and merged["planned_end"] < merged["planned_start"]:
            raise HTTPException(status_code=422, detail="planned_end must not precede planned_start (ISO-8601 strings)")
        if new_status == "completed" and (not merged["completion_summary"].strip() or not merged["after_evidence"].strip()):
            raise HTTPException(status_code=422, detail="completion_summary and after_evidence are required before completion")
        if new_status == "verified" and (merged["verification_status"] != "verified" or not merged["after_evidence"].strip()):
            raise HTTPException(status_code=422, detail="verified status requires verification_status=verified and after_evidence")
        allowed = {"status","priority","owner","planned_start","planned_end","estimated_labor_hours",
                   "parts_materials","completion_summary","before_evidence","after_evidence","verification_status"}
        changes = {k:v for k,v in data.items() if k in allowed}
        if changes:
            assignments = ",".join(k+"=?" for k in changes)
            db.execute("UPDATE work_orders SET "+assignments+",source_id=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE work_order_id=?",
                       [*changes.values(),source_id,work_order_id])
        db.execute("INSERT INTO work_order_audit_events(work_order_id,action,from_status,to_status,source_id) VALUES (?,?,?,?,?)",
                   (work_order_id,"updated",before["status"],new_status,source_id))
        return dict(db.execute("SELECT * FROM work_orders WHERE work_order_id=?", (work_order_id,)).fetchone())



@router.get("/{work_order_id}/audit")
def list_work_order_audit(work_order_id: str,
                          limit: int = Query(default=100, ge=1, le=1000),
                          offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    with connect() as db:
        if db.execute("SELECT 1 FROM work_orders WHERE work_order_id=?", (work_order_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Work order not found")
        total = db.execute("SELECT COUNT(*) FROM work_order_audit_events WHERE work_order_id=?",
                           (work_order_id,)).fetchone()[0]
        rows = db.execute("""SELECT audit_id,work_order_id,action,from_status,to_status,source_id,recorded_at
                             FROM work_order_audit_events WHERE work_order_id=?
                             ORDER BY audit_id LIMIT ? OFFSET ?""",
                          (work_order_id, limit, offset)).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "events": [dict(row) for row in rows],
            "note": "Application audit trail; actor identity and tamper-proof external storage are not implemented."}

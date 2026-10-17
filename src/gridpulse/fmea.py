"""Failure Mode and Effects Analysis persistence for engineering risk review."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class FMEAStore:
    """SQLite-backed failure-mode register with deterministic RPN calculation."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS failure_modes (
                failure_mode_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL,
                function TEXT NOT NULL, failure_mode TEXT NOT NULL, cause TEXT NOT NULL,
                effect TEXT NOT NULL, severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 10),
                occurrence INTEGER NOT NULL CHECK(occurrence BETWEEN 1 AND 10),
                detectability INTEGER NOT NULL CHECK(detectability BETWEEN 1 AND 10),
                rpn INTEGER NOT NULL, mitigation TEXT NOT NULL, evidence_reference TEXT NOT NULL,
                source_id TEXT NOT NULL, verification_status TEXT NOT NULL, revision TEXT NOT NULL,
                approval_status TEXT NOT NULL, notes TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY(asset_id) REFERENCES assets(asset_id))""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_fmea_asset ON failure_modes(asset_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_fmea_rpn ON failure_modes(rpn DESC)")
            db.execute("""CREATE TABLE IF NOT EXISTS fmea_audit_events (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT, failure_mode_id TEXT NOT NULL,
                action TEXT NOT NULL, source_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        payload = {**data, "rpn": data["severity"] * data["occurrence"] * data["detectability"]}
        with self._connect() as db:
            if db.execute("SELECT 1 FROM assets WHERE asset_id=?", (payload["asset_id"],)).fetchone() is None:
                raise ValueError("asset_id does not exist")
            db.execute("""INSERT INTO failure_modes
                (failure_mode_id,asset_id,function,failure_mode,cause,effect,severity,occurrence,detectability,rpn,mitigation,evidence_reference,source_id,verification_status,revision,approval_status,notes)
                VALUES (:failure_mode_id,:asset_id,:function,:failure_mode,:cause,:effect,:severity,:occurrence,:detectability,:rpn,:mitigation,:evidence_reference,:source_id,:verification_status,:revision,:approval_status,:notes)""", payload)
            db.execute("INSERT INTO fmea_audit_events(failure_mode_id,action,source_id) VALUES (?,?,?)", (payload["failure_mode_id"], "created", payload["source_id"]))
            return dict(db.execute("SELECT * FROM failure_modes WHERE failure_mode_id=?", (payload["failure_mode_id"],)).fetchone())

    def list(self, *, asset_id: str | None = None, approval_status: str | None = None, min_rpn: int | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (("asset_id", asset_id), ("approval_status", approval_status)):
            if value is not None:
                clauses.append(f"{column}=?")
                params.append(value)
        if min_rpn is not None:
            clauses.append("rpn>=?")
            params.append(min_rpn)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as db:
            rows = db.execute("SELECT * FROM failure_modes" + where + " ORDER BY rpn DESC, failure_mode_id", params).fetchall()
            return [dict(row) for row in rows]

    def get(self, failure_mode_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM failure_modes WHERE failure_mode_id=?", (failure_mode_id,)).fetchone()
            return dict(row) if row else None

    def update_review(self, failure_mode_id: str, *, mitigation: str | None, approval_status: str | None, verification_status: str | None, source_id: str) -> dict[str, Any] | None:
        changes = {k: v for k, v in (("mitigation", mitigation), ("approval_status", approval_status), ("verification_status", verification_status)) if v is not None}
        with self._connect() as db:
            if db.execute("SELECT 1 FROM failure_modes WHERE failure_mode_id=?", (failure_mode_id,)).fetchone() is None:
                return None
            if changes:
                assignments = ", ".join(f"{key}=?" for key in changes)
                db.execute("UPDATE failure_modes SET " + assignments + ", updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE failure_mode_id=?", [*changes.values(), failure_mode_id])
            db.execute("INSERT INTO fmea_audit_events(failure_mode_id,action,source_id) VALUES (?,?,?)", (failure_mode_id, "review_updated", source_id))
            return dict(db.execute("SELECT * FROM failure_modes WHERE failure_mode_id=?", (failure_mode_id,)).fetchone())

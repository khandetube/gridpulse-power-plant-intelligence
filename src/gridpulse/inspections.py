"""Traceable inspection register for asset condition and maintenance evidence."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class InspectionStore:
    """Persist inspections without inferring condition from missing measurements."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        from gridpulse.assets import AssetStore
        AssetStore(self.database_path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS inspections (
                inspection_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                inspection_type TEXT NOT NULL,
                inspected_at TEXT NOT NULL,
                inspector TEXT NOT NULL,
                condition_rating TEXT NOT NULL CHECK(condition_rating IN
                    ('unknown','good','monitor','degraded','critical')),
                findings TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                evidence_reference TEXT NOT NULL,
                method_reference TEXT NOT NULL,
                source_id TEXT NOT NULL,
                verification_status TEXT NOT NULL CHECK(verification_status IN
                    ('unverified','reviewed','verified')),
                approval_status TEXT NOT NULL CHECK(approval_status IN
                    ('pending','reviewed','approved','rejected')),
                next_due_at TEXT,
                notes TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                FOREIGN KEY(asset_id) REFERENCES assets(asset_id))""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_inspections_asset_date ON inspections(asset_id, inspected_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_inspections_condition ON inspections(condition_rating)")
            db.execute("""CREATE TABLE IF NOT EXISTS inspection_audit_events (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id TEXT NOT NULL, action TEXT NOT NULL, source_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = ("inspection_id", "asset_id", "inspection_type", "inspected_at", "inspector",
                  "condition_rating", "findings", "recommendation", "evidence_reference",
                  "method_reference", "source_id", "verification_status", "approval_status",
                  "next_due_at", "notes")
        with self._connect() as db:
            if db.execute("SELECT 1 FROM assets WHERE asset_id=?", (data["asset_id"],)).fetchone() is None:
                raise ValueError("asset_id does not exist")
            db.execute("INSERT INTO inspections (" + ",".join(fields) + ") VALUES (" +
                       ",".join(":" + field for field in fields) + ")", data)
            db.execute("INSERT INTO inspection_audit_events(inspection_id,action,source_id) VALUES (?,?,?)",
                       (data["inspection_id"], "created", data["source_id"]))
            return dict(db.execute("SELECT * FROM inspections WHERE inspection_id=?",
                                   (data["inspection_id"],)).fetchone())

    def list(self, *, asset_id: str | None = None, condition_rating: str | None = None,
             approval_status: str | None = None, limit: int = 100, offset: int = 0
             ) -> tuple[list[dict[str, Any]], int]:
        clauses, params = [], []
        for column, value in (("asset_id", asset_id), ("condition_rating", condition_rating),
                              ("approval_status", approval_status)):
            if value is not None:
                clauses.append(column + "=?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as db:
            total = db.execute("SELECT COUNT(*) FROM inspections" + where, params).fetchone()[0]
            rows = db.execute("SELECT * FROM inspections" + where +
                              " ORDER BY inspected_at DESC, inspection_id LIMIT ? OFFSET ?",
                              [*params, limit, offset]).fetchall()
        return [dict(row) for row in rows], int(total)

    def get(self, inspection_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM inspections WHERE inspection_id=?", (inspection_id,)).fetchone()
        return dict(row) if row else None

    def update_review(self, inspection_id: str, *, findings: str | None,
                      recommendation: str | None, condition_rating: str | None,
                      verification_status: str | None, approval_status: str | None,
                      source_id: str) -> dict[str, Any] | None:
        changes = {k: v for k, v in (("findings", findings), ("recommendation", recommendation),
                   ("condition_rating", condition_rating), ("verification_status", verification_status),
                   ("approval_status", approval_status)) if v is not None}
        with self._connect() as db:
            if db.execute("SELECT 1 FROM inspections WHERE inspection_id=?", (inspection_id,)).fetchone() is None:
                return None
            if changes:
                assignments = ", ".join(k + "=?" for k in changes)
                db.execute("UPDATE inspections SET " + assignments +
                           ", updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE inspection_id=?",
                           [*changes.values(), inspection_id])
            db.execute("INSERT INTO inspection_audit_events(inspection_id,action,source_id) VALUES (?,?,?)",
                       (inspection_id, "review_updated", source_id))
            return dict(db.execute("SELECT * FROM inspections WHERE inspection_id=?",
                                   (inspection_id,)).fetchone())

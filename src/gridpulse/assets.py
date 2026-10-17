"""Asset registry persistence for engineering decision support.

The registry stores caller-supplied equipment metadata only. It does not imply
that an asset exists at a plant until the supplied record is independently
verified against an authoritative plant document or data source.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class AssetStore:
    """SQLite-backed normalized asset registry with hierarchy and audit records."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    plant TEXT NOT NULL,
                    name TEXT NOT NULL,
                    asset_type TEXT NOT NULL,
                    parent_asset_id TEXT,
                    manufacturer TEXT NOT NULL,
                    model TEXT NOT NULL,
                    serial_number TEXT NOT NULL,
                    criticality TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL,
                    commissioning_date TEXT,
                    rated_capacity_mw REAL,
                    source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    FOREIGN KEY(parent_asset_id) REFERENCES assets(asset_id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_plant ON assets(plant)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_parent ON assets(parent_asset_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_criticality ON assets(criticality)")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_audit_events (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )

    def create(self, asset: dict[str, Any]) -> dict[str, Any]:
        sql = """
            INSERT INTO assets (
                asset_id, plant, name, asset_type, parent_asset_id, manufacturer,
                model, serial_number, criticality, lifecycle_state, commissioning_date,
                rated_capacity_mw, source_id, verification_status, notes
            ) VALUES (
                :asset_id, :plant, :name, :asset_type, :parent_asset_id, :manufacturer,
                :model, :serial_number, :criticality, :lifecycle_state, :commissioning_date,
                :rated_capacity_mw, :source_id, :verification_status, :notes
            )
        """
        with self._connect() as connection:
            connection.execute(sql, asset)
            connection.execute(
                "INSERT INTO asset_audit_events(asset_id, action, source_id, verification_status) VALUES (?, 'created', ?, ?)",
                (asset["asset_id"], asset["source_id"], asset["verification_status"]),
            )
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset["asset_id"],)).fetchone()
        return dict(row)

    def list(
        self,
        *,
        plant: str | None = None,
        asset_type: str | None = None,
        criticality: str | None = None,
        lifecycle_state: str | None = None,
        parent_asset_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("plant", plant),
            ("asset_type", asset_type),
            ("criticality", criticality),
            ("lifecycle_state", lifecycle_state),
            ("parent_asset_id", parent_asset_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM assets" + where, params).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM assets" + where + " ORDER BY plant, asset_type, name LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], int(total)

    def get(self, asset_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
        return dict(row) if row else None

    def update(self, asset_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        if not changes:
            return self.get(asset_id)
        allowed = {
            "name", "asset_type", "parent_asset_id", "manufacturer", "model",
            "serial_number", "criticality", "lifecycle_state", "commissioning_date",
            "rated_capacity_mw", "source_id", "verification_status", "notes",
        }
        if set(changes) - allowed:
            raise ValueError("Unsupported asset fields")
        assignments = [f"{key} = ?" for key in changes]
        values = [changes[key] for key in changes]
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE assets SET " + ", ".join(assignments) + ", updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE asset_id = ?",
                [*values, asset_id],
            )
            if cursor.rowcount == 0:
                return None
            current = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            connection.execute(
                "INSERT INTO asset_audit_events(asset_id, action, source_id, verification_status) VALUES (?, 'updated', ?, ?)",
                (asset_id, current["source_id"], current["verification_status"]),
            )
        return dict(current)

    def delete(self, asset_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM assets WHERE asset_id = ?", (asset_id,)).fetchone()
            if not row:
                return False
            child = connection.execute("SELECT 1 FROM assets WHERE parent_asset_id = ? LIMIT 1", (asset_id,)).fetchone()
            if child:
                raise ValueError("Cannot delete an asset that has child assets")
            connection.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
            connection.execute(
                "INSERT INTO asset_audit_events(asset_id, action, source_id, verification_status) VALUES (?, 'deleted', ?, ?)",
                (asset_id, row["source_id"], row["verification_status"]),
            )
        return True

    def hierarchy(self, plant: str | None = None) -> list[dict[str, Any]]:
        records, _ = self.list(plant=plant, limit=10000)
        children: dict[str | None, list[dict[str, Any]]] = {}
        for record in records:
            children.setdefault(record["parent_asset_id"], []).append(record)
        def build(parent: str | None) -> list[dict[str, Any]]:
            result = []
            for record in children.get(parent, []):
                item = dict(record)
                item["children"] = build(record["asset_id"])
                result.append(item)
            return result
        return build(None)

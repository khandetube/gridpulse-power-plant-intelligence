"""Small SQLite persistence layer for caller-supplied, source-labelled observations."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class ObservationStore:
    """Transactional SQLite store; it never connects to plant systems."""

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
                CREATE TABLE IF NOT EXISTS observations (
                    record_id TEXT PRIMARY KEY,
                    plant TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observations_metric_period "
                "ON observations(metric, period_start)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observations_plant_period "
                "ON observations(plant, period_start)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_observations_verification "
                "ON observations(verification_status)"
            )

    def insert_many(self, records: list[dict[str, Any]]) -> int:
        """Insert a batch atomically; duplicate IDs reject and roll back the whole batch."""
        sql = """
            INSERT INTO observations (
                record_id, plant, metric, value, unit, period_start, period_end,
                scope, source_id, verification_status
            ) VALUES (
                :record_id, :plant, :metric, :value, :unit, :period_start, :period_end,
                :scope, :source_id, :verification_status
            )
        """
        with self._connect() as connection:
            connection.executemany(sql, records)
        return len(records)

    def list_records(
        self,
        *,
        plant: str | None = None,
        metric: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("plant", plant),
            ("metric", metric),
            ("verification_status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if start_date is not None:
            clauses.append("period_start >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("period_end <= ?")
            params.append(end_date)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM observations" + where, params
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM observations" + where
                + " ORDER BY period_start DESC, record_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], int(total)


    def _initialize_maintenance(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS maintenance_events (
                    event_id TEXT PRIMARY KEY,
                    plant TEXT NOT NULL,
                    equipment TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_plant_start "
                "ON maintenance_events(plant, start_time)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_equipment_start "
                "ON maintenance_events(equipment, start_time)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_maintenance_status "
                "ON maintenance_events(verification_status)"
            )

    def insert_maintenance_many(self, records: list[dict[str, Any]]) -> int:
        """Insert maintenance events atomically; elapsed duration is not downtime."""
        self._initialize_maintenance()
        sql = """
            INSERT INTO maintenance_events (
                event_id, plant, equipment, event_type, start_time, end_time,
                timezone, source_id, verification_status, notes
            ) VALUES (
                :event_id, :plant, :equipment, :event_type, :start_time, :end_time,
                :timezone, :source_id, :verification_status, :notes
            )
        """
        with self._connect() as connection:
            connection.executemany(sql, records)
        return len(records)

    def list_maintenance_events(
        self,
        *,
        plant: str | None = None,
        equipment: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        self._initialize_maintenance()
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("plant", plant),
            ("equipment", equipment),
            ("event_type", event_type),
            ("verification_status", status),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if start_date is not None:
            clauses.append("end_time >= ?")
            params.append(start_date)
        if end_date is not None:
            clauses.append("start_time < ?")
            params.append(end_date)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM maintenance_events" + where, params
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM maintenance_events" + where
                + " ORDER BY start_time DESC, event_id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], int(total)

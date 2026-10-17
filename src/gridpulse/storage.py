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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_entity "
                "ON audit_events(entity_type, entity_id, audit_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_recorded "
                "ON audit_events(recorded_at)"
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
            connection.executemany(
                "INSERT INTO audit_events(entity_type, entity_id, action, source_id, verification_status) "
                "VALUES ('observation', :record_id, 'created', :source_id, :verification_status)",
                records,
            )
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
            connection.executemany(
                "INSERT INTO audit_events(entity_type, entity_id, action, source_id, verification_status) "
                "VALUES ('maintenance_event', :event_id, 'created', :source_id, :verification_status)",
                records,
            )
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


    def summarize_maintenance_events(
        self,
        *,
        plant: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate maintenance event counts and elapsed hours in SQLite.

        Elapsed time is intentionally not named downtime: the event record alone
        does not establish the equipment's operating state.
        """
        self._initialize_maintenance()
        clauses: list[str] = []
        params: list[Any] = []
        if plant is not None:
            clauses.append("plant = ?")
            params.append(plant)
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
            by_type = connection.execute(
                "SELECT event_type, COUNT(*) AS event_count, "
                "COALESCE(SUM(MAX(0, (julianday(end_time)-julianday(start_time))*24)), 0) "
                "AS elapsed_hours FROM maintenance_events" + where
                + " GROUP BY event_type ORDER BY event_type",
                params,
            ).fetchall()
            by_equipment = connection.execute(
                "SELECT equipment, COUNT(*) AS event_count, "
                "COALESCE(SUM(MAX(0, (julianday(end_time)-julianday(start_time))*24)), 0) "
                "AS elapsed_hours FROM maintenance_events" + where
                + " GROUP BY equipment ORDER BY event_count DESC, equipment",
                params,
            ).fetchall()
            statuses = connection.execute(
                "SELECT verification_status, COUNT(*) AS event_count "
                "FROM maintenance_events" + where
                + " GROUP BY verification_status ORDER BY verification_status",
                params,
            ).fetchall()
        return {
            "total_events": int(total),
            "by_event_type": [dict(row) for row in by_type],
            "by_equipment": [dict(row) for row in by_equipment],
            "verification_status_counts": {
                row["verification_status"]: row["event_count"] for row in statuses
            },
            "duration_semantics": (
                "Elapsed event duration only; not equipment downtime or availability."
            ),
        }


    def observation_quality_report(self, *, plant: str | None = None) -> dict[str, Any]:
        """Summarize dataset coverage and provenance labels without inventing thresholds."""
        clauses = ["plant = ?"] if plant is not None else []
        params: list[Any] = [plant] if plant is not None else []
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            overview = connection.execute(
                "SELECT COUNT(*) AS total_records, "
                "COUNT(DISTINCT plant) AS plant_count, "
                "COUNT(DISTINCT metric) AS metric_count, "
                "COUNT(DISTINCT source_id) AS source_count, "
                "MIN(period_start) AS first_period, MAX(period_end) AS last_period "
                "FROM observations" + where,
                params,
            ).fetchone()
            statuses = connection.execute(
                "SELECT verification_status, COUNT(*) AS count FROM observations"
                + where + " GROUP BY verification_status ORDER BY verification_status",
                params,
            ).fetchall()
            scopes = connection.execute(
                "SELECT scope, COUNT(*) AS count FROM observations"
                + where + " GROUP BY scope ORDER BY scope",
                params,
            ).fetchall()
            sources = connection.execute(
                "SELECT source_id, COUNT(*) AS count FROM observations"
                + where + " GROUP BY source_id ORDER BY count DESC, source_id LIMIT 20",
                params,
            ).fetchall()
            metric_units = connection.execute(
                "SELECT metric, unit, COUNT(*) AS count FROM observations"
                + where + " GROUP BY metric, unit ORDER BY metric, unit",
                params,
            ).fetchall()
        return {
            "overview": dict(overview),
            "verification_status_counts": {
                row["verification_status"]: row["count"] for row in statuses
            },
            "scope_counts": {row["scope"]: row["count"] for row in scopes},
            "records_by_source_top_20": [dict(row) for row in sources],
            "metric_unit_coverage": [dict(row) for row in metric_units],
            "integrity_notes": [
                "Required schema fields are validated at ingestion; missing required fields are rejected.",
                "Unique record IDs are enforced by the database primary key.",
                "Verification labels are supplied by the data owner and are not independently certified.",
                "Counts and coverage do not establish accuracy, completeness against the real plant, or operational fitness.",
            ],
        }


    def list_audit_events(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Read the append-only application audit trail with bounded pagination."""
        clauses: list[str] = []
        params: list[Any] = []
        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM audit_events" + where, params
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT audit_id, entity_type, entity_id, action, source_id, "
                "verification_status, recorded_at FROM audit_events" + where
                + " ORDER BY audit_id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(row) for row in rows], int(total)

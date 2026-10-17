"""Persistent test-plan and test-execution records for engineering evidence."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class TestStore:
    """SQLite-backed test management with explicit evidence and approval state."""

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
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS test_plans (
                    plan_id TEXT PRIMARY KEY, title TEXT NOT NULL, plant TEXT NOT NULL,
                    asset_id TEXT, work_package_id TEXT, objective TEXT NOT NULL,
                    method_reference TEXT NOT NULL, revision TEXT NOT NULL,
                    status TEXT NOT NULL, source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL, notes TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    FOREIGN KEY(asset_id) REFERENCES assets(asset_id)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS test_cases (
                    case_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, title TEXT NOT NULL,
                    parameter TEXT NOT NULL, unit TEXT NOT NULL, acceptance_min REAL,
                    acceptance_max REAL, acceptance_text TEXT NOT NULL, method_reference TEXT NOT NULL,
                    instrument_reference TEXT NOT NULL, baseline_value REAL, notes TEXT NOT NULL,
                    FOREIGN KEY(plan_id) REFERENCES test_plans(plan_id) ON DELETE CASCADE
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS test_executions (
                    execution_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, executed_at TEXT NOT NULL,
                    measured_value REAL, measured_unit TEXT NOT NULL, result TEXT NOT NULL,
                    operator TEXT NOT NULL, evidence_reference TEXT NOT NULL, source_id TEXT NOT NULL,
                    verification_status TEXT NOT NULL, approval_status TEXT NOT NULL,
                    notes TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    FOREIGN KEY(case_id) REFERENCES test_cases(case_id) ON DELETE CASCADE
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_test_cases_plan ON test_cases(plan_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_test_exec_case ON test_executions(case_id)")
            db.execute("CREATE TABLE IF NOT EXISTS test_audit_events (audit_id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL, source_id TEXT NOT NULL, recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))")

    def create_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("INSERT INTO test_plans(plan_id,title,plant,asset_id,work_package_id,objective,method_reference,revision,status,source_id,verification_status,notes) VALUES (:plan_id,:title,:plant,:asset_id,:work_package_id,:objective,:method_reference,:revision,:status,:source_id,:verification_status,:notes)", data)
            db.execute("INSERT INTO test_audit_events(entity_type,entity_id,action,source_id) VALUES ('test_plan',?,?,?)", (data['plan_id'], 'created', data['source_id']))
            return dict(db.execute("SELECT * FROM test_plans WHERE plan_id=?", (data['plan_id'],)).fetchone())

    def create_case(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            if db.execute("SELECT 1 FROM test_plans WHERE plan_id=?", (data['plan_id'],)).fetchone() is None:
                raise ValueError("plan_id does not exist")
            db.execute("INSERT INTO test_cases(case_id,plan_id,title,parameter,unit,acceptance_min,acceptance_max,acceptance_text,method_reference,instrument_reference,baseline_value,notes) VALUES (:case_id,:plan_id,:title,:parameter,:unit,:acceptance_min,:acceptance_max,:acceptance_text,:method_reference,:instrument_reference,:baseline_value,:notes)", data)
            return dict(db.execute("SELECT * FROM test_cases WHERE case_id=?", (data['case_id'],)).fetchone())

    def create_execution(self, data: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            case = db.execute("SELECT * FROM test_cases WHERE case_id=?", (data['case_id'],)).fetchone()
            if case is None:
                raise ValueError("case_id does not exist")
            result = data['result']
            measured = data.get('measured_value')
            if measured is not None:
                minimum, maximum = case['acceptance_min'], case['acceptance_max']
                if minimum is not None and measured < minimum:
                    result = 'fail'
                if maximum is not None and measured > maximum:
                    result = 'fail'
            data = {**data, 'result': result}
            db.execute("INSERT INTO test_executions(execution_id,case_id,executed_at,measured_value,measured_unit,result,operator,evidence_reference,source_id,verification_status,approval_status,notes) VALUES (:execution_id,:case_id,:executed_at,:measured_value,:measured_unit,:result,:operator,:evidence_reference,:source_id,:verification_status,:approval_status,:notes)", data)
            db.execute("INSERT INTO test_audit_events(entity_type,entity_id,action,source_id) VALUES ('test_execution',?,?,?)", (data['execution_id'], 'created', data['source_id']))
            return dict(db.execute("SELECT * FROM test_executions WHERE execution_id=?", (data['execution_id'],)).fetchone())

    def list_cases(self, plan_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if plan_id:
                rows = db.execute("SELECT * FROM test_cases WHERE plan_id=? ORDER BY case_id", (plan_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM test_cases ORDER BY case_id").fetchall()
            return [dict(row) for row in rows]

    def list_executions(self, case_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as db:
            if case_id:
                rows = db.execute("SELECT * FROM test_executions WHERE case_id=? ORDER BY executed_at DESC", (case_id,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM test_executions ORDER BY executed_at DESC").fetchall()
            return [dict(row) for row in rows]

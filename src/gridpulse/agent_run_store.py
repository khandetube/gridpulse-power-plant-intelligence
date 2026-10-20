"""Durable SQLite ledger for completed autonomous-agent runs.

The ledger stores run metadata and result evidence, never API credentials. The path can
be overridden with GRIDPULSE_AGENT_DB_PATH; deployers should place it on a persistent volume.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_DB = Path("data/agent_runs.sqlite3")


def _database_path() -> Path:
    raw = os.environ.get("GRIDPULSE_AGENT_DB_PATH", str(_DEFAULT_DB)).strip()
    return Path(raw).expanduser()


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('completed', 'failed')),
            request_fingerprint TEXT NOT NULL,
            result_json TEXT,
            error_summary TEXT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at DESC)"
    )
    return connection


def record_completed_run(request_metadata: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Persist a completed run atomically; store a hash, not the original prompt."""
    request_bytes = json.dumps(
        request_metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    request_fingerprint = hashlib.sha256(request_bytes).hexdigest()
    result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
    run_id = str(uuid.uuid4())
    created_at = datetime.now(UTC).isoformat()
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO agent_runs
                (run_id, created_at, status, request_fingerprint, result_json, error_summary)
            VALUES (?, ?, 'completed', ?, ?, NULL)
            """,
            (run_id, created_at, request_fingerprint, result_json),
        )
    return {
        "run_id": run_id,
        "created_at": created_at,
        "status": "completed",
        "request_fingerprint": request_fingerprint,
    }


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Return metadata only, bounded to 1–100 records."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with closing(_connect()) as connection, connection:
        rows = connection.execute(
            """
            SELECT run_id, created_at, status, request_fingerprint
            FROM agent_runs ORDER BY created_at DESC, rowid DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    """Retrieve one recorded result by UUID."""
    try:
        normalized_id = str(uuid.UUID(run_id))
    except (ValueError, TypeError, AttributeError):
        return None
    with closing(_connect()) as connection, connection:
        row = connection.execute(
            """
            SELECT run_id, created_at, status, request_fingerprint, result_json, error_summary
            FROM agent_runs WHERE run_id = ?
            """,
            (normalized_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["result"] = json.loads(item.pop("result_json")) if item["result_json"] else None
    return item

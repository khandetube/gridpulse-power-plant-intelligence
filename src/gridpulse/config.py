"""Shared filesystem configuration for GridPulse API modules.

Use one source-registry resolver so every workflow validates records against the same
registry, including deployments that mount their data directory at /app/data.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    configured = os.environ.get("GRIDPULSE_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return ROOT_DIR / "data"


def source_registry_path() -> Path:
    """Return the same source registry path for every API router."""
    configured = os.environ.get("GRIDPULSE_DATA_DIR", "").strip()
    if configured:
        preferred = Path(configured).expanduser() / "source_registry.csv"
        return preferred

    candidates = (ROOT_DIR / "data" / "source_registry.csv", Path("/app/data/source_registry.csv"))
    return next((path for path in candidates if path.is_file()), candidates[0])


def database_path() -> Path:
    """Return the shared SQLite path; deployments should set it to a persistent volume."""
    configured = os.environ.get("GRIDPULSE_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path("/tmp/gridpulse-observations.sqlite3")

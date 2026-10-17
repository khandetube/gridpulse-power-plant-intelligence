"""Read-only API foundation for source-aware power plant analytics.

This service intentionally does not connect to plant control or dispatch systems.
It exposes project metadata and source registry information only.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl

ROOT_DIR = Path(__file__).resolve().parents[2]
SOURCE_REGISTRY = ROOT_DIR / "data" / "source_registry.csv"

app = FastAPI(
    title="GridPulse AI API",
    version="0.1.0",
    description=(
        "Source-aware power plant analytics research API. "
        "No live telemetry or dispatch connection is configured."
    ),
)


class SourceRecord(BaseModel):
    source_id: str
    title: str
    publisher: str
    url: HttpUrl
    source_type: str
    scope: str
    publication_date: str | None = None
    verification_status: Literal["unverified", "reviewed", "verified"]
    notes: str


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for local development and deployment probes."""
    return {"status": "ok", "service": "gridpulse-api", "version": "0.1.0"}


@app.get("/api/v1/project")
def project_info() -> dict[str, object]:
    """Return project scope and data-integrity guarantees."""
    return {
        "name": "GridPulse AI",
        "version": "0.1.0",
        "focus": "power generation analytics and maintenance research",
        "case_study": "Shahid Kaveh combined-cycle power plant, Qaen, Iran",
        "live_telemetry_connected": False,
        "dispatch_system_connected": False,
        "data_policy": "Source-backed records only; unverified leads are labelled.",
    }


@app.get("/api/v1/sources", response_model=list[SourceRecord])
def list_sources(
    status: Literal["unverified", "reviewed", "verified"] | None = None,
) -> list[SourceRecord]:
    """List source leads; optionally filter by verification status."""
    if not SOURCE_REGISTRY.exists():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")

    try:
        with SOURCE_REGISTRY.open("r", encoding="utf-8", newline="") as csv_file:
            records = [SourceRecord.model_validate(row) for row in csv.DictReader(csv_file)]
    except (OSError, csv.Error, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Unable to read source registry") from exc

    if status is not None:
        records = [record for record in records if record.verification_status == status]
    return records

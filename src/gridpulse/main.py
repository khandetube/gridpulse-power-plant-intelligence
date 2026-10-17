"""Read-only API foundation for source-aware power plant analytics.

This service intentionally does not connect to plant control or dispatch systems.
It exposes project metadata and source registry information only.
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator

from gridpulse.analytics import analyze_observations

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


class ObservationInput(BaseModel):
    """One source-labelled observation supplied by an authorized data owner."""

    record_id: str = Field(min_length=1, max_length=128)
    plant: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=160)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=40)
    period_start: date
    period_end: date
    scope: Literal["unit", "plant", "multiple_plants", "regional", "national"]
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Literal["unverified", "reviewed", "verified"]

    @model_validator(mode="after")
    def validate_period(self) -> ObservationInput:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class ObservationBatch(BaseModel):
    """Bounded batch request for deterministic analytics."""

    records: list[ObservationInput] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_record_ids(self) -> ObservationBatch:
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id values must be unique within a batch")
        return self


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


@app.post("/api/v1/analytics/observations")
def analyze_observation_batch(batch: ObservationBatch) -> dict[str, object]:
    """Return grouped descriptive statistics and conservative IQR review flags."""
    payload = [
        {
            **record.model_dump(mode="json"),
            "period_start": record.period_start.isoformat(),
            "period_end": record.period_end.isoformat(),
        }
        for record in batch.records
    ]
    return analyze_observations(payload)


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

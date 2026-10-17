"""Read-only API foundation for source-aware power plant analytics.

This service intentionally does not connect to plant control or dispatch systems.
It exposes project metadata and source registry information only.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, model_validator

from gridpulse.analytics import analyze_observations
from gridpulse.engineering import calculate_generation_performance
from gridpulse.storage import ObservationStore

ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIGURED_DATA_DIR = Path(os.environ.get("GRIDPULSE_DATA_DIR", ROOT_DIR / "data"))
_DATA_DIR_CANDIDATES = (_CONFIGURED_DATA_DIR, Path("/app/data"))
SOURCE_REGISTRY = next(
    (directory / "source_registry.csv" for directory in _DATA_DIR_CANDIDATES
     if (directory / "source_registry.csv").is_file()),
    _CONFIGURED_DATA_DIR / "source_registry.csv",
)

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


class GenerationPerformanceInput(BaseModel):
    """Inputs must describe the same plant boundary and reporting interval."""

    plant: str = Field(min_length=1, max_length=200)
    period_start: date
    period_end: date
    net_generation_mwh: float = Field(gt=0, allow_inf_nan=False)
    fuel_thermal_input_mwh: float = Field(gt=0, allow_inf_nan=False)
    net_capacity_mw: float = Field(gt=0, allow_inf_nan=False)
    period_hours: float = Field(gt=0, le=8784, allow_inf_nan=False)
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Literal["unverified", "reviewed", "verified"]

    @model_validator(mode="after")
    def validate_period(self) -> GenerationPerformanceInput:
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class MaintenanceEventInput(BaseModel):
    """Source-labelled maintenance event; elapsed duration is not assumed downtime."""

    event_id: str = Field(min_length=1, max_length=128)
    plant: str = Field(min_length=1, max_length=200)
    equipment: str = Field(min_length=1, max_length=200)
    event_type: Literal[
        "inspection", "preventive", "corrective", "overhaul", "test", "other"
    ]
    start_time: datetime
    end_time: datetime
    timezone: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Literal["unverified", "reviewed", "verified"]
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_timestamps(self) -> MaintenanceEventInput:
        if self.start_time.utcoffset() is None or self.end_time.utcoffset() is None:
            raise ValueError("start_time and end_time must include an explicit UTC offset")
        if self.end_time < self.start_time:
            raise ValueError("end_time must be on or after start_time")
        return self


class MaintenanceEventBatch(BaseModel):
    records: list[MaintenanceEventInput] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_event_ids(self) -> MaintenanceEventBatch:
        ids = [record.event_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("event_id values must be unique within a batch")
        return self


def ensure_registered_sources(records: list[ObservationInput | MaintenanceEventInput]) -> None:
    """Reject records whose provenance IDs are absent from the source registry."""
    if not SOURCE_REGISTRY.exists():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    try:
        with SOURCE_REGISTRY.open("r", encoding="utf-8", newline="") as csv_file:
            registered = {
                row.get("source_id", "").strip()
                for row in csv.DictReader(csv_file)
                if row.get("source_id", "").strip()
            }
    except (OSError, csv.Error) as exc:
        raise HTTPException(status_code=503, detail="Source registry cannot be read") from exc
    unknown = sorted({str(record.source_id) for record in records} - registered)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"message": "Every record must reference a registered source_id.", "unknown_source_ids": unknown},
        )


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


def get_observation_store() -> ObservationStore:
    """Resolve the database path at request time for container and test isolation."""
    database_path = os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3")
    return ObservationStore(database_path)


@app.post("/api/v1/observations", status_code=201)
def create_observations(batch: ObservationBatch) -> dict[str, object]:
    """Persist a validated observation batch in one SQLite transaction."""
    ensure_registered_sources(batch.records)
    records = [record.model_dump(mode="json") for record in batch.records]
    try:
        count = get_observation_store().insert_many(records)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="At least one record_id already exists; no records from this batch were stored.",
        ) from exc
    return {
        "inserted_count": count,
        "record_ids": [record["record_id"] for record in records],
        "storage": "sqlite",
        "message": "Caller-supplied observations stored; source truth is not independently verified.",
    }


@app.get("/api/v1/observations")
def get_observations(
    plant: str | None = Query(default=None, min_length=1, max_length=200),
    metric: str | None = Query(default=None, min_length=1, max_length=160),
    status: Literal["unverified", "reviewed", "verified"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """Query stored observations with filters and bounded pagination."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    records, total = get_observation_store().list_records(
        plant=plant,
        metric=metric,
        status=status,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "limit": limit, "offset": offset, "records": records}


@app.post("/api/v1/maintenance/events", status_code=201)
def create_maintenance_events(batch: MaintenanceEventBatch) -> dict[str, object]:
    """Persist validated, offset-aware maintenance events in one transaction."""
    ensure_registered_sources(batch.records)
    records = []
    for event in batch.records:
        row = event.model_dump(mode="json")
        row["start_time"] = event.start_time.astimezone(UTC).isoformat()
        row["end_time"] = event.end_time.astimezone(UTC).isoformat()
        records.append(row)
    try:
        count = get_observation_store().insert_maintenance_many(records)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="At least one event_id already exists; no events from this batch were stored.",
        ) from exc
    return {
        "inserted_count": count,
        "event_ids": [record["event_id"] for record in records],
        "storage": "sqlite",
        "duration_semantics": "Elapsed event duration; not necessarily equipment downtime.",
    }


@app.get("/api/v1/maintenance/events")
def get_maintenance_events(
    plant: str | None = Query(default=None, min_length=1, max_length=200),
    equipment: str | None = Query(default=None, min_length=1, max_length=200),
    event_type: Literal["inspection", "preventive", "corrective", "overhaul", "test", "other"] | None = None,
    status: Literal["unverified", "reviewed", "verified"] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """Query maintenance events with validated filters and bounded pagination."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    records, total = get_observation_store().list_maintenance_events(
        plant=plant,
        equipment=equipment,
        event_type=event_type,
        status=status,
        start_date=start_date.isoformat() + "T00:00:00" if start_date else None,
        end_date=(end_date + timedelta(days=1)).isoformat() + "T00:00:00" if end_date else None,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "records": records,
        "duration_semantics": "Elapsed event duration; not necessarily equipment downtime.",
    }


@app.get("/api/v1/maintenance/summary")
def maintenance_summary(
    plant: str | None = Query(default=None, min_length=1, max_length=200),
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, object]:
    """Return SQL-backed maintenance counts and elapsed-time summaries."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    summary = get_observation_store().summarize_maintenance_events(
        plant=plant,
        start_date=start_date.isoformat() + "T00:00:00" if start_date else None,
        end_date=(end_date + timedelta(days=1)).isoformat() + "T00:00:00" if end_date else None,
    )
    return summary


@app.get("/api/v1/analytics/data-quality")
def observation_data_quality(
    plant: str | None = Query(default=None, min_length=1, max_length=200),
) -> dict[str, object]:
    """Report dataset coverage and provenance distribution from persisted records."""
    return get_observation_store().observation_quality_report(plant=plant)


@app.post("/api/v1/engineering/generation-performance")
def generation_performance(
    request: GenerationPerformanceInput,
) -> dict[str, object]:
    """Calculate net efficiency, net heat rate, and capacity factor from explicit units."""
    ensure_registered_sources([request])
    try:
        result = calculate_generation_performance(
            net_generation_mwh=request.net_generation_mwh,
            fuel_thermal_input_mwh=request.fuel_thermal_input_mwh,
            net_capacity_mw=request.net_capacity_mw,
            period_hours=request.period_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "plant": request.plant,
        "period_start": request.period_start.isoformat(),
        "period_end": request.period_end.isoformat(),
        "source_id": request.source_id,
        "verification_status": request.verification_status,
        **result,
    }


@app.get("/api/v1/audit/events")
def get_audit_events(
    entity_type: Literal["observation", "maintenance_event"] | None = None,
    entity_id: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """Return append-only ingestion audit records with bounded pagination."""
    records, total = get_observation_store().list_audit_events(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return {"total": total, "limit": limit, "offset": offset, "events": records}


@app.post("/api/v1/analytics/observations")
def analyze_observation_batch(batch: ObservationBatch) -> dict[str, object]:
    """Return grouped descriptive statistics and conservative IQR review flags."""
    ensure_registered_sources(batch.records)
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

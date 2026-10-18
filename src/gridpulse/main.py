"""Source-aware API foundation for power plant engineering decision support."""
from __future__ import annotations

import csv
import os
import secrets
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator

from gridpulse.analytics import analyze_observations
from gridpulse.assets_api import router as assets_router
from gridpulse.engineering import calculate_generation_performance
from gridpulse.fmea_api import router as fmea_router
from gridpulse.inspections_api import router as inspections_router
from gridpulse.offline_ai_api import router as offline_ai_router
from gridpulse.storage import ObservationStore
from gridpulse.testing_api import router as testing_router
from gridpulse.turnarounds_api import router as turnarounds_router
from gridpulse.work_orders_api import router as work_orders_router

ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIGURED_DATA_DIR = Path(os.environ.get("GRIDPULSE_DATA_DIR", ROOT_DIR / "data"))
_DATA_DIR_CANDIDATES = (_CONFIGURED_DATA_DIR, Path("/app/data"))
SOURCE_REGISTRY = next((directory / "source_registry.csv" for directory in _DATA_DIR_CANDIDATES if (directory / "source_registry.csv").is_file()), _CONFIGURED_DATA_DIR / "source_registry.csv")

app = FastAPI(title="GridPulse AI API", version="0.1.0", description="Source-aware power plant analytics and engineering decision-support API. No live telemetry or dispatch connection is configured.")
app.include_router(assets_router)
app.include_router(testing_router)
app.include_router(fmea_router)
app.include_router(inspections_router)
app.include_router(offline_ai_router)
app.include_router(work_orders_router)
app.include_router(turnarounds_router)


@app.middleware("http")
async def optional_api_key_guard(request: Request, call_next):
    expected_key = os.environ.get("GRIDPULSE_API_KEY", "")
    if expected_key and request.url.path.startswith("/api/v1/"):
        supplied_key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(supplied_key, expected_key):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key."}, headers={"WWW-Authenticate": "ApiKey"})
    return await call_next(request)


# Permit the public static dashboard to talk only to a loopback API instance.
# The API key remains mandatory when configured; CORS is not authentication.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://khandetube.github.io", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
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
    records: list[ObservationInput] = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def unique_record_ids(self) -> ObservationBatch:
        ids = [record.record_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id values must be unique within a batch")
        return self


class GenerationPerformanceInput(BaseModel):
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
    event_id: str = Field(min_length=1, max_length=128)
    plant: str = Field(min_length=1, max_length=200)
    equipment: str = Field(min_length=1, max_length=200)
    event_type: Literal["inspection", "preventive", "corrective", "overhaul", "test", "other"]
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
    if not SOURCE_REGISTRY.exists():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    try:
        with SOURCE_REGISTRY.open("r", encoding="utf-8", newline="") as csv_file:
            registered = {row.get("source_id", "").strip() for row in csv.DictReader(csv_file) if row.get("source_id", "").strip()}
    except (OSError, csv.Error) as exc:
        raise HTTPException(status_code=503, detail="Source registry cannot be read") from exc
    unknown = sorted({str(record.source_id) for record in records} - registered)
    if unknown:
        raise HTTPException(status_code=422, detail={"message": "Every record must reference a registered source_id.", "unknown_source_ids": unknown})


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe: confirms the web process can answer requests."""
    return {"status": "ok", "service": "gridpulse-api", "version": "0.1.0"}


@app.get("/ready", response_model=None)
def readiness() -> JSONResponse | dict[str, object]:
    """Readiness probe checks the source registry and configured SQLite storage."""
    checks: dict[str, str] = {
        "source_registry": "ok" if SOURCE_REGISTRY.is_file() else "unavailable",
        "database": "unknown",
    }
    try:
        store = get_observation_store()
        with sqlite3.connect(store.database_path, timeout=3) as connection:
            connection.execute("SELECT 1").fetchone()
        checks["database"] = "ok"
    except (OSError, sqlite3.Error, RuntimeError):
        checks["database"] = "unavailable"
    ready = all(value == "ok" for value in checks.values())
    payload = {"status": "ready" if ready else "not_ready", "service": "gridpulse-api", "checks": checks}
    return payload if ready else JSONResponse(status_code=503, content=payload)


@app.get("/api/v1/system/diagnostics")
def system_diagnostics() -> dict[str, object]:
    """Return bounded, non-secret diagnostics for the local application stack."""
    source_count = 0
    source_registry_status = "unavailable"
    try:
        with SOURCE_REGISTRY.open("r", encoding="utf-8", newline="") as source_file:
            reader = csv.DictReader(source_file)
            if reader.fieldnames and "source_id" in reader.fieldnames:
                source_count = sum(1 for row in reader if (row.get("source_id") or "").strip())
                source_registry_status = "ok"
            else:
                source_registry_status = "invalid_schema"
    except (OSError, csv.Error):
        source_registry_status = "unavailable"

    database_status = "unavailable"
    table_counts: dict[str, int] = {}
    try:
        store = get_observation_store()
        with sqlite3.connect(store.database_path, timeout=3) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            if integrity and integrity[0] == "ok":
                database_status = "ok"
            existing_tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table in ("observations", "maintenance_events", "audit_events"):
                if table in existing_tables:
                    # Table names are selected from this fixed allow-list, not user input.
                    table_counts[table] = int(
                        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    )
                else:
                    table_counts[table] = 0
    except (OSError, sqlite3.Error, RuntimeError):
        database_status = "unavailable"

    checks = {"source_registry": source_registry_status, "database": database_status}
    return {
        "service": "gridpulse-api",
        "status": "ok" if all(value == "ok" for value in checks.values()) else "degraded",
        "checks": checks,
        "registered_source_count": source_count,
        "stored_record_counts": table_counts,
        "capabilities": {
            "persistent_storage": database_status == "ok",
            "source_registry": source_registry_status == "ok",
            "live_plant_telemetry": False,
            "dispatch_connection": False,
            "predictive_model_validated": False,
        },
        "notes": [
            "Counts are application-local and do not certify source truth or plant state.",
            "No secrets, filesystem paths, credentials, or network configuration are returned.",
        ],
    }


@app.get("/api/v1/project")
def project_info() -> dict[str, object]:
    return {"name": "GridPulse AI", "version": "0.1.0", "focus": "power generation analytics and maintenance research", "case_study": "Shahid Kaveh combined-cycle power plant, Qaen, Iran", "live_telemetry_connected": False, "dispatch_system_connected": False, "data_policy": "Source-backed records only; unverified leads are labelled."}


def get_observation_store() -> ObservationStore:
    return ObservationStore(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))


@app.post("/api/v1/observations", status_code=201)
def create_observations(batch: ObservationBatch) -> dict[str, object]:
    ensure_registered_sources(batch.records)
    records = [record.model_dump(mode="json") for record in batch.records]
    try:
        count = get_observation_store().insert_many(records)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="At least one record_id already exists; no records from this batch were stored.") from exc
    return {"inserted_count": count, "record_ids": [record["record_id"] for record in records], "storage": "sqlite", "message": "Caller-supplied observations stored; source truth is not independently verified."}


@app.get("/api/v1/observations")
def get_observations(plant: str | None = Query(default=None, min_length=1, max_length=200), metric: str | None = Query(default=None, min_length=1, max_length=160), status: Literal["unverified", "reviewed", "verified"] | None = None, start_date: date | None = None, end_date: date | None = None, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    records, total = get_observation_store().list_records(plant=plant, metric=metric, status=status, start_date=start_date.isoformat() if start_date else None, end_date=end_date.isoformat() if end_date else None, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "records": records}


@app.post("/api/v1/maintenance/events", status_code=201)
def create_maintenance_events(batch: MaintenanceEventBatch) -> dict[str, object]:
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
        raise HTTPException(status_code=409, detail="At least one event_id already exists; no events from this batch were stored.") from exc
    return {"inserted_count": count, "event_ids": [record["event_id"] for record in records], "storage": "sqlite", "duration_semantics": "Elapsed event duration; not necessarily equipment downtime."}


@app.get("/api/v1/maintenance/events")
def get_maintenance_events(plant: str | None = Query(default=None, min_length=1, max_length=200), equipment: str | None = Query(default=None, min_length=1, max_length=200), event_type: Literal["inspection", "preventive", "corrective", "overhaul", "test", "other"] | None = None, status: Literal["unverified", "reviewed", "verified"] | None = None, start_date: date | None = None, end_date: date | None = None, limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    records, total = get_observation_store().list_maintenance_events(plant=plant, equipment=equipment, event_type=event_type, status=status, start_date=start_date.isoformat() + "T00:00:00" if start_date else None, end_date=(end_date + timedelta(days=1)).isoformat() + "T00:00:00" if end_date else None, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "records": records, "duration_semantics": "Elapsed event duration; not necessarily equipment downtime."}


@app.get("/api/v1/maintenance/summary")
def maintenance_summary(plant: str | None = Query(default=None, min_length=1, max_length=200), start_date: date | None = None, end_date: date | None = None) -> dict[str, object]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    return get_observation_store().summarize_maintenance_events(plant=plant, start_date=start_date.isoformat() + "T00:00:00" if start_date else None, end_date=(end_date + timedelta(days=1)).isoformat() + "T00:00:00" if end_date else None)


@app.get("/api/v1/analytics/data-quality")
def observation_data_quality(plant: str | None = Query(default=None, min_length=1, max_length=200)) -> dict[str, object]:
    return get_observation_store().observation_quality_report(plant=plant)


@app.post("/api/v1/engineering/generation-performance")
def generation_performance(request: GenerationPerformanceInput) -> dict[str, object]:
    ensure_registered_sources([request])
    try:
        result = calculate_generation_performance(net_generation_mwh=request.net_generation_mwh, fuel_thermal_input_mwh=request.fuel_thermal_input_mwh, net_capacity_mw=request.net_capacity_mw, period_hours=request.period_hours)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"plant": request.plant, "period_start": request.period_start.isoformat(), "period_end": request.period_end.isoformat(), "source_id": request.source_id, "verification_status": request.verification_status, **result}


@app.get("/api/v1/audit/events")
def get_audit_events(entity_type: Literal["observation", "maintenance_event"] | None = None, entity_id: str | None = Query(default=None, min_length=1, max_length=128), limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    records, total = get_observation_store().list_audit_events(entity_type=entity_type, entity_id=entity_id, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "events": records}


@app.post("/api/v1/analytics/observations")
def analyze_observation_batch(batch: ObservationBatch) -> dict[str, object]:
    ensure_registered_sources(batch.records)
    payload = [{**record.model_dump(mode="json"), "period_start": record.period_start.isoformat(), "period_end": record.period_end.isoformat()} for record in batch.records]
    return analyze_observations(payload)


@app.get("/api/v1/sources", response_model=list[SourceRecord])
def list_sources(status: Literal["unverified", "reviewed", "verified"] | None = None) -> list[SourceRecord]:
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

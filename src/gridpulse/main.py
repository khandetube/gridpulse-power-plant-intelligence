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
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl, model_validator

from gridpulse.analytics import analyze_observations
from gridpulse.assets_api import router as assets_router
from gridpulse.engineering import calculate_generation_performance
from gridpulse.fmea_api import router as fmea_router
from gridpulse.storage import ObservationStore
from gridpulse.testing_api import router as testing_router

ROOT_DIR = Path(__file__).resolve().parents[2]
_CONFIGURED_DATA_DIR = Path(os.environ.get("GRIDPULSE_DATA_DIR", ROOT_DIR / "data"))
_DATA_DIR_CANDIDATES = (_CONFIGURED_DATA_DIR, Path("/app/data"))
SOURCE_REGISTRY = next((directory / "source_registry.csv" for directory in _DATA_DIR_CANDIDATES if (directory / "source_registry.csv").is_file()), _CONFIGURED_DATA_DIR / "source_registry.csv")

app = FastAPI(title="GridPulse AI API", version="0.1.0", description="Source-aware power plant analytics and engineering decision-support API. No live telemetry or dispatch connection is configured.")
app.include_router(assets_router)
app.include_router(testing_router)
app.include_router(fmea_router)


@app.middleware("http")
async def optional_api_key_guard(request: Request, call_next):
    expected_key = os.environ.get("GRIDPULSE_API_KEY", "")
    if expected_key and request.url.path.startswith("/api/v1/"):
        supplied_key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(supplied_key, expected_key):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key."}, headers={"WWW-Authenticate": "ApiKey"})
    return await call_next(request)


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

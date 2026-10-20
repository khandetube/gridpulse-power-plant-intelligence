"""API routes for traceable Failure Mode and Effects Analysis."""
from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gridpulse.fmea import FMEAStore

router = APIRouter(prefix="/api/v1/fmea", tags=["fmea"])
Verification = Literal["unverified", "reviewed", "verified"]
Approval = Literal["pending", "reviewed", "approved", "rejected"]

class FailureModeInput(BaseModel):
    failure_mode_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    function: str = Field(min_length=1, max_length=1000)
    failure_mode: str = Field(min_length=1, max_length=2000)
    cause: str = Field(min_length=1, max_length=4000)
    effect: str = Field(min_length=1, max_length=4000)
    severity: int = Field(ge=1, le=10)
    occurrence: int = Field(ge=1, le=10)
    detectability: int = Field(ge=1, le=10)
    mitigation: str = Field(default="", max_length=4000)
    evidence_reference: str = Field(default="", max_length=1000)
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Verification = "unverified"
    revision: str = Field(default="1.0", max_length=40)
    approval_status: Approval = "pending"
    notes: str = Field(default="", max_length=4000)

class FMEAReview(BaseModel):
    mitigation: str | None = Field(default=None, max_length=4000)
    approval_status: Approval | None = None
    verification_status: Verification | None = None
    source_id: str = Field(min_length=1, max_length=128)

def store() -> FMEAStore:
    return FMEAStore(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))

def require_source(source_id: str) -> None:
    from gridpulse.config import source_registry_path
    registry = source_registry_path()
    if not registry.is_file():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    with registry.open("r", encoding="utf-8", newline="") as handle:
        ids = {row.get("source_id", "").strip() for row in csv.DictReader(handle)}
    if source_id not in ids:
        raise HTTPException(status_code=422, detail={"message": "source_id is not registered", "source_id": source_id})

@router.post("", status_code=201)
def create_failure_mode(request: FailureModeInput) -> dict[str, object]:
    require_source(request.source_id)
    try:
        return store().create(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="failure_mode_id already exists or asset_id is invalid") from exc

@router.get("")
def list_failure_modes(asset_id: str | None = Query(default=None, max_length=128), approval_status: Approval | None = None, min_rpn: int | None = Query(default=None, ge=1, le=1000)) -> dict[str, object]:
    return {"records": store().list(asset_id=asset_id, approval_status=approval_status, min_rpn=min_rpn)}

@router.get("/{failure_mode_id}")
def get_failure_mode(failure_mode_id: str) -> dict[str, object]:
    record = store().get(failure_mode_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Failure mode not found")
    return record

@router.patch("/{failure_mode_id}")
def review_failure_mode(failure_mode_id: str, request: FMEAReview) -> dict[str, object]:
    require_source(request.source_id)
    record = store().update_review(failure_mode_id, mitigation=request.mitigation, approval_status=request.approval_status, verification_status=request.verification_status, source_id=request.source_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Failure mode not found")
    return record

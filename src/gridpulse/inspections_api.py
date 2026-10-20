"""API endpoints for traceable equipment inspections."""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gridpulse.inspections import InspectionStore

router = APIRouter(prefix="/api/v1/inspections", tags=["inspections"])
Condition = Literal["unknown", "good", "monitor", "degraded", "critical"]
Verification = Literal["unverified", "reviewed", "verified"]
Approval = Literal["pending", "reviewed", "approved", "rejected"]


class InspectionInput(BaseModel):
    inspection_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    inspection_type: str = Field(min_length=1, max_length=160)
    inspected_at: datetime
    inspector: str = Field(min_length=1, max_length=200)
    condition_rating: Condition = "unknown"
    findings: str = Field(default="", max_length=6000)
    recommendation: str = Field(default="", max_length=6000)
    evidence_reference: str = Field(default="", max_length=1000)
    method_reference: str = Field(min_length=1, max_length=500)
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Verification = "unverified"
    approval_status: Approval = "pending"
    next_due_at: datetime | None = None
    notes: str = Field(default="", max_length=4000)


class InspectionReview(BaseModel):
    findings: str | None = Field(default=None, max_length=6000)
    recommendation: str | None = Field(default=None, max_length=6000)
    condition_rating: Condition | None = None
    verification_status: Verification | None = None
    approval_status: Approval | None = None
    source_id: str = Field(min_length=1, max_length=128)


def store() -> InspectionStore:
    return InspectionStore(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))


def require_source(source_id: str) -> None:
    from gridpulse.config import source_registry_path
    registry = source_registry_path()
    if not registry.is_file():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    try:
        with registry.open("r", encoding="utf-8", newline="") as handle:
            ids = {row.get("source_id", "").strip() for row in csv.DictReader(handle)}
    except (OSError, csv.Error) as exc:
        raise HTTPException(status_code=503, detail="Source registry cannot be read") from exc
    if source_id not in ids:
        raise HTTPException(status_code=422, detail={"message": "source_id is not registered", "source_id": source_id})


@router.post("", status_code=201)
def create_inspection(request: InspectionInput) -> dict[str, object]:
    require_source(request.source_id)
    if request.inspected_at.utcoffset() is None or (request.next_due_at and request.next_due_at.utcoffset() is None):
        raise HTTPException(status_code=422, detail="Timestamps must include an explicit UTC offset")
    payload = request.model_dump(mode="json")
    payload["inspected_at"] = request.inspected_at.isoformat()
    payload["next_due_at"] = request.next_due_at.isoformat() if request.next_due_at else None
    try:
        return store().create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="inspection_id already exists or asset_id is invalid") from exc


@router.get("")
def list_inspections(asset_id: str | None = Query(default=None, max_length=128),
                     condition_rating: Condition | None = None, approval_status: Approval | None = None,
                     limit: int = Query(default=100, ge=1, le=1000),
                     offset: int = Query(default=0, ge=0)) -> dict[str, object]:
    records, total = store().list(asset_id=asset_id, condition_rating=condition_rating,
                                  approval_status=approval_status, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "records": records,
            "note": "Inspection records are caller-supplied and do not constitute a safety clearance."}


@router.get("/{inspection_id}")
def get_inspection(inspection_id: str) -> dict[str, object]:
    record = store().get(inspection_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return record


@router.patch("/{inspection_id}")
def review_inspection(inspection_id: str, request: InspectionReview) -> dict[str, object]:
    require_source(request.source_id)
    record = store().update_review(inspection_id, findings=request.findings,
        recommendation=request.recommendation, condition_rating=request.condition_rating,
        verification_status=request.verification_status, approval_status=request.approval_status,
        source_id=request.source_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return record

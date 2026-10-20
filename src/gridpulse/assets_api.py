"""API routes for normalized equipment/assets used by engineering workflows."""
from __future__ import annotations

import csv
import os
import sqlite3
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from gridpulse.assets import AssetStore

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])

from gridpulse.config import source_registry_path

SOURCE_REGISTRY = source_registry_path()

AssetCriticality = Literal["low", "medium", "high", "critical"]
LifecycleState = Literal["planned", "active", "standby", "maintenance", "retired"]
VerificationStatus = Literal["unverified", "reviewed", "verified"]


class AssetInput(BaseModel):
    asset_id: str = Field(min_length=1, max_length=128)
    plant: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(min_length=1, max_length=120)
    parent_asset_id: str | None = Field(default=None, max_length=128)
    manufacturer: str = Field(default="", max_length=160)
    model: str = Field(default="", max_length=160)
    serial_number: str = Field(default="", max_length=160)
    criticality: AssetCriticality = "medium"
    lifecycle_state: LifecycleState = "active"
    commissioning_date: date | None = None
    rated_capacity_mw: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: VerificationStatus = "unverified"
    notes: str = Field(default="", max_length=4000)


class AssetPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_type: str | None = Field(default=None, min_length=1, max_length=120)
    parent_asset_id: str | None = Field(default=None, max_length=128)
    manufacturer: str | None = Field(default=None, max_length=160)
    model: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=160)
    criticality: AssetCriticality | None = None
    lifecycle_state: LifecycleState | None = None
    commissioning_date: date | None = None
    rated_capacity_mw: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source_id: str | None = Field(default=None, min_length=1, max_length=128)
    verification_status: VerificationStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)


def store() -> AssetStore:
    return AssetStore(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))


def require_source(source_id: str) -> None:
    if not SOURCE_REGISTRY.is_file():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    try:
        with SOURCE_REGISTRY.open("r", encoding="utf-8", newline="") as handle:
            registered = {row.get("source_id", "").strip() for row in csv.DictReader(handle)}
    except (OSError, csv.Error) as exc:
        raise HTTPException(status_code=503, detail="Source registry cannot be read") from exc
    if source_id not in registered:
        raise HTTPException(status_code=422, detail={"message": "source_id is not registered", "source_id": source_id})


@router.post("", status_code=201)
def create_asset(request: AssetInput) -> dict[str, object]:
    require_source(request.source_id)
    payload = request.model_dump(mode="json")
    try:
        return store().create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="asset_id already exists or parent_asset_id is invalid") from exc


@router.get("")
def list_assets(
    plant: str | None = Query(default=None, min_length=1, max_length=200),
    asset_type: str | None = Query(default=None, min_length=1, max_length=120),
    criticality: AssetCriticality | None = None,
    lifecycle_state: LifecycleState | None = None,
    parent_asset_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    records, total = store().list(plant=plant, asset_type=asset_type, criticality=criticality,
                                  lifecycle_state=lifecycle_state, parent_asset_id=parent_asset_id,
                                  limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "records": records}


@router.get("/hierarchy")
def asset_hierarchy(plant: str | None = Query(default=None, min_length=1, max_length=200)) -> dict[str, object]:
    return {"plant": plant, "hierarchy": store().hierarchy(plant=plant)}


@router.get("/{asset_id}")
def get_asset(asset_id: str) -> dict[str, object]:
    record = store().get(asset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return record


@router.patch("/{asset_id}")
def update_asset(asset_id: str, request: AssetPatch) -> dict[str, object]:
    changes = request.model_dump(exclude_unset=True, mode="json")
    if "source_id" in changes:
        require_source(changes["source_id"])
    try:
        record = store().update(asset_id, changes)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Invalid parent_asset_id or asset constraint") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return record


@router.delete("/{asset_id}")
def delete_asset(asset_id: str) -> dict[str, object]:
    try:
        deleted = store().delete(asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found")
    return {"asset_id": asset_id, "deleted": True}

"""API for traceable engineering test plans, cases and executions."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from gridpulse.testing import TestStore

router = APIRouter(prefix="/api/v1/testing", tags=["testing"])

Status = Literal["draft", "ready", "in_progress", "completed", "approved", "archived"]
Verification = Literal["unverified", "reviewed", "verified"]
Result = Literal["pass", "fail", "inconclusive", "not_executed"]
Approval = Literal["pending", "reviewed", "approved", "rejected"]


class TestPlanInput(BaseModel):
    plan_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    plant: str = Field(min_length=1, max_length=200)
    asset_id: str | None = Field(default=None, max_length=128)
    work_package_id: str | None = Field(default=None, max_length=128)
    objective: str = Field(min_length=1, max_length=4000)
    method_reference: str = Field(min_length=1, max_length=500)
    revision: str = Field(default="1.0", max_length=40)
    status: Status = "draft"
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Verification = "unverified"
    notes: str = Field(default="", max_length=4000)


class TestCaseInput(BaseModel):
    case_id: str = Field(min_length=1, max_length=128)
    plan_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    parameter: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    acceptance_min: float | None = None
    acceptance_max: float | None = None
    acceptance_text: str = Field(default="", max_length=1000)
    method_reference: str = Field(min_length=1, max_length=500)
    instrument_reference: str = Field(default="", max_length=240)
    baseline_value: float | None = None
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def bounds(self) -> TestCaseInput:
        if self.acceptance_min is not None and self.acceptance_max is not None and self.acceptance_min > self.acceptance_max:
            raise ValueError("acceptance_min must be <= acceptance_max")
        return self


class TestExecutionInput(BaseModel):
    execution_id: str = Field(min_length=1, max_length=128)
    case_id: str = Field(min_length=1, max_length=128)
    executed_at: datetime
    measured_value: float | None = None
    measured_unit: str = Field(min_length=1, max_length=40)
    result: Result = "not_executed"
    operator: str = Field(min_length=1, max_length=200)
    evidence_reference: str = Field(default="", max_length=1000)
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Verification = "unverified"
    approval_status: Approval = "pending"
    notes: str = Field(default="", max_length=4000)


def store() -> TestStore:
    return TestStore(os.environ.get("GRIDPULSE_DB_PATH", "/tmp/gridpulse-observations.sqlite3"))


def require_source(source_id: str) -> None:
    registry = Path(os.environ.get("GRIDPULSE_DATA_DIR", Path(__file__).resolve().parents[2] / "data")) / "source_registry.csv"
    if not registry.is_file():
        raise HTTPException(status_code=503, detail="Source registry is unavailable")
    import csv
    with registry.open("r", encoding="utf-8", newline="") as handle:
        ids = {row.get("source_id", "").strip() for row in csv.DictReader(handle)}
    if source_id not in ids:
        raise HTTPException(status_code=422, detail={"message": "source_id is not registered", "source_id": source_id})


@router.post("/plans", status_code=201)
def create_plan(request: TestPlanInput) -> dict[str, object]:
    require_source(request.source_id)
    try:
        return store().create_plan(request.model_dump(mode="json"))
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="plan_id already exists or asset_id is invalid") from exc


@router.post("/cases", status_code=201)
def create_case(request: TestCaseInput) -> dict[str, object]:
    try:
        return store().create_case(request.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="case_id already exists") from exc


@router.post("/executions", status_code=201)
def create_execution(request: TestExecutionInput) -> dict[str, object]:
    require_source(request.source_id)
    payload = request.model_dump(mode="json")
    try:
        return store().create_execution(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="execution_id already exists") from exc


@router.get("/cases")
def list_cases(plan_id: str | None = Query(default=None, max_length=128)) -> dict[str, object]:
    return {"records": store().list_cases(plan_id=plan_id)}


@router.get("/executions")
def list_executions(case_id: str | None = Query(default=None, max_length=128)) -> dict[str, object]:
    return {"records": store().list_executions(case_id=case_id)}

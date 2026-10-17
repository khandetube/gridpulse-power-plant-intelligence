"""API endpoint for local deterministic engineering analytics."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from gridpulse.local_llm import LocalModelUnavailable, generate_local_answer, local_model_status
from gridpulse.offline_ai import analyze_offline

router = APIRouter(prefix="/api/v1/ai", tags=["offline-ai"])


class OfflineObservation(BaseModel):
    record_id: str = Field(min_length=1, max_length=128)
    plant: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=160)
    value: float
    unit: str = Field(min_length=1, max_length=40)
    period_start: str
    period_end: str
    scope: Literal["unit", "plant", "multiple_plants", "regional", "national"]
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Literal["unverified", "reviewed", "verified"]


class OfflineAnalysisRequest(BaseModel):
    records: list[OfflineObservation] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_record_ids(self) -> OfflineAnalysisRequest:
        ids = [row.record_id for row in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id values must be unique")
        return self


@router.get("/status")
def offline_ai_status() -> dict[str, Any]:
    return {
        "engine": "gridpulse-offline-analytics-v1",
        "available": True,
        "mode": "offline_deterministic_statistics",
        "network_access": False,
        "external_services_required": False,
        "trained_language_model_included": False,\n        "optional_local_language_model": local_model_status(),
        "capabilities": ["robust_outlier_candidates", "group_statistics", "linear_trend_estimates", "input_quality_checks"],
        "not_capable_of": ["natural_language_generation", "failure_certification", "plant_control", "automatic_trip_or_dispatch"],
    }


@router.post("/analyze")
def offline_ai_analyze(request: OfflineAnalysisRequest) -> dict[str, Any]:
    try:
        return analyze_offline([record.model_dump(mode="json") for record in request.records])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class LocalChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=8000)
    context_records: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


@router.post("/chat")
def offline_ai_chat(request: LocalChatRequest) -> dict[str, Any]:
    try:
        return generate_local_answer(request.question, request.context_records)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LocalModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

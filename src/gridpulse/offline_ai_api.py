"""API endpoint for local deterministic engineering analytics."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from gridpulse.approved_limits import review_approved_limits
from gridpulse.data_quality import assess_data_quality
from gridpulse.diagnostic_ai import diagnose_observations
from gridpulse.knowledge import search_documents
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


class DataQualityRequest(BaseModel):
    records: list[OfflineObservation] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_record_ids(self) -> DataQualityRequest:
        ids = [row.record_id for row in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("record_id values must be unique")
        return self


class EngineeringLimit(BaseModel):
    plant: str = Field(min_length=1, max_length=200)
    metric: str = Field(min_length=1, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    scope: Literal["unit", "plant", "multiple_plants", "regional", "national"]
    min_value: float | None = None
    max_value: float | None = None
    source_id: str = Field(min_length=1, max_length=128)
    verification_status: Literal["unverified", "reviewed", "verified"]


class EngineeringLimitReviewRequest(BaseModel):
    records: list[OfflineObservation] = Field(min_length=1, max_length=5000)
    approved_limits: list[EngineeringLimit] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def unique_record_ids(self) -> EngineeringLimitReviewRequest:
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
        "trained_language_model_included": False,
        "optional_local_language_model": local_model_status(),
        "capabilities": ["robust_outlier_candidates", "group_statistics", "linear_trend_estimates", "trend_sample_sufficiency", "descriptive_linear_fit_r_squared", "rolling_mean_3", "first_to_latest_change_pct", "data_quality_report", "evidence_backed_review_insights", "input_quality_checks", "data_quality_evidence_engine", "verified_engineering_limit_review", "local_lexical_document_retrieval", "robust_recent_shift_screening", "sustained_level_shift_screening", "observation_cadence_gap_detection", "exploratory_matched_date_metric_associations"],
        "not_capable_of": ["language_generation_without_a_configured_local_model", "failure_certification", "plant_control", "automatic_trip_or_dispatch"],
    }


@router.post("/analyze")
def offline_ai_analyze(request: OfflineAnalysisRequest) -> dict[str, Any]:
    try:
        return analyze_offline([record.model_dump(mode="json") for record in request.records])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/data-quality")
def data_quality_review(request: DataQualityRequest) -> dict[str, Any]:
    try:
        return assess_data_quality([record.model_dump(mode="json") for record in request.records])
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/limits/review")
def engineering_limits_review(request: EngineeringLimitReviewRequest) -> dict[str, Any]:
    try:
        return review_approved_limits(
            [record.model_dump(mode="json") for record in request.records],
            [rule.model_dump(mode="json") for rule in request.approved_limits],
        )
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


class KnowledgeDocument(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=200000)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    documents: list[KnowledgeDocument] = Field(min_length=1, max_length=40)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/knowledge/search")
def offline_knowledge_search(request: KnowledgeSearchRequest) -> dict[str, Any]:
    try:
        return search_documents(
            request.query,
            [document.model_dump() for document in request.documents],
            request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/diagnose")
def offline_ai_diagnose(request: OfflineAnalysisRequest) -> dict[str, Any]:
    """Run advanced evidence-screening heuristics on bounded caller-supplied records."""
    try:
        return diagnose_observations([record.model_dump(mode="json") for record in request.records])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

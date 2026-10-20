"""HTTP API for the parametric prompt-to-CAD engine."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError

from gridpulse.cad_engine import (
    Discipline,
    EngineeringSpec,
    review_spec,
    to_dxf,
    to_freecad_macro,
    to_openscad,
    to_svg,
)
from gridpulse.cad_engine_advanced_calculations import run_advanced_calculations
from gridpulse.cad_engine_agent import run_design_agent
from gridpulse.cad_engine_calculations import run_engineering_calculations
from gridpulse.cad_engine_intelligence import analyze_design_intelligence
from gridpulse.ai_design_reasoning import run_engineering_reasoning
from gridpulse.cad_change_impact import analyze_change_impact
from gridpulse.cad_engine_multiformat import (
    export_engineering_workbook,
    export_multi_application_bundle,
)

router = APIRouter(prefix="/api/v1/cad", tags=["parametric-cad"])


class GenerateCadRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    site_width: float = Field(default=80, ge=10, le=500)
    site_length: float = Field(default=55, ge=10, le=500)
    template: Literal["process", "power", "substation", "building", "water"] = "process"
    disciplines: list[Discipline] = Field(default_factory=lambda: ["Mechanical", "Piping", "Electrical", "Instrumentation", "Architecture"], min_length=1, max_length=10)
    use_llm: bool = True


class CalculationRequest(BaseModel):
    spec: EngineeringSpec
    parameters: dict[str, float | int | str | None] = Field(default_factory=dict, max_length=100)


class ChangeImpactRequest(BaseModel):
    before: EngineeringSpec
    after: EngineeringSpec


@router.get("/status")
def cad_engine_status() -> dict:
    """Report actual runtime capabilities and whether the optional model is configured."""
    import os
    configured = all(os.environ.get(key, "").strip() for key in ("GRIDPULSE_LLM_BASE_URL", "GRIDPULSE_LLM_API_KEY", "GRIDPULSE_LLM_MODEL"))
    return {
        "engine": "GridPulse Parametric CAD Engine",
        "version": "0.6.0",
        "available": True,
        "geometry_backend": "parametric-spec + multi-stage design agent + deterministic engineering calculations + advanced sizing/network calculations + OpenSCAD + FreeCAD macro source + SVG + DXF R12",
        "calculation_backend": "first-principles deterministic equations with explicit-input gating, traceability and project-limit rule checks",
        "llm_configured": configured,
        "llm_mode": "OpenAI-compatible JSON spec" if configured else "deterministic prompt parser + multi-stage reasoning",
        "agent_stages": ["requirements", "discipline coordination", "parametric geometry", "topology/clash heuristics", "engineering calculations/rules", "advanced sizing/network calculations", "evidence-first AI reasoning", "design critique and quality gate", "multi-application handoff"],
        "outputs": ["engineering_spec.json", "plan.svg", "plan.dxf", "model.scad", "model.FCMacro", "autocad_model.dxf", "3dsmax_generator.ms", "revit_dynamo_generator.py", "gridpulse_engineering_handoff.xlsx", "engineering_intelligence.json", "design_agent_report.json", "calculation_report.json", "advanced_calculation_report.json"],
        "limitations": ["Calculations require explicit design-basis inputs and do not invent missing values", "Project/code-specific limits and manufacturer data are not inferred", "STEP/FCStd files are generated only when the exported macro is run in an installed FreeCAD environment", "No construction/safety approval", "Not connected to plant telemetry or dispatch systems"],
    }


@router.post("/generate")
def generate_cad(request: GenerateCadRequest) -> dict:
    """Generate one bounded, editable geometry model plus reasoning, calculations and exports."""
    try:
        agent = run_design_agent(request.prompt, request.site_width, request.site_length, request.disciplines, request.template, request.use_llm)
        spec = EngineeringSpec.model_validate(agent["model"])
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = spec.model_dump(mode="json")
    intelligence = agent["intelligence"]
    return {
        "engine": "gridpulse-parametric-cad-v0.6.0",
        "interpretation_mode": agent["interpretation_mode"],
        "agent": agent,
        "spec": payload,
        "review": review_spec(spec),
        "engineering_intelligence": intelligence,
        "ai_reasoning": agent["ai_reasoning"],
        "quality_gate": agent["quality_gate"],
        "calculations": agent["calculations"],
        "advanced_calculations": agent["advanced_calculations"],
        "exports": {
            "engineering_spec.json": json.dumps(payload, ensure_ascii=False, indent=2),
            "engineering_intelligence.json": json.dumps(intelligence, ensure_ascii=False, indent=2),
            "ai_reasoning_report.json": json.dumps(agent["ai_reasoning"], ensure_ascii=False, indent=2),
            "quality_gate_report.json": json.dumps(agent["quality_gate"], ensure_ascii=False, indent=2),
            "calculation_report.json": json.dumps(agent["calculations"], ensure_ascii=False, indent=2),
            "advanced_calculation_report.json": json.dumps(agent["advanced_calculations"], ensure_ascii=False, indent=2),
            "design_agent_report.json": json.dumps(agent, ensure_ascii=False, indent=2),
            "plan.svg": to_svg(spec),
            "plan.dxf": to_dxf(spec),
            "model.scad": to_openscad(spec),
            "model.FCMacro": to_freecad_macro(spec),
            **export_multi_application_bundle(spec, agent["calculations"], agent["advanced_calculations"]),
        },
        "notice": "Conceptual engineering assistance only. Numeric calculations are traceable deterministic calculations, but project-specific codes, design basis, manufacturer data and qualified engineering review remain mandatory.",
    }


@router.post("/agent")
def run_agent(request: GenerateCadRequest) -> dict:
    """Run the design agent without packaging the CAD files into the response."""
    try:
        return run_design_agent(request.prompt, request.site_width, request.site_length, request.disciplines, request.template, request.use_llm)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/impact-analysis")
def analyze_change(request: ChangeImpactRequest) -> dict:
    """Compare two model versions and identify changed objects and connected routes for review."""
    return analyze_change_impact(request.before.model_dump(mode="json"), request.after.model_dump(mode="json"))


@router.post("/calculations")
def calculate_engineering(request: CalculationRequest) -> dict:
    """Run base and advanced deterministic calculations on an existing validated model."""
    base = run_engineering_calculations(request.spec, request.parameters)
    advanced = run_advanced_calculations(request.parameters)
    return {
        "engine": "GridPulse Engineering Calculation Engine v0.6.0",
        "parameters": request.parameters,
        "base": base,
        "advanced": advanced,
        "summary": {
            "calculations": base["summary"]["total"] + advanced["summary"]["total"],
            "calculated": base["summary"]["calculated"] + advanced["summary"]["calculated"],
            "insufficient_input": base["summary"]["insufficient_input"] + advanced["summary"]["insufficient_input"],
            "rules": base["summary"]["rules"] + advanced["summary"]["rules"],
        },
    }


@router.post("/analyze")
def analyze_cad(spec: EngineeringSpec) -> dict:
    """Run engineering intelligence and evidence-first reasoning on an existing model."""
    intelligence = analyze_design_intelligence(spec)
    reasoning = run_engineering_reasoning(spec.model_dump(mode="json"), {"required_disciplines": sorted({a.discipline for a in spec.assets}), "explicit_parameters": {}})
    return {"engineering_intelligence": intelligence, "ai_reasoning": reasoning}


@router.post("/export/{format_name}")
def export_cad(format_name: Literal["json", "svg", "dxf", "scad", "FCMacro", "xlsx"], spec: EngineeringSpec) -> Response:
    """Re-export a validated model using the deterministic geometry backend."""
    if format_name == "json":
        content, media, name = json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2), "application/json", "engineering_spec.json"
    elif format_name == "svg":
        content, media, name = to_svg(spec), "image/svg+xml", "plan.svg"
    elif format_name == "dxf":
        content, media, name = to_dxf(spec), "application/dxf", "plan.dxf"
    elif format_name == "scad":
        content, media, name = to_openscad(spec), "text/plain; charset=utf-8", "model.scad"
    elif format_name == "xlsx":
        content = export_engineering_workbook(spec, review_spec(spec))
        return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=gridpulse_engineering_handoff.xlsx"})
    else:
        content, media, name = to_freecad_macro(spec), "text/plain; charset=utf-8", "model.FCMacro"
    return Response(content=content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/export-bundle")
def export_multi_application(spec: EngineeringSpec) -> dict:
    """Export the same validated EngineeringSpec for AutoCAD, 3ds Max and Revit."""
    bundle = export_multi_application_bundle(spec)
    return {
        "engine": "gridpulse-multi-application-export-v1",
        "model_id": spec.project_name,
        "formats": {
            "autocad": {"filename": "autocad_model.dxf", "type": "DXF", "status": "generated"},
            "3ds_max": {"filename": "3dsmax_generator.ms", "type": "MaxScript", "status": "generated_script"},
            "revit": {"filename": "revit_dynamo_generator.py", "type": "Dynamo Python", "status": "generated_script"},
            "source": {"filename": "engineering_spec.json", "type": "GridPulse EngineeringSpec", "status": "generated"},
            "excel": {"filename": "gridpulse_engineering_handoff.xlsx", "type": "XLSX", "status": "base64_encoded_in_exports"},
        },
        "exports": bundle,
        "limitations": ["DXF contains editable conceptual plan geometry.", "The 3ds Max MaxScript must be run inside a compatible 3ds Max installation.", "The Revit Python script must be run in Dynamo inside an open Revit project; it creates approximate DirectShape envelopes, not a native RVT file by itself.", "This shared model does not yet create native Revit MEP systems or manufacturer-level 3D assemblies.", "All outputs are conceptual and require qualified engineering review."],
    }

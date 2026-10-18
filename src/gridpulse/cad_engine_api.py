"""HTTP API for the parametric prompt-to-CAD engine."""
from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field, ValidationError

from gridpulse.cad_engine import (
    Discipline,
    EngineeringSpec,
    build_spec,
    review_spec,
    to_dxf,
    to_freecad_macro,
    to_openscad,
    to_svg,
)
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
    disciplines: list[Discipline] = Field(
        default_factory=lambda: ["Mechanical", "Piping", "Electrical", "Instrumentation", "Architecture"],
        min_length=1, max_length=10,
    )
    use_llm: bool = True


@router.get("/status")
def cad_engine_status() -> dict:
    """Report actual runtime capabilities and whether the optional model is configured."""
    import os
    configured = all(os.environ.get(key, "").strip() for key in (
        "GRIDPULSE_LLM_BASE_URL", "GRIDPULSE_LLM_API_KEY", "GRIDPULSE_LLM_MODEL"
    ))
    return {
        "engine": "GridPulse Parametric CAD Engine",
        "version": "0.2.0",
        "available": True,
        "geometry_backend": "parametric-spec + OpenSCAD + FreeCAD macro source + SVG + DXF R12",
        "llm_configured": configured,
        "llm_mode": "OpenAI-compatible JSON spec" if configured else "deterministic prompt parser",
        "outputs": ["engineering_spec.json", "plan.svg", "plan.dxf", "model.scad", "model.FCMacro", "autocad_model.dxf", "3dsmax_generator.ms", "revit_dynamo_generator.py", "gridpulse_engineering_handoff.xlsx"],
        "limitations": [
            "Conceptual envelopes and schematic routes only",
            "STEP/FCStd files are generated only when the exported macro is run in an installed FreeCAD environment",
            "No engineering code calculations or safety approval",
            "Not connected to plant telemetry or dispatch systems",
        ],
    }


@router.post("/generate")
def generate_cad(request: GenerateCadRequest) -> dict:
    """Generate one bounded, editable geometry model and multiple exports."""
    try:
        spec, interpretation = build_spec(
            request.prompt, request.site_width, request.site_length,
            request.disciplines, request.template, request.use_llm,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload = spec.model_dump(mode="json")
    return {
        "engine": "gridpulse-parametric-cad-v0.2.0",
        "interpretation_mode": interpretation,
        "spec": payload,
        "review": review_spec(spec),
        "exports": {
            "engineering_spec.json": json.dumps(payload, ensure_ascii=False, indent=2),
            "plan.svg": to_svg(spec),
            "plan.dxf": to_dxf(spec),
            "model.scad": to_openscad(spec),
            "model.FCMacro": to_freecad_macro(spec),
            **export_multi_application_bundle(spec),
        },
        "notice": "Conceptual design only. Outputs are editable but are not construction-approved engineering.",
    }


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
        return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": "attachment; filename=gridpulse_engineering_handoff.xlsx"})
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
        "limitations": [
            "DXF contains editable conceptual plan geometry.",
            "The 3ds Max MaxScript must be run inside a compatible 3ds Max installation.",
            "The Revit Python script must be run in Dynamo inside an open Revit project; it creates approximate DirectShape envelopes, not a native RVT file by itself.",
            "This shared model does not yet create native Revit MEP systems or manufacturer-level 3D assemblies.",
            "All outputs are conceptual and require qualified engineering review.",
        ],
    }

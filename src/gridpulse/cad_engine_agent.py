"""Multi-stage engineering design agent with deterministic calculation feedback."""
from __future__ import annotations

from typing import Any

from gridpulse.cad_engine import (
    Discipline,
    EngineeringSpec,
    build_spec,
    review_spec,
)
from gridpulse.cad_engine_advanced_calculations import run_advanced_calculations
from gridpulse.cad_engine_calculations import (
    parse_explicit_parameters,
    run_engineering_calculations,
)
from gridpulse.cad_engine_intelligence import analyze_design_intelligence
from gridpulse.cad_engine_parameter_parser import parse_advanced_parameters


DISCIPLINE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Mechanical": ("pump", "turbine", "generator", "compressor", "vessel", "tank", "mechanical", "پمپ", "توربین", "ژنراتور", "مخزن"),
    "Piping": ("pipe", "piping", "line", "process", "cooling water", "لوله", "پایپینگ", "فرآیند", "آب خنک"),
    "Electrical": ("electrical", "transformer", "switchgear", "mcc", "cable", "power", "برق", "ترانس", "تابلو", "کابل"),
    "Instrumentation": ("instrument", "control", "dcs", "plc", "sensor", "ابزار دقیق", "کنترل", "سنسور"),
    "Fire": ("fire", "آتش", "firefighting", "اطفای"),
    "HVAC": ("hvac", "ventilation", "air conditioning", "تهویه", "هواساز"),
    "Grounding": ("grounding", "earthing", "زمین", "ارت"),
    "Lighting": ("lighting", "روشنایی", "چراغ"),
    "Drainage": ("drainage", "drain", "زهکشی", "فاضلاب"),
    "Architecture": ("building", "room", "control building", "ساختمان", "اتاق"),
}


def extract_requirements(prompt: str, selected: list[Discipline] | None = None) -> dict[str, Any]:
    text = prompt.casefold()
    inferred = [d for d, words in DISCIPLINE_KEYWORDS.items() if any(w.casefold() in text for w in words)]
    disciplines = list(dict.fromkeys((selected or []) + inferred))
    if not disciplines:
        disciplines = ["Mechanical", "Piping", "Electrical", "Instrumentation"]
    plant_types = []
    for label, words in {
        "power": ("power plant", "combined cycle", "نیروگاه", "سیکل ترکیبی"),
        "substation": ("substation", "پست برق", "پست فشار قوی"),
        "water": ("water treatment", "wastewater", "تصفیه خانه", "تصفیه‌خانه"),
        "process": ("process plant", "process", "فرآیندی", "فرآیند"),
    }.items():
        if any(w in text for w in words):
            plant_types.append(label)
    explicit_parameters = parse_explicit_parameters(prompt)
    explicit_parameters.update(parse_advanced_parameters(prompt))
    return {
        "objective": prompt.strip(),
        "inferred_plant_types": plant_types or ["process"],
        "required_disciplines": disciplines,
        "explicit_parameters": explicit_parameters,
        "deliverables": ["validated EngineeringSpec", "editable CAD exports", "engineering intelligence report", "deterministic calculation report", "advanced sizing and network checks", "assumption and risk register"],
        "unknowns": ["approved design basis and applicable codes", "vendor/manufacturer dimensions and connection points", "survey/geotechnical information and authoritative plant interfaces", "process, electrical and instrumentation design calculations not represented by explicit inputs"],
    }


def plan_design(requirements: dict[str, Any], template: str) -> dict[str, Any]:
    disciplines = requirements["required_disciplines"]
    phases = [
        {"stage": 1, "name": "requirements", "status": "complete"},
        {"stage": 2, "name": "discipline coordination", "status": "planned", "inputs": disciplines},
        {"stage": 3, "name": "parametric geometry", "status": "planned", "template": template},
        {"stage": 4, "name": "topology and clash heuristics", "status": "planned"},
        {"stage": 5, "name": "deterministic engineering calculations and rules", "status": "planned"},
        {"stage": 6, "name": "advanced sizing and network calculations", "status": "planned"},
        {"stage": 7, "name": "design critique", "status": "planned"},
        {"stage": 8, "name": "multi-application handoff", "status": "planned"},
    ]
    return {"strategy": "single-source-of-truth EngineeringSpec + traceable calculation layers", "phases": phases}


def _critique(spec: EngineeringSpec, intelligence: dict[str, Any], calculations: dict[str, Any], advanced: dict[str, Any]) -> dict[str, Any]:
    findings = []
    if len(spec.assets) < 2:
        findings.append({"severity": "high", "code": "LOW_MODEL_COVERAGE", "message": "Model contains too few assets for meaningful system coordination."})
    if not spec.routes:
        findings.append({"severity": "medium", "code": "NO_ROUTES", "message": "No schematic routes were generated; connectivity remains incomplete."})
    if calculations["summary"]["insufficient_input"]:
        findings.append({"severity": "medium", "code": "CALC_INPUT_GAPS", "message": f"{calculations['summary']['insufficient_input']} base calculation(s) require explicit engineering inputs before numeric evaluation."})
    if advanced["summary"]["insufficient_input"]:
        findings.append({"severity": "medium", "code": "ADVANCED_CALC_INPUT_GAPS", "message": f"{advanced['summary']['insufficient_input']} advanced calculation(s) require explicit engineering inputs."})
    for rule in advanced["rule_checks"]:
        if rule["status"] == "fail":
            findings.append({"severity": "high", "code": rule["id"], "message": rule["message"]})
    for action in intelligence["recommended_actions"]:
        findings.append({"severity": action.get("priority", "medium"), "code": action.get("code", "REVIEW"), "message": action.get("action", "Review required")})
    return {"finding_count": len(findings), "findings": findings, "gate": "review_required" if any(x["severity"] == "high" for x in findings) else "coordination_review"}


def run_design_agent(prompt: str, site_width: float = 80, site_length: float = 55,
                     disciplines: list[Discipline] | None = None, template: str = "process",
                     use_llm: bool = True) -> dict[str, Any]:
    requirements = extract_requirements(prompt, disciplines)
    plan = plan_design(requirements, template)
    effective_disciplines = requirements["required_disciplines"]
    spec, interpretation = build_spec(prompt, site_width, site_length, effective_disciplines, template, use_llm)
    review = review_spec(spec)
    calculations = run_engineering_calculations(spec, requirements["explicit_parameters"])
    advanced = run_advanced_calculations(requirements["explicit_parameters"])
    intelligence = analyze_design_intelligence(spec, calculations)
    critique = _critique(spec, intelligence, calculations, advanced)
    return {
        "agent": "GridPulse Engineering Design Agent v0.3",
        "interpretation_mode": interpretation,
        "requirements": requirements,
        "plan": plan,
        "model": spec.model_dump(mode="json"),
        "review": review,
        "calculations": calculations,
        "advanced_calculations": advanced,
        "intelligence": intelligence,
        "critique": critique,
        "metrics": {"assets": len(spec.assets), "routes": len(spec.routes), "disciplines": sorted({a.discipline for a in spec.assets} | {r.discipline for r in spec.routes}), "readiness_score": intelligence["readiness_score"], "risk_count": critique["finding_count"], "calculations_total": calculations["summary"]["total"] + advanced["summary"]["total"], "calculations_complete": calculations["summary"]["calculated"] + advanced["summary"]["calculated"]},
        "next_actions": ["Resolve high-priority findings.", "Provide approved design-basis/code/vendor inputs for calculations marked insufficient_input.", "Run project-specific discipline calculations and code checks before construction use."],
    }

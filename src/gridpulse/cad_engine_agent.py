"""Multi-stage engineering design agent built around the bounded CAD spec.

The agent is intentionally deterministic after prompt interpretation. It decomposes a
request into requirements, derives a design plan, generates a validated candidate,
and performs a critique pass before returning the final handoff. It is an engineering
coordination assistant, not an authority for construction or safety approval.
"""
from __future__ import annotations

from typing import Any

from gridpulse.cad_engine import Discipline, EngineeringSpec, build_spec, review_spec
from gridpulse.cad_engine_intelligence import analyze_design_intelligence


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
    return {
        "objective": prompt.strip(),
        "inferred_plant_types": plant_types or ["process"],
        "required_disciplines": disciplines,
        "deliverables": ["validated EngineeringSpec", "editable CAD exports", "engineering intelligence report", "assumption and risk register"],
        "unknowns": ["approved design basis and applicable codes", "vendor/manufacturer dimensions and connection points", "survey/geotechnical information and authoritative plant interfaces", "process, electrical and instrumentation design calculations"],
    }


def plan_design(requirements: dict[str, Any], template: str) -> dict[str, Any]:
    disciplines = requirements["required_disciplines"]
    phases = [
        {"stage": 1, "name": "requirements", "status": "complete"},
        {"stage": 2, "name": "discipline coordination", "status": "planned", "inputs": disciplines},
        {"stage": 3, "name": "parametric geometry", "status": "planned", "template": template},
        {"stage": 4, "name": "topology and clash heuristics", "status": "planned"},
        {"stage": 5, "name": "design critique", "status": "planned"},
        {"stage": 6, "name": "multi-application handoff", "status": "planned"},
    ]
    return {"strategy": "single-source-of-truth EngineeringSpec", "phases": phases}


def _critique(spec: EngineeringSpec, intelligence: dict[str, Any]) -> dict[str, Any]:
    findings = []
    if len(spec.assets) < 2:
        findings.append({"severity": "high", "code": "LOW_MODEL_COVERAGE", "message": "Model contains too few assets for meaningful system coordination."})
    if not spec.routes:
        findings.append({"severity": "medium", "code": "NO_ROUTES", "message": "No schematic routes were generated; connectivity remains incomplete."})
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
    intelligence = analyze_design_intelligence(spec)
    critique = _critique(spec, intelligence)
    return {
        "agent": "GridPulse Engineering Design Agent v0.1",
        "interpretation_mode": interpretation,
        "requirements": requirements,
        "plan": plan,
        "model": spec.model_dump(mode="json"),
        "review": review,
        "intelligence": intelligence,
        "critique": critique,
        "metrics": {"assets": len(spec.assets), "routes": len(spec.routes), "disciplines": sorted(set(a.discipline for a in spec.assets) | set(r.discipline for r in spec.routes)), "readiness_score": intelligence["readiness_score"], "risk_count": critique["finding_count"]},
        "next_actions": ["Resolve high-priority findings.", "Replace conceptual assumptions with approved design-basis data.", "Run discipline-specific engineering calculations and code checks before construction use."],
    }

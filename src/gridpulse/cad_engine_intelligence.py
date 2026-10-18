"""Engineering reasoning layer for GridPulse conceptual CAD models."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any

from gridpulse.cad_engine import EngineeringSpec, review_spec


def _center(asset: Any) -> tuple[float, float, float]:
    return (asset.x + asset.length / 2, asset.y + asset.width / 2, asset.z + asset.height / 2)


def _distance(a: Any, b: Any) -> float:
    return math.dist(_center(a), _center(b))


def _kind_for_asset(asset: Any) -> str:
    text = f"{asset.tag} {asset.name}".casefold()
    if any(k in text for k in ("pump", "پمپ")):
        return "pump"
    if any(k in text for k in ("tank", "vessel", "مخزن", "ظرف")):
        return "vessel"
    if any(k in text for k in ("turbine", "توربین")):
        return "turbine"
    if any(k in text for k in ("generator", "ژنراتور")):
        return "generator"
    if any(k in text for k in ("transformer", "ترانس")):
        return "transformer"
    if any(k in text for k in ("mcc", "switchgear", "panel", "تابلو")):
        return "electrical_panel"
    if any(k in text for k in ("control", "کنترل")):
        return "control"
    return asset.shape


def infer_system_topology(spec: EngineeringSpec) -> dict[str, Any]:
    """Infer reviewable connectivity candidates from roles and spatial proximity."""
    nodes = [{"id": a.tag, "name": a.name, "discipline": a.discipline, "type": _kind_for_asset(a)} for a in spec.assets]
    edges: list[dict[str, Any]] = []
    routes_by_discipline = defaultdict(list)
    for r in spec.routes:
        routes_by_discipline[r.discipline].append(r.tag)

    roles = {a.tag: _kind_for_asset(a) for a in spec.assets}
    for a, b in combinations(spec.assets, 2):
        ka, kb = roles[a.tag], roles[b.tag]
        pair = {ka, kb}
        distance = _distance(a, b)
        proposed = None
        if pair == {"pump", "vessel"}:
            proposed = "process_or_utility_connection"
        elif pair == {"pump", "turbine"}:
            proposed = "utility_or_auxiliary_connection"
        elif pair == {"generator", "transformer"}:
            proposed = "electrical_power_connection_candidate"
        elif "electrical_panel" in pair and any(x in pair for x in ("pump", "turbine", "generator")):
            proposed = "power_or_control_connection_candidate"
        elif "control" in pair and any(x in pair for x in ("electrical_panel", "pump", "turbine", "generator")):
            proposed = "instrumentation_or_control_connection_candidate"
        if proposed and distance <= max(spec.site_width, spec.site_length) * 0.55:
            edges.append({"from": a.tag, "to": b.tag, "relation": proposed,
                          "distance_model_units": round(distance, 3), "confidence": "heuristic"})

    return {
        "nodes": nodes,
        "candidate_connections": edges,
        "route_inventory": {k: sorted(v) for k, v in routes_by_discipline.items()},
        "note": "Connections are coordination candidates, not approved P&ID, SLD or control logic connections.",
    }


def analyze_design_intelligence(spec: EngineeringSpec) -> dict[str, Any]:
    """Produce a deterministic engineering-assistant report from one validated spec."""
    base = review_spec(spec)
    topology = infer_system_topology(spec)
    disciplines = Counter(a.discipline for a in spec.assets)
    route_disciplines = Counter(r.discipline for r in spec.routes)
    actions: list[dict[str, Any]] = []
    selected = set(disciplines) | set(route_disciplines)
    expected = {"Mechanical", "Piping", "Electrical", "Instrumentation"}
    missing = sorted(expected - selected)
    for discipline in missing:
        actions.append({"priority": "high", "code": "DISCIPLINE_MISSING", "discipline": discipline,
                        "action": f"Review whether {discipline} scope is required before design freeze."})
    if "Piping" in selected and not any(r.kind == "pipe" for r in spec.routes):
        actions.append({"priority": "high", "code": "PIPING_NO_ROUTES",
                        "action": "Add process/utility piping routes or explicitly mark piping out of scope."})
    if "Electrical" in selected and not any(r.kind == "cable_tray" for r in spec.routes):
        actions.append({"priority": "medium", "code": "ELECTRICAL_NO_TRAY",
                        "action": "Review cable-tray/power distribution routing."})
    if "Instrumentation" in selected and not any("control" in _kind_for_asset(a) for a in spec.assets):
        actions.append({"priority": "medium", "code": "CONTROL_NODE_MISSING",
                        "action": "Review DCS/PLC/control-panel location and instrumentation interfaces."})

    maintenance_risks = []
    for a in spec.assets:
        nearby = [b.tag for b in spec.assets if b.tag != a.tag and
                  _distance(a, b) < 1.25 * max(a.length, a.width, b.length, b.width)]
        if nearby:
            maintenance_risks.append({"asset": a.tag, "nearby_assets": nearby[:12], "risk": "review_access_clearance"})
    if maintenance_risks:
        actions.append({"priority": "medium", "code": "MAINTENANCE_CLEARANCE_REVIEW",
                        "action": "Verify equipment removal paths, operating envelopes and maintenance clearances."})

    penalty = min(60, len(base["geometric_findings"]) * 3) + min(20, len(missing) * 5)
    if not topology["candidate_connections"]:
        penalty += 10
    readiness = max(0, 100 - penalty)
    return {
        "engine": "GridPulse Engineering Intelligence v0.3",
        "mode": "deterministic_reasoning_over_validated_spec",
        "readiness_score": readiness,
        "readiness_label": "coordination prototype" if readiness >= 70 else "coordination review required",
        "scope": {"assets": len(spec.assets), "routes": len(spec.routes),
                  "asset_disciplines": dict(disciplines), "route_disciplines": dict(route_disciplines)},
        "topology": topology,
        "coordination_findings": base["geometric_findings"],
        "recommended_actions": actions,
        "assumption_register": list(spec.design_basis),
        "limitations": [
            "No hydraulic sizing, pipe stress, electrical load-flow/short-circuit/protection, structural analysis, fire engineering, HVAC load calculation or code compliance calculation is performed.",
            "Semantic connections are candidate relationships inferred from names, disciplines and spatial proximity.",
            "The result must not be used as construction, procurement or operational approval.",
        ],
    }

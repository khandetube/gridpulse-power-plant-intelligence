"""Deterministic, traceable engineering calculations for GridPulse CAD.

Only explicit inputs are used. Missing data produces ``insufficient_input`` rather
than an invented engineering value. Calculations are preliminary engineering aids;
project codes, vendor data, material properties and qualified review remain required.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from gridpulse.cad_engine import EngineeringSpec

G = 9.80665
RHO_WATER = 998.2
MU_WATER = 1.002e-3
COPPER_RESISTIVITY_20C = 1.724e-8
SQRT3 = math.sqrt(3.0)


@dataclass(frozen=True)
class Calculation:
    id: str
    discipline: str
    name: str
    status: str
    value: float | None
    unit: str
    formula: str
    inputs: dict[str, Any]
    assumptions: list[str] = field(default_factory=list)
    provenance: str = "explicit_user_input"
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "discipline": self.discipline, "name": self.name,
                "status": self.status, "value": self.value, "unit": self.unit,
                "formula": self.formula, "inputs": self.inputs,
                "assumptions": self.assumptions, "provenance": self.provenance,
                "warnings": self.warnings}


@dataclass(frozen=True)
class RuleCheck:
    id: str
    discipline: str
    severity: str
    status: str
    message: str
    basis: str
    inputs: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "discipline": self.discipline, "severity": self.severity,
                "status": self.status, "message": self.message, "basis": self.basis,
                "inputs": self.inputs}


def _num(params: dict[str, Any], key: str) -> float | None:
    value = params.get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _positive(params: dict[str, Any], key: str) -> float | None:
    value = _num(params, key)
    return value if value is not None and value > 0 else None


def _calc_missing(calc_id: str, discipline: str, name: str, formula: str,
                  required: Iterable[str], params: dict[str, Any]) -> Calculation:
    missing = [k for k in required if _positive(params, k) is None]
    return Calculation(calc_id, discipline, name, "insufficient_input", None, "", formula,
                       {k: params.get(k) for k in required},
                       [f"Missing or non-positive required input: {k}" for k in missing],
                       "explicit_user_input", ["No value was assumed for missing inputs."])


def parse_explicit_parameters(prompt: str) -> dict[str, Any]:
    """Extract unambiguous engineering values from natural language without guessing."""
    text = prompt.replace(",", "")
    p: dict[str, Any] = {}

    def first(patterns: list[str]):
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
        return None

    patterns = {
        "power_mw": [r"([0-9]+(?:\.[0-9]+)?)\s*(?:MW|megawatt)s?\b"],
        "voltage_kv": [r"([0-9]+(?:\.[0-9]+)?)\s*(?:kV|kilovolt)s?\b"],
        "voltage_v": [r"([0-9]+(?:\.[0-9]+)?)\s*(?:V|volt)s?\b"],
        "frequency_hz": [r"([0-9]+(?:\.[0-9]+)?)\s*Hz\b"],
        "power_factor": [r"(?:pf|power factor)\s*(?:=|:)?\s*(0?\.\d+|1(?:\.0)?)"],
        "flow_m3_h": [r"([0-9]+(?:\.[0-9]+)?)\s*(?:m3/h|m³/h|m3/hr|m³/hr)\b"],
        "head_m": [r"([0-9]+(?:\.[0-9]+)?)\s*(?:m\s*(?:head|هد)|meter[s]?\s*(?:head))\b"],
        "pressure_bar": [r"([0-9]+(?:\.[0-9]+)?)\s*bar\b"],
        "diameter_mm": [r"(?:DN|dn)\s*([0-9]+(?:\.[0-9]+)?)"],
        "ach": [r"([0-9]+(?:\.[0-9]+)?)\s*ACH\b"],
        "lux": [r"([0-9]+(?:\.[0-9]+)?)\s*lux\b"],
        "area_m2": [r"([0-9]+(?:\.[0-9]+)?)\s*m2\b", r"([0-9]+(?:\.[0-9]+)?)\s*m²\b"],
        "volume_m3": [r"([0-9]+(?:\.[0-9]+)?)\s*m3\b", r"([0-9]+(?:\.[0-9]+)?)\s*m³\b"],
        "current_a": [r"([0-9]+(?:\.[0-9]+)?)\s*A\b"],
        "cable_length_m": [r"([0-9]+(?:\.[0-9]+)?)\s*(?:m|meter[s]?)\s*(?:cable|کابل)\b"],
        "cable_area_mm2": [r"(?:cable|conductor|کابل)\s*(?:area|سطح مقطع)?\s*([0-9]+(?:\.[0-9]+)?)\s*mm2\b", r"([0-9]+(?:\.[0-9]+)?)\s*mm²\s*(?:cable|conductor|کابل)"],
        "tray_width_mm": [r"(?:tray|سینی)\s*(?:width|عرض)?\s*([0-9]+(?:\.[0-9]+)?)\s*mm"],
        "pipe_roughness_mm": [r"(?:roughness|زبری)\s*([0-9]+(?:\.[0-9]+)?)\s*mm"],
        "fluid_density_kg_m3": [r"(?:density|چگالی)\s*([0-9]+(?:\.[0-9]+)?)\s*kg/m3\b"],
        "fluid_viscosity_pa_s": [r"(?:viscosity|ویسکوزیته)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:Pa\.s|Pa s)\b"],
        "efficiency": [r"(?:efficiency|راندمان)\s*(?:=|:)?\s*(0?\.[0-9]+|1(?:\.0)?)"],
    }
    for key, pats in patterns.items():
        value = first(pats)
        if value is not None:
            p[key] = value
    return p


def _piping(spec: EngineeringSpec, p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    q, d = _positive(p, "flow_m3_h"), _positive(p, "diameter_mm")
    if q is not None and d is not None:
        q_s, d_m = q / 3600.0, d / 1000.0
        area = math.pi * d_m**2 / 4
        velocity = q_s / area
        out.append(Calculation("PIP-VEL-001", "Piping", "Pipe internal velocity", "calculated", velocity, "m/s",
            "v = Q / (pi D^2 / 4)", {"flow_m3_h": q, "diameter_mm": d},
            ["DN is treated as the hydraulic internal diameter for this preliminary calculation; use actual ID for final design."], "explicit_user_input"))

        rho = _positive(p, "fluid_density_kg_m3") or RHO_WATER
        mu = _positive(p, "fluid_viscosity_pa_s") or MU_WATER
        re = rho * velocity * d_m / mu
        out.append(Calculation("PIP-RE-001", "Piping", "Reynolds number", "calculated", re, "dimensionless",
            "Re = rho*v*D/mu", {"density_kg_m3": rho, "velocity_m_s": velocity, "diameter_m": d_m, "viscosity_pa_s": mu},
            ["Water properties are used only when density/viscosity are not explicitly supplied."], "explicit_user_input" if "fluid_density_kg_m3" in p or "fluid_viscosity_pa_s" in p else "standard_physical_property"))

        rough = (_positive(p, "pipe_roughness_mm") or 0.045) / 1000.0
        if re > 0:
            f = 0.25 / (math.log10(rough / (3.7*d_m) + 5.74/(re**0.9)))**2
            out.append(Calculation("PIP-F-001", "Piping", "Darcy friction factor", "calculated", f, "dimensionless",
                "f = 0.25/[log10(e/(3.7D)+5.74/Re^0.9)]^2 (Swamee-Jain)",
                {"roughness_m": rough, "diameter_m": d_m, "reynolds": re},
                ["Swamee-Jain explicit approximation for turbulent flow."], "explicit_user_input" if "pipe_roughness_mm" in p else "standard_physical_property"))
            length = _positive(p, "pipe_length_m")
            if length is not None:
                dp = f * (length/d_m) * (rho*velocity**2/2)
                out.append(Calculation("PIP-DP-001", "Piping", "Darcy-Weisbach straight-pipe pressure loss", "calculated", dp/1e5, "bar",
                    "DeltaP = f*(L/D)*(rho*v^2/2)", {"friction_factor": f, "length_m": length, "diameter_m": d_m, "density_kg_m3": rho, "velocity_m_s": velocity},
                    ["Straight pipe only; fittings, valves, elevation and equipment losses are excluded."], "explicit_user_input"))
    else:
        out.append(_calc_missing("PIP-VEL-001", "Piping", "Pipe internal velocity", "v = Q / (pi D^2 / 4)", ("flow_m3_h", "diameter_mm"), p))
    length = 0.0
    for r in spec.routes:
        if r.kind == "pipe":
            length += sum(math.dist(a, b) for a, b in zip(r.points, r.points[1:]))
    out.append(Calculation("PIP-LEN-001", "Piping", "Total modeled pipe route length", "calculated", length, spec.units,
        "sum(sqrt(dx^2+dy^2+dz^2)) for all pipe segments", {"pipe_route_count": sum(r.kind == "pipe" for r in spec.routes)},
        ["Geometric centerline length only; fittings, allowances and stress flexibility are excluded."], "validated_engineering_spec"))
    return out


def _electrical(spec: EngineeringSpec, p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    mw, kv, pf = _positive(p, "power_mw"), _positive(p, "voltage_kv"), _positive(p, "power_factor")
    if mw is not None and kv is not None and pf is not None and pf <= 1:
        kva = mw * 1000 / pf
        current = kva / (SQRT3 * kv)
        out.extend([
            Calculation("ELEC-S-001", "Electrical", "Apparent power", "calculated", kva, "kVA", "S(kVA)=P(MW)*1000/pf", {"power_mw": mw, "power_factor": pf}),
            Calculation("ELEC-I-001", "Electrical", "Three-phase line current", "calculated", current, "A", "I=S(kVA)/(sqrt(3)*V(kV))", {"power_mw": mw, "voltage_kv": kv, "power_factor": pf}, ["Balanced three-phase RMS system; voltage is line-to-line."], "explicit_user_input")
        ])
    else:
        out.append(_calc_missing("ELEC-I-001", "Electrical", "Three-phase line current", "I=P/(sqrt(3)*V*pf)", ("power_mw", "voltage_kv", "power_factor"), p))

    i, l, a = _positive(p, "current_a"), _positive(p, "cable_length_m"), _positive(p, "cable_area_mm2")
    if i is not None and l is not None and a is not None:
        area_m2 = a * 1e-6
        r = COPPER_RESISTIVITY_20C * l / area_m2
        loss = i*i*r
        vd = i*r
        out.extend([
            Calculation("ELEC-R-001", "Electrical", "Copper conductor resistance", "calculated", r, "ohm", "R=rho*L/A", {"current_a": i, "length_m": l, "area_mm2": a, "resistivity_ohm_m": COPPER_RESISTIVITY_20C}, ["Copper at approximately 20 C; actual operating temperature changes resistance."], "explicit_user_input"),
            Calculation("ELEC-L-001", "Electrical", "Cable I²R loss per conductor", "calculated", loss, "W", "P_loss=I²R", {"current_a": i, "resistance_ohm": r}, ["One conductor; multiply according to actual circuit topology."], "explicit_user_input"),
            Calculation("ELEC-V-001", "Electrical", "Cable voltage drop per conductor", "calculated", vd, "V", "DeltaV=I*R", {"current_a": i, "resistance_ohm": r}, ["Resistance-only preliminary result; reactance, power factor and installation temperature are excluded."], "explicit_user_input")
        ])
    else:
        out.append(_calc_missing("ELEC-R-001", "Electrical", "Copper conductor resistance", "R=rho*L/A", ("cable_length_m", "cable_area_mm2"), p))
    return out


def _hvac(p: dict[str, Any]) -> list[Calculation]:
    v, ach = _positive(p, "volume_m3"), _positive(p, "ach")
    if v is None or ach is None:
        return [_calc_missing("HVAC-AIR-001", "HVAC", "Ventilation airflow", "Q(m3/h)=room_volume*ACH", ("volume_m3", "ach"), p)]
    return [Calculation("HVAC-AIR-001", "HVAC", "Ventilation airflow", "calculated", v*ach, "m3/h", "Q=V*ACH", {"volume_m3": v, "ach": ach}, ["ACH is an explicit design input; no code minimum is inferred."], "explicit_user_input")]


def _lighting(p: dict[str, Any]) -> list[Calculation]:
    area, lux = _positive(p, "area_m2"), _positive(p, "lux")
    if area is None or lux is None:
        return [_calc_missing("LGT-FLUX-001", "Lighting", "Required illuminance flux", "Phi=E*A", ("area_m2", "lux"), p)]
    return [Calculation("LGT-FLUX-001", "Lighting", "Required ideal illuminance flux", "calculated", area*lux, "lm", "Phi=E(lux)*A(m2)", {"area_m2": area, "lux": lux}, ["Ideal maintained flux before utilization, maintenance, optical and fixture factors."], "explicit_user_input")]


def _mechanical(spec: EngineeringSpec, p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    for a in spec.assets:
        volume = a.length*a.width*a.height
        if a.shape in {"tank", "vessel", "cylinder"} and a.diameter:
            volume = math.pi*(a.diameter**2)/4*a.height
        out.append(Calculation(f"MECH-VOL-{a.tag}", "Mechanical", f"Envelope volume {a.tag}", "calculated", volume, f"{spec.units}^3",
            "L*W*H or pi*D^2/4*H", {"tag": a.tag, "length": a.length, "width": a.width, "height": a.height, "diameter": a.diameter}, ["Geometric envelope, not process working volume."], "validated_engineering_spec"))
    return out


def _rules(calcs: list[Calculation]) -> list[RuleCheck]:
    rules: list[RuleCheck] = []
    velocity = next((c for c in calcs if c.id == "PIP-VEL-001" and c.status == "calculated"), None)
    if velocity:
        rules.append(RuleCheck("PIP-SCREEN-001", "Piping", "info", "review", f"Velocity={velocity.value:.3f} m/s. Compare with service/project-specific allowable velocity.", "No universal velocity limit assumed", velocity.inputs))
    current = next((c for c in calcs if c.id == "ELEC-I-001" and c.status == "calculated"), None)
    if current:
        rules.append(RuleCheck("ELEC-SCREEN-001", "Electrical", "high", "review", f"Current={current.value:.1f} A. Cable ampacity, breaker, voltage-drop, thermal and short-circuit checks remain required.", "Project-specific electrical design basis required", current.inputs))
    for c in calcs:
        if c.status == "insufficient_input":
            rules.append(RuleCheck(f"INPUT-{c.id}", c.discipline, "medium", "unknown", f"{c.name} cannot be calculated because required inputs are missing.", c.formula, c.inputs))
    return rules


def run_engineering_calculations(spec: EngineeringSpec, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    p = dict(parameters or {})
    calcs: list[Calculation] = []
    calcs.extend(_piping(spec, p)); calcs.extend(_electrical(spec, p)); calcs.extend(_hvac(p)); calcs.extend(_lighting(p)); calcs.extend(_mechanical(spec, p))
    rules = _rules(calcs)
    calculated = sum(c.status == "calculated" for c in calcs)
    unknown = sum(c.status == "insufficient_input" for c in calcs)
    return {
        "engine": "GridPulse Deterministic Engineering Calculation Engine v0.2",
        "mode": "real_equations_no_silent_assumptions",
        "parameters": p,
        "calculations": [c.as_dict() for c in calcs],
        "rule_checks": [r.as_dict() for r in rules],
        "summary": {"total": len(calcs), "calculated": calculated, "insufficient_input": unknown, "rules": len(rules)},
        "gate": "calculation_review_required" if unknown else "calculation_complete_subject_to_code_and_design_basis_review",
        "limitations": ["Only implemented equations are executed.", "No code limits, equipment ratings, material properties or protection settings are invented.", "Results require project-specific design basis and qualified review before construction or operation."],
    }

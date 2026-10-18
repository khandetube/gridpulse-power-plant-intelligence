"""Deterministic engineering calculations and rule checks for GridPulse CAD.

This module performs real mathematical calculations only when the required inputs are
explicitly available. It never invents engineering design values. Every result carries
units, formula, inputs, assumptions and provenance so downstream CAD/export layers can
trace how a number was produced.

These calculations are engineering-assistance calculations, not a substitute for
licensed design, project specifications, applicable codes, manufacturer data, or
validated specialist software.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from gridpulse.cad_engine import EngineeringSpec

G = 9.80665
RHO_WATER = 998.2
COPPER_RESISTIVITY = 1.724e-8
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
        return {
            "id": self.id, "discipline": self.discipline, "name": self.name,
            "status": self.status, "value": self.value, "unit": self.unit,
            "formula": self.formula, "inputs": self.inputs,
            "assumptions": self.assumptions, "provenance": self.provenance,
            "warnings": self.warnings,
        }


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
        return {
            "id": self.id, "discipline": self.discipline, "severity": self.severity,
            "status": self.status, "message": self.message, "basis": self.basis,
            "inputs": self.inputs,
        }


def _num(params: dict[str, Any], key: str) -> float | None:
    value = params.get(key)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _calc_missing(calc_id: str, discipline: str, name: str, formula: str,
                  required: Iterable[str], params: dict[str, Any]) -> Calculation:
    missing = [k for k in required if _num(params, k) is None]
    return Calculation(calc_id, discipline, name, "insufficient_input", None, "",
                       formula, {k: params.get(k) for k in required},
                       [f"Missing required input: {k}" for k in missing],
                       "explicit_user_input", ["No value was assumed for missing inputs."])


def parse_explicit_parameters(prompt: str) -> dict[str, Any]:
    """Extract explicit numeric engineering inputs; no values are inferred.

    The parser intentionally captures only unambiguous patterns. Ambiguous phrases are
    left for a human/design-basis input form rather than guessed.
    """
    text = prompt.replace(",", "")
    p: dict[str, Any] = {}

    def first(patterns: list[str], cast=float):
        for pattern in patterns:
            m = re.search(pattern, text, re.I)
            if m:
                try:
                    return cast(m.group(1))
                except ValueError:
                    pass
        return None

    power = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:MW|megawatt)s?\b"])
    if power is not None: p["power_mw"] = power
    voltage = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:kV|kilovolt)s?\b"])
    if voltage is not None: p["voltage_kv"] = voltage
    voltage_v = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:V|volt)s?\b"])
    if voltage_v is not None: p["voltage_v"] = voltage_v
    freq = first([r"([0-9]+(?:\.[0-9]+)?)\s*Hz\b"])
    if freq is not None: p["frequency_hz"] = freq
    pf = first([r"(?:pf|power factor)\s*(?:=|:)?\s*(0?\.\d+|1(?:\.0)?)"])
    if pf is not None: p["power_factor"] = pf
    flow = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:m3/h|m³/h|m3/hr|m³/hr)\b"])
    if flow is not None: p["flow_m3_h"] = flow
    head = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:m\s*(?:head|هد)|meter[s]?\s*(?:head))\b"])
    if head is not None: p["head_m"] = head
    pressure = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:bar)\b"])
    if pressure is not None: p["pressure_bar"] = pressure
    diameter = first([r"(?:DN|dn)\s*([0-9]+(?:\.[0-9]+)?)"])
    if diameter is not None: p["diameter_mm"] = diameter
    ach = first([r"([0-9]+(?:\.[0-9]+)?)\s*ACH\b"])
    if ach is not None: p["ach"] = ach
    lux = first([r"([0-9]+(?:\.[0-9]+)?)\s*lux\b"])
    if lux is not None: p["lux"] = lux
    area = first([r"([0-9]+(?:\.[0-9]+)?)\s*m2\b", r"([0-9]+(?:\.[0-9]+)?)\s*m²\b"])
    if area is not None: p["area_m2"] = area
    room_volume = first([r"([0-9]+(?:\.[0-9]+)?)\s*m3\b", r"([0-9]+(?:\.[0-9]+)?)\s*m³\b"])
    if room_volume is not None: p["volume_m3"] = room_volume
    current = first([r"([0-9]+(?:\.[0-9]+)?)\s*A\b"])
    if current is not None: p["current_a"] = current
    cable_length = first([r"([0-9]+(?:\.[0-9]+)?)\s*(?:m|meter[s]?)\s*(?:cable|کابل)\b"])
    if cable_length is not None: p["cable_length_m"] = cable_length
    tray_width = first([r"(?:tray|سینی)\s*(?:width|عرض)?\s*([0-9]+(?:\.[0-9]+)?)\s*mm"])
    if tray_width is not None: p["tray_width_mm"] = tray_width
    return p


def _piping(spec: EngineeringSpec, p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    q = _num(p, "flow_m3_h")
    d = _num(p, "diameter_mm")
    if q is not None and d is not None:
        q_s = q / 3600.0
        area = math.pi * (d / 1000.0) ** 2 / 4.0
        velocity = q_s / area
        out.append(Calculation("PIP-VEL-001", "Piping", "Pipe internal velocity", "calculated",
            velocity, "m/s", "v = Q / (pi D^2 / 4)", {"flow_m3_h": q, "diameter_mm": d},
            ["Circular internal diameter is represented by DN for this preliminary calculation."],
            "explicit_user_input"))
    else:
        out.append(_calc_missing("PIP-VEL-001", "Piping", "Pipe internal velocity",
            "v = Q / (pi D^2 / 4)", ("flow_m3_h", "diameter_mm"), p))
    length = 0.0
    for r in spec.routes:
        if r.kind == "pipe":
            length += sum(math.dist(a, b) for a, b in zip(r.points, r.points[1:]))
    out.append(Calculation("PIP-LEN-001", "Piping", "Total modeled pipe route length", "calculated",
        length, spec.units, "sum(sqrt(dx^2+dy^2+dz^2)) for all pipe segments",
        {"pipe_route_count": sum(r.kind == "pipe" for r in spec.routes)},
        ["This is geometric route length only; fittings, allowances and stress flexibility are excluded."],
        "validated_engineering_spec"))
    return out


def _electrical(spec: EngineeringSpec, p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    mw, kv, pf = _num(p, "power_mw"), _num(p, "voltage_kv"), _num(p, "power_factor")
    if mw is not None and kv is not None and pf is not None and 0 < pf <= 1 and kv > 0:
        kva = mw * 1000 / pf
        current = kva / (SQRT3 * kv)
        out += [Calculation("ELEC-S-001", "Electrical", "Apparent power", "calculated", kva, "kVA",
            "S(kVA) = P(MW)*1000/pf", {"power_mw": mw, "power_factor": pf}),
            Calculation("ELEC-I-001", "Electrical", "Three-phase line current", "calculated", current, "A",
            "I = S(kVA)/(sqrt(3)*V(kV))", {"power_mw": mw, "voltage_kv": kv, "power_factor": pf},
            ["Balanced three-phase system; voltage is line-to-line RMS."], "explicit_user_input")]
    else:
        out.append(_calc_missing("ELEC-I-001", "Electrical", "Three-phase line current",
            "I = P/(sqrt(3)*V*pf)", ("power_mw", "voltage_kv", "power_factor"), p))
    if _num(p, "current_a") is not None and _num(p, "cable_length_m") is not None:
        i = _num(p, "current_a"); l = _num(p, "cable_length_m")
        out.append(Calculation("ELEC-L-001", "Electrical", "Cable I²R loss per conductor",
            "calculated", i*i*COPPER_RESISTIVITY*l, "W", "P_loss = I²*rho*L/A",
            {"current_a": i, "cable_length_m": l, "copper_resistivity_ohm_m": COPPER_RESISTIVITY,
             "conductor_area_m2": None},
            ["Conductor cross-sectional area is required for a numeric loss; this result is not reported as valid without it."],
            "explicit_user_input", ["Missing conductor area: formula contains A and cannot be evaluated."]))
    return out


def _hvac(p: dict[str, Any]) -> list[Calculation]:
    v, ach = _num(p, "volume_m3"), _num(p, "ach")
    if v is None or ach is None:
        return [_calc_missing("HVAC-AIR-001", "HVAC", "Ventilation airflow",
            "Q(m3/h) = room_volume(m3) * ACH", ("volume_m3", "ach"), p)]
    return [Calculation("HVAC-AIR-001", "HVAC", "Ventilation airflow", "calculated", v*ach, "m3/h",
        "Q = V * ACH", {"volume_m3": v, "ach": ach},
        ["ACH is an explicitly supplied design input; no code minimum is inferred."], "explicit_user_input")]


def _lighting(p: dict[str, Any]) -> list[Calculation]:
    area, lux = _num(p, "area_m2"), _num(p, "lux")
    if area is None or lux is None:
        return [_calc_missing("LGT-FLUX-001", "Lighting", "Required illuminance flux",
            "Phi = E(lux) * A(m2)", ("area_m2", "lux"), p)]
    return [Calculation("LGT-FLUX-001", "Lighting", "Required illuminance flux", "calculated", area*lux, "lm",
        "Phi = E * A", {"area_m2": area, "lux": lux},
        ["This is ideal maintained flux before utilization, maintenance, optical and fixture factors."], "explicit_user_input")]


def _mechanical(spec: EngineeringSpec, p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    for a in spec.assets:
        volume = a.length * a.width * a.height
        if a.shape in {"tank", "vessel", "cylinder"} and a.diameter:
            volume = math.pi * (a.diameter ** 2) / 4 * a.height
        out.append(Calculation(f"MECH-VOL-{a.tag}", "Mechanical", f"Envelope volume {a.tag}", "calculated",
            volume, f"{spec.units}^3", "L * W * H (or pi*D^2/4*H for a specified diameter)",
            {"tag": a.tag, "length": a.length, "width": a.width, "height": a.height, "diameter": a.diameter},
            ["Envelope volume is geometric, not process working volume."], "validated_engineering_spec"))
    return out


def _rules(calcs: list[Calculation], p: dict[str, Any]) -> list[RuleCheck]:
    rules: list[RuleCheck] = []
    velocity = next((c for c in calcs if c.id == "PIP-VEL-001" and c.status == "calculated"), None)
    if velocity:
        # Generic screening only; no pipe-service/code limit is universal.
        rules.append(RuleCheck("PIP-SCREEN-001", "Piping", "info", "review",
            f"Calculated velocity is {velocity.value:.3f} m/s; compare against the project/service-specific limit.",
            "No universal velocity limit assumed", velocity.inputs))
    current = next((c for c in calcs if c.id == "ELEC-I-001" and c.status == "calculated"), None)
    if current:
        rules.append(RuleCheck("ELEC-SCREEN-001", "Electrical", "high", "review",
            f"Calculated current is {current.value:.1f} A; cable, breaker, voltage-drop and thermal checks are still required.",
            "Project-specific cable/protection design basis required", current.inputs))
    for c in calcs:
        if c.status == "insufficient_input":
            rules.append(RuleCheck(f"INPUT-{c.id}", c.discipline, "medium", "unknown",
                f"{c.name} cannot be calculated because required inputs are missing.",
                c.formula, c.inputs))
    return rules


def run_engineering_calculations(spec: EngineeringSpec, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run all currently implemented deterministic calculations against one spec."""
    p = dict(parameters or {})
    calcs: list[Calculation] = []
    calcs.extend(_piping(spec, p))
    calcs.extend(_electrical(spec, p))
    calcs.extend(_hvac(p))
    calcs.extend(_lighting(p))
    calcs.extend(_mechanical(spec, p))
    rules = _rules(calcs, p)
    calculated = sum(c.status == "calculated" for c in calcs)
    unknown = sum(c.status == "insufficient_input" for c in calcs)
    return {
        "engine": "GridPulse Deterministic Engineering Calculation Engine v0.1",
        "mode": "real_equations_no_silent_assumptions",
        "parameters": p,
        "calculations": [c.as_dict() for c in calcs],
        "rule_checks": [r.as_dict() for r in rules],
        "summary": {"total": len(calcs), "calculated": calculated, "insufficient_input": unknown,
                    "rules": len(rules)},
        "gate": "calculation_review_required" if unknown else "calculation_complete_subject_to_code_and_design_basis_review",
        "limitations": [
            "A calculation is only marked calculated when its required numeric inputs are available.",
            "Code limits, equipment ratings, material properties and protection settings are not invented.",
            "Results are preliminary engineering calculations and require project-specific design basis and qualified review before construction or operation.",
        ],
    }

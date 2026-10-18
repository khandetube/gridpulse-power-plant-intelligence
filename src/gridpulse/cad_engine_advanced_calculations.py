"""Higher-order deterministic engineering calculations.

This module deliberately separates calculations that need additional project inputs
from the base geometry calculations. It never selects a code limit or equipment
rating silently. Every numeric result is traceable to explicit inputs.
"""
from __future__ import annotations

import math
from typing import Any

from gridpulse.cad_engine_calculations import Calculation, RuleCheck

G = 9.80665
SQRT3 = math.sqrt(3.0)


def _positive(p: dict[str, Any], key: str) -> float | None:
    try:
        value = float(p[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _missing(cid: str, discipline: str, name: str, formula: str, keys: tuple[str, ...], p: dict[str, Any]) -> Calculation:
    missing = [k for k in keys if _positive(p, k) is None]
    return Calculation(cid, discipline, name, "insufficient_input", None, "", formula,
                       {k: p.get(k) for k in keys},
                       [f"Missing or non-positive required input: {k}" for k in missing],
                       "explicit_user_input", ["No design value was invented."])


def _hydraulic_sizing(p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    q = _positive(p, "flow_m3_h")
    vmax = _positive(p, "max_velocity_m_s")
    if q is not None and vmax is not None:
        q_s = q / 3600.0
        d = math.sqrt(4.0 * q_s / (math.pi * vmax))
        out.append(Calculation("PIP-SIZE-001", "Piping", "Required hydraulic inside diameter", "calculated", d * 1000.0, "mm",
            "D=sqrt(4Q/(pi*v_allow))", {"flow_m3_h": q, "max_velocity_m_s": vmax},
            ["This is a hydraulic sizing diameter, not a DN selection; wall thickness, pressure class and actual internal diameter must be checked separately."],
            "explicit_user_input"))
    else:
        out.append(_missing("PIP-SIZE-001", "Piping", "Required hydraulic inside diameter", "D=sqrt(4Q/(pi*v_allow))",
                            ("flow_m3_h", "max_velocity_m_s"), p))

    rho = _positive(p, "fluid_density_kg_m3")
    q = _positive(p, "flow_m3_h")
    head = _positive(p, "pump_head_m")
    eta = _positive(p, "pump_efficiency")
    if rho is not None and q is not None and head is not None and eta is not None and eta <= 1:
        hydraulic = rho * G * (q / 3600.0) * head
        shaft = hydraulic / eta
        out.extend([
            Calculation("PUMP-P-001", "Piping", "Pump hydraulic power", "calculated", hydraulic / 1000.0, "kW",
                "P_h=rho*g*Q*H", {"density_kg_m3": rho, "flow_m3_h": q, "head_m": head},
                ["Steady incompressible-flow relationship; no transient effects."], "explicit_user_input"),
            Calculation("PUMP-S-001", "Mechanical", "Pump shaft power", "calculated", shaft / 1000.0, "kW",
                "P_shaft=P_h/eta", {"hydraulic_power_kw": hydraulic / 1000.0, "pump_efficiency": eta},
                ["Pump efficiency must be supplied from the selected operating point or vendor data."], "explicit_user_input"),
        ])
    else:
        out.append(_missing("PUMP-S-001", "Mechanical", "Pump shaft power", "P_shaft=rho*g*Q*H/eta",
                            ("fluid_density_kg_m3", "flow_m3_h", "pump_head_m", "pump_efficiency"), p))
    return out


def _advanced_electrical(p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    current = _positive(p, "current_a")
    length = _positive(p, "cable_length_m")
    area = _positive(p, "cable_area_mm2")
    voltage = _positive(p, "voltage_v") or ((_positive(p, "voltage_kv") or 0.0) * 1000.0 or None)
    pf = _positive(p, "power_factor")
    reactance = _positive(p, "cable_reactance_ohm_km")
    if current and length and area and voltage:
        rho = _positive(p, "conductor_resistivity_ohm_m") or 1.724e-8
        temp_factor = _positive(p, "resistance_temperature_factor") or 1.0
        r = rho * length / (area * 1e-6) * temp_factor
        x = (reactance * length / 1000.0) if reactance else 0.0
        angle_factor = pf if pf is not None and pf <= 1 else 1.0
        sinphi = math.sqrt(max(0.0, 1.0 - angle_factor ** 2))
        drop = SQRT3 * current * (r * angle_factor + x * sinphi)
        out.extend([
            Calculation("ELEC-VD-3PH-001", "Electrical", "Three-phase cable voltage drop", "calculated", drop, "V",
                "DeltaV=sqrt(3)*I*(R*cosphi+X*sinphi)", {"current_a": current, "length_m": length, "area_mm2": area, "resistance_ohm": r, "reactance_ohm": x, "power_factor": angle_factor, "voltage_v": voltage},
                ["Balanced three-phase circuit. If reactance is absent, X=0 is explicitly treated as a resistance-only calculation."], "explicit_user_input"),
            Calculation("ELEC-VD-PCT-001", "Electrical", "Three-phase voltage-drop percentage", "calculated", 100.0 * drop / voltage, "%",
                "%DeltaV=100*DeltaV/V", {"drop_v": drop, "voltage_v": voltage},
                ["Compare with the project/code allowable limit supplied by the user; no universal limit is assumed."], "explicit_user_input"),
        ])
    else:
        out.append(_missing("ELEC-VD-3PH-001", "Electrical", "Three-phase cable voltage drop", "DeltaV=sqrt(3)*I*(R*cosphi+X*sinphi)",
                            ("current_a", "cable_length_m", "cable_area_mm2", "voltage_v"), p))

    transformer_mva = _positive(p, "transformer_mva")
    transformer_kv = _positive(p, "transformer_voltage_kv")
    z_pct = _positive(p, "transformer_impedance_pct")
    if transformer_mva and transformer_kv and z_pct:
        flc = transformer_mva * 1000.0 / (SQRT3 * transformer_kv)
        fault = flc * 100.0 / z_pct
        out.extend([
            Calculation("ELEC-TR-I-001", "Electrical", "Transformer full-load current", "calculated", flc, "A",
                "I=S/(sqrt(3)*V)", {"transformer_mva": transformer_mva, "transformer_voltage_kv": transformer_kv},
                ["Three-phase line current at the stated transformer voltage."], "explicit_user_input"),
            Calculation("ELEC-SC-001", "Electrical", "Transformer-terminal prospective three-phase fault current", "calculated", fault, "A",
                "Isc=I_FL*(100/Z%)", {"full_load_current_a": flc, "transformer_impedance_pct": z_pct},
                ["Initial symmetrical fault approximation at transformer terminals; source impedance, X/R, tap and network contributions are excluded."], "explicit_user_input")
        ])
    else:
        out.append(_missing("ELEC-SC-001", "Electrical", "Transformer-terminal prospective three-phase fault current", "Isc=I_FL*(100/Z%)",
                            ("transformer_mva", "transformer_voltage_kv", "transformer_impedance_pct"), p))
    return out


def _tray(p: dict[str, Any]) -> list[Calculation]:
    count = _positive(p, "cable_count")
    cable_d = _positive(p, "cable_outer_diameter_mm")
    tray_w = _positive(p, "tray_width_mm")
    if count and cable_d and tray_w:
        occupied = count * cable_d
        fill = 100.0 * occupied / tray_w
        return [Calculation("ELEC-TRAY-FILL-001", "Electrical", "Cable tray projected fill", "calculated", fill, "%",
            "Fill=100*N*D/W", {"cable_count": count, "cable_outer_diameter_mm": cable_d, "tray_width_mm": tray_w},
            ["One-dimensional projected-width screening; cable arrangement, separation, heat dissipation and applicable tray fill rules require project-specific verification."], "explicit_user_input")]
    return [_missing("ELEC-TRAY-FILL-001", "Electrical", "Cable tray projected fill", "Fill=100*N*D/W",
                     ("cable_count", "cable_outer_diameter_mm", "tray_width_mm"), p)]


def _advanced_rules(calcs: list[Calculation], p: dict[str, Any]) -> list[RuleCheck]:
    rules: list[RuleCheck] = []
    for cid, label, limit_key in [
        ("ELEC-VD-PCT-001", "Voltage drop", "max_voltage_drop_pct"),
        ("ELEC-TRAY-FILL-001", "Tray projected fill", "max_tray_fill_pct"),
    ]:
        calc = next((c for c in calcs if c.id == cid and c.status == "calculated"), None)
        limit = _positive(p, limit_key)
        if calc and limit:
            passed = calc.value <= limit
            rules.append(RuleCheck(f"RULE-{cid}", calc.discipline, "high" if not passed else "info", "pass" if passed else "fail",
                f"{label}={calc.value:.3f} {calc.unit}; project limit={limit:.3f}.",
                "Explicit project limit supplied by user", {"value": calc.value, "limit": limit}))
        elif calc:
            rules.append(RuleCheck(f"RULE-{cid}", calc.discipline, "medium", "review",
                f"{label} calculated as {calc.value:.3f} {calc.unit}; no allowable limit was supplied.",
                "No universal project limit assumed", calc.inputs))
    return rules


def run_advanced_calculations(parameters: dict[str, Any]) -> dict[str, Any]:
    p = dict(parameters)
    calculations = _hydraulic_sizing(p) + _advanced_electrical(p) + _tray(p)
    rules = _advanced_rules(calculations, p)
    return {
        "engine": "GridPulse Advanced Engineering Calculation Engine v0.3",
        "calculations": [c.as_dict() for c in calculations],
        "rule_checks": [r.as_dict() for r in rules],
        "summary": {
            "total": len(calculations),
            "calculated": sum(c.status == "calculated" for c in calculations),
            "insufficient_input": sum(c.status == "insufficient_input" for c in calculations),
            "rules": len(rules),
        },
        "methodology": "First-principles deterministic equations with explicit project inputs; no automatic code-limit selection.",
    }

"""Higher-order deterministic engineering calculations.

Calculations are screening-level, traceable and input-gated. No code limit, rating,
or absent physical property is silently selected. Final design needs discipline review.
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
            ["Hydraulic inside diameter only; do not equate this directly to nominal pipe size."], "explicit_user_input"))
    else:
        out.append(_missing("PIP-SIZE-001", "Piping", "Required hydraulic inside diameter", "D=sqrt(4Q/(pi*v_allow))",
                            ("flow_m3_h", "max_velocity_m_s"), p))

    rho, q, head, eta = (_positive(p, k) for k in ("fluid_density_kg_m3", "flow_m3_h", "pump_head_m", "pump_efficiency"))
    if rho and q and head and eta and eta <= 1:
        hydraulic = rho * G * (q / 3600.0) * head
        out.extend([
            Calculation("PUMP-P-001", "Piping", "Pump hydraulic power", "calculated", hydraulic / 1000.0, "kW",
                "P_h=rho*g*Q*H", {"density_kg_m3": rho, "flow_m3_h": q, "head_m": head},
                ["Steady incompressible-flow relationship; system curve and transient effects excluded."], "explicit_user_input"),
            Calculation("PUMP-S-001", "Mechanical", "Pump shaft power", "calculated", hydraulic / eta / 1000.0, "kW",
                "P_shaft=P_h/eta", {"hydraulic_power_kw": hydraulic / 1000.0, "pump_efficiency": eta},
                ["Efficiency must correspond to the selected operating point or vendor data."], "explicit_user_input"),
        ])
    else:
        out.append(_missing("PUMP-S-001", "Mechanical", "Pump shaft power", "P_shaft=rho*g*Q*H/eta",
                            ("fluid_density_kg_m3", "flow_m3_h", "pump_head_m", "pump_efficiency"), p))
    return out


def _advanced_electrical(p: dict[str, Any]) -> list[Calculation]:
    out: list[Calculation] = []
    current, length, area = (_positive(p, k) for k in ("current_a", "cable_length_m", "cable_area_mm2"))
    voltage = _positive(p, "voltage_v") or ((_positive(p, "voltage_kv") or 0.0) * 1000.0 or None)
    pf = _positive(p, "power_factor")
    reactance = _positive(p, "cable_reactance_ohm_km")
    if current and length and area and voltage:
        rho = _positive(p, "conductor_resistivity_ohm_m") or 1.724e-8
        temp_factor = _positive(p, "resistance_temperature_factor") or 1.0
        resistance = rho * length / (area * 1e-6) * temp_factor
        x = reactance * length / 1000.0 if reactance else 0.0
        cosphi = pf if pf is not None and pf <= 1 else 1.0
        sinphi = math.sqrt(max(0.0, 1.0 - cosphi ** 2))
        drop = SQRT3 * current * (resistance * cosphi + x * sinphi)
        out.extend([
            Calculation("ELEC-VD-3PH-001", "Electrical", "Three-phase cable voltage drop", "calculated", drop, "V",
                "DeltaV=sqrt(3)*I*(R*cosphi+X*sinphi)", {"current_a": current, "length_m": length, "area_mm2": area, "resistance_ohm": resistance, "reactance_ohm": x, "power_factor": cosphi, "voltage_v": voltage},
                ["Balanced three-phase circuit; reactance is zero only when no reactance input is supplied, so result is resistance-only."], "explicit_user_input"),
            Calculation("ELEC-VD-PCT-001", "Electrical", "Three-phase voltage-drop percentage", "calculated", 100.0 * drop / voltage, "%",
                "%DeltaV=100*DeltaV/V", {"drop_v": drop, "voltage_v": voltage},
                ["Compare with project/code limit supplied explicitly; no universal limit is assumed."], "explicit_user_input"),
        ])
    else:
        out.append(_missing("ELEC-VD-3PH-001", "Electrical", "Three-phase cable voltage drop", "DeltaV=sqrt(3)*I*(R*cosphi+X*sinphi)",
                            ("current_a", "cable_length_m", "cable_area_mm2", "voltage_v"), p))

    transformer_mva, transformer_kv, z_pct = (_positive(p, k) for k in ("transformer_mva", "transformer_voltage_kv", "transformer_impedance_pct"))
    if transformer_mva and transformer_kv and z_pct:
        flc = transformer_mva * 1000.0 / (SQRT3 * transformer_kv)
        fault = flc * 100.0 / z_pct
        out.extend([
            Calculation("ELEC-TR-I-001", "Electrical", "Transformer full-load current", "calculated", flc, "A",
                "I=S/(sqrt(3)*V)", {"transformer_mva": transformer_mva, "transformer_voltage_kv": transformer_kv},
                ["Three-phase line current at stated transformer voltage."], "explicit_user_input"),
            Calculation("ELEC-SC-001", "Electrical", "Transformer-terminal prospective three-phase fault current", "calculated", fault, "A",
                "Isc=I_FL*(100/Z%)", {"full_load_current_a": flc, "transformer_impedance_pct": z_pct},
                ["Simplified initial symmetrical transformer-terminal estimate; source impedance, X/R, taps and network contributions excluded."], "explicit_user_input")
        ])
    else:
        out.append(_missing("ELEC-SC-001", "Electrical", "Transformer-terminal prospective three-phase fault current", "Isc=I_FL*(100/Z%)",
                            ("transformer_mva", "transformer_voltage_kv", "transformer_impedance_pct"), p))
    return out


def _tray(p: dict[str, Any]) -> list[Calculation]:
    count, cable_d, tray_w = (_positive(p, k) for k in ("cable_count", "cable_outer_diameter_mm", "tray_width_mm"))
    if count and cable_d and tray_w:
        fill = 100.0 * count * cable_d / tray_w
        return [Calculation("ELEC-TRAY-FILL-001", "Electrical", "Cable tray projected fill", "calculated", fill, "%",
            "Fill=100*N*D/W", {"cable_count": count, "cable_outer_diameter_mm": cable_d, "tray_width_mm": tray_w},
            ["One-dimensional projected-width screening only; cable arrangement, separation, heat dissipation and code fill method require verification."], "explicit_user_input")]
    return [_missing("ELEC-TRAY-FILL-001", "Electrical", "Cable tray projected fill", "Fill=100*N*D/W",
                     ("cable_count", "cable_outer_diameter_mm", "tray_width_mm"), p)]


def _pipe_minor_loss(p: dict[str, Any]) -> list[Calculation]:
    q, d, rho, k_total = (_positive(p, key) for key in ("flow_m3_h", "diameter_mm", "fluid_density_kg_m3", "minor_loss_coefficient"))
    if not (q and d and rho and k_total):
        return [_missing("PIP-MINOR-DP-001", "Piping", "Fitting and valve minor pressure loss", "DeltaP=K_total*rho*v^2/2",
                         ("flow_m3_h", "diameter_mm", "fluid_density_kg_m3", "minor_loss_coefficient"), p)]
    velocity = (q / 3600.0) / (math.pi * (d / 1000.0) ** 2 / 4.0)
    dp_pa = k_total * rho * velocity ** 2 / 2.0
    return [Calculation("PIP-MINOR-DP-001", "Piping", "Fitting and valve minor pressure loss", "calculated", dp_pa / 1e5, "bar",
        "DeltaP=K_total*rho*v^2/2", {"flow_m3_h": q, "diameter_mm": d, "density_kg_m3": rho, "total_loss_coefficient": k_total, "velocity_m_s": velocity},
        ["K_total must be the sum for the actual fittings/valves at the relevant Reynolds number; straight-pipe friction and static head are separate."], "explicit_user_input")]


def _hvac_thermal(p: dict[str, Any]) -> list[Calculation]:
    flow, rho, cp, delta_t = (_positive(p, key) for key in ("airflow_m3_h", "air_density_kg_m3", "air_specific_heat_j_kg_k", "temperature_difference_k"))
    if not (flow and rho and cp and delta_t):
        return [_missing("HVAC-LOAD-001", "HVAC", "Sensible air-side thermal load", "Qdot=rho*Vdot*cp*DeltaT",
                         ("airflow_m3_h", "air_density_kg_m3", "air_specific_heat_j_kg_k", "temperature_difference_k"), p)]
    kw = rho * (flow / 3600.0) * cp * delta_t / 1000.0
    return [Calculation("HVAC-LOAD-001", "HVAC", "Sensible air-side thermal load", "calculated", kw, "kW",
        "Qdot=rho*Vdot*cp*DeltaT", {"airflow_m3_h": flow, "air_density_kg_m3": rho, "air_specific_heat_j_kg_k": cp, "temperature_difference_k": delta_t},
        ["Sensible load only; latent load, fan heat, envelope transmission, infiltration and diversity are excluded."], "explicit_user_input")]


def _lighting(p: dict[str, Any]) -> list[Calculation]:
    lux, area, lumens, uf, mf = (_positive(p, key) for key in ("target_illuminance_lux", "area_m2", "fixture_lumens", "utilization_factor", "maintenance_factor"))
    if not (lux and area and lumens and uf and mf and uf <= 1 and mf <= 1):
        return [_missing("LIGHT-FIX-001", "Lighting", "Preliminary luminaire quantity", "N=ceil(E*A/(lumens*UF*MF))",
                         ("target_illuminance_lux", "area_m2", "fixture_lumens", "utilization_factor", "maintenance_factor"), p)]
    count = math.ceil(lux * area / (lumens * uf * mf))
    return [Calculation("LIGHT-FIX-001", "Lighting", "Preliminary luminaire quantity", "calculated", float(count), "fixtures",
        "N=ceil(E*A/(lumens*UF*MF))", {"target_illuminance_lux": lux, "area_m2": area, "fixture_lumens": lumens, "utilization_factor": uf, "maintenance_factor": mf},
        ["Lumen-method estimate; photometric layout, uniformity, glare, emergency lighting and applicable standard checks remain necessary."], "explicit_user_input")]


def _grounding_rod(p: dict[str, Any]) -> list[Calculation]:
    rho, length, diameter = (_positive(p, key) for key in ("soil_resistivity_ohm_m", "ground_rod_length_m", "ground_rod_diameter_m"))
    if not (rho and length and diameter):
        return [_missing("GROUND-ROD-R-001", "Grounding", "Single vertical rod resistance estimate", "R=rho/(2*pi*L)*(ln(4L/d)-1)",
                         ("soil_resistivity_ohm_m", "ground_rod_length_m", "ground_rod_diameter_m"), p)]
    if 4.0 * length / diameter <= 1.0:
        return [Calculation("GROUND-ROD-R-001", "Grounding", "Single vertical rod resistance estimate", "invalid_input", None, "ohm",
            "R=rho/(2*pi*L)*(ln(4L/d)-1)", {"soil_resistivity_ohm_m": rho, "ground_rod_length_m": length, "ground_rod_diameter_m": diameter},
            ["Geometry is outside the valid domain of this approximate expression."], "explicit_user_input")]
    resistance = rho / (2.0 * math.pi * length) * (math.log(4.0 * length / diameter) - 1.0)
    return [Calculation("GROUND-ROD-R-001", "Grounding", "Single vertical rod resistance estimate", "calculated", resistance, "ohm",
        "R=rho/(2*pi*L)*(ln(4L/d)-1)", {"soil_resistivity_ohm_m": rho, "ground_rod_length_m": length, "ground_rod_diameter_m": diameter},
        ["Approximate homogeneous-soil single-rod model; ignores layered soil, mutual coupling, seasonal change, grid geometry, touch/step voltage and safety criteria. Not a grounding compliance result."], "explicit_user_input")]


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
    """Run available advanced checks; each missing-input result is explicit."""
    p = dict(parameters)
    calculations = (_hydraulic_sizing(p) + _advanced_electrical(p) + _tray(p)
                    + _pipe_minor_loss(p) + _hvac_thermal(p) + _lighting(p) + _grounding_rod(p))
    rules = _advanced_rules(calculations, p)
    return {
        "engine": "GridPulse Advanced Engineering Calculation Engine v0.4",
        "calculations": [c.as_dict() for c in calculations],
        "rule_checks": [r.as_dict() for r in rules],
        "summary": {
            "total": len(calculations),
            "calculated": sum(c.status == "calculated" for c in calculations),
            "insufficient_input": sum(c.status == "insufficient_input" for c in calculations),
            "invalid_input": sum(c.status == "invalid_input" for c in calculations),
            "rules": len(rules),
        },
        "methodology": "Traceable first-principles equations with explicit-input gating; no automatic code-limit selection.",
    }

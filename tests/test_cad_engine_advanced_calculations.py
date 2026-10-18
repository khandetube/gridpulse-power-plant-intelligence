from gridpulse.cad_engine_advanced_calculations import run_advanced_calculations


def get(report, calc_id):
    return next(c for c in report["calculations"] if c["id"] == calc_id)


def test_hydraulic_pipe_sizing_uses_first_principles():
    report = run_advanced_calculations({"flow_m3_h": 500, "max_velocity_m_s": 2.0})
    calc = get(report, "PIP-SIZE-001")
    assert calc["status"] == "calculated"
    assert abs(calc["value"] - 297.7) < 1.0


def test_pump_power_is_physical_equation():
    report = run_advanced_calculations({
        "fluid_density_kg_m3": 998.2,
        "flow_m3_h": 500,
        "pump_head_m": 50,
        "pump_efficiency": 0.8,
    })
    hydraulic = get(report, "PUMP-P-001")
    shaft = get(report, "PUMP-S-001")
    assert abs(hydraulic["value"] - 67.93) < 0.2
    assert abs(shaft["value"] - 84.91) < 0.3


def test_transformer_fault_current_is_traceable():
    report = run_advanced_calculations({
        "transformer_mva": 40,
        "transformer_voltage_kv": 11,
        "transformer_impedance_pct": 8,
    })
    flc = get(report, "ELEC-TR-I-001")
    fault = get(report, "ELEC-SC-001")
    assert abs(flc["value"] - 2099.4) < 2
    assert abs(fault["value"] - 26242.5) < 30


def test_voltage_drop_uses_three_phase_impedance_equation():
    report = run_advanced_calculations({
        "current_a": 100,
        "cable_length_m": 100,
        "cable_area_mm2": 35,
        "voltage_v": 400,
        "power_factor": 0.9,
        "cable_reactance_ohm_km": 0.08,
    })
    drop = get(report, "ELEC-VD-3PH-001")
    pct = get(report, "ELEC-VD-PCT-001")
    assert drop["status"] == "calculated"
    assert 5 < drop["value"] < 10
    assert pct["value"] == drop["value"] / 4


def test_project_limit_creates_real_rule_result():
    report = run_advanced_calculations({
        "cable_count": 20,
        "cable_outer_diameter_mm": 20,
        "tray_width_mm": 400,
        "max_tray_fill_pct": 80,
    })
    rule = next(r for r in report["rule_checks"] if r["id"] == "RULE-ELEC-TRAY-FILL-001")
    assert rule["status"] == "pass"


def test_advanced_engine_never_invents_missing_inputs():
    report = run_advanced_calculations({})
    assert all(c["status"] == "insufficient_input" for c in report["calculations"])
    assert all(c["value"] is None for c in report["calculations"])

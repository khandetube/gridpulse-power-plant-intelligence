from gridpulse.cad_engine import CadAsset, EngineeringSpec
from gridpulse.cad_engine_calculations import parse_explicit_parameters, run_engineering_calculations


def _spec():
    return EngineeringSpec(
        project_name="calc-test",
        site_width=50,
        site_length=40,
        assets=[CadAsset(tag="P-1", name="Pump", discipline="Mechanical", shape="pump", x=2, y=2, length=3, width=2, height=2)],
        routes=[],
    )


def test_explicit_parameter_parser_does_not_guess():
    p = parse_explicit_parameters("10 MW, 11 kV, 50 Hz, power factor 0.9, 500 m3/h, DN200, 6 bar, 30 ACH, 500 lux")
    assert p["power_mw"] == 10
    assert p["voltage_kv"] == 11
    assert p["frequency_hz"] == 50
    assert p["power_factor"] == 0.9
    assert p["flow_m3_h"] == 500
    assert p["diameter_mm"] == 200
    assert p["pressure_bar"] == 6
    assert p["ach"] == 30
    assert p["lux"] == 500


def test_three_phase_current_is_real_formula():
    report = run_engineering_calculations(_spec(), {"power_mw": 10, "voltage_kv": 11, "power_factor": 0.9})
    current = next(c for c in report["calculations"] if c["id"] == "ELEC-I-001")
    assert current["status"] == "calculated"
    assert abs(current["value"] - 583.16) < 0.5


def test_pipe_velocity_is_real_formula():
    report = run_engineering_calculations(_spec(), {"flow_m3_h": 500, "diameter_mm": 200})
    velocity = next(c for c in report["calculations"] if c["id"] == "PIP-VEL-001")
    assert velocity["status"] == "calculated"
    assert abs(velocity["value"] - 4.42097) < 0.01


def test_darcy_pressure_drop_uses_explicit_length_and_fluid_data():
    report = run_engineering_calculations(_spec(), {
        "flow_m3_h": 100, "diameter_mm": 100, "pipe_length_m": 100,
        "fluid_density_kg_m3": 998.2, "fluid_viscosity_pa_s": 0.001002,
        "pipe_roughness_mm": 0.045,
    })
    reynolds = next(c for c in report["calculations"] if c["id"] == "PIP-RE-001")
    friction = next(c for c in report["calculations"] if c["id"] == "PIP-F-001")
    loss = next(c for c in report["calculations"] if c["id"] == "PIP-DP-001")
    assert reynolds["status"] == "calculated"
    assert reynolds["value"] > 100000
    assert 0.01 < friction["value"] < 0.04
    assert loss["value"] > 0


def test_cable_resistance_loss_and_voltage_drop_require_area():
    report = run_engineering_calculations(_spec(), {"current_a": 100, "cable_length_m": 100, "cable_area_mm2": 35})
    resistance = next(c for c in report["calculations"] if c["id"] == "ELEC-R-001")
    loss = next(c for c in report["calculations"] if c["id"] == "ELEC-L-001")
    drop = next(c for c in report["calculations"] if c["id"] == "ELEC-V-001")
    assert abs(resistance["value"] - 0.049257) < 0.001
    assert abs(loss["value"] - 492.57) < 1
    assert abs(drop["value"] - 4.9257) < 0.01


def test_missing_input_is_not_silently_assumed():
    report = run_engineering_calculations(_spec(), {})
    velocity = next(c for c in report["calculations"] if c["id"] == "PIP-VEL-001")
    assert velocity["status"] == "insufficient_input"
    assert velocity["value"] is None
    assert report["summary"]["insufficient_input"] >= 4


def test_hvac_and_lighting_calculations():
    report = run_engineering_calculations(_spec(), {"volume_m3": 1000, "ach": 6, "area_m2": 200, "lux": 500})
    airflow = next(c for c in report["calculations"] if c["id"] == "HVAC-AIR-001")
    flux = next(c for c in report["calculations"] if c["id"] == "LGT-FLUX-001")
    assert airflow["value"] == 6000
    assert flux["value"] == 100000

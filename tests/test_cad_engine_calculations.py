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


def test_missing_input_is_not_silently_assumed():
    report = run_engineering_calculations(_spec(), {})
    velocity = next(c for c in report["calculations"] if c["id"] == "PIP-VEL-001")
    assert velocity["status"] == "insufficient_input"
    assert velocity["value"] is None
    assert report["summary"]["insufficient_input"] >= 3


def test_hvac_and_lighting_calculations():
    report = run_engineering_calculations(_spec(), {"volume_m3": 1000, "ach": 6, "area_m2": 200, "lux": 500})
    airflow = next(c for c in report["calculations"] if c["id"] == "HVAC-AIR-001")
    flux = next(c for c in report["calculations"] if c["id"] == "LGT-FLUX-001")
    assert airflow["value"] == 6000
    assert flux["value"] == 100000

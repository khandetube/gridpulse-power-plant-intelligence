from gridpulse.cad_engine_parameter_parser import parse_advanced_parameters


def test_parser_extracts_explicit_hvac_and_lighting_values():
    values = parse_advanced_parameters(
        "airflow 3600 m3/h, air density 1.2 kg/m3, "
        "air specific heat 1005 J/kg/K, temperature difference 10 K, "
        "target illuminance 500 lux, fixture output 10000 lm, "
        "utilization factor 0.7, maintenance factor 0.8"
    )
    assert values["airflow_m3_h"] == 3600
    assert values["air_density_kg_m3"] == 1.2
    assert values["temperature_difference_k"] == 10
    assert values["target_illuminance_lux"] == 500
    assert values["fixture_lumens"] == 10000


def test_parser_does_not_invent_missing_advanced_values():
    values = parse_advanced_parameters("Design a ventilation system and lighting layout")
    assert values == {}

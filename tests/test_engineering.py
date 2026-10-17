import pytest

from gridpulse.engineering import calculate_generation_performance


def test_generation_performance_formulas_and_explicit_units():
    result = calculate_generation_performance(
        net_generation_mwh=100,
        fuel_thermal_input_mwh=250,
        net_capacity_mw=50,
        period_hours=4,
    )
    assert result["net_efficiency_percent"] == pytest.approx(40)
    assert result["net_heat_rate_kj_per_kwh"] == pytest.approx(9000)
    assert result["capacity_factor_percent"] == pytest.approx(50)
    assert result["warnings"] == []
    assert result["formula_version"] == "gridpulse-generation-performance-v1"


def test_generation_performance_flags_impossible_efficiency_and_capacity_factor():
    result = calculate_generation_performance(
        net_generation_mwh=200,
        fuel_thermal_input_mwh=100,
        net_capacity_mw=10,
        period_hours=10,
    )
    assert result["net_efficiency_percent"] == pytest.approx(200)
    assert result["capacity_factor_percent"] == pytest.approx(200)
    assert len(result["warnings"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("net_generation_mwh", 0),
        ("fuel_thermal_input_mwh", -1),
        ("net_capacity_mw", 0),
        ("period_hours", 0),
        ("period_hours", float("inf")),
    ],
)
def test_generation_performance_rejects_invalid_physical_inputs(field, value):
    values = {
        "net_generation_mwh": 100,
        "fuel_thermal_input_mwh": 250,
        "net_capacity_mw": 50,
        "period_hours": 4,
    }
    values[field] = value
    with pytest.raises(ValueError):
        calculate_generation_performance(**values)

import pytest

from gridpulse.unit_conversion import convert_value


def test_converts_power_units():
    result = convert_value(1.5, "MW", "kW")
    assert result["converted_value"] == pytest.approx(1500.0)
    assert result["library"] == "Pint"
    assert result["dimension"] == "[mass] * [length] ** 2 / [time] ** 3"


def test_converts_energy_units():
    result = convert_value(2.0, "MWh", "kWh")
    assert result["converted_value"] == pytest.approx(2000.0)


def test_rejects_incompatible_units():
    with pytest.raises(ValueError, match="dimensionally incompatible"):
        convert_value(1.0, "MW", "MWh")


def test_rejects_unknown_units():
    with pytest.raises(ValueError, match="unknown source or target"):
        convert_value(1.0, "not-a-real-unit", "MW")


def test_rejects_non_finite_values():
    with pytest.raises(ValueError, match="finite"):
        convert_value(float("inf"), "MW", "kW")

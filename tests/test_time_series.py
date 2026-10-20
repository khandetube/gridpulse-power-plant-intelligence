from datetime import date, timedelta

import pytest

from gridpulse.time_series import decompose_time_series


def make_records(values: list[float]) -> list[dict[str, object]]:
    start = date(2026, 1, 1)
    return [
        {
            "record_id": f"series-{index:03d}",
            "metric": "net_generation",
            "unit": "MWh",
            "value": value,
            "period_start": (start + timedelta(days=index)).isoformat(),
            "source_id": "SRC-001",
            "verification_status": "reviewed",
        }
        for index, value in enumerate(values)
    ]


def test_stl_decomposition_returns_components_and_provenance():
    values = [100 + index * 0.5 + [0, 2, -1, 1, -2, 0, 1][index % 7] for index in range(28)]
    result = decompose_time_series(make_records(values), period=7)
    assert result["method"] == "statsmodels STL with robust fitting"
    assert result["observation_count"] == 28
    assert len(result["observations"]) == 28
    assert {"trend", "seasonal", "residual", "residual_robust_z_score"} <= set(result["observations"][0])
    assert result["observations"][0]["source_id"] == "SRC-001"
    assert 0 <= result["seasonal_strength"] <= 1
    assert 0 <= result["trend_strength"] <= 1


def test_stl_requires_two_periods():
    with pytest.raises(ValueError, match="at least 14 observations"):
        decompose_time_series(make_records([1.0] * 13), period=7)


def test_stl_rejects_mixed_units():
    records = make_records([float(index) for index in range(14)])
    records[-1]["unit"] = "kW"
    with pytest.raises(ValueError, match="same metric and unit"):
        decompose_time_series(records, period=7)


def test_stl_rejects_non_finite_values():
    records = make_records([float(index) for index in range(14)])
    records[-1]["value"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        decompose_time_series(records, period=7)


def test_stl_rejects_invalid_period():
    with pytest.raises(ValueError, match="between 2 and 365"):
        decompose_time_series(make_records([1.0] * 14), period=1)

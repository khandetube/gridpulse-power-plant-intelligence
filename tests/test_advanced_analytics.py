from datetime import date, timedelta

import pytest

from gridpulse.advanced_analytics import detect_anomalies


def records(values: list[float]) -> list[dict]:
    start = date(2026, 1, 1)
    return [
        {
            "record_id": f"r-{index}",
            "plant": "Test plant",
            "metric": "net_generation",
            "value": value,
            "unit": "MWh",
            "period_start": (start + timedelta(days=index)).isoformat(),
            "source_id": "SRC-TEST",
            "verification_status": "reviewed",
        }
        for index, value in enumerate(values)
    ]


def test_isolation_forest_flags_extreme_candidate_and_preserves_provenance():
    result = detect_anomalies(
        records([100, 101, 99, 102, 100, 98, 101, 99, 100, 1000]),
        contamination=0.1,
    )
    assert result["algorithm"] == "scikit-learn IsolationForest"
    assert result["observation_count"] == 10
    assert result["flagged_count"] >= 1
    assert all(item["source_id"] == "SRC-TEST" for item in result["flagged_observations"])
    assert "not alarms" in result["limitations"][0]


def test_isolation_forest_requires_minimum_observation_count():
    with pytest.raises(ValueError, match="at least 8"):
        detect_anomalies(records([1, 2, 3, 4, 5, 6, 7]))


def test_isolation_forest_rejects_mixed_metric_or_unit():
    batch = records(list(range(1, 9)))
    batch[-1]["unit"] = "kWh"
    with pytest.raises(ValueError, match="same metric and unit"):
        detect_anomalies(batch)


def test_isolation_forest_rejects_invalid_contamination():
    with pytest.raises(ValueError, match="between 0.01 and 0.20"):
        detect_anomalies(records(list(range(1, 9))), contamination=0.5)


def test_isolation_forest_rejects_non_finite_values():
    batch = records(list(range(1, 9)))
    batch[-1]["value"] = float("inf")
    with pytest.raises(ValueError, match="finite"):
        detect_anomalies(batch)

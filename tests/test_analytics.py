from gridpulse.analytics import analyze_observations


def row(record_id: str, value: float, *, metric: str = "net_generation", unit: str = "MWh"):
    return {
        "record_id": record_id,
        "plant": "Example plant",
        "metric": metric,
        "value": value,
        "unit": unit,
        "period_start": "2026-01-01",
        "period_end": "2026-01-01",
        "scope": "unit",
        "source_id": "SRC-TEST",
        "verification_status": "reviewed",
    }


def test_summary_is_grouped_by_metric_and_unit():
    result = analyze_observations([
        row("a", 10), row("b", 20), row("c", 30),
        row("d", 5, metric="fuel_rate", unit="t/h"),
    ])
    assert result["observation_count"] == 4
    assert result["group_count"] == 2
    generation = next(group for group in result["groups"] if group["metric"] == "net_generation")
    assert generation["mean"] == 20
    assert generation["median"] == 20
    assert generation["range"] == 20


def test_iqr_flags_extreme_value_only_with_enough_nonconstant_values():
    result = analyze_observations([row("a", 10), row("b", 11), row("c", 12), row("d", 13), row("e", 100)])
    assert result["flagged_record_ids"] == ["e"]


def test_iqr_does_not_flag_groups_with_fewer_than_four_values():
    result = analyze_observations([row("a", 1), row("b", 2), row("c", 100)])
    assert result["flagged_record_ids"] == []


def test_iqr_zero_spread_emits_no_flags():
    result = analyze_observations([row("a", 4), row("b", 4), row("c", 4), row("d", 4), row("e", 99)])
    assert result["flagged_record_ids"] == []


def test_duplicate_ids_are_rejected():
    try:
        analyze_observations([row("same", 1), row("same", 2)])
    except ValueError as exc:
        assert "duplicate record_id" in str(exc)
    else:
        raise AssertionError("duplicate record IDs should be rejected")

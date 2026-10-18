from gridpulse.diagnostic_ai import diagnose_observations


def row(record_id, metric, value, day, status="verified"):
    return {
        "record_id": record_id,
        "plant": "Demo plant",
        "metric": metric,
        "value": value,
        "unit": "unit",
        "period_start": day,
        "period_end": day,
        "scope": "plant",
        "source_id": "SRC-001",
        "verification_status": status,
    }


def test_recent_shift_is_detected_with_traceable_evidence():
    records = [row(f"r{i}", "temperature", 10 + (i % 2) * 0.1,
                   f"2026-01-{i:02d}") for i in range(1, 7)]
    records.append(row("latest", "temperature", 50, "2026-01-07"))
    result = diagnose_observations(records)
    finding = next(x for x in result["findings"] if x["kind"] == "recent_baseline_shift_candidate")
    assert finding["observed_value"] == 50
    assert finding["source_id"] == "SRC-001"
    assert finding["evidence_record_ids"] == ["latest"]
    assert finding["evidence_grade"] == "screening_only"


def test_low_confidence_source_is_explicit():
    records = [row(f"r{i}", "pressure", 10, f"2026-02-{i:02d}") for i in range(1, 7)]
    records.append(row("latest", "pressure", 25, "2026-02-07", "unverified"))
    result = diagnose_observations(records)
    finding = next(x for x in result["findings"] if x["kind"] == "recent_baseline_shift_candidate")
    assert finding["evidence_grade"] == "low_source_confidence"


def test_sustained_shift_candidate_requires_sufficient_dates():
    values = [10, 10, 11, 10, 10, 30, 31, 30, 32, 31]
    records = [row(f"r{i}", "output", value, f"2026-03-{i:02d}")
               for i, value in enumerate(values, start=1)]
    result = diagnose_observations(records)
    assert any(x["kind"] == "sustained_level_shift_candidate" for x in result["findings"])


def test_metric_association_is_matched_by_date_and_not_claimed_causal():
    records = []
    for i, value in enumerate([1, 2, 3, 4, 5, 6], start=1):
        day = f"2026-04-{i:02d}"
        records.extend([
            row(f"a{i}", "load", value, day),
            row(f"b{i}", "fuel", value * 2, day),
        ])
    result = diagnose_observations(records)
    finding = next(x for x in result["findings"] if x["kind"] == "exploratory_metric_association")
    assert finding["pearson_r"] == 1.0
    assert finding["matched_distinct_days"] == 6
    assert "not_causation" in finding["evidence_grade"]


def test_gap_and_bad_records_are_reported_without_imputation():
    records = [
        row("a", "vibration", 1, "2026-05-01"),
        row("b", "vibration", 1, "2026-05-02"),
        row("c", "vibration", 1, "2026-05-03"),
        row("d", "vibration", 1, "2026-05-04"),
        row("e", "vibration", 1, "2026-05-30"),
        {**row("bad", "vibration", 2, "not-a-date"), "period_start": "not-a-date"},
    ]
    result = diagnose_observations(records)
    assert result["skipped_count"] == 1
    assert any(x["kind"] == "observation_gap" for x in result["findings"])
    assert "No missing values are imputed" in result["limitations"][2]


def test_diagnostic_engine_is_bounded_and_deterministic():
    records = [row("r1", "x", 1, "2026-06-01")]
    assert diagnose_observations(records) == diagnose_observations(records)
    try:
        diagnose_observations(records * 5001)
    except ValueError as exc:
        assert "5000" in str(exc)
    else:
        raise AssertionError("Oversized request should be rejected")

from gridpulse.approved_limits import review_approved_limits, validate_limits


def _record(value=100):
    return {
        "record_id": "r1", "plant": "P1", "metric": "temperature",
        "unit": "C", "scope": "bearing-1", "value": value,
    }


def _rule(min_value=90, max_value=110, status="verified"):
    return {
        "plant": "P1", "metric": "temperature", "unit": "C", "scope": "bearing-1",
        "min_value": min_value, "max_value": max_value,
        "source_id": "OEM-MANUAL-001", "verification_status": status,
    }


def test_upper_and_lower_bound_review():
    low = review_approved_limits([_record(80)], [_rule()])
    high = review_approved_limits([_record(120)], [_rule()])
    assert low["violations"][0]["reasons"] == ["below_minimum"]
    assert high["violations"][0]["reasons"] == ["above_maximum"]


def test_matching_scope_unit_metric_and_plant_is_required():
    record = _record(120)
    record["unit"] = "F"
    result = review_approved_limits([record], [_rule()])
    assert result["violation_count"] == 0
    assert result["records_without_verified_rule"] == ["r1"]


def test_unverified_rule_is_skipped():
    result = review_approved_limits([_record(120)], [_rule(status="draft")])
    assert result["violation_count"] == 0
    assert result["skipped_unverified_rules"]


def test_invalid_rule_is_reported():
    rule = _rule(min_value=120, max_value=90)
    assert validate_limits([rule])[0]["reason"] == "min_value_greater_than_max_value"


def test_ambiguous_verified_rules_are_not_applied():
    result = review_approved_limits([_record(120)], [_rule(), _rule(min_value=80)])
    assert result["violation_count"] == 0
    assert result["ambiguous_verified_rules"]

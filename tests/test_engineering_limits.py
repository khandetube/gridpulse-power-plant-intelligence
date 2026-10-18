from gridpulse.engineering_limits import review_engineering_limits


def _record(value=105):
    return {
        "record_id": "r1", "plant": "P1", "metric": "temperature", "value": value,
        "unit": "C", "scope": "unit", "source_id": "src-1", "verification_status": "verified",
    }


def _rule(**overrides):
    rule = {
        "rule_id": "lim-1", "plant": "P1", "metric": "temperature", "unit": "C",
        "scope": "unit", "min_value": 0, "max_value": 100,
        "source_id": "manual-approval-1", "verification_status": "verified",
    }
    rule.update(overrides)
    return rule


def test_upper_limit_violation_is_review_flag():
    result = review_engineering_limits([_record()], [_rule()])
    assert result["violation_count"] == 1
    assert result["violations"][0]["direction"] == "above_maximum"
    assert result["violations"][0]["review_required"] is True


def test_matching_scope_and_unit_are_required():
    result = review_engineering_limits([_record(50)], [_rule(scope="plant")])
    assert result["violation_count"] == 0
    assert result["unmatched_or_unreviewed"][0]["reason"] == "no_verified_matching_rule"


def test_unverified_rule_is_never_used():
    result = review_engineering_limits([_record()], [_rule(verification_status="reviewed")])
    assert result["violation_count"] == 0
    assert result["invalid_or_skipped_rules"][0]["reason"] == "unverified_rule_skipped"


def test_invalid_rule_range_is_skipped():
    result = review_engineering_limits([_record()], [_rule(min_value=101, max_value=100)])
    assert result["violation_count"] == 0
    assert result["invalid_or_skipped_rules"][0]["reason"] == "invalid_rule"


def test_ambiguous_verified_rules_are_not_auto_selected():
    result = review_engineering_limits([_record()], [_rule(), _rule(rule_id="lim-2")])
    assert result["violation_count"] == 0
    assert result["unmatched_or_unreviewed"][0]["reason"] == "ambiguous_verified_rules"

"""Deterministic review of observations against explicitly approved engineering limits.

Limits are never invented by GridPulse. Each rule must carry an approved source,
scope, unit and verification status. This module only produces human-review flags;
it never emits control or protection actions.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def validate_limits(limits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate limit definitions without applying them to observations."""
    issues: list[dict[str, Any]] = []
    for index, rule in enumerate(limits):
        required = ("plant", "metric", "unit", "scope", "source_id", "verification_status")
        missing = [field for field in required if not str(rule.get(field, "")).strip()]
        if missing:
            issues.append({"index": index, "reason": "missing_" + ",".join(missing)})
            continue
        minimum = _finite(rule.get("min_value"))
        maximum = _finite(rule.get("max_value"))
        if minimum is None and maximum is None:
            issues.append({"index": index, "reason": "at_least_one_finite_bound_required"})
            continue
        if minimum is not None and maximum is not None and minimum > maximum:
            issues.append({"index": index, "reason": "min_value_greater_than_max_value"})
    return issues


def review_approved_limits(
    records: list[dict[str, Any]], limits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare observations only with verified rules matching plant/metric/unit/scope."""
    if len(records) > 5000:
        raise ValueError("A limit review is limited to 5000 records.")
    if len(limits) > 1000:
        raise ValueError("A limit review is limited to 1000 limit rules.")
    validation_issues = validate_limits(limits)
    valid_rules = [rule for index, rule in enumerate(limits)
                   if not any(issue["index"] == index for issue in validation_issues)]
    skipped_unverified = [
        {"index": index, "source_id": str(rule.get("source_id", "")),
         "reason": "rule_not_verified"}
        for index, rule in enumerate(valid_rules)
        if str(rule.get("verification_status", "")).strip().lower() != "verified"
    ]
    verified = [rule for rule in valid_rules
                if str(rule.get("verification_status", "")).strip().lower() == "verified"]
    by_key: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for rule in verified:
        key = tuple(str(rule[field]).strip() for field in ("plant", "metric", "unit", "scope"))
        by_key.setdefault(key, []).append(rule)

    violations: list[dict[str, Any]] = []
    no_verified_rule: list[str] = []
    ambiguous_rules: list[dict[str, Any]] = []
    for key, rules in by_key.items():
        if len(rules) > 1:
            ambiguous_rules.append({"key": list(key), "rule_count": len(rules),
                                    "source_ids": [str(r["source_id"]) for r in rules]})

    for row in records:
        record_id = str(row.get("record_id", "")).strip()
        key = tuple(str(row.get(field, "")).strip() for field in ("plant", "metric", "unit", "scope"))
        matches = by_key.get(key, [])
        if not matches:
            no_verified_rule.append(record_id)
            continue
        if len(matches) != 1:
            continue
        rule = matches[0]
        value = _finite(row.get("value"))
        if value is None:
            continue
        minimum = _finite(rule.get("min_value"))
        maximum = _finite(rule.get("max_value"))
        reasons: list[str] = []
        if minimum is not None and value < minimum:
            reasons.append("below_minimum")
        if maximum is not None and value > maximum:
            reasons.append("above_maximum")
        if reasons:
            violations.append({
                "record_id": record_id, "plant": key[0], "metric": key[1],
                "unit": key[2], "scope": key[3], "value": value,
                "min_value": minimum, "max_value": maximum,
                "source_id": str(rule["source_id"]),
                "verification_status": str(rule["verification_status"]),
                "reasons": reasons, "review_required": True,
            })

    return {
        "engine": "gridpulse-approved-limits-v1",
        "mode": "human_review_only",
        "input_record_count": len(records),
        "input_rule_count": len(limits),
        "verified_rule_count": len(verified),
        "validation_issues": validation_issues,
        "skipped_unverified_rules": skipped_unverified,
        "ambiguous_verified_rules": ambiguous_rules,
        "records_without_verified_rule": no_verified_rule,
        "violation_count": len(violations),
        "violations": violations,
        "safety_notice": "Limits must come from authorised manufacturer/site engineering documentation. A violation is a review flag, not an alarm, diagnosis, trip or operating instruction.",
    }

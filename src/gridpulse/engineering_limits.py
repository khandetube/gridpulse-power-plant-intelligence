"""Deterministic review of explicitly approved engineering limits.

Limits are evidence records, not invented defaults. Only rules marked verified are
eligible for evaluation. Results are review flags and never operating commands.
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


def review_engineering_limits(
    records: list[dict[str, Any]],
    approved_limits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Review observations against unambiguous, verified limits only."""
    if len(records) > 5000 or len(approved_limits) > 1000:
        raise ValueError("Review is limited to 5000 records and 1000 limit rules.")

    invalid_rules: list[dict[str, Any]] = []
    eligible: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for index, rule in enumerate(approved_limits):
        key_fields = ("plant", "metric", "unit", "scope", "source_id", "verification_status")
        missing = [field for field in key_fields if not str(rule.get(field, "")).strip()]
        low = _finite(rule.get("min_value"))
        high = _finite(rule.get("max_value"))
        if missing or (low is None and high is None) or (low is not None and high is not None and low > high):
            invalid_rules.append({
                "index": index,
                "rule_id": str(rule.get("rule_id", "")),
                "reason": "invalid_rule",
                "missing_fields": missing,
            })
            continue
        if str(rule.get("verification_status")).strip() != "verified":
            invalid_rules.append({
                "index": index,
                "rule_id": str(rule.get("rule_id", "")),
                "reason": "unverified_rule_skipped",
            })
            continue
        key = tuple(str(rule[field]).strip() for field in ("plant", "metric", "unit", "scope"))
        eligible.setdefault(key, []).append({**rule, "min_value": low, "max_value": high})

    ambiguous = {
        key: rules for key, rules in eligible.items() if len(rules) > 1
    }
    violations: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for record in records:
        value = _finite(record.get("value"))
        key = tuple(str(record.get(field, "")).strip() for field in ("plant", "metric", "unit", "scope"))
        rules = eligible.get(key, [])
        if value is None:
            unmatched.append({"record_id": str(record.get("record_id", "")), "reason": "invalid_value"})
            continue
        if not rules:
            unmatched.append({"record_id": str(record.get("record_id", "")), "reason": "no_verified_matching_rule"})
            continue
        if len(rules) > 1:
            unmatched.append({"record_id": str(record.get("record_id", "")), "reason": "ambiguous_verified_rules"})
            continue
        rule = rules[0]
        low, high = rule["min_value"], rule["max_value"]
        below = low is not None and value < low
        above = high is not None and value > high
        if below or above:
            violations.append({
                "record_id": str(record.get("record_id", "")),
                "plant": key[0], "metric": key[1], "unit": key[2], "scope": key[3],
                "value": value, "min_value": low, "max_value": high,
                "direction": "below_minimum" if below else "above_maximum",
                "rule_id": str(rule.get("rule_id", "")),
                "source_id": str(rule["source_id"]),
                "verification_status": "verified",
                "review_required": True,
            })

    return {
        "engine": "gridpulse-engineering-limit-review-v1",
        "rule_count": len(approved_limits),
        "verified_eligible_rule_count": sum(len(rules) for rules in eligible.values()),
        "invalid_or_skipped_rule_count": len(invalid_rules),
        "ambiguous_key_count": len(ambiguous),
        "record_count": len(records),
        "violation_count": len(violations),
        "unmatched_or_unreviewed_count": len(unmatched),
        "violations": violations,
        "unmatched_or_unreviewed": unmatched,
        "invalid_or_skipped_rules": invalid_rules,
        "safety_notice": "Review flags only. Do not use this result alone to operate equipment or change protection/control settings.",
    }

"""Deterministic data-quality and evidence-coverage diagnostics.

Governance-only diagnostics: these checks identify records that deserve review;
they do not establish physical plausibility, equipment faults, or safe operating limits.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
from itertools import pairwise
from math import isfinite
from statistics import median
from typing import Any

ENGINE_ID = "gridpulse-data-quality-v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _period(row: dict[str, Any]) -> tuple[date, date] | None:
    try:
        start = date.fromisoformat(_text(row.get("period_start")))
        end = date.fromisoformat(_text(row.get("period_end")))
    except ValueError:
        return None
    return start, end


def _key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (_text(row.get("plant")), _text(row.get("metric")), _text(row.get("unit")), _text(row.get("scope")))


def _record_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (_key(row), _text(row.get("record_id")), _number(row.get("value")), _text(row.get("period_start")), _text(row.get("period_end")), _text(row.get("source_id")), _text(row.get("verification_status")))


def _severity_for_issue(kind: str) -> str:
    if kind in {"duplicate_record_id_conflict", "overlapping_reporting_period", "unit_mismatch", "scope_mismatch"}:
        return "high"
    if kind in {"missing_source_id", "invalid_period", "missing_required_field", "temporal_gap", "irregular_sampling"}:
        return "medium"
    return "review"


def assess_data_quality(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Assess provenance, identity, consistency and temporal evidence coverage."""
    if not isinstance(records, list):
        raise TypeError("records must be a list")
    if len(records) > 10000:
        raise ValueError("A single data-quality assessment is limited to 10000 records.")

    issues: list[dict[str, Any]] = []
    by_id: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    groups: dict[tuple[str, str, str, str], list[tuple[int, dict[str, Any], tuple[date, date]]]] = defaultdict(list)
    field_missing = Counter()
    verified = source_present = valid_periods = valid_values = 0
    required = ("record_id", "plant", "metric", "unit", "scope", "value", "period_start", "period_end")

    for index, row in enumerate(records):
        if not isinstance(row, dict):
            issues.append({"issue_id": f"row:{index}:not_object", "kind": "invalid_record", "severity": "high", "index": index, "action": "Replace non-object record."})
            continue
        rid = _text(row.get("record_id"))
        if rid:
            by_id[rid].append((index, row))
        missing = [field for field in required if (field == "value" and row.get(field) is None) or (field != "value" and not _text(row.get(field)))]
        for field in missing:
            field_missing[field] += 1
        if missing:
            issues.append({"issue_id": f"row:{index}:missing_required", "kind": "missing_required_field", "severity": "medium", "record_id": rid, "fields": missing, "index": index, "action": "Complete the required record fields and rerun the assessment."})
        source = _text(row.get("source_id"))
        if source:
            source_present += 1
        else:
            issues.append({"issue_id": f"row:{index}:missing_source", "kind": "missing_source_id", "severity": "medium", "record_id": rid, "index": index, "action": "Attach the authoritative source/document identifier."})
        if _text(row.get("verification_status")) == "verified":
            verified += 1
        period = _period(row)
        if period and period[1] >= period[0]:
            valid_periods += 1
        else:
            issues.append({"issue_id": f"row:{index}:invalid_period", "kind": "invalid_period", "severity": "medium", "record_id": rid, "index": index, "action": "Correct period_start/period_end using the source reporting period."})
        if _number(row.get("value")) is not None:
            valid_values += 1
        if not missing and period and period[1] >= period[0]:
            groups[_key(row)].append((index, row, period))

    for rid, entries in sorted(by_id.items()):
        if len(entries) <= 1:
            continue
        signatures = {_record_signature(row) for _, row in entries}
        kind = "duplicate_record_id" if len(signatures) == 1 else "duplicate_record_id_conflict"
        issues.append({"issue_id": f"record:{rid}:duplicate", "kind": kind, "severity": _severity_for_issue(kind), "record_id": rid, "indices": [i for i, _ in entries], "action": "Keep one authoritative record or resolve the conflicting duplicate before analysis."})

    temporal_stats: list[dict[str, Any]] = []
    for key, entries in sorted(groups.items()):
        ordered = sorted(entries, key=lambda item: (item[2][0], item[2][1], _text(item[1].get("record_id"))))
        starts = [period[0] for _, _, period in ordered]
        unique_starts = sorted(set(starts))
        deltas = [(b - a).days for a, b in pairwise(unique_starts) if (b - a).days > 0]
        expected = median(deltas) if deltas else None
        gap_days = []
        irregular = False
        if expected and expected > 0:
            for a, b in pairwise(unique_starts):
                delta = (b - a).days
                if delta >= expected * 2:
                    gap_days.append({"from": a.isoformat(), "to": b.isoformat(), "days": delta})
                if delta != expected:
                    irregular = True
        if gap_days:
            issues.append({"issue_id": f"group:{key}:temporal_gap", "kind": "temporal_gap", "severity": "medium", "group": key, "gaps": gap_days, "action": "Verify whether missing reporting periods are expected and document the reason."})
        if irregular and len(unique_starts) >= 4:
            issues.append({"issue_id": f"group:{key}:irregular_sampling", "kind": "irregular_sampling", "severity": "medium", "group": key, "sampling_intervals_days": deltas, "action": "Confirm sampling/reporting cadence before comparing trends."})
        for left_idx, left in enumerate(ordered):
            left_period = left[2]
            for right in ordered[left_idx + 1:]:
                right_period = right[2]
                if right_period[0] > left_period[1]:
                    break
                if right[1].get("record_id") != left[1].get("record_id"):
                    issues.append({"issue_id": f"group:{key}:overlap:{left[0]}:{right[0]}", "kind": "overlapping_reporting_period", "severity": "high", "group": key, "record_ids": [_text(left[1].get("record_id")), _text(right[1].get("record_id"))], "periods": [list(map(str, left_period)), list(map(str, right_period))], "action": "Resolve overlapping reporting windows or explicitly document that the records are non-additive."})
        temporal_stats.append({"group": key, "record_count": len(entries), "distinct_start_dates": len(unique_starts), "sampling_intervals_days": deltas, "median_interval_days": expected, "gap_count": len(gap_days), "irregular_sampling": irregular})

    metric_units: dict[tuple[str, str], set[str]] = defaultdict(set)
    metric_scopes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in records:
        plant, metric, unit, scope = _key(row)
        if plant and metric:
            metric_units[(plant, metric)].add(unit)
            metric_scopes[(plant, metric)].add(scope)
    for (plant, metric), units in sorted(metric_units.items()):
        units.discard("")
        if len(units) > 1:
            issues.append({"issue_id": f"metric:{plant}:{metric}:unit_mismatch", "kind": "unit_mismatch", "severity": "high", "plant": plant, "metric": metric, "units": sorted(units), "action": "Do not combine records until the source-defined units are reconciled."})
    for (plant, metric), scopes in sorted(metric_scopes.items()):
        scopes.discard("")
        if len(scopes) > 1:
            issues.append({"issue_id": f"metric:{plant}:{metric}:scope_mismatch", "kind": "scope_mismatch", "severity": "high", "plant": plant, "metric": metric, "scopes": sorted(scopes), "action": "Keep scopes separate unless an authorised mapping explicitly permits comparison."})

    total = len(records)
    coverage_components = {
        "record_identity": sum(1 for r in records if _text(r.get("record_id"))) / total if total else 0,
        "source_provenance": source_present / total if total else 0,
        "valid_period": valid_periods / total if total else 0,
        "finite_numeric_value": valid_values / total if total else 0,
        "verified_status": verified / total if total else 0,
    }
    evidence_coverage_score = round(sum(coverage_components.values()) / len(coverage_components) * 100, 2) if total else 0.0
    issue_penalty = min(40.0, sum({"high": 8.0, "medium": 3.0, "review": 1.0}.get(i["severity"], 2.0) for i in issues))
    data_quality_score = round(max(0.0, min(100.0, evidence_coverage_score - issue_penalty)), 2)
    severity_counts = Counter(issue["severity"] for issue in issues)
    actionable = sorted(issues, key=lambda x: ({"high": 0, "medium": 1, "review": 2}.get(x["severity"], 3), x["issue_id"]))

    canonical_input = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    input_fingerprint = sha256(canonical_input.encode("utf-8")).hexdigest()
    issue_fingerprint = sha256(json.dumps(actionable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()

    return {
        "engine": ENGINE_ID,
        "audit": {
            "input_sha256": input_fingerprint,
            "issues_sha256": issue_fingerprint,
            "fingerprint_algorithm": "SHA-256",
            "canonicalization": "UTF-8 JSON, sorted object keys, compact separators",
            "reproducible": True,
        },
        "mode": "governance_review_only",
        "input_record_count": total,
        "issue_count": len(issues),
        "severity_counts": dict(sorted(severity_counts.items())),
        "data_quality_score": data_quality_score,
        "evidence_coverage_score": evidence_coverage_score,
        "coverage_components": {k: round(v * 100, 2) for k, v in coverage_components.items()},
        "missing_field_counts": dict(sorted(field_missing.items())),
        "temporal_groups": temporal_stats,
        "issues": actionable,
        "limitations": ["Scores are governance heuristics for evidence quality, not physical health or safety scores.", "Unit and scope mismatches are flagged rather than automatically converted or reconciled.", "Temporal gaps and overlaps are inferred from supplied reporting periods only."],
        "safety_notice": "Resolve material evidence-quality issues and verify source documents before using analytics for engineering review.",
    }

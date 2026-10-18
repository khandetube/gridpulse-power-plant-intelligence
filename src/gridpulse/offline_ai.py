"""Deterministic, network-free engineering analytics for offline decision support.

This module deliberately makes no remote API calls and uses no external model weights.
It is a transparent statistical assistant, not a trained language model or a safety system.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from math import isfinite
from statistics import median
from typing import Any

ENGINE_ID = "gridpulse-offline-analytics-v1"
LIMITATIONS = [
    "Runs locally without network access, remote APIs, or model downloads.",
    "Statistical flags are review prompts, not alarms, diagnoses, or failure predictions.",
    "No plant-specific thresholds are assumed; all records must retain source and scope.",
    "No control commands, switching instructions, or return-to-service decisions are produced.",
]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _mad(values: list[float]) -> float:
    center = median(values)
    return median([abs(value - center) for value in values])


def _linear_slope(points: list[tuple[date, float]]) -> float | None:
    if len(points) < 2:
        return None
    origin = min(point[0] for point in points)
    xs = [(day - origin).days for day, _ in points]
    ys = [value for _, value in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


def _linear_r_squared(points: list[tuple[date, float]], slope: float | None) -> float | None:
    """Return descriptive R-squared for a dated linear fit, not a forecast-confidence score."""
    if slope is None or len(points) < 3:
        return None
    origin = min(point[0] for point in points)
    xs = [(day - origin).days for day, _ in points]
    ys = [value for _, value in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    intercept = y_mean - slope * x_mean
    total = sum((value - y_mean) ** 2 for value in ys)
    if total == 0:
        return 1.0
    residual = sum((value - (intercept + slope * x)) ** 2 for x, value in zip(xs, ys))
    return max(0.0, min(1.0, 1.0 - residual / total))


def analyze_offline(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return reproducible group summaries, robust outlier candidates, and trend estimates."""
    if not records:
        raise ValueError("Provide at least one observation record.")
    if len(records) > 5000:
        raise ValueError("A single offline analysis is limited to 5000 records.")

    groups: dict[tuple[str, str, str, str], list[tuple[date, float, dict[str, Any]]]] = defaultdict(list)
    invalid: list[dict[str, str]] = []
    seen: set[str] = set()

    for index, row in enumerate(records):
        record_id = str(row.get("record_id", "")).strip()
        if not record_id:
            invalid.append({"index": str(index), "reason": "missing_record_id"})
            continue
        if record_id in seen:
            invalid.append({"record_id": record_id, "reason": "duplicate_record_id"})
            continue
        seen.add(record_id)
        value = _number(row.get("value"))
        try:
            start = date.fromisoformat(str(row.get("period_start", "")))
            end = date.fromisoformat(str(row.get("period_end", "")))
        except ValueError:
            invalid.append({"record_id": record_id, "reason": "invalid_period_date"})
            continue
        if value is None:
            invalid.append({"record_id": record_id, "reason": "value_not_finite_number"})
            continue
        if end < start:
            invalid.append({"record_id": record_id, "reason": "period_end_before_start"})
            continue
        required = ("plant", "metric", "unit", "scope", "source_id", "verification_status")
        missing = [field for field in required if not str(row.get(field, "")).strip()]
        if missing:
            invalid.append({"record_id": record_id, "reason": "missing_" + ",".join(missing)})
            continue
        key = (
            str(row["plant"]).strip(),
            str(row["metric"]).strip(),
            str(row["unit"]).strip(),
            str(row["scope"]).strip(),
        )
        groups[key].append((start, value, row))

    summaries: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for (plant, metric, unit, scope), points in sorted(groups.items()):
        values = [point[1] for point in points]
        center = median(values)
        mad = _mad(values)
        # Modified z-score is robust against isolated extreme values. A zero MAD
        # means the robust score is undefined; flag only values distinct from a
        # constant baseline, and label that fallback explicitly.
        group_anomalies = []
        for day, value, row in points:
            if len(values) < 4:
                continue
            if mad > 0:
                score = 0.67448975 * (value - center) / mad
                is_candidate = abs(score) >= 3.5
                method = "modified_z_score_mad"
            else:
                score = None
                is_candidate = value != center
                method = "constant_median_deviation_fallback"
            if is_candidate:
                item = {
                    "record_id": str(row["record_id"]),
                    "plant": plant,
                    "metric": metric,
                    "unit": unit,
                    "scope": scope,
                    "period_start": day.isoformat(),
                    "value": value,
                    "group_median": center,
                    "robust_score": round(score, 4) if score is not None else None,
                    "method": method,
                    "source_id": str(row["source_id"]),
                    "verification_status": str(row["verification_status"]),
                    "review_required": True,
                }
                group_anomalies.append(item)
                candidates.append(item)
        dated = sorted(points, key=lambda point: (point[0], str(point[2]["record_id"])))
        trend_points = [(day, value) for day, value, _ in dated]
        slope = _linear_slope(trend_points)
        distinct_dates = sorted({day for day, _, _ in dated})
        span_days = (distinct_dates[-1] - distinct_dates[0]).days
        trend_r_squared = _linear_r_squared(trend_points, slope)
        trend_evidence_level = (
            "insufficient" if len(distinct_dates) < 3
            else "preliminary" if len(distinct_dates) < 5 or span_days < 7
            else "descriptive_multi_point"
        )
        first_value = dated[0][1]
        latest_value = dated[-1][1]
        change_pct = (
            round((latest_value - first_value) / abs(first_value) * 100, 4)
            if first_value != 0
            else None
        )
        rolling_window = [value for _, value, _ in dated[-3:]]
        direction = (
            "increasing" if slope is not None and slope > 0
            else "decreasing" if slope is not None and slope < 0
            else "flat_or_unresolved" if slope is not None
            else "insufficient_distinct_dates"
        )
        summaries.append({
            "plant": plant,
            "metric": metric,
            "unit": unit,
            "scope": scope,
            "count": len(points),
            "distinct_date_count": len(distinct_dates),
            "observation_span_days": span_days,
            "trend_r_squared": round(trend_r_squared, 6) if trend_r_squared is not None else None,
            "trend_evidence_level": trend_evidence_level,
            "minimum": min(values),
            "maximum": max(values),
            "mean": round(sum(values) / len(values), 6),
            "median": center,
            "mad": mad,
            "first_value": first_value,
            "first_period_start": dated[0][0].isoformat(),
            "latest_value": latest_value,
            "latest_period_start": dated[-1][0].isoformat(),
            "change_from_first_pct": change_pct,
            "latest_rolling_mean_3": round(sum(rolling_window) / len(rolling_window), 6),
            "trend_per_day": round(slope, 8) if slope is not None else None,
            "trend_status": "estimate_only" if slope is not None else "insufficient_distinct_dates",
            "trend_direction": direction,
            "anomaly_candidate_count": len(group_anomalies),
            "source_ids": sorted({str(point[2]["source_id"]) for point in points}),
            "verification_statuses": sorted({str(point[2]["verification_status"]) for point in points}),
        })

    verification_counts: dict[str, int] = defaultdict(int)
    source_ids: set[str] = set()
    for row in records:
        status = str(row.get("verification_status", "")).strip() or "missing"
        verification_counts[status] += 1
        source_id = str(row.get("source_id", "")).strip()
        if source_id:
            source_ids.add(source_id)
    quality = {
        "input_records": len(records),
        "analyzed_records": sum(item["count"] for item in summaries),
        "invalid_or_skipped_records": len(invalid),
        "analysis_coverage_pct": round(sum(item["count"] for item in summaries) / len(records) * 100, 2),
        "verification_status_counts": dict(sorted(verification_counts.items())),
        "distinct_source_count": len(source_ids),
        "records_missing_source_id": sum(1 for row in records if not str(row.get("source_id", "")).strip()),
        "invalid_reason_counts": {
            reason: sum(1 for item in invalid if item.get("reason") == reason)
            for reason in sorted({item.get("reason", "unknown") for item in invalid})
        },
    }
    insights: list[dict[str, Any]] = []
    if invalid:
        insights.append({
            "id": "data_quality_review",
            "severity": "high" if len(invalid) / len(records) >= 0.1 else "medium",
            "title": "Review skipped or invalid records",
            "evidence": f"{len(invalid)} of {len(records)} input records were not analyzed.",
            "recommended_review": "Correct the reported validation issues and rerun analysis before relying on trends.",
            "evidence_record_ids": [item.get("record_id", item.get("index", "")) for item in invalid[:20]],
        })
    if any(row.get("verification_status") != "verified" for row in records):
        insights.append({
            "id": "source_verification_review",
            "severity": "medium",
            "title": "Confirm source and verification status",
            "evidence": "At least one input record is not marked verified.",
            "recommended_review": "Check each record against its original authorised source and record the reviewer and verification status.",
            "evidence_record_ids": [str(row.get("record_id", "")) for row in records if row.get("verification_status") != "verified"][:20],
        })
    for item in candidates[:50]:
        insights.append({
            "id": "outlier:" + item["record_id"],
            "severity": "review",
            "title": f"Potential statistical outlier: {item['metric']}",
            "evidence": f"Record {item['record_id']} value {item['value']} {item['unit']}; group median {item['group_median']}.",
            "recommended_review": "Verify units, time window, operating context, data quality and approved engineering limits; do not treat this flag as a confirmed fault.",
            "evidence_record_ids": [item["record_id"]],
        })
    for item in summaries:
        if item["count"] >= 3 and item["trend_direction"] in ("increasing", "decreasing"):
            insights.append({
                "id": f"trend:{item['plant']}:{item['metric']}:{item['scope']}",
                "severity": "review",
                "title": f"Observed {item['trend_direction']} trend: {item['metric']}",
                "evidence": f"{item['count']} records; estimated slope {item['trend_per_day']} {item['unit']}/day; first-to-latest change {item['change_from_first_pct']}%.",
                "recommended_review": "Check data comparability, operating regime and approved performance baselines before drawing an engineering conclusion.",
                "trend_evidence_level": item["trend_evidence_level"],
                "distinct_date_count": item["distinct_date_count"],
                "observation_span_days": item["observation_span_days"],
                "trend_r_squared": item["trend_r_squared"],
                "evidence_record_ids": [],
            })

    return {
        "engine": ENGINE_ID,
        "mode": "offline_deterministic_statistics",
        "network_access": False,
        "model_weights_required": False,
        "input_count": len(records),
        "analyzed_count": sum(item["count"] for item in summaries),
        "group_count": len(summaries),
        "invalid_or_skipped_count": len(invalid),
        "groups": summaries,
        "data_quality": quality,
        "insights": insights[:100],
        "anomaly_candidates": candidates,
        "invalid_or_skipped_records": invalid,
        "limitations": LIMITATIONS,
        "safety_notice": "Review findings against original records and approved engineering limits. Never use this output alone to operate equipment.",
    }


def main() -> int:
    """Run the analytics engine directly against a local JSON file."""
    parser = argparse.ArgumentParser(description="Run GridPulse offline analytics on a local JSON file.")
    parser.add_argument("input", help="UTF-8 JSON file containing an object with a 'records' array")
    parser.add_argument("--output", help="Optional output JSON path; defaults to stdout")
    args = parser.parse_args()
    try:
        with open(args.input, encoding="utf-8") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise TypeError("Input JSON must be an object containing a 'records' array.")
        result = analyze_offline(payload["records"])
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as stream:
                stream.write(rendered + chr(10))
        else:
            sys.stdout.write(rendered + chr(10))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"offline analysis failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

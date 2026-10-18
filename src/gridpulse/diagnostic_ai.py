"""Evidence-graded diagnostic features built from local observations only.

These are screening heuristics for human review, not alarms, causal models, or
validated failure predictions. No equipment-specific limits are inferred.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import isfinite, sqrt
from statistics import median
from typing import Any

ENGINE_ID = "gridpulse-evidence-diagnostics-v1"
MAX_RECORDS = 5000


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _mad(values: list[float]) -> float:
    centre = median(values)
    return median([abs(value - centre) for value in values])


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    dx, dy = [x - mx for x in xs], [y - my for y in ys]
    denominator = sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if denominator == 0:
        return None
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(dx, dy)) / denominator))


def diagnose_observations(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return robust shift, sustained-regime, cadence-gap and association candidates."""
    if not isinstance(records, list) or not records:
        raise ValueError("Provide at least one observation record.")
    if len(records) > MAX_RECORDS:
        raise ValueError(f"A single diagnostic run is limited to {MAX_RECORDS} records.")

    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    skipped: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, row in enumerate(records):
        if not isinstance(row, dict):
            skipped.append({"index": str(index), "reason": "record_not_object"})
            continue
        record_id = str(row.get("record_id", "")).strip()
        if not record_id:
            skipped.append({"index": str(index), "reason": "missing_record_id"})
            continue
        if record_id in seen:
            skipped.append({"record_id": record_id, "reason": "duplicate_record_id"})
            continue
        seen.add(record_id)
        value = _finite(row.get("value"))
        try:
            start = date.fromisoformat(str(row.get("period_start", "")))
            end = date.fromisoformat(str(row.get("period_end", "")))
        except (TypeError, ValueError):
            skipped.append({"record_id": record_id, "reason": "invalid_period_date"})
            continue
        if value is None:
            skipped.append({"record_id": record_id, "reason": "value_not_finite_number"})
            continue
        if end < start:
            skipped.append({"record_id": record_id, "reason": "period_end_before_start"})
            continue
        fields = ("plant", "metric", "unit", "scope", "source_id", "verification_status")
        if any(not str(row.get(field, "")).strip() for field in fields):
            skipped.append({"record_id": record_id, "reason": "missing_required_metadata"})
            continue
        key = (str(row["plant"]).strip(), str(row["metric"]).strip(),
               str(row["unit"]).strip(), str(row["scope"]).strip())
        groups[key].append({
            "record_id": record_id, "date": start, "value": value,
            "source_id": str(row["source_id"]).strip(),
            "verification_status": str(row["verification_status"]).strip(),
        })

    findings: list[dict[str, Any]] = []
    series_by_key: dict[tuple[str, str, str], dict[date, float]] = {}
    series_meta: dict[tuple[str, str, str], dict[str, str]] = {}
    for (plant, metric, unit, scope), points in sorted(groups.items()):
        points.sort(key=lambda p: (p["date"], p["record_id"]))
        dates = sorted({p["date"] for p in points})
        # Multiple readings on one day are collapsed by median for time-series screening.
        daily: dict[date, float] = {}
        for day in dates:
            daily[day] = median([p["value"] for p in points if p["date"] == day])
        identity = (plant, metric, scope)
        series_by_key[identity] = daily
        series_meta[identity] = {"unit": unit}
        values = [daily[day] for day in dates]

        # Compare the newest value to a baseline of preceding distinct days.
        if len(values) >= 6:
            baseline = values[:-1]
            centre = median(baseline)
            spread = _mad(baseline)
            latest = values[-1]
            score = (0.67448975 * (latest - centre) / spread) if spread > 0 else None
            shifted = abs(score) >= 3.5 if score is not None else (spread == 0 and latest != centre)
            if shifted:
                last_point = points[-1]
                verified = last_point["verification_status"] == "verified"
                findings.append({
                    "id": f"recent-shift:{plant}:{metric}:{scope}:{dates[-1].isoformat()}",
                    "kind": "recent_baseline_shift_candidate",
                    "severity": "review",
                    "plant": plant, "metric": metric, "unit": unit, "scope": scope,
                    "period": dates[-1].isoformat(), "observed_value": latest,
                    "baseline_median": centre, "baseline_mad": spread,
                    "modified_z_score": round(score, 4) if score is not None else None,
                    "baseline_distinct_days": len(baseline),
                    "source_id": last_point["source_id"],
                    "verification_status": last_point["verification_status"],
                    "evidence_grade": "screening_only" if verified else "low_source_confidence",
                    "evidence_record_ids": [p["record_id"] for p in points if p["date"] == dates[-1]],
                    "explanation": "The latest daily median differs substantially from the preceding baseline; check units, operating regime, source quality and approved limits.",
                    "recommended_review": "Independently verify the original reading and context; do not treat this statistical flag as an alarm or fault diagnosis.",
                })

        # Compare halves only when there are enough distinct dates to reduce noise.
        if len(values) >= 8:
            midpoint = len(values) // 2
            earlier, later = values[:midpoint], values[midpoint:]
            early_med, late_med = median(earlier), median(later)
            combined_mad = _mad(values)
            shift = late_med - early_med
            material = abs(shift) > 0 if combined_mad == 0 else abs(shift) >= 2.5 * combined_mad
            if material:
                findings.append({
                    "id": f"regime-shift:{plant}:{metric}:{scope}",
                    "kind": "sustained_level_shift_candidate",
                    "severity": "review",
                    "plant": plant, "metric": metric, "unit": unit, "scope": scope,
                    "earlier_median": early_med, "later_median": late_med,
                    "absolute_median_shift": shift, "whole_series_mad": combined_mad,
                    "earlier_distinct_days": len(earlier), "later_distinct_days": len(later),
                    "evidence_grade": "exploratory",
                    "evidence_record_ids": [p["record_id"] for p in points],
                    "explanation": "The medians of the two chronological halves differ relative to the series' robust spread.",
                    "recommended_review": "Check maintenance events, load, ambient conditions, instrumentation changes and source comparability before interpreting the shift.",
                })

        # A gap is reported only relative to the series' own cadence.
        if len(dates) >= 5:
            gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
            positive = [gap for gap in gaps if gap > 0]
            if positive:
                typical_gap = median(positive)
                for i, gap in enumerate(gaps, start=1):
                    if gap > max(3 * typical_gap, typical_gap + 7):
                        findings.append({
                            "id": f"cadence-gap:{plant}:{metric}:{scope}:{dates[i].isoformat()}",
                            "kind": "observation_gap",
                            "severity": "data_quality_review",
                            "plant": plant, "metric": metric, "unit": unit, "scope": scope,
                            "gap_start": dates[i - 1].isoformat(), "gap_end": dates[i].isoformat(),
                            "gap_days": gap, "typical_gap_days": typical_gap,
                            "evidence_grade": "descriptive",
                            "evidence_record_ids": [],
                            "explanation": "The interval between observations is unusually long compared with this series' own historical cadence.",
                            "recommended_review": "Confirm whether records are missing or the measurement schedule changed; no missing value is imputed.",
                        })

    # Exploratory Pearson associations across distinct metrics on matched dates.
    identities = sorted(series_by_key)
    associations = 0
    for i, left_key in enumerate(identities):
        for right_key in identities[i + 1:]:
            if left_key[0] != right_key[0] or left_key[2] != right_key[2] or left_key[1] == right_key[1]:
                continue
            left, right = series_by_key[left_key], series_by_key[right_key]
            common = sorted(set(left).intersection(right))
            if len(common) < 6:
                continue
            corr = _pearson([left[d] for d in common], [right[d] for d in common])
            if corr is None or abs(corr) < 0.8:
                continue
            associations += 1
            findings.append({
                "id": f"association:{left_key[0]}:{left_key[1]}:{right_key[1]}:{left_key[2]}",
                "kind": "exploratory_metric_association",
                "severity": "research_review",
                "plant": left_key[0], "scope": left_key[2],
                "metric_a": left_key[1], "unit_a": series_meta[left_key]["unit"],
                "metric_b": right_key[1], "unit_b": series_meta[right_key]["unit"],
                "matched_distinct_days": len(common), "pearson_r": round(corr, 5),
                "evidence_grade": "exploratory_association_not_causation",
                "evidence_record_ids": [],
                "explanation": "The two metrics move together in the matched observations; common trends, load, seasonality or confounders may explain the association.",
                "recommended_review": "Inspect a time plot, operating context, lag effects and confounders. Correlation does not establish causation or a physical relationship.",
            })

    findings.sort(key=lambda item: (item["kind"], item["id"]))
    verified_count = sum(1 for row in records if isinstance(row, dict) and row.get("verification_status") == "verified")
    return {
        "engine": ENGINE_ID,
        "mode": "local_evidence_screening",
        "network_access": False,
        "input_count": len(records),
        "usable_count": sum(len(points) for points in groups.values()),
        "skipped_count": len(skipped),
        "group_count": len(groups),
        "verified_input_count": verified_count,
        "finding_count": len(findings),
        "findings": findings[:200],
        "skipped_records": skipped[:200],
        "methods": [
            "latest daily median versus preceding robust median/MAD baseline (minimum six distinct dates)",
            "chronological half-series median shift relative to robust spread (minimum eight distinct dates)",
            "observation cadence gap relative to the series' own median interval",
            "Pearson association for matched dates (minimum six; exploratory only)",
        ],
        "limitations": [
            "These screening thresholds are generic heuristics, not validated plant-specific operating limits.",
            "No causal inference, trained failure prediction, alarm, trip, dispatch or control output is produced.",
            "Missing values are not imputed; repeated observations on a day are collapsed to their median for screening.",
            "Results depend on comparable units, scope, operating regime, timestamps and source integrity.",
        ],
        "safety_notice": "Use findings to prioritize human review only. Verify original records and approved engineering procedures before any operational decision.",
    }

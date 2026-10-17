"""Deterministic descriptive analytics for source-labelled observations.

No predictions, control actions, or plant-system integrations are performed here.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite
from statistics import mean, median
from typing import Any


def _quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile using the (n - 1) * q convention."""
    if not sorted_values:
        raise ValueError("quantile requires at least one value")
    position = (len(sorted_values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def analyze_observations(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize observations by metric and unit, retaining provenance labels.

    A record is flagged only when its metric/unit group has >=4 values and its
    value is outside Tukey's 1.5*IQR fences. A zero IQR produces no flags because
    this simple rule cannot distinguish meaningful deviations in that case.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    ids: set[str] = set()
    for record in records:
        record_id = str(record["record_id"])
        if record_id in ids:
            raise ValueError(f"duplicate record_id: {record_id}")
        ids.add(record_id)
        value = float(record["value"])
        if not isfinite(value):
            raise ValueError(f"non-finite value for record_id: {record_id}")
        groups[(str(record["metric"]), str(record["unit"]))].append(record)

    summaries: list[dict[str, Any]] = []
    flagged_ids: set[str] = set()
    for (metric, unit), group in sorted(groups.items()):
        values = sorted(float(row["value"]) for row in group)
        q1 = _quantile(values, 0.25)
        q3 = _quantile(values, 0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        group_flags: list[str] = []
        if len(values) >= 4 and iqr > 0:
            for row in group:
                value = float(row["value"])
                if value < lower or value > upper:
                    record_id = str(row["record_id"])
                    flagged_ids.add(record_id)
                    group_flags.append(record_id)
        summaries.append(
            {
                "metric": metric,
                "unit": unit,
                "count": len(values),
                "mean": mean(values),
                "median": median(values),
                "minimum": values[0],
                "maximum": values[-1],
                "range": values[-1] - values[0],
                "q1": q1,
                "q3": q3,
                "iqr": iqr,
                "iqr_lower_fence": lower,
                "iqr_upper_fence": upper,
                "flagged_record_ids": sorted(group_flags),
                "verification_status_counts": {
                    status: sum(
                        1 for row in group
                        if row.get("verification_status") == status
                    )
                    for status in ("unverified", "reviewed", "verified")
                },
            }
        )

    return {
        "observation_count": len(records),
        "group_count": len(groups),
        "flagged_record_ids": sorted(flagged_ids),
        "groups": summaries,
        "method": "Descriptive statistics; Tukey 1.5*IQR fences per metric/unit group.",
        "limitations": [
            "Statistical flags are review candidates, not alarms, diagnoses, or predictions.",
            "No source truth is independently verified by this endpoint.",
            "Comparisons are grouped by metric and unit; different scopes may still be incomparable.",
            "A group needs at least four values and a non-zero IQR before flags are emitted.",
        ],
    }

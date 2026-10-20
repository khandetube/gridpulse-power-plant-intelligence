"""Optional multivariate-ready anomaly screening using established data/ML libraries.

This endpoint produces review candidates only; it is not a plant alarm or diagnosis.
"""
# isort: skip_file
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import median_abs_deviation
from sklearn.ensemble import IsolationForest


MINIMUM_RECORDS = 8


def detect_anomalies(
    records: list[dict[str, object]], *, contamination: float = 0.05
) -> dict[str, object]:
    """Sort one comparable metric series and flag IsolationForest outliers."""
    if not 0.01 <= contamination <= 0.20:
        raise ValueError("contamination must be between 0.01 and 0.20")
    if len(records) < MINIMUM_RECORDS:
        raise ValueError(f"at least {MINIMUM_RECORDS} observations are required")

    frame = pd.DataFrame.from_records(records)
    required = {"record_id", "metric", "unit", "value", "period_start"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    if frame["record_id"].duplicated().any():
        raise ValueError("record_id values must be unique")
    if frame[["metric", "unit"]].drop_duplicates().shape[0] != 1:
        raise ValueError("all observations must share the same metric and unit")

    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    values = frame["value"].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("all observation values must be finite")

    frame["period_start"] = pd.to_datetime(frame["period_start"], errors="coerce", utc=True)
    if frame["period_start"].isna().any():
        raise ValueError("period_start must contain valid dates")
    frame = frame.sort_values(["period_start", "record_id"], kind="stable").reset_index(drop=True)

    median = float(np.median(values))
    mad = float(median_abs_deviation(values, scale=1.0, nan_policy="raise"))
    robust_scores = (0.6744897501960817 * (values - median) / mad if mad > 0 else np.zeros_like(values))
    statistical_candidates: list[dict[str, object]] = []
    for index, score in enumerate(robust_scores):
        if abs(float(score)) >= 3.5:
            row = frame.iloc[index]
            statistical_candidates.append({
                "record_id": str(row["record_id"]),
                "period_start": row["period_start"].isoformat(),
                "value": float(row["value"]),
                "robust_z_score": round(float(score), 6),
                "source_id": str(row.get("source_id", "")),
                "verification_status": str(row.get("verification_status", "unverified")),
            })
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
        max_samples=min(256, len(frame)),
        n_jobs=1,
    )
    matrix = frame[["value"]].to_numpy(dtype=float)
    predictions = model.fit_predict(matrix)
    scores = model.decision_function(matrix)

    flagged: list[dict[str, object]] = []
    for index, prediction in enumerate(predictions):
        if prediction == -1:
            row = frame.iloc[index]
            flagged.append(
                {
                    "record_id": str(row["record_id"]),
                    "period_start": row["period_start"].isoformat(),
                    "value": float(row["value"]),
                    "anomaly_score": round(float(scores[index]), 8),
                    "source_id": str(row.get("source_id", "")),
                    "verification_status": str(row.get("verification_status", "unverified")),
                }
            )

    return {
        "observation_count": len(frame),
        "metric": str(frame.iloc[0]["metric"]),
        "unit": str(frame.iloc[0]["unit"]),
        "algorithm": "scikit-learn IsolationForest",
        "parameters": {
            "contamination": contamination,
            "n_estimators": 200,
            "random_state": 42,
            "minimum_records": MINIMUM_RECORDS,
        },
        "flagged_count": len(flagged),
        "flagged_observations": flagged,
        "robust_statistics": {
            "method": "median absolute deviation (MAD)",
            "median": median,
            "median_absolute_deviation": mad,
            "threshold_absolute_robust_z_score": 3.5,
            "candidate_count": len(statistical_candidates),
            "candidates": statistical_candidates,
            "note": "When MAD is zero, robust scores are set to zero; no MAD candidates are emitted.",
        },
        "limitations": [
            "Flags are review candidates, not alarms, diagnoses, or predictions.",
            "IsolationForest is unsupervised and may flag valid operating changes.",
            "Both statistical and ML screening evaluate values only; they do not model seasonality, load, ambient conditions, or equipment context.",
            "MAD and IsolationForest use different assumptions and should be reviewed independently. The algorithms do not verify source truth and do not connect to plant or dispatch systems.",
            "Choose contamination based on domain review; it is not an estimated failure probability.",
        ],
    }

"""Optional multivariate-ready anomaly screening using established data/ML libraries.

This endpoint produces review candidates only; it is not a plant alarm or diagnosis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from typing import Any


MINIMUM_RECORDS = 8


def detect_anomalies(
    records: list[dict[str, Any]], *, contamination: float = 0.05
) -> dict[str, Any]:
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

    flagged: list[dict[str, Any]] = []
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
        "limitations": [
            "Flags are review candidates, not alarms, diagnoses, or predictions.",
            "IsolationForest is unsupervised and may flag valid operating changes.",
            "This version evaluates values only; it does not model seasonality, load, ambient conditions, or equipment context.",
            "The algorithm does not verify source truth and does not connect to plant or dispatch systems.",
            "Choose contamination based on domain review; it is not an estimated failure probability.",
        ],
    }

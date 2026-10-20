"""Seasonal decomposition for source-labelled power-plant time series."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import median_abs_deviation
from statsmodels.tsa.seasonal import STL

MINIMUM_PERIOD = 2


def decompose_time_series(
    records: list[dict[str, object]], *, period: int = 7
) -> dict[str, object]:
    """Decompose one comparable series into trend, seasonality, and residuals.

    The period is measured in observations, not calendar days. The caller must
    choose it to match the cadence and plausible operating cycle of the data.
    """
    if not MINIMUM_PERIOD <= period <= 365:
        raise ValueError("period must be between 2 and 365 observations")
    if len(records) < 2 * period:
        raise ValueError(f"at least {2 * period} observations are required for period={period}")

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

    series = pd.Series(frame["value"].to_numpy(dtype=float))
    result = STL(series, period=period, robust=True).fit()
    trend = np.asarray(result.trend, dtype=float)
    seasonal = np.asarray(result.seasonal, dtype=float)
    residual = np.asarray(result.resid, dtype=float)
    residual_center = float(np.median(residual))
    residual_mad = float(median_abs_deviation(residual, scale=1.0, nan_policy="raise"))
    robust_scores = (
        0.6744897501960817 * (residual - residual_center) / residual_mad
        if residual_mad > 0
        else np.zeros_like(residual)
    )

    rows: list[dict[str, object]] = []
    for index, row in frame.iterrows():
        rows.append({
            "record_id": str(row["record_id"]),
            "period_start": row["period_start"].isoformat(),
            "value": float(row["value"]),
            "trend": round(float(trend[index]), 8),
            "seasonal": round(float(seasonal[index]), 8),
            "residual": round(float(residual[index]), 8),
            "residual_robust_z_score": round(float(robust_scores[index]), 6),
            "residual_candidate": bool(abs(float(robust_scores[index])) >= 3.5),
            "source_id": str(row.get("source_id", "")),
            "verification_status": str(row.get("verification_status", "unverified")),
        })

    residual_variance = float(np.var(residual))
    combined_variance = float(np.var(seasonal + residual))
    trend_variance = float(np.var(trend))
    trend_residual_variance = float(np.var(trend + residual))
    seasonal_strength = (
        max(0.0, min(1.0, 1.0 - residual_variance / combined_variance))
        if combined_variance > 0
        else 0.0
    )
    trend_strength = (
        max(0.0, min(1.0, 1.0 - residual_variance / trend_residual_variance))
        if trend_residual_variance > 0
        else 0.0
    )

    return {
        "observation_count": len(frame),
        "metric": str(frame.iloc[0]["metric"]),
        "unit": str(frame.iloc[0]["unit"]),
        "method": "statsmodels STL with robust fitting",
        "period_observations": period,
        "seasonal_strength": round(seasonal_strength, 6),
        "trend_strength": round(trend_strength, 6),
        "residual_candidate_count": sum(item["residual_candidate"] for item in rows),
        "observations": rows,
        "limitations": [
            "Period is measured in observations, not calendar days; irregular sampling can make decomposition misleading.",
            "At least two complete cycles are required by this API, but longer histories are preferable.",
            "Residual candidates are statistical review prompts, not alarms, diagnoses, or failure probabilities.",
            "The method does not validate source truth or model plant physics, load, ambient conditions, or equipment state.",
        ],
    }

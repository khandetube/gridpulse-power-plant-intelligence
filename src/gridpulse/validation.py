"""Validation helpers for source-aware generation observations."""
from __future__ import annotations
import csv
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = {"record_id", "plant", "metric", "value", "unit", "period_start", "period_end", "scope", "source_id", "verification_status"}
ALLOWED_STATUS = {"unverified", "reviewed", "verified"}
ALLOWED_SCOPE = {"unit", "plant", "multiple_plants", "regional", "national"}

class DatasetValidationError(ValueError):
    """Raised when an input dataset violates the documented schema."""

def validate_observation_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate rows without inferring missing values or silently converting units."""
    if not rows:
        raise DatasetValidationError("Dataset contains no observation rows")
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for line_number, row in enumerate(rows, start=2):
        missing = REQUIRED_COLUMNS - set(row)
        if missing:
            raise DatasetValidationError(f"Row {line_number}: missing columns: {', '.join(sorted(missing))}")
        record_id = str(row["record_id"]).strip()
        if not record_id:
            raise DatasetValidationError(f"Row {line_number}: record_id is empty")
        if record_id in seen_ids:
            raise DatasetValidationError(f"Row {line_number}: duplicate record_id {record_id}")
        seen_ids.add(record_id)
        for field in ("plant", "metric", "unit", "scope", "source_id", "verification_status"):
            if not str(row[field]).strip():
                raise DatasetValidationError(f"Row {line_number}: {field} is empty")
        try:
            value = float(row["value"])
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(f"Row {line_number}: value must be numeric") from exc
        if value != value or value in (float("inf"), float("-inf")):
            raise DatasetValidationError(f"Row {line_number}: value must be finite")
        try:
            start = date.fromisoformat(str(row["period_start"]))
            end = date.fromisoformat(str(row["period_end"]))
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(f"Row {line_number}: dates must use YYYY-MM-DD format") from exc
        if end < start:
            raise DatasetValidationError(f"Row {line_number}: period_end precedes period_start")
        status = str(row["verification_status"]).strip()
        if status not in ALLOWED_STATUS:
            raise DatasetValidationError(f"Row {line_number}: invalid verification_status {status}")
        scope = str(row["scope"]).strip()
        if scope not in ALLOWED_SCOPE:
            raise DatasetValidationError(f"Row {line_number}: invalid scope {scope}")
        item = {key: str(value_).strip() for key, value_ in row.items()}
        item.update(record_id=record_id, value=value, period_start=start.isoformat(), period_end=end.isoformat())
        normalized.append(item)
    return normalized

def validate_observations_csv(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate a UTF-8 CSV file with the observation schema."""
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise DatasetValidationError("CSV header row is missing")
            missing = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise DatasetValidationError(f"CSV header missing columns: {', '.join(sorted(missing))}")
            rows = list(reader)
    except OSError as exc:
        raise DatasetValidationError(f"Cannot read CSV file: {exc}") from exc
    except csv.Error as exc:
        raise DatasetValidationError(f"Malformed CSV: {exc}") from exc
    return validate_observation_rows(rows)

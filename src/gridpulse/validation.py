"""Validation helpers for source-aware power-plant datasets."""
from __future__ import annotations

import csv
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

REQUIRED_COLUMNS = {"record_id", "plant", "metric", "value", "unit", "period_start", "period_end", "scope", "source_id", "verification_status"}
MAINTENANCE_REQUIRED_COLUMNS = {"event_id", "plant", "equipment", "event_type", "start_time", "end_time", "timezone", "source_id", "verification_status", "notes"}
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
        if not math.isfinite(value):
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


def validate_maintenance_event_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate maintenance event metadata and timezone-aware ISO timestamps.

    This checks structure and chronology only; it does not confirm the event happened.
    """
    if not rows:
        raise DatasetValidationError("Dataset contains no maintenance event rows")
    seen_ids: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for line_number, row in enumerate(rows, start=2):
        missing = MAINTENANCE_REQUIRED_COLUMNS - set(row)
        if missing:
            raise DatasetValidationError(
                f"Row {line_number}: missing columns: {', '.join(sorted(missing))}"
            )
        event_id = str(row["event_id"]).strip()
        if not event_id:
            raise DatasetValidationError(f"Row {line_number}: event_id is empty")
        if event_id in seen_ids:
            raise DatasetValidationError(f"Row {line_number}: duplicate event_id {event_id}")
        seen_ids.add(event_id)
        for field in ("plant", "equipment", "event_type", "timezone", "source_id", "verification_status"):
            if not str(row[field]).strip():
                raise DatasetValidationError(f"Row {line_number}: {field} is empty")
        status = str(row["verification_status"]).strip()
        if status not in ALLOWED_STATUS:
            raise DatasetValidationError(f"Row {line_number}: invalid verification_status {status}")
        try:
            start = datetime.fromisoformat(str(row["start_time"]).strip())
            end = datetime.fromisoformat(str(row["end_time"]).strip())
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(
                f"Row {line_number}: timestamps must be ISO 8601 with a timezone offset"
            ) from exc
        if start.utcoffset() is None or end.utcoffset() is None:
            raise DatasetValidationError(
                f"Row {line_number}: start_time and end_time must include a timezone offset"
            )
        if end < start:
            raise DatasetValidationError(f"Row {line_number}: end_time precedes start_time")
        item = {key: str(value_).strip() for key, value_ in row.items()}
        item["event_id"] = event_id
        item["start_time"] = start.isoformat()
        item["end_time"] = end.isoformat()
        item["duration_hours"] = (end - start).total_seconds() / 3600
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


def validate_maintenance_events_csv(path: str | Path) -> list[dict[str, Any]]:
    """Load and validate a UTF-8 CSV file with the maintenance-event schema."""
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise DatasetValidationError("CSV header row is missing")
            missing = MAINTENANCE_REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise DatasetValidationError(
                    f"CSV header missing columns: {', '.join(sorted(missing))}"
                )
            rows = list(reader)
    except OSError as exc:
        raise DatasetValidationError(f"Cannot read CSV file: {exc}") from exc
    except csv.Error as exc:
        raise DatasetValidationError(f"Malformed CSV: {exc}") from exc
    return validate_maintenance_event_rows(rows)

# Observation data dictionary

The validated observation CSV uses one row per measured or reported fact.

| Column | Required | Meaning | Example |
|---|---|---|---|
| record_id | Yes | Unique stable identifier | OBS-0001 |
| plant | Yes | Plant or approved pseudonym | Shahid Kaveh CCPP |
| metric | Yes | Metric name; do not mix different metrics | net_generation |
| value | Yes | Finite numeric value | 125.4 |
| unit | Yes | Explicit source unit | MWh |
| period_start | Yes | ISO date, inclusive | 2026-01-01 |
| period_end | Yes | ISO date, inclusive | 2026-01-31 |
| scope | Yes | unit, plant, multiple_plants, regional, or national | plant |
| source_id | Yes | ID from the source registry | SRC-001 |
| verification_status | Yes | unverified, reviewed, or verified | unverified |

## Rules

- Never attribute a multi-plant or regional total to one plant.
- Do not infer a missing unit, reporting period, or source.
- Use ISO dates (YYYY-MM-DD); timestamp support should be added explicitly before importing sub-daily readings.
- Keep raw files immutable and validate a copy before processing.
- Unit conversions must be metric-specific, documented, and tested; this validator does not convert units.
- A passing schema check is not proof that the source itself is true. Source verification remains a separate review step.

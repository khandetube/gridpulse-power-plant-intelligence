# Observation and maintenance-event data dictionary

## Observation records

The observation CSV uses one row per measured or reported fact.

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

## Maintenance events

One row represents a reported maintenance or outage event. The schema is for authorized/public source records, not for confidential operational details.

| Column | Required | Meaning |
|---|---|---|
| event_id | Yes | Unique stable event identifier |
| plant | Yes | Plant or approved pseudonym |
| equipment | Yes | Equipment/unit label supported by the source |
| event_type | Yes | Event category as reported; do not infer a failure mode |
| start_time | Yes | ISO 8601 timestamp with UTC offset, e.g. 2026-01-01T08:00:00+03:30 |
| end_time | Yes | ISO 8601 timestamp with UTC offset; must not precede start_time |
| timezone | Yes | IANA timezone label where known, e.g. Asia/Tehran |
| source_id | Yes | ID in the source registry |
| verification_status | Yes | unverified, reviewed, or verified |
| notes | Yes | Short source-grounded context; do not put secrets or sensitive control details here |

The validator computes elapsed duration from the two timestamps. Both timestamps must include explicit offsets; the separate timezone label is retained as source metadata and is not used to reinterpret timestamps. Elapsed duration is not necessarily equivalent to unit downtime unless the source defines the event and outage boundaries accordingly.

## Rules

- Never attribute a multi-plant or regional total to one plant.
- Do not infer a missing unit, reporting period, event time, or source.
- Use ISO dates for observations and timezone-aware ISO 8601 timestamps for events.
- Keep raw files immutable and validate a copy before processing.
- Unit conversions must be metric-specific, documented, and tested; the validator does not convert units.
- Schema validation checks structure and chronology only; it does not verify that the source itself is true.
- Never add credentials, private records, network addresses, control-system configurations, or confidential dispatch data.

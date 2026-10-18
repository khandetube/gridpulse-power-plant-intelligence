# GridPulse AI — Data Quality & Evidence Engine

`gridpulse-data-quality-v1` is a deterministic, governance-only review engine for imported observation records.

## Checks

- duplicate `record_id` values, including conflicting duplicates
- missing required identity fields
- missing source/provenance identifiers
- invalid or reversed reporting periods
- non-finite numeric values
- unit mismatch for the same plant/metric
- scope mismatch for the same plant/metric
- overlapping reporting periods
- material temporal gaps using the observed cadence
- irregular sampling/reporting cadence

## Scores

### Evidence Coverage Score

A transparent percentage based on five supplied-evidence dimensions:

1. record identity
2. source provenance
3. valid reporting period
4. finite numeric value
5. verified status

It is **not** a physical or safety score.

### Data Quality Score

Starts from evidence coverage and applies bounded penalties for detected governance issues. It is intended to prioritize data remediation, not to certify the underlying measurements.

## API

`POST /api/v1/ai/data-quality`

The endpoint accepts the same governed observation schema used by the offline analytics API. Duplicate record IDs are rejected at the API boundary so the review input remains auditable.

## Browser console

GitHub Pages console:

`docs/data-quality-review.html`

The console sends records only to the API URL entered by the operator. GitHub Pages itself does not execute Python.

## Safety / governance boundary

The engine does not infer missing measurements, convert units automatically, diagnose equipment faults, invent engineering limits, connect to SCADA/DCS/EMS/dispatch, or issue control instructions. Material issues must be reconciled against the authoritative source before downstream engineering review.

# Data provenance and verification

## Purpose
This document defines how GridPulse AI records and verifies public information related to the Shahid Kaveh combined-cycle power plant in Qaen and the Khorasan gas power plant management company.

## Source register

| Source | URL | Intended use | Verification status |
|---|---|---|---|
| Khorasan Gas Power Plant Management Company | https://khgpp.ir/ | Primary source for company announcements and official plant information | Official domain identified; individual facts must be linked to a specific page and checked |
| Tasnim News Agency report on fuel supply to Shahid Kaveh | https://www.tasnimnews.ir/fa/news/1404/06/27/3402540/ | Reported plant/fuel context | Secondary source; validate publication details and exact figures before ingestion |
| KhabarFarsi result reporting spring 1405 generation | https://khabarfarsi.com/u/250484980 | Lead for reported aggregate generation, fuel use, and maintenance events | Secondary aggregation; reporting period, original attribution, and scope require verification |
| EIA electricity data | https://www.eia.gov/electricity/data/detail-data.php | Reference for data-model design and general electricity data practices | Not plant-specific evidence for Qaen; never attribute EIA records to this plant without proof |

## Previously identified figures — not yet validated dataset records
The following figures were identified during preliminary research and must not be treated as fully verified until the original article/report is checked and its reporting period and aggregation scope are recorded:

- Reported installed capacity: 630 MW.
- A report described 437,951 MWh generation for a combined scope involving Shahid Kaveh and Qaen gas power plants in spring 1405; this is an aggregate, not automatically the generation of Shahid Kaveh alone.
- Fuel consumption and maintenance statements found in secondary reporting require source-level review before being used in calculations.

These figures are leads for verification, not a substitute for a source-backed data file.

## Required metadata for each record
- source_url
- source_title
- source_publisher
- publication_date (nullable if unknown)
- observation_start and observation_end (nullable if unknown)
- plant_id or aggregation_scope
- metric_name
- value
- unit
- verification_status: unverified, reviewed, or verified
- notes and limitations

## Verification rules
1. Prefer the operator, Ministry of Energy, Tavanir, or other primary sources.
2. Do not infer an exact time interval from a vague article.
3. Do not allocate a combined total to a single plant without an explicit source.
4. Normalize units only after retaining the original value and unit.
5. Keep reported, derived, and synthetic/demo data separate.
6. Do not claim predictive performance until a model is evaluated on appropriate, documented data.
7. Do not attempt unauthorized access to plant, SCADA, or dispatch systems. Request authorized exports from the operator instead.

## Requesting authorized operational exports
A safe starting point is a request for non-sensitive historical CSV/XLSX exports, such as daily generation, fuel consumption, operating hours, maintenance dates, and categorized outage durations. Sensor-level data should only be used if the operator explicitly approves sharing it and its release is safe.

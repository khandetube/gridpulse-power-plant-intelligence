# GridPulse AI ⚡
### Power Plant Analytics & Predictive Maintenance

GridPulse AI is an open-source analytics platform for power-generation reporting, fuel-use analysis, maintenance-event tracking, and operational anomaly detection. The initial case study focuses on publicly reported information about the Shahid Kaveh combined-cycle power plant in Qaen, Iran.

> **Data integrity notice:** This repository does not claim access to plant SCADA, dispatch-center systems, or confidential operational networks. Publicly reported figures must retain their source and reporting period. Missing operational data is not fabricated or presented as real. Any synthetic/demo data added for software testing will be clearly labelled.

## Project goals
- Maintain a traceable catalogue of public sources and reported plant facts.
- Record generation and fuel figures with units, time periods, and aggregation scope.
- Visualize trends only when the available data supports them.
- Prepare a validated import path for authorized CSV/XLSX operational exports.
- Add anomaly detection and predictive-maintenance experiments only when suitable data is available.
- Keep data provenance, limitations, and validation results visible to users.

## Planned capabilities
- Plant and unit registry
- Generation and fuel-use dashboard
- Source and data-quality registry
- Maintenance-event timeline
- CSV import with schema validation
- Analytics API and interactive dashboard
- Tested, reproducible ML experiments when appropriate labelled data is available

## Data policy
Every imported record should include its source, publication date (when known), observation period, unit, scope (unit/plant/multiple plants), and verification status. Aggregated values must not be attributed to an individual plant unless the source explicitly supports that attribution.

No credentials, private records, network addresses, control-system configurations, or confidential dispatch data belong in this repository.

## Development status
**Prototype — active development.** The repository includes a FastAPI/SQLite API for caller-supplied observations, source-aware maintenance events, assets, test management, FMEA, inspections, and maintenance work orders, plus a bilingual static dashboard, local engineering workbenches, Docker deployment and CI tests. These modules are under active development and are not yet a production-validated plant system. Public-source figures still require record-by-record verification before they can be treated as validated dataset entries. No live plant telemetry, dispatch connection, multi-user authorization, or validated predictive model is available.

## Quick links
- Dashboard preview (deployment depends on GitHub Pages setup): https://khandetube.github.io/gridpulse-power-plant-intelligence/
- Dashboard source: https://github.com/khandetube/gridpulse-power-plant-intelligence/blob/main/index.html
- Observation data dictionary: docs/DATA_DICTIONARY.md
- Authorized data request and handling: docs/REQUEST_FOR_DATA.md
- Source provenance: docs/DATA_PROVENANCE.md
- CI workflow: .github/workflows/tests.yml

## Validate an observation CSV
Install the package and development dependencies, then call `validate_observations_csv(path)` from `gridpulse.validation`. The validator rejects missing columns, empty identifiers, duplicate record IDs, non-numeric or non-finite values, invalid ISO dates, reversed reporting periods, unknown scope values, and invalid verification states. Passing validation checks structure only; it does not verify the truth of a source.

## Suggested technology stack
- Python 3.12+
- FastAPI for the analytics API
- Pandas for tabular data validation and processing
- Pydantic for typed schemas
- React + TypeScript for the dashboard (planned)
- Pytest and GitHub Actions for automated checks (planned)

## Repository layout
```
data/
  raw/                 # Authorized or public source files; do not commit confidential data
  processed/           # Validated, documented datasets
docs/
  DATA_PROVENANCE.md   # Data sources, confidence, and limitations
src/
  gridpulse/           # Python analytics package (planned)
tests/                 # Automated tests (planned)
```

## Responsible use
GridPulse AI is an independent portfolio/research project. It is not an official system of the plant operator, the national grid dispatcher, or any government body. It must not be connected to operational technology or used to make real-time control decisions without formal authorization, engineering validation, and appropriate safety review.

## Contributing
Please document the origin, license, units, time coverage, and limitations of every dataset before adding it. Never label simulated values as real operational measurements.


## Browser operations console

- [Maintenance Operations Console](docs/maintenance-console.html) — browser client for work orders and turnaround planning. It requires the local FastAPI service to be running and is not connected to live plant systems.



## Local backup and recovery

The backend includes a local SQLite backup utility with online consistent snapshots, SHA-256 manifest verification, integrity checks, and opt-in restore. See [the operations runbook](docs/operations-runbook.md) for commands and the stop-before-restore procedure. Backups are not uploaded or encrypted by the utility; copy them to a separately managed protected location and retain the JSON manifest alongside each database file.

## Offline AI decision support

A network-free deterministic analytics engine is available for group statistics, robust outlier candidates, trend estimates, and input-quality checks. An optional local GGUF language-model adapter can generate natural-language answers when the operator supplies compatible model weights and installs the optional runtime; there is no hosted service or remote fallback. Model weights are not bundled. Statistical flags are not alarms or failure predictions. See [the offline AI guide](docs/offline-ai.md) for setup, limits, and offline deployment notes.

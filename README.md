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
**Initial scaffold — active development.** Public-source figures require record-by-record verification before they are treated as validated dataset entries. The repository does not yet provide live plant telemetry or a validated predictive model.

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

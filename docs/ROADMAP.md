# Roadmap

## Phase 1 — trustworthy data foundation
- [x] Create repository and define data-integrity policy
- [x] Document initial source leads and known limitations
- [ ] Verify public figures against original primary/secondary reports
- [x] Add machine-readable source registry and observation data dictionary
- [x] Add schema validation for generation and fuel observations
- [x] Define and validate a source-aware maintenance-event schema

## Phase 2 — analytics backend
- [x] Create typed API schemas and validation endpoint
- [x] Add SQLite persistence for caller-supplied observations, transactional batch ingestion, duplicate protection, filtered queries, and pagination
- [x] Add grouped descriptive-statistics and IQR review endpoint for source-labelled observation batches
- [x] Add tests for numeric values, dates, duplicate IDs, and event chronology
- [ ] Add unit-conversion rules only where source units and metric definitions support them

## Phase 3 — dashboard
- [x] Plant overview and source confidence indicators
- [x] CSV import with local schema validation
- [x] Trend chart for user-imported dated observations
- [x] Analytics lab with metric/status/date filters, descriptive statistics, IQR review flags, and CSV/JSON export
- [x] Clear empty states when source-backed observations are unavailable
- [x] Add local maintenance-event CSV import, validation, filtering, and timeline to dashboard
- [x] Persist imported maintenance events in browser local storage with a clear-data action
- [x] Export imported maintenance events as CSV
- [ ] Add cross-session backup/import guidance and browser-storage size handling

## Phase 4 — reliability analytics
- [ ] Define data requirements with an authorized data provider
- [x] Add conservative IQR screening as a review-only statistical heuristic; production anomaly detection still requires operational context and evaluation
- [ ] Evaluate models with temporal holdouts and documented metrics
- [ ] Add predictive-maintenance experiments only when labelled data is sufficient

## Phase 5 — delivery quality
- [x] CI checks and automated tests
- [x] Docker-based local setup with non-root container, read-only filesystem, loopback-only host binding, dropped capabilities, and persistent database volume
- [x] API runbook and deployment-boundary documentation
- [ ] Security and safety review

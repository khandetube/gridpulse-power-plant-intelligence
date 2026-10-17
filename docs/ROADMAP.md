# Roadmap

## Phase 1 — trustworthy data foundation
- [x] Create repository and define data-integrity policy
- [x] Document initial source leads and known limitations
- [ ] Verify public figures against original primary/secondary reports
- [x] Add machine-readable source registry and observation data dictionary
- [x] Add schema validation for generation and fuel observations
- [x] Define and validate a source-aware maintenance-event schema

## Phase 2 — analytics backend
- [ ] Create typed API schemas and validation endpoint
- [ ] Add generation/fuel summary endpoints
- [x] Add tests for numeric values, dates, duplicate IDs, and event chronology
- [ ] Add unit-conversion rules only where source units and metric definitions support them

## Phase 3 — dashboard
- [x] Plant overview and source confidence indicators
- [x] CSV import with local schema validation
- [x] Trend chart for user-imported dated observations
- [x] Clear empty states when source-backed observations are unavailable
- [x] Add local maintenance-event CSV import, validation, filtering, and timeline to dashboard
- [x] Persist imported maintenance events in browser local storage with a clear-data action
- [x] Export imported maintenance events as CSV
- [ ] Add cross-session backup/import guidance and browser-storage size handling

## Phase 4 — reliability analytics
- [ ] Define data requirements with an authorized data provider
- [ ] Explore baseline statistical anomaly detection
- [ ] Evaluate models with temporal holdouts and documented metrics
- [ ] Add predictive-maintenance experiments only when labelled data is sufficient

## Phase 5 — delivery quality
- [x] CI checks and automated tests
- [ ] Docker-based local setup
- [ ] Deployment and operational documentation
- [ ] Security and safety review

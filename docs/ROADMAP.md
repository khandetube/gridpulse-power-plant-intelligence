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
- [x] Add persistent maintenance-event API with timezone-aware validation, UTC normalization, overlap-aware date filtering, and duplicate protection
- [x] Require registered source IDs for observation and maintenance ingestion; distinguish source catalogue presence from fact verification
- [x] Add transactionally written, paginated ingestion audit records for observation and maintenance events
- [x] Add SQL-backed maintenance summaries grouped by event type and equipment; elapsed time is not labelled downtime
- [x] Add persisted dataset quality reporting for source coverage, metric/unit coverage, scope, and verification labels
- [x] Add grouped descriptive-statistics and IQR review endpoint for source-labelled observation batches
- [x] Add tests for numeric values, dates, duplicate IDs, and event chronology
- [x] Add explicitly unit-labelled net efficiency, net heat rate, and capacity-factor calculations with input-boundary checks and out-of-range review warnings
- [ ] Add unit-conversion rules only where source units and metric definitions support them

## Phase 3 — dashboard
- [x] Plant overview and source confidence indicators
- [x] CSV import with local schema validation
- [x] Trend chart for user-imported dated observations
- [x] Analytics lab with metric/status/date filters, descriptive statistics, IQR review flags, and CSV/JSON export
- [x] Bilingual local engineering calculator for net efficiency, net heat rate, and capacity factor; empty by default, clearly separated from live plant data, and exportable as CSV/JSON
- [x] Clear empty states when source-backed observations are unavailable
- [x] Add local maintenance-event CSV import, validation, filtering, and timeline to dashboard
- [x] Persist imported maintenance events in browser local storage with a clear-data action
- [x] Export imported maintenance events as CSV
- [x] Add standalone Engineering Workbench for performance testing, merit-order studies, damage/loss estimation, overhaul work-package planning, acceptance-test comparison, and R&D experiment registers
- [x] Add standalone Asset Intelligence registry with stable IDs, hierarchy, criticality and lifecycle metadata
- [ ] Add cross-session backup/import guidance and browser-storage size handling

## Phase 4 — reliability analytics
- [ ] Define data requirements with an authorized data provider
- [x] Add conservative IQR screening as a review-only statistical heuristic; production anomaly detection still requires operational context and evaluation
- [ ] Evaluate models with temporal holdouts and documented metrics
- [ ] Add predictive-maintenance experiments only when labelled data is sufficient
- [x] Add transparent MTBF/MTTR and availability study calculator with explicit limitations; formal RAM modelling remains pending approved event definitions

## Phase 5 — engineering operations and decision support
- [x] Add upgrade/retrofit scenario comparator with explicit assumptions and simple-payback study
- [x] Add simplified reserve-aware merit-order dispatch study; network/security constraints remain future work and no commands are issued
- [x] Add turnaround dependency planner with cycle detection
- [x] Add recovery readiness evidence gates without return-to-service authorization
- [x] Build normalized asset/equipment registry into the API (optional shared API key; not multi-user authentication)
- [x] Add test plans, test cases, executions, acceptance bounds and evidence references
- [x] Add FMEA with traceable severity/occurrence/detectability scoring and review states
- [x] Add inspection register with condition ratings, evidence references, source provenance and review states
- [x] Add maintenance work orders linked to assets and optional inspection/FMEA origins, lifecycle guards, completion evidence and audit events
- [x] Add turnaround plans, task dependency DAG validation, cycle prevention, guarded task/plan status transitions, critical-path duration estimates and task/plan audit history
- [ ] Add resource-constrained scheduling, calendar/shift rules, permits/isolation gates, parts availability and formal change-control entities
- [ ] Add engineering calculation library with explicit units, formula versions, assumptions and traceable inputs
- [ ] Add full scenario engine for upgrade/retrofit comparison and before/after performance studies
- [ ] Add loss/damage assessment with documented assumptions, uncertainty ranges and evidence attachments
- [ ] Add dispatch-planning studies with constraints, reserve requirements, ramp limits and economic assumptions; never issue direct control commands
- [ ] Add recovery/turnaround planning with dependencies, milestones, resource estimates and readiness gates
- [ ] Add R&D experiment tracking, reproducibility metadata and result provenance

## Phase 6 — delivery quality and safety
- [x] CI checks and automated tests
- [x] CI Docker image build and hardened-container runtime smoke test
- [x] Docker-based local setup with non-root container, read-only filesystem, loopback-only host binding, dropped capabilities, and persistent database volume
- [x] Optional shared API-key guard for `/api/v1/*` routes and secret injection through Compose
- [x] API runbook and deployment-boundary documentation
- [ ] Security and safety review
- [ ] Multi-user authentication, roles, rate limits, audit actor identity and tamper-resistant audit export
- [ ] Authorized integration boundary for telemetry/EMS/SCADA only after security, authorization and safety review

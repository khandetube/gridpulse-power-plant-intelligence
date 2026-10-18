# GridPulse AI — Operational Readiness Gate

This checklist distinguishes a working software deployment from a plant-authorized operational system. A green CI run is necessary, but it is not evidence that engineering calculations, plant data, or operational decisions are validated.

## 1. Current deployment boundaries

- [ ] Static GitHub Pages dashboard opens over HTTPS.
- [ ] Python CI passes, including unit tests, JavaScript syntax checks, style checks, and the API container smoke test.
- [ ] The API runs only in an approved environment with an explicitly configured API key.
- [ ] The API database and backup directory use persistent storage with documented retention.
- [ ] A restore has been tested against a separate destination database.
- [ ] No credentials, private plant records, network addresses, or confidential control-system details are committed to this public repository.

**Not currently established by this repository alone:** live SCADA/DCS/EMS/dispatch integration, identity-provider-backed multi-user roles, high availability, disaster-recovery objectives, plant-specific alarm thresholds, validated failure-prediction accuracy, or authorization for operational use.

## 2. Before accepting a dataset

For each incoming CSV or source document:

1. Confirm that the owner has authorized its use and storage.
2. Keep the original file immutable; work on a copy.
3. Register a source identifier and preserve publication date, reporting period, units, plant/unit scope, and verification status.
4. Run schema and chronology validation.
5. Check for duplicate IDs, missing fields, non-finite values, incompatible units, and reversed periods.
6. Review whether a plant-level number actually refers to that plant, rather than a regional or multi-plant aggregate.
7. Mark source truth as unverified until an accountable reviewer checks it. Passing schema validation does not verify source truth.
8. Keep a record of who reviewed the dataset, when, and against which source.

## 3. Before enabling the local API

- [ ] Set a strong API key through the deployment environment; never place it in source control or browser JavaScript.
- [ ] Keep the API bound to a trusted interface and restrict network access with host firewall or deployment network policy.
- [ ] Use TLS at an approved reverse proxy if requests cross an untrusted network.
- [ ] Confirm unauthenticated protected requests return HTTP 401.
- [ ] Confirm the persistent database volume is mounted and writable only by the service account.
- [ ] Create a backup and verify its manifest/integrity.
- [ ] Restore the backup into a separate destination and check SQLite integrity before relying on the restore process.
- [ ] Set backup retention, access control, monitoring, and an owner for restore drills.
- [ ] Avoid putting secrets or confidential data in logs and error messages.

The API key mechanism is not a substitute for per-user identity, role-based authorization, key rotation, or a complete production security review.

## 4. Engineering analytics acceptance

Before an analytic result is used outside research:

- [ ] Confirm the metric, unit, time basis, aggregation scope, and source provenance.
- [ ] Review missing data, duplicate observations, data quality, and known sensor/reporting changes.
- [ ] Independently recalculate representative outputs with an engineering-reviewed reference calculation.
- [ ] Test boundary cases, invalid inputs, constant series, outliers, and missing/duplicate dates.
- [ ] Record the algorithm version, input dataset version, output, reviewer, and limitations.
- [ ] Treat statistical anomaly candidates as review prompts—not alarms, fault diagnoses, or predictions.
- [ ] Do not use dashboard output to issue switching, trip, start/stop, protection, or return-to-service commands.

A predictive-maintenance claim requires suitable labelled historical data, a documented train/validation/test split, leakage checks, a baseline comparison, appropriate metrics, and review by qualified domain specialists. No such performance claim should be made solely from a successful software test suite.

## 5. Browser and release acceptance

For each release, test both dashboards in a current desktop and mobile browser:

- [ ] Select Persian; verify headings, buttons, labels, table content, placeholders, and dynamically refreshed content.
- [ ] Switch back to English; verify that the original labels return without duplicated or corrupted text.
- [ ] Reload the page; verify that the selected language persists.
- [ ] Check right-to-left layout, charts, horizontal tables, keyboard focus, and readable contrast.
- [ ] Exercise import, validation errors, export, filters, and local-storage reset using non-sensitive test data.
- [ ] Confirm that browser-local data is not mistaken for server-side persistence.
- [ ] Confirm API status and error states are understandable when the local service is unavailable.
- [ ] Check GitHub Actions and the published Pages URL after the deployment completes.

Static translation checks and JavaScript syntax checks do not replace interactive browser testing.

## 6. Go-live decision

The platform may be described as a **research/prototype dashboard** while any required gate above remains incomplete. Production use at a power plant requires a named system owner, approved data flows, threat model, access-control design, monitoring and incident response, backup/recovery objectives, engineering validation, change management, and formal operational acceptance.

Never connect this public demo directly to a control network. Any future integration must be separately designed and approved by the plant's OT/security and engineering owners, use a least-privilege read-only data path where appropriate, and remain isolated from control actions.

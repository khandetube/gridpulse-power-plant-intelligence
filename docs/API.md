# GridPulse API

## Run locally with Docker

Prerequisites: Docker Engine and the Docker Compose plugin.

```sh
docker compose up --build -d
docker compose ps
docker compose logs -f gridpulse-api
```

The API binds to `127.0.0.1:8000` on the host, not all host interfaces.

- Health: `GET http://127.0.0.1:8000/health`
- Project boundaries: `GET http://127.0.0.1:8000/api/v1/project`
- Source registry: `GET http://127.0.0.1:8000/api/v1/sources`
- Interactive OpenAPI docs: `http://127.0.0.1:8000/docs`
- Persist observations: `POST http://127.0.0.1:8000/api/v1/observations`
- Query stored observations: `GET http://127.0.0.1:8000/api/v1/observations`
- Descriptive analytics (stateless batch): `POST http://127.0.0.1:8000/api/v1/analytics/observations`
- Persisted data-quality report: `GET http://127.0.0.1:8000/api/v1/analytics/data-quality`
- Generation engineering calculations: `POST http://127.0.0.1:8000/api/v1/engineering/generation-performance`
- Append-only ingestion audit: `GET http://127.0.0.1:8000/api/v1/audit/events`

Stop the service with `docker compose down`.

## Persist and query observations\n\nUse `POST /api/v1/observations` with the same `records` schema shown below. The complete batch is stored transactionally; duplicate record IDs return HTTP 409 and roll back the entire batch. Each `source_id` must exist in `data/source_registry.csv`; unregistered IDs return HTTP 422. `GET /api/v1/observations` supports `plant`, `metric`, `status`, `start_date`, `end_date`, `limit` (1–1000) and `offset` filters. The response includes `total` before pagination.\n\n## Analytics request

The endpoint accepts a JSON object with a `records` array. The array must contain 1–10,000 records. Each record includes:

- `record_id`, `plant`, `metric`, `value`, `unit`
- `period_start`, `period_end` in ISO `YYYY-MM-DD` format
- `scope`: `unit`, `plant`, `multiple_plants`, `regional`, or `national`
- `source_id`
- `verification_status`: `unverified`, `reviewed`, or `verified`

Example body:

```json
{
  "records": [
    {
      "record_id": "DEMO-001",
      "plant": "Example plant",
      "metric": "net_generation",
      "value": 120.5,
      "unit": "MWh",
      "period_start": "2026-01-01",
      "period_end": "2026-01-01",
      "scope": "unit",
      "source_id": "SRC-DEMO",
      "verification_status": "unverified"
    }
  ]
}
```

The example is synthetic API documentation only; it is not a claim about a real plant. The `source_id` must nevertheless exist in the source registry. An existing registry entry proves only that the source is catalogued, not that the submitted observation is true.

The data-quality report summarizes record counts, plant/metric/source coverage, verification labels, scope distribution, and top source usage. It is not a completeness score against real plant telemetry.\n\nThe analytics response groups statistics by metric and unit, retains verification-status counts, and emits conservative Tukey 1.5×IQR review flags only when a group has at least four observations and a non-zero IQR. Results are descriptive, not forecasts, alarms, diagnoses, or operating instructions. Grouping by metric and unit does not guarantee that different plant scopes are comparable.

## Security and deployment boundaries

- This service has no plant telemetry, SCADA, historian, or dispatch connection.
- Caller-supplied observations can be persisted to SQLite using the ingest endpoint. Docker Compose stores the database in the named `gridpulse-data` volume. Direct API analytics requests remain stateless. The static GitHub Pages dashboard is not connected to this API automatically.
- Optional API key protection is enabled by setting a strong `GRIDPULSE_API_KEY`; requests to `/api/v1/*` must then send it in the `X-API-Key` header. With the variable unset, the API has no authentication and is intended only for the loopback-bound local Compose setup.
- The API key is a shared secret, not multi-user authentication: roles, per-user identity, tenant isolation, key rotation workflows, and rate limiting are not implemented. Do not expose the service publicly until these controls and a security review are complete.
- The container runs as a non-root user, uses a read-only root filesystem, drops Linux capabilities, and binds the published port to loopback.
- Before shared or production deployment, add authentication/authorization, rate limits, structured audit logging, durable storage, backups, retention rules, threat modelling, and an authorized data-ingestion agreement.


## Engineering generation-performance endpoint

`POST /api/v1/engineering/generation-performance` accepts a single source-labelled reporting-period record containing:

- `net_generation_mwh`: net electrical generation in MWh
- `fuel_thermal_input_mwh`: thermal fuel input in MWh, using a documented heating-value convention
- `net_capacity_mw`: net rated capacity in MW
- `period_hours`: actual reporting interval in hours (must be greater than zero and no more than 8,784)
- `period_start`, `period_end`, `plant`, `source_id`, `verification_status`

Returned indicators:

- Net efficiency (%) = net generation MWh / fuel thermal input MWh × 100
- Net heat rate (kJ/kWh) = fuel thermal input MWh / net generation MWh × 3,600
- Capacity factor (%) = net generation MWh / (net capacity MW × period hours) × 100

The service flags calculated efficiency or capacity factor above 100% for review; it does not silently clamp values. Generation, capacity, thermal input, and reporting period must refer to the same plant boundary and interval. The source ID must be present in the source registry, but that alone does not verify the submitted values. Ambient conditions, startup/shutdown, fuel quality, and heating-value conventions are not corrected automatically. Do not use the indicators alone to diagnose equipment or direct plant operation.


## Ingestion audit trail

`GET /api/v1/audit/events` returns append-only application records for successful observation and maintenance-event creation. Filters: `entity_type` (`observation` or `maintenance_event`), `entity_id`, `limit` (1–1,000), and `offset`. Audit inserts occur in the same SQLite transaction as the source record, so failed duplicate batches do not leave false audit entries. The current audit records identify the entity, action, registered source ID, verification label, and recording time; they do not establish who the actor was because authentication and user identity are not yet implemented. This is an application audit log, not a tamper-proof external ledger.


## Asset, test, risk, inspection and work-order registers

The following endpoints are available in the local FastAPI service. All writes require a registered `source_id` where shown by the request schema. These are engineering records and review workflows; they do not constitute safety certification or operational commands.

### Asset registry
- `POST /api/v1/assets` — create an asset with a stable ID, plant, type, hierarchy, criticality, lifecycle, capacity metadata and source.
- `GET /api/v1/assets` — filter and paginate assets.
- `GET /api/v1/assets/hierarchy` — view parent/child relationships.
- `GET /api/v1/assets/{asset_id}`, `PATCH /api/v1/assets/{asset_id}`, `DELETE /api/v1/assets/{asset_id}` — retrieve, update or delete; parent deletion is blocked while children exist.

### Test management
- `POST /api/v1/testing/plans` — create a source-labelled test plan.
- `POST /api/v1/testing/cases` — add a test case with units and acceptance bounds.
- `POST /api/v1/testing/executions` — record measured values, evidence and review states; pass/fail is evaluated against case bounds.
- `GET /api/v1/testing/cases`, `GET /api/v1/testing/executions` — query records.

### Failure Mode and Effects Analysis (FMEA)
- `POST /api/v1/fmea` — record a failure mode linked to an asset. RPN is calculated as severity × occurrence × detectability (each 1–10); it is a prioritization aid, not a calibrated probability.
- `GET /api/v1/fmea` and `GET /api/v1/fmea/{failure_mode_id}` — query failure modes.
- `PATCH /api/v1/fmea/{failure_mode_id}` — update mitigation/review state with source provenance.

### Inspections
- `POST /api/v1/inspections` — record an inspection, method, findings, condition rating, evidence reference, source and next due date. Timestamps must include an explicit UTC offset.
- `GET /api/v1/inspections` — filter by asset, condition and approval state; supports pagination.
- `GET /api/v1/inspections/{inspection_id}` — retrieve an inspection.
- `PATCH /api/v1/inspections/{inspection_id}` — update findings/recommendations and review states.

### Maintenance work orders
- `POST /api/v1/work-orders` — create a proposed work order linked to an existing asset. An optional origin may link to an inspection or FMEA record on the same asset.
- `GET /api/v1/work-orders` — filter by asset, status, priority or origin and paginate. Urgent/high priority records sort first.
- `GET /api/v1/work-orders/{work_order_id}` — retrieve a work order.
- `PATCH /api/v1/work-orders/{work_order_id}` — transition status and update owner, schedule, labor estimate, parts/materials, completion summary and evidence.
- `GET /api/v1/work-orders/{work_order_id}/audit` — query paginated status-change/application audit events, including source ID and from/to status.

Work-order status transitions are guarded: proposed → approved → in_progress → completed → verified, with permitted hold/cancel paths. Completion requires a completion summary and after-evidence reference; verification requires `verification_status=verified` and after-evidence. The API checks that evidence references are present, not that an external file is authentic or technically adequate. These checks do not replace work permits, lockout/tagout, independent inspection, OEM procedures or the site's authorized return-to-service process.

### Operational boundaries
The static GitHub Pages dashboard is not automatically connected to this API. To use the API, run the Docker Compose service locally and consult the OpenAPI page at `http://127.0.0.1:8000/docs`. The Compose binding is loopback-only by default. Do not expose it to the internet: the optional API key is a shared secret, not role-based authentication. No live telemetry, SCADA/DCS/EMS or dispatch integration is configured, and no records in the repository should be interpreted as real inspection findings or real work orders unless independently supplied and verified by an authorized source.


### Turnaround planning
- `POST /api/v1/turnarounds/plans` — create a plan with tasks, duration estimates, optional asset links, crew labels and task dependencies. The API rejects duplicate task IDs, unknown dependencies and dependency cycles.
- `GET /api/v1/turnarounds/plans` — list/filter/paginate plans.
- `GET /api/v1/turnarounds/plans/{plan_id}` — retrieve the plan, tasks, estimated total labor-hours and dependency-based critical-path hours.
- `PATCH /api/v1/turnarounds/plans/{plan_id}` — guarded plan lifecycle transitions; a plan cannot be approved without tasks or closed while tasks are incomplete.
- `PATCH /api/v1/turnarounds/plans/{plan_id}/tasks/{task_id}?status=ready&source_id=SRC-001` — update task status. Dependencies must be completed before dependent tasks can become ready, start or complete. Task transitions are guarded.
- `GET /api/v1/turnarounds/plans/{plan_id}/audit` and `GET /api/v1/turnarounds/plans/{plan_id}/tasks/{task_id}/audit` — inspect plan/task status history.

Critical-path and labor estimates are planning aids only. The current estimator assumes task durations and dependencies are valid and does not yet optimize shared crews, calendar constraints, equipment isolation, permit windows, material availability or uncertainty. An approved plan in this API is not an operational permit or authority to start/stop equipment.


### Browser maintenance console
A browser console is available at `docs/maintenance-console.html` and is linked from the main dashboard. It can create work orders and turnaround plans and display records from the connected API. The browser must be able to reach the local API at the configured URL; the API has a restricted CORS allowlist for `https://khandetube.github.io` and loopback origins. If the console cannot connect, first start `docker compose up -d --build`, then enter the configured API key in the console. The key is kept only in page memory and is not persisted by the console. Do not put a production API key into a shared/public browser or expose the loopback-bound API to the internet.

The console is a thin browser client, not an authorization layer. The shared API key is not per-user identity, roles or audit actor identity. Use an approved private deployment with HTTPS, proper identity and authorization controls before multi-user or production use.

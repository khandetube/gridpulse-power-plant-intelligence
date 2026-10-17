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

The response groups statistics by metric and unit, retains verification-status counts, and emits conservative Tukey 1.5×IQR review flags only when a group has at least four observations and a non-zero IQR. Results are descriptive, not forecasts, alarms, diagnoses, or operating instructions. Grouping by metric and unit does not guarantee that different plant scopes are comparable.

## Security and deployment boundaries

- This service has no plant telemetry, SCADA, historian, or dispatch connection.
- Caller-supplied observations can be persisted to SQLite using the ingest endpoint. Docker Compose stores the database in the named `gridpulse-data` volume. Direct API analytics requests remain stateless. The static GitHub Pages dashboard is not connected to this API automatically.
- No authentication, multi-user access control, or tenant isolation is implemented. Keep it local/private; do not expose it to the public internet or submit confidential operational data.
- The container runs as a non-root user, uses a read-only root filesystem, drops Linux capabilities, and binds the published port to loopback.
- Before shared or production deployment, add authentication/authorization, rate limits, structured audit logging, durable storage, backups, retention rules, threat modelling, and an authorized data-ingestion agreement.

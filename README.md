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

## Advanced statistical and ML screening

The runtime includes NumPy, pandas, SciPy, and scikit-learn for numerical processing, robust statistics, and machine learning. The dashboard uses Chart.js for interactive observation timelines; the chart library is loaded from a public CDN and the report remains available if the CDN cannot be reached. The endpoint `POST /api/v1/analytics/anomalies?contamination=0.05` accepts a source-labelled observation batch and applies a deterministic `IsolationForest` configuration to one comparable metric/unit series. It requires at least eight observations and returns flagged record IDs, dates, values, anomaly scores, robust median-absolute-deviation (MAD) candidates, and provenance labels. The contamination parameter is bounded to 0.01–0.20.

Example request body:

```json
{
  "records": [
    {
      "record_id": "example-001",
      "plant": "Example plant",
      "metric": "net_generation",
      "value": 100.0,
      "unit": "MWh",
      "period_start": "2026-01-01",
      "period_end": "2026-01-01",
      "scope": "plant",
      "source_id": "SRC-001",
      "verification_status": "reviewed"
    }
  ]
}
```

The example above illustrates the record schema only; a valid request needs at least eight observations and a registered source. ML flags are review candidates—not alarm thresholds, failure probabilities, fault diagnoses, or control instructions. Both methods use values only and do not model seasonality, load, ambient conditions, or equipment context. Statistical flags are candidates for human review, not confirmed anomalies. The algorithms do not independently verify the underlying data.

### STL time-series decomposition

The API exposes `POST /api/v1/analytics/time-series?period=7` using statsmodels STL with robust fitting. It decomposes one source-labelled, comparable metric/unit series into observed values, trend, seasonal component, and residuals; it also reports trend/seasonal strength and robust residual review candidates. The period is a number of observations, not calendar days, and the API requires at least two periods. Irregular sampling, short histories, regime changes, and an incorrectly selected cycle length can make results misleading. Results are statistical review aids, not alarms or fault diagnoses. The dashboard includes an interactive component chart and JSON report.

### Unit-aware engineering conversions

The API exposes `POST /api/v1/analytics/units/convert`, powered by Pint. Example body: `{"value": 1.5, "from_unit": "MW", "to_unit": "kW"}`. The response includes the converted value and dimensionality. Incompatible dimensions (for example MW to MWh), unknown units, and non-finite values are rejected. The dashboard includes a unit-converter panel for common power, energy, temperature, and mass-flow units. A mathematically valid conversion does not verify the measurement's source or engineering context.

## Frontend–backend integration and troubleshooting

The main dashboard now has a **Sync all backend data** action. It checks `/ready`, then fetches the registered sources, paginated observations, and paginated maintenance events from the configured API. API-backed rows are refreshed on each sync while browser-only CSV imports are preserved. A sync error is displayed in the dashboard; it does not silently replace local records.

### Local development

1. Set a strong API key in the shell before starting the API:
   ```bash
   export GRIDPULSE_API_KEY="replace-with-a-long-random-secret"
   docker compose up --build -d
   ```
2. Open the public dashboard and enter `http://127.0.0.1:8000` as the API base URL. Enter the same API key in the password field; the key is kept in the page session and is not written to local storage.
3. Click **Check backend health**, then **Sync all backend data**. The connection badge should report that the backend is connected and ready.
4. To inspect API routes and schemas, open `http://127.0.0.1:8000/docs` on the same computer.

### Deployment and browser limits

- GitHub Pages hosts only static frontend files. **There is no publicly deployed backend URL configured by this repository**, so a visitor cannot access the API merely by opening the Pages link. The default loopback URL refers to that visitor's own computer.
- A remote backend must have an HTTPS URL, persistent storage, a strong `GRIDPULSE_API_KEY`, and CORS configured to allow `https://khandetube.github.io`. Do not expose a production API without authentication.
- Browser mixed-content and CORS rules can block invalid API URLs; the frontend validates the URL and shows a diagnostic error rather than treating a failed request as an empty dataset.
- The sync endpoint is read-only from the frontend: it fetches sources, observations and maintenance events. CSV import remains local in the browser and is not automatically uploaded to the API.
- Backend health proves only application readiness. It does not prove access to plant telemetry, SCADA, or dispatch systems; those connections remain unconfigured.

## Data policy
Every imported record should include its source, publication date (when known), observation period, unit, scope (unit/plant/multiple plants), and verification status. Aggregated values must not be attributed to an individual plant unless the source explicitly supports that attribution.

No credentials, private records, network addresses, control-system configurations, or confidential dispatch data belong in this repository.


## Bounded autonomous engineering supervisor

The backend includes a bounded propose–review–revise supervisor at `POST /api/v1/cad/autonomous-run`. It reuses the validated CAD/design pipeline, retains the best candidate by the quality-gate ranking, fingerprints each candidate to detect repeated models, and emits an iteration trace with read-only tool audits. The allowlisted review tools currently validate the typed `EngineeringSpec`, inspect quality-report structure, and screen model geometry for non-finite numeric values.

Example request:

```json
{
  "prompt": "Create a conceptual combined-cycle plant layout; identify unknown design-basis inputs instead of guessing.",
  "site_width": 80,
  "site_length": 55,
  "template": "power",
  "use_llm": true,
  "max_iterations": 3
}
```

Important boundaries:
- The API requires the Python backend to be deployed; GitHub Pages is static and does not host this endpoint.
- Revision iterations require `GRIDPULSE_LLM_MODEL` and a reachable OpenAI-compatible inference endpoint. `GRIDPULSE_LLM_BASE_URL` defaults to local Ollama (`http://localhost:11434/v1`); `GRIDPULSE_LLM_API_KEY` is optional for local inference and only needed by providers that require authentication. Without an explicitly configured model, the endpoint performs one deterministic screening pass and reports that it cannot revise autonomously.
- This is not yet a general-purpose autonomous agent: there is no persistent run memory, background job manager, external-tool execution, or live plant/SCADA/dispatch connection.
- A passed software screening gate is not code compliance, safety approval, or permission to construct or operate equipment. Qualified engineers must verify all design inputs and outputs.


### Independent 3D envelope screening

The autonomous review registry now includes an independent axis-aligned 3D bounding-box overlap audit for assets that provide finite `x/y/z` coordinates and `length/width/height` dimensions. Positive-volume intersections are reported as potential clashes, count as failed review-tool evidence, and are fed into the next bounded LLM revision prompt. A run cannot report `screening_passed` unless the available independent checks pass. Face-to-face contact alone is not counted as overlap. Missing dimensions are explicitly listed as unassessed rather than assumed clash-free; an incomplete asset-envelope audit now fails closed and its missing-geometry findings are fed into the next bounded revision prompt.

This is a conservative first-pass heuristic, not a full CAD/BIM clash solver: it does not yet account for rotated geometry, nozzle projections, pipe insulation, electrical clearances, access/maintenance zones, fire separation or discipline-specific standards. It must not be treated as engineering approval.

## Open-source LLM inference (Ollama)

GridPulse can use a locally hosted open-weight model for structured design proposals through Ollama's OpenAI-compatible endpoint. This avoids requiring a paid API key for local inference; the model runs on the machine or server where Ollama is installed. See the [Ollama API guide](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).

1. Install Ollama on the backend host and pull a model that your hardware can run, for example `ollama pull qwen2.5:7b` (choose a smaller quantized model if RAM/VRAM is limited).
2. Configure the backend environment:

```bash
GRIDPULSE_LLM_BASE_URL=http://localhost:11434/v1
GRIDPULSE_LLM_MODEL=qwen2.5:7b
# GRIDPULSE_LLM_API_KEY is optional for local Ollama; set it only if your endpoint requires it.
```

3. Restart the API process and inspect `GET /api/v1/cad/status`. Then call CAD generation or the bounded autonomous endpoint with `use_llm: true`.

For a separately hosted OpenAI-compatible provider, set `GRIDPULSE_LLM_BASE_URL`, `GRIDPULSE_LLM_MODEL`, and (if required) `GRIDPULSE_LLM_API_KEY` to that provider's values. Do not expose an unauthenticated Ollama port to the public internet. Model-generated geometry is an untrusted proposal: Pydantic bounds and deterministic audits still validate it, and it is not an engineering approval. If inference fails or returns invalid output, the CAD engine falls back to deterministic generation. GitHub Pages cannot run the model; this requires the Python backend and compute resources.


### Model readiness check

After setting the environment variables and starting the Python API, call `GET /api/v1/cad/llm-status`. This performs a bounded three-second request to the configured `/v1/models` endpoint and reports whether the endpoint is reachable and the exact configured model ID is listed. It does not return the endpoint URL, API key, or other credentials. A reachable endpoint is not proof that generation quality is adequate; run a test generation and review its validation report as well.

## Persistent agent run ledger

Completed autonomous runs are recorded in a local SQLite ledger. The API returns a `run_record.run_id` after a successful run, and provides:

- `GET /api/v1/cad/autonomous-runs?limit=20` — bounded recent-run metadata.
- `GET /api/v1/cad/autonomous-runs/{run_id}` — stored result and iteration/tool audit trace.
- `GRIDPULSE_AGENT_DB_PATH` — optional database path override. In container deployments, point this at a persistent mounted volume; ephemeral filesystems do not provide durable history across redeploys.

The ledger stores a fingerprint of request metadata and the result, not the original prompt or model credentials. Stored engineering results may still contain project details, so deployers must protect the database and API with appropriate access controls and backups. This is durable history, not yet a resumable background job queue.

## MEP Studio — preliminary electrical/mechanical design and 3D concept export

Open the static [MEP Studio](docs/mep-studio.html) from GitHub Pages to enter building dimensions, floor count, net-area ratio, and explicit preliminary electrical/mechanical assumptions. The browser computes geometric areas, rough connected/coincident electrical loads, a first-pass cooling estimate, fresh-air volume, and a concept BOQ. It supports CSV/JSON export, a lightweight rotatable conceptual massing view, OBJ export, and a MAXScript (.ms) script that can be run inside Autodesk 3ds Max to generate simple boxes representing the building and main conceptual routes.

**This is not a construction-ready design or BIM authoring tool.** The built-in values are example assumptions, not surveyed building data or code-prescribed values. The counts and route quantities are rough estimates. It does not size cables or protective devices, calculate fault current/voltage drop/earthing, perform hourly heating/cooling load calculations, size ducts/pipes, calculate pressure losses, or create a native MAX file directly. OBJ/MAXScript output is simplified massing geometry without detailed fittings, connectors, coordinated architecture/structure, or BIM metadata. All project inputs, units, geometry scale, local codes, engineering calculations, and quantities require review by qualified electrical and mechanical engineers before procurement or construction. The page operates locally in the browser and does not upload project data.

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

- [Main dashboard AI operating guide](docs/main-dashboard-ai-runbook.md) — local API startup, document loading, troubleshooting, and safety limits.

- [Offline AI Console](https://khandetube.github.io/gridpulse-power-plant-intelligence/docs/offline-ai-console.html) — browser interface for local analytics and optional local-model chat. It requires the API running on your computer; it does not connect to live plant systems.

A network-free deterministic analytics engine and lexical document retrieval endpoint are available for group statistics, robust outlier candidates, trend estimates, input-quality checks, and source/line-cited local text search. An optional local GGUF language-model adapter can generate natural-language answers when the operator supplies compatible model weights and installs the optional runtime; there is no hosted service or remote fallback. Model weights are not bundled. Statistical flags are not alarms or failure predictions. See [the offline AI guide](docs/offline-ai.md) for setup, limits, and offline deployment notes.

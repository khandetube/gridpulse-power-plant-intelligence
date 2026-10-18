# Main dashboard AI: local operating guide

The AI workspace is embedded in the main dashboard. The hosted GitHub Pages site is a static front end; it does not host a language model or a backend database. API calls are sent only to the API address that the user enters.

## 1. Start the local API with Docker

Prerequisites: Docker Engine/Desktop with Compose.

From a terminal in the repository root:

```bash
docker compose -f compose.yaml up -d --build
docker compose -f compose.yaml ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/ai/status
```

The Compose file binds the service to `127.0.0.1`, not to all network interfaces. The SQLite database is stored in the persistent `gridpulse-data` volume. The API key is optional in the current configuration; for local use, set a strong `GRIDPULSE_API_KEY` environment variable before starting the container if access control is required. When the key is configured, enter the same value in the dashboard's API key field. Do not publish port 8000 to the public internet.

To stop the service:

```bash
docker compose -f compose.yaml down
```

## 2. Use the AI workspace in the main dashboard

Open the [main dashboard](https://khandetube.github.io/gridpulse-power-plant-intelligence/), scroll to **Engineering AI Workspace**, keep the API address at `http://127.0.0.1:8000`, and choose **Check AI status**.

The API is local to the computer running the browser. It will not connect to another user's computer. If the browser reports a network/CORS/mixed-content error, check the API health endpoint and browser console. A more reliable fully local setup is to serve the dashboard from a local development origin that is explicitly allowed by the API's CORS configuration; do not solve this by opening CORS to every origin.

## 3. Load authorised engineering text

The workspace accepts a JSON array of documents and local `.txt` or `.md` files. Each document must have a title, a source ID and text. The file picker loads text into the browser form; it does not upload the file to GitHub. When you click search/ask, the browser sends the document text to the configured API. Use only documents you are authorised to process and do not paste confidential plant, personal, credentials, or dispatch data into the hosted page.

The retrieval engine normalizes common Persian/Arabic letter variants and zero-width non-joiners, then ranks matching paragraphs lexically. It is not semantic/vector search. Line citations refer to the submitted text, not necessarily the original PDF page. PDF files and scanned images are not parsed by this file picker. The example documents are synthetic and are not approved operating procedures.

## 4. Understand AI modes

- **Deterministic analysis:** calculates descriptive statistics, trend estimates and potential outliers from valid supplied records. A flag is not a confirmed fault, alarm, or prediction.
- **Local knowledge retrieval:** returns text excerpts with source IDs and line ranges. No result means no lexical match was found; it does not prove the topic is absent from the source.
- **Natural-language chat:** requires a compatible GGUF model file and the optional `llama-cpp-python` runtime. The repository does not include model weights and does not fall back to a hosted model. If the model is not configured, chat may return HTTP 503 even when search and statistical analysis work.
- **No plant connectivity:** no SCADA/DCS/EMS/disptach connection or live telemetry is included. The dashboard must not be used to issue control, trip, dispatch, or return-to-service decisions.

## 5. Troubleshooting

- **API unavailable:** run `docker compose -f compose.yaml ps` and `docker compose -f compose.yaml logs --tail=100 gridpulse-api`.
- **401 response:** set the matching API key in the dashboard, or check the local environment configuration.
- **422 response:** inspect the API response body for validation errors; observation analysis requires unique IDs, valid dates, units, source IDs, scopes and verification states.
- **No retrieval results:** try terms in the same language and spelling as the supplied documents; ensure the document is loaded into the JSON area and has non-empty text.
- **Chat returns 503:** install/configure the optional local model runtime and compatible GGUF weights as documented in [offline AI documentation](offline-ai.md). Statistical analysis and lexical retrieval do not require model weights.

## Operational status

This is an actively developed research/engineering prototype. Passing automated tests verifies the tested software paths, not plant-specific accuracy, cybersecurity certification, regulatory compliance, or operational readiness. Before any real plant use, complete authorized data integration, access-control review, threat modeling, source validation, independent engineering verification, backup/recovery drills, and formal safety approval.

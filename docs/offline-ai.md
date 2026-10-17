# Offline AI engine

## What this is today

GridPulse includes a deterministic, local analytics engine at `src/gridpulse/offline_ai.py`. It performs group statistics, median/MAD-based candidate outlier screening, simple linear trend estimates, and input-quality checks using Python's standard library. It does not make network requests, call hosted AI services, or download model weights.

The deterministic engine is paired with an optional adapter for a local GGUF language model. The repository does not bundle multi-gigabyte model weights. Without a user-supplied model file and the optional `llama-cpp-python` runtime, natural-language inference remains unavailable; there is no remote fallback. The deterministic analytics engine still works without the model.

## Run directly from local files

The command-line mode does not start a web server and does not require network access during analysis. Prepare a UTF-8 JSON input with a `records` array, then run:

```sh
python -m gridpulse.offline_ai observations.json --output analysis-report.json
```

If `--output` is omitted, the report is printed to standard output. Keep original source files and the generated report together for auditability.

## API

- `GET /api/v1/ai/status`: capabilities and limits.
- `POST /api/v1/ai/analyze`: analyze 1–5,000 caller-provided observations.\n- `POST /api/v1/ai/chat`: use a locally installed GGUF model to answer a question; returns HTTP 503 if no local model/runtime is available.\n- `POST /api/v1/ai/knowledge/search`: rank caller-supplied local document text and return matching excerpts with source IDs and line ranges.\n- `GET /api/v1/ai/status` also reports whether the optional local model runtime and file are ready.

Example request:

```json
{
  "records": [
    {
      "record_id": "EXAMPLE-1",
      "plant": "Example plant",
      "metric": "net_generation",
      "value": 10.0,
      "unit": "MWh",
      "period_start": "2026-01-01",
      "period_end": "2026-01-01",
      "scope": "plant",
      "source_id": "SRC-001",
      "verification_status": "unverified"
    }
  ]
}
```

Example values are illustrative and are not real plant data. As with other API routes, configure `GRIDPULSE_API_KEY` to require the API key. All calls are handled by the local API process.

## Statistical interpretation and safety

Outlier candidates require at least four points in a matching plant/metric/unit/scope group. When median absolute deviation is nonzero, a modified z-score threshold is used; constant-baseline deviations use an explicitly labelled fallback. Trend is ordinary least-squares slope per calendar day. These are review aids, not alarms, predictions, calibrated plant models, or approved engineering thresholds. The source ID and verification status remain visible. Review the original records and applicable operating procedures before drawing conclusions. This module does not control equipment.

## Optional local language model

Install the optional runtime from a trusted offline wheelhouse, not from the disconnected machine:

```sh
pip install --no-index --find-links /path/to/offline-wheelhouse '.[local-llm]'
```

Set `GRIDPULSE_LOCAL_MODEL_PATH` to the path of a compatible GGUF model already stored on the computer. Optional settings are `GRIDPULSE_LOCAL_MODEL_CONTEXT`, `GRIDPULSE_LOCAL_MODEL_THREADS`, and `GRIDPULSE_LOCAL_MODEL_GPU_LAYERS`. The default uses CPU inference. Confirm the model's license, provenance, RAM/VRAM requirements, and suitability before use. No model downloader or remote fallback exists.

Example local request:

```json
{
  "question": "Summarize the evidence and explain what remains uncertain.",
  "context_records": [
    {
      "record_id": "EXAMPLE-1",
      "metric": "net_generation",
      "value": 10.0,
      "unit": "MWh",
      "source_id": "SRC-001",
      "verification_status": "unverified"
    }
  ]
}
```

The example is synthetic. Context records are treated as untrusted input. Model output can be wrong or hallucinated and must not be used alone for engineering decisions.

## Fully offline deployment

The analytics module has no runtime third-party AI dependency and needs no network to compute once the application package is installed. For a physically isolated computer, install the project and dependencies from a trusted, verified offline package bundle, then disconnect the network. The static GitHub Pages interface itself is hosted online; use the local API/docs or locally served static files for a fully disconnected installation.


## Source-grounded local document search

The API endpoint `POST /api/v1/ai/knowledge/search` implements deterministic lexical retrieval over document text supplied by the caller. It returns excerpts, source IDs, line ranges, matched terms, and a transparent relevance score. It does not read arbitrary server paths, fetch documents from the internet, or persist submitted document contents. This is a retrieval component—not a complete RAG answer generator or semantic embedding system. Documents should be reviewed for licensing, currency, scope, and approval status before being used as engineering evidence. Do not paste confidential material into the public GitHub Pages interface; serve a local copy for sensitive documents.

Example request:

```json
{
  "query": "vibration inspection limits",
  "limit": 5,
  "documents": [
    {
      "title": "Approved maintenance standard",
      "source_id": "DOC-123",
      "text": "Section 1: Scope\\n...\\n\\nSection 2: Vibration\\n..."
    }
  ]
}
```

The text above is illustrative. Search results only indicate lexical matches; a high score does not certify that a source is authoritative or that a retrieved requirement applies to a particular asset.

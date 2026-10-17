# Offline AI engine

## What this is today

GridPulse includes a deterministic, local analytics engine at `src/gridpulse/offline_ai.py`. It performs group statistics, median/MAD-based candidate outlier screening, simple linear trend estimates, and input-quality checks using Python's standard library. It does not make network requests, call hosted AI services, or download model weights.

This is a useful offline decision-support component, but **it is not a trained LLM** and does not generate open-ended natural-language answers. No large model weights are bundled. A trained language model requires a compatible model file, local inference runtime, hardware sizing, license review, and separate validation; none should be implied to exist until packaged and tested.

## Run directly from local files

The command-line mode does not start a web server and does not require network access during analysis. Prepare a UTF-8 JSON input with a `records` array, then run:

```sh
python -m gridpulse.offline_ai observations.json --output analysis-report.json
```

If `--output` is omitted, the report is printed to standard output. Keep original source files and the generated report together for auditability.

## API

- `GET /api/v1/ai/status`: capabilities and limits.
- `POST /api/v1/ai/analyze`: analyze 1–5,000 caller-provided observations.

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

## Fully offline deployment

The analytics module has no runtime third-party AI dependency and needs no network to compute once the application package is installed. For a physically isolated computer, install the project and dependencies from a trusted, verified offline package bundle, then disconnect the network. The static GitHub Pages interface itself is hosted online; use the local API/docs or locally served static files for a fully disconnected installation.

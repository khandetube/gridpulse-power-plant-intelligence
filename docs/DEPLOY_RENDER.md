# Deploy the GridPulse API with Render

This is an optional deployment path for the FastAPI backend. It is not deployed automatically by adding this file.

## Before deploying
- Review Render's current plan and persistent-disk pricing. The included Blueprint selects the Starter plan and a 1 GB persistent disk; charges may apply.
- Do not connect this API to plant OT/SCADA or dispatch networks without formal authorization and a separate security review.
- This API is an independent engineering prototype, not an official plant system.

## Deploy
1. Open Render and choose **New → Blueprint**.
2. Select the GitHub repository `khandetube/gridpulse-power-plant-intelligence`.
3. Review the resources and cost estimate before confirming deployment.
4. Render reads `render.yaml`, creates the Docker web service, generates `GRIDPULSE_API_KEY`, and mounts persistent storage at `/data`.
5. After deployment, open the service URL plus `/ready`. A successful readiness response confirms app readiness only, not plant data connectivity.
6. In the GridPulse dashboard, enter the service's HTTPS base URL and the generated API key in the API key field. Do not publish the key in repository files, screenshots, or public messages.
7. Run **Check backend health**, then **Sync all backend data**. Verify the sources, observations and maintenance events are the expected records.

## CORS and authentication
The current API allows the public GitHub Pages origin `https://khandetube.github.io` and local loopback origins. Requests to versioned API routes require the generated `X-API-Key` when production mode is enabled. CORS is not authentication. Keep the key private and rotate it if exposed.

## Persistence and backups
The SQLite database is configured at `/data/gridpulse.sqlite3` and the Blueprint mounts a persistent disk there. Persistent storage is not a backup: configure and periodically test a separate protected backup process before relying on stored records.

## Limitations
- The dashboard/API does not currently ingest live plant telemetry, SCADA, or dispatch data.
- Frontend CSV imports remain in the browser and are not automatically uploaded.
- A green health/readiness check means the service responds; it does not validate source truth, model quality, or engineering safety.
- Do not use statistical flags or generated design suggestions as alarms, operating instructions, or construction approval.

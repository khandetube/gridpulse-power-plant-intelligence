# Local operations runbook

## Scope and prerequisites

GridPulse currently ships a static GitHub Pages frontend and a separately run FastAPI/SQLite backend. The documented Docker Compose deployment binds the API to `127.0.0.1:8000` and stores its database in the named `gridpulse-data` volume at `/data/gridpulse.sqlite3`. Do not expose this API directly to the public internet.

Set a long random API key in a local `.env` file before starting the service:

```dotenv
GRIDPULSE_API_KEY=replace-with-a-long-random-secret
```

Start and inspect the service:

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 gridpulse-api
curl -fsS http://127.0.0.1:8000/health
```

The health endpoint confirms process availability only; it does not certify data quality, plant readiness, or a connection to operational control systems.

The readiness endpoint checks that the source registry file is present and that SQLite can open the configured database. It is an application-dependency check, not a plant/equipment readiness signal:

```sh
curl -i http://127.0.0.1:8000/ready
```

A `200` response means the local API dependencies passed these basic checks; a `503` response includes a `checks` object identifying an unavailable dependency. The endpoint intentionally does not prove that records are correct, that backups exist, or that any plant telemetry is connected. The API is still a local service; GitHub Pages hosts only the static frontend.

For a safe application inventory, query the authenticated versioned API diagnostics route:

```sh
curl -fsS http://127.0.0.1:8000/api/v1/system/diagnostics \\
  -H "X-API-Key: $GRIDPULSE_API_KEY"
```

The response reports source-registry and SQLite integrity status, local record counts, and explicit capability flags. It does not return filesystem paths or credentials and does not establish live telemetry, dispatch connectivity, predictive-model validity, or real plant condition. If `GRIDPULSE_API_KEY` is not configured, this local diagnostic route is not protected by the optional key middleware; configure the key before using the API beyond isolated local development.

## Filtered observation CSV export

The API provides a bounded CSV export for authorized local analysis. Example (the API key is required when `GRIDPULSE_API_KEY` is configured):

```sh
curl -fsS -G 'http://127.0.0.1:8000/api/v1/observations/export.csv' \
  --data-urlencode 'plant=Example plant' \
  --data-urlencode 'metric=net_generation' \
  --data-urlencode 'start_date=2026-01-01' \
  --data-urlencode 'end_date=2026-01-31' \
  --data-urlencode 'limit=1000' \
  -H "X-API-Key: $GRIDPULSE_API_KEY" \
  -o gridpulse-observations.csv
```

The endpoint returns at most 10,000 rows per request; use `offset` for subsequent pages. It preserves verification-status labels, reports total/returned counts in response headers, and prefixes risky untrusted text cells to reduce spreadsheet-formula injection risk. A successful export does not independently verify the source or measurement. Protect exported files according to their contents.

## Create and verify a consistent backup

The backup command uses SQLite's online backup API, checks database integrity, and writes a SHA-256 manifest next to the backup. It runs locally inside the container and does not upload data.

```sh
docker compose exec gridpulse-api python -m gridpulse.backup backup \
  --database /data/gridpulse.sqlite3 --output-dir /data/backups
```

The command prints the exact backup filename and manifest filename. Preserve both files together. Verify a backup before relying on it:

```sh
docker compose exec gridpulse-api python -m gridpulse.backup verify \
  --backup /data/backups/EXACT-BACKUP-FILENAME.sqlite3
```

Replace the example filename with the exact name printed by the backup command. For disaster recovery, copy the database backup and its JSON manifest to a separately managed, access-controlled location. A backup stored only in the same Docker volume is not protection against volume loss.

## Restore procedure — destructive operation

Restore is a deliberate operator action; the API does not expose a remote restore endpoint. First verify the backup, then stop the application so no writer is using the database:

```sh
docker compose exec gridpulse-api python -m gridpulse.backup verify \
  --backup /data/backups/EXACT-BACKUP-FILENAME.sqlite3
docker compose stop gridpulse-api
docker compose run --rm --no-deps gridpulse-api python -m gridpulse.backup restore \
  --backup /data/backups/EXACT-BACKUP-FILENAME.sqlite3 \
  --destination /data/gridpulse.sqlite3 --overwrite
docker compose up -d gridpulse-api
docker compose ps
docker compose logs --tail=100 gridpulse-api
```

The restore command refuses to overwrite an existing destination unless `--overwrite` is supplied, verifies the backup hash and SQLite integrity, stages the restored copy, and checks the staged database before replacing the destination. Confirm the API health endpoint and application records after restoration. Keep a separate pre-restore copy before performing recovery on important data.

## Limitations

- The utility verifies file integrity and a SHA-256 manifest; it does not encrypt backups, store them off-site, schedule backups, or guarantee recovery-point/recovery-time objectives.
- Anyone with access to the Docker volume or backup files may be able to read the data. Apply filesystem and host access controls and encryption at rest as required.
- Restore requires the application to be stopped. Do not treat the command as an automatic failover mechanism.
- There is no live SCADA/DCS/EMS or dispatch integration. The platform is engineering decision support, not a plant control system or work-permit authority.

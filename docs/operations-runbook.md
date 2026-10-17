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

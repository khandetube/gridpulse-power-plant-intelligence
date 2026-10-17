"""Safe SQLite backup, verification, and opt-in restore utilities.

Use this utility against the application's configured database file. It does not
upload backups or expose a network endpoint. Restore always stages and verifies
a copy before replacing the destination.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _integrity_check(path: Path) -> list[str]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Database file is missing or empty: {path}")
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)) as db:
            rows = [str(row[0]) for row in db.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Unable to read SQLite database: {exc}") from exc
    if rows != ["ok"]:
        raise ValueError("SQLite integrity_check failed: " + "; ".join(rows[:10]))
    return rows


def create_backup(database: Path, output_dir: Path) -> dict[str, Any]:
    """Create an online, consistent SQLite backup and a SHA-256 manifest."""
    database = database.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Source database does not exist: {database}")
    _integrity_check(database)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = output_dir / f"gridpulse-{stamp}.sqlite3"
    if backup.exists():
        raise FileExistsError(f"Backup already exists: {backup}")
    fd, temporary_name = tempfile.mkstemp(prefix=".gridpulse-backup-", suffix=".sqlite3", dir=output_dir)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with (
            closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=10)) as source,
            closing(sqlite3.connect(temporary, timeout=10)) as target,
        ):
            source.backup(target)
            target.commit()
        _integrity_check(temporary)
        os.replace(temporary, backup)
        manifest = {
            "format": "gridpulse-sqlite-backup-v1",
            "created_at": datetime.now(UTC).isoformat(),
            "database_file_name": database.name,
            "backup_file_name": backup.name,
            "size_bytes": backup.stat().st_size,
            "sha256": _sha256(backup),
            "integrity_check": "ok",
            "restore_note": "Restore only after stopping application writers and verifying the target path.",
        }
        manifest_path = backup.with_suffix(backup.suffix + ".json")
        manifest_tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
        manifest_tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(manifest_tmp, manifest_path)
        return {"backup": str(backup), "manifest": str(manifest_path), **manifest}
    finally:
        temporary.unlink(missing_ok=True)


def verify_backup(backup: Path) -> dict[str, Any]:
    backup = backup.expanduser().resolve()
    _integrity_check(backup)
    manifest_path = backup.with_suffix(backup.suffix + ".json")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Backup manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Backup manifest is unreadable: {exc}") from exc
    if manifest.get("format") != "gridpulse-sqlite-backup-v1":
        raise ValueError("Unsupported backup manifest format")
    actual_hash = _sha256(backup)
    if manifest.get("sha256") != actual_hash:
        raise ValueError("Backup SHA-256 does not match its manifest")
    if manifest.get("size_bytes") != backup.stat().st_size:
        raise ValueError("Backup size does not match its manifest")
    return {"backup": str(backup), "integrity_check": "ok", "sha256": actual_hash,
            "size_bytes": backup.stat().st_size, "manifest": str(manifest_path)}


def restore_backup(backup: Path, destination: Path, *, overwrite: bool = False) -> dict[str, Any]:
    """Restore a verified backup to a destination; existing files require explicit overwrite."""
    backup = backup.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if backup == destination:
        raise ValueError("Backup and destination must be different paths")
    verify_backup(backup)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Destination exists; pass --overwrite to replace it: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".gridpulse-restore-", suffix=".sqlite3",
                                          dir=destination.parent)
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with (
            closing(sqlite3.connect(f"{backup.as_uri()}?mode=ro", uri=True, timeout=10)) as source,
            closing(sqlite3.connect(temporary, timeout=10)) as target,
        ):
            source.backup(target)
            target.commit()
        _integrity_check(temporary)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Destination exists; pass --overwrite to replace it: {destination}")
        os.replace(temporary, destination)
        return {"restored_to": str(destination), "integrity_check": "ok",
                "sha256": _sha256(destination), "size_bytes": destination.stat().st_size}
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local GridPulse SQLite backup tools (no network upload).")
    commands = parser.add_subparsers(dest="command", required=True)
    backup_cmd = commands.add_parser("backup", help="create a consistent backup")
    backup_cmd.add_argument("--database", type=Path, required=True)
    backup_cmd.add_argument("--output-dir", type=Path, required=True)
    verify_cmd = commands.add_parser("verify", help="verify hash and SQLite integrity")
    verify_cmd.add_argument("--backup", type=Path, required=True)
    restore_cmd = commands.add_parser("restore", help="restore a verified backup to a local file")
    restore_cmd.add_argument("--backup", type=Path, required=True)
    restore_cmd.add_argument("--destination", type=Path, required=True)
    restore_cmd.add_argument("--overwrite", action="store_true",
                             help="allow replacing an existing destination file")
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = create_backup(args.database, args.output_dir)
        elif args.command == "verify":
            result = verify_backup(args.backup)
        else:
            result = restore_backup(args.backup, args.destination, overwrite=args.overwrite)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

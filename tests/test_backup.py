import json
import sqlite3

import pytest

from gridpulse.backup import create_backup, restore_backup, verify_backup


def database(path, value="original"):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE records (record_id TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO records VALUES ('record-1', ?)", (value,))


def test_backup_verify_and_restore_round_trip(tmp_path):
    source = tmp_path / "source.sqlite3"
    backups = tmp_path / "backups"
    destination = tmp_path / "restored.sqlite3"
    database(source)

    result = create_backup(source, backups)
    backup = backups / result["backup_file_name"]
    manifest = backup.with_suffix(backup.suffix + ".json")
    assert manifest.is_file()
    assert verify_backup(backup)["integrity_check"] == "ok"

    restored = restore_backup(backup, destination)
    assert restored["integrity_check"] == "ok"
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT value FROM records WHERE record_id='record-1'").fetchone()[0] == "original"


def test_restore_refuses_existing_destination_without_explicit_overwrite(tmp_path):
    source = tmp_path / "source.sqlite3"
    database(source)
    result = create_backup(source, tmp_path / "backups")
    backup = tmp_path / result["backup_file_name"]
    destination = tmp_path / "destination.sqlite3"
    database(destination, "keep-me")

    with pytest.raises(FileExistsError):
        restore_backup(backup, destination)
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT value FROM records").fetchone()[0] == "keep-me"

    restore_backup(backup, destination, overwrite=True)
    with sqlite3.connect(destination) as db:
        assert db.execute("SELECT value FROM records").fetchone()[0] == "original"


def test_verify_detects_backup_tampering(tmp_path):
    source = tmp_path / "source.sqlite3"
    database(source)
    result = create_backup(source, tmp_path / "backups")
    backup = tmp_path / result["backup_file_name"]
    manifest_path = backup.with_suffix(backup.suffix + ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256"):
        verify_backup(backup)


def test_backup_rejects_missing_source_and_restore_same_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "missing.sqlite3", tmp_path / "backups")
    source = tmp_path / "source.sqlite3"
    database(source)
    result = create_backup(source, tmp_path / "backups")
    backup = tmp_path / result["backup_file_name"]
    with pytest.raises(ValueError, match="different paths"):
        restore_backup(backup, backup)

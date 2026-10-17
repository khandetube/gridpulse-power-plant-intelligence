import sqlite3

import pytest

from gridpulse.storage import ObservationStore


def observation(record_id: str, *, plant: str = "Plant A", metric: str = "generation"):
    return {
        "record_id": record_id,
        "plant": plant,
        "metric": metric,
        "value": 12.5,
        "unit": "MWh",
        "period_start": "2026-01-01",
        "period_end": "2026-01-01",
        "scope": "unit",
        "source_id": "SRC-1",
        "verification_status": "reviewed",
    }


def test_insert_and_filter_persisted_observations(tmp_path):
    store = ObservationStore(tmp_path / "gridpulse.db")
    assert store.insert_many([observation("a"), observation("b", plant="Plant B")]) == 2
    records, total = store.list_records(plant="Plant A", limit=10)
    assert total == 1
    assert records[0]["record_id"] == "a"
    assert records[0]["created_at"].endswith("Z")


def test_duplicate_batch_rolls_back_atomically(tmp_path):
    store = ObservationStore(tmp_path / "gridpulse.db")
    store.insert_many([observation("existing")])
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_many([observation("new"), observation("existing")])
    records, total = store.list_records()
    assert total == 1
    assert [record["record_id"] for record in records] == ["existing"]


def test_pagination_reports_total(tmp_path):
    store = ObservationStore(tmp_path / "gridpulse.db")
    store.insert_many([observation("a"), observation("b"), observation("c")])
    records, total = store.list_records(limit=1, offset=1)
    assert total == 3
    assert len(records) == 1



def test_observation_quality_report_summarizes_provenance_and_coverage(tmp_path):
    store = ObservationStore(tmp_path / "quality.db")
    store.insert_many([observation("a"), observation("b", plant="Plant B")])
    report = store.observation_quality_report()
    assert report["overview"]["total_records"] == 2
    assert report["overview"]["plant_count"] == 2
    assert report["verification_status_counts"] == {"reviewed": 2}
    assert report["scope_counts"] == {"unit": 2}
    assert report["overview"]["source_count"] == 1
    assert any("not independently certified" in note for note in report["integrity_notes"])



def test_ingestion_audit_records_are_written_atomically(tmp_path):
    store = ObservationStore(tmp_path / "audit.db")
    store.insert_many([observation("obs-a")])
    audit, total = store.list_audit_events(entity_type="observation")
    assert total == 1
    assert audit[0]["entity_id"] == "obs-a"
    assert audit[0]["action"] == "created"
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_many([observation("obs-b"), observation("obs-a")])
    audit, total = store.list_audit_events(entity_type="observation")
    assert total == 1
    assert [row["entity_id"] for row in audit] == ["obs-a"]

import sqlite3

import pytest

from gridpulse.storage import ObservationStore


def event(event_id: str, *, plant: str = "Plant A", equipment: str = "GT-1"):
    return {
        "event_id": event_id,
        "plant": plant,
        "equipment": equipment,
        "event_type": "inspection",
        "start_time": "2026-01-01T08:00:00+00:00",
        "end_time": "2026-01-01T10:00:00+00:00",
        "timezone": "UTC",
        "source_id": "SRC-1",
        "verification_status": "reviewed",
        "notes": "Test record",
    }


def test_maintenance_events_persist_and_filter(tmp_path):
    store = ObservationStore(tmp_path / "gridpulse.db")
    assert store.insert_maintenance_many([event("m1"), event("m2", equipment="ST-1")]) == 2
    records, total = store.list_maintenance_events(equipment="GT-1", limit=10)
    assert total == 1
    assert records[0]["event_id"] == "m1"


def test_maintenance_date_filter_includes_overlapping_events(tmp_path):
    store = ObservationStore(tmp_path / "gridpulse.db")
    record = event("m1")
    record["start_time"] = "2025-12-31T23:30:00+00:00"
    record["end_time"] = "2026-01-01T00:30:00+00:00"
    store.insert_maintenance_many([record])
    records, total = store.list_maintenance_events(
        start_date="2026-01-01T00:00:00",
        end_date="2026-01-02T00:00:00",
    )
    assert total == 1
    assert records[0]["event_id"] == "m1"


def test_duplicate_maintenance_event_batch_is_atomic(tmp_path):
    store = ObservationStore(tmp_path / "gridpulse.db")
    store.insert_maintenance_many([event("existing")])
    with pytest.raises(sqlite3.IntegrityError):
        store.insert_maintenance_many([event("new"), event("existing")])
    records, total = store.list_maintenance_events()
    assert total == 1
    assert [record["event_id"] for record in records] == ["existing"]



def test_maintenance_summary_groups_elapsed_hours_without_claiming_downtime(tmp_path):
    store = ObservationStore(tmp_path / "summary.db")
    first = event("one")
    second = event("two", equipment="ST-1")
    second["event_type"] = "corrective"
    second["start_time"] = "2026-01-02T08:00:00+00:00"
    second["end_time"] = "2026-01-02T11:00:00+00:00"
    store.insert_maintenance_many([first, second])
    summary = store.summarize_maintenance_events(plant="Plant A")
    assert summary["total_events"] == 2
    assert len(summary["by_event_type"]) == 2
    assert sum(row["elapsed_hours"] for row in summary["by_event_type"]) == pytest.approx(5.0, abs=0.01)
    assert "not equipment downtime" in summary["duration_semantics"]

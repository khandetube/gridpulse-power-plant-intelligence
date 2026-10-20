from gridpulse import agent_run_store


def test_run_ledger_persists_metadata_and_result(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_AGENT_DB_PATH", str(tmp_path / "state" / "runs.sqlite3"))
    metadata = {"template": "power", "prompt_sha256": "a" * 64}
    result = {"agent": "GridPulse", "execution_trace": [{"iteration": 1}]}

    recorded = agent_run_store.record_completed_run(metadata, result)
    detail = agent_run_store.get_run(recorded["run_id"])

    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["result"] == result
    assert detail["request_fingerprint"] == recorded["request_fingerprint"]
    assert "prompt" not in detail


def test_run_ledger_lists_newest_and_bounds_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_AGENT_DB_PATH", str(tmp_path / "runs.sqlite3"))
    first = agent_run_store.record_completed_run({"n": 1}, {"n": 1})
    second = agent_run_store.record_completed_run({"n": 2}, {"n": 2})

    records = agent_run_store.list_runs(limit=1)

    assert len(records) == 1
    assert records[0]["run_id"] == second["run_id"]
    assert records[0]["run_id"] != first["run_id"]
    try:
        agent_run_store.list_runs(limit=101)
    except ValueError as exc:
        assert "between 1 and 100" in str(exc)
    else:
        raise AssertionError("expected bounded history limit")


def test_run_ledger_returns_none_for_unknown_or_invalid_id(tmp_path, monkeypatch):
    monkeypatch.setenv("GRIDPULSE_AGENT_DB_PATH", str(tmp_path / "runs.sqlite3"))
    assert agent_run_store.get_run("not-a-uuid") is None

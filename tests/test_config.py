from pathlib import Path

from gridpulse.config import source_registry_path


def test_source_registry_respects_explicit_data_directory(tmp_path, monkeypatch):
    expected = tmp_path / "mounted-data" / "source_registry.csv"
    monkeypatch.setenv("GRIDPULSE_DATA_DIR", str(expected.parent))

    assert source_registry_path() == expected


def test_default_source_registry_resolves_repository_data_or_container_mount(monkeypatch):
    monkeypatch.delenv("GRIDPULSE_DATA_DIR", raising=False)
    result = source_registry_path()

    assert result.name == "source_registry.csv"
    assert result.is_absolute()

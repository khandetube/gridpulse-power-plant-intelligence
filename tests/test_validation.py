import pytest
from gridpulse.validation import DatasetValidationError, validate_observation_rows

BASE = {"record_id":"OBS-001", "plant":"Demo Plant", "metric":"net_generation", "value":"12.5", "unit":"MWh", "period_start":"2026-01-01", "period_end":"2026-01-31", "scope":"plant", "source_id":"SRC-DEMO", "verification_status":"unverified"}

def test_valid_row_normalizes_numeric_value():
    result = validate_observation_rows([BASE])
    assert result[0]["value"] == 12.5
    assert result[0]["period_start"] == "2026-01-01"

@pytest.mark.parametrize("field,value", [("value","not-a-number"),("value","NaN"),("period_start","01/01/2026"),("period_end","2025-12-31"),("scope","unknown"),("verification_status","confirmed-ish"),("source_id","")])
def test_rejects_invalid_values(field, value):
    row = dict(BASE); row[field] = value
    with pytest.raises(DatasetValidationError):
        validate_observation_rows([row])

def test_rejects_duplicate_ids():
    second = dict(BASE); second["value"] = "14"
    with pytest.raises(DatasetValidationError, match="duplicate"):
        validate_observation_rows([BASE, second])

def test_rejects_empty_dataset():
    with pytest.raises(DatasetValidationError, match="no observation"):
        validate_observation_rows([])

def test_rejects_missing_fields():
    row = dict(BASE); del row["source_id"]
    with pytest.raises(DatasetValidationError, match="missing columns"):
        validate_observation_rows([row])

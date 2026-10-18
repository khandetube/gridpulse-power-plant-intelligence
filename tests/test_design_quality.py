from gridpulse.design_quality import evaluate_design_quality


def test_quality_gate_finds_missing_routes_and_open_design_basis():
    result = evaluate_design_quality(
        {"assets": [{"id": "P-1", "x": 1, "y": 2, "z": 0}], "routes": []},
        {"calculations": [], "rule_checks": []},
        {"calculations": [], "rule_checks": []},
        {},
        {"unknowns": ["approved design basis"]},
    )
    assert result["gate"] == "review_required"
    codes = {item["code"] for item in result["findings"]}
    assert "ROUTES_MISSING" in codes
    assert "DESIGN_BASIS_OPEN" in codes
    assert len(result["model_fingerprint_sha256"]) == 64


def test_quality_gate_blocks_negative_geometry_and_failed_rule():
    result = evaluate_design_quality(
        {"assets": [{"id": "P-1", "length": -2}], "routes": []},
        {"calculations": [], "rule_checks": [{"id": "R-1", "status": "fail"}]},
        {"calculations": [], "rule_checks": []},
        {},
        {"unknowns": []},
    )
    assert result["gate"] == "blocked"
    codes = {item["code"] for item in result["findings"]}
    assert "GEOMETRY_NEGATIVE" in codes
    assert "RULE_CHECK_FAILURES" in codes


def test_quality_gate_fingerprint_is_stable_and_changes_with_model():
    args = (
        {"assets": [{"id": "A", "x": 1}], "routes": []},
        {"calculations": [], "rule_checks": []},
        {"calculations": [], "rule_checks": []},
        {},
        {"unknowns": []},
    )
    first = evaluate_design_quality(*args)
    second = evaluate_design_quality(*args)
    changed = evaluate_design_quality(
        {"assets": [{"id": "A", "x": 2}], "routes": []}, *args[1:]
    )
    assert first["model_fingerprint_sha256"] == second["model_fingerprint_sha256"]
    assert first["model_fingerprint_sha256"] != changed["model_fingerprint_sha256"]

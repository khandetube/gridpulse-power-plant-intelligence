from gridpulse import autonomous_agent


def candidate(fingerprint, gate="review_required", findings=None, mode="deterministic_prompt_parser"):
    if findings is None:
        findings = [{"code": "ROUTES_MISSING", "severity": "high", "message": "No routes."}]
    return {
        "model": {"assets": [{"tag": fingerprint}], "routes": []},
        "interpretation_mode": mode,
        "quality_gate": {
            "gate": gate,
            "counts": {"critical": 0, "high": 1 if findings else 0, "medium": 0},
            "findings": findings,
            "action_queue": [{"code": "ROUTES_MISSING", "action": "Add verified routes."}] if findings else [],
        },
        "ai_reasoning": {"finding_count": len(findings), "next_actions": []},
    }


def test_autonomous_cycle_stops_when_llm_is_not_configured(monkeypatch):
    monkeypatch.setattr(autonomous_agent, "run_design_agent", lambda *args: candidate("A"))
    result = autonomous_agent.run_autonomous_design_cycle("design a plant", use_llm=False)
    assert result["iterations_executed"] == 1
    assert "deterministic screening" in result["stop_reason"]
    assert result["best_candidate"]["model"]["assets"][0]["tag"] == "A"


def test_autonomous_cycle_keeps_best_candidate_and_stops_on_repeat(monkeypatch):
    sequence = iter([candidate("A", mode="llm_structured_spec"), candidate("B", findings=[], mode="llm_structured_spec"), candidate("B", findings=[], mode="llm_structured_spec")])
    monkeypatch.setattr(autonomous_agent, "run_design_agent", lambda *args: next(sequence))
    result = autonomous_agent.run_autonomous_design_cycle("design a plant", max_iterations=3)
    assert result["iterations_executed"] == 3
    assert {item["tool"] for item in result["execution_trace"][0]["tool_audit"]} == {"validate_model", "audit_quality_evidence", "audit_finite_geometry", "audit_asset_envelopes"}
    assert result["stop_reason"] == "no_model_change_detected"
    assert result["best_candidate"]["model"]["assets"][0]["tag"] == "B"


def test_autonomous_cycle_rejects_unbounded_iterations():
    try:
        autonomous_agent.run_autonomous_design_cycle("design a plant", max_iterations=4)
    except ValueError as exc:
        assert "between 1 and 3" in str(exc)
    else:
        raise AssertionError("expected bounded iteration validation")


def test_autonomous_cycle_does_not_pass_when_independent_model_validation_fails(monkeypatch):
    invalid = candidate("A", gate="screening_passed", findings=[])
    monkeypatch.setattr(autonomous_agent, "run_design_agent", lambda *args: invalid)

    result = autonomous_agent.run_autonomous_design_cycle("design a plant", use_llm=False)

    assert result["stop_reason"] != "all_available_screening_checks_passed"
    assert result["execution_trace"][0]["tool_failure_count"] >= 1



def test_asset_envelope_audit_detects_positive_volume_overlap():
    candidate_data = {
        "model": {
            "assets": [
                {"tag": "P-101", "x": 0, "y": 0, "z": 0, "length": 4, "width": 3, "height": 2},
                {"tag": "M-101", "x": 3, "y": 2, "z": 1, "length": 3, "width": 3, "height": 2},
            ]
        }
    }

    result = autonomous_agent._tool_audit_asset_envelopes(candidate_data)

    assert result["ok"] is False
    assert result["overlap_count"] == 1
    assert result["overlaps"][0] == {"asset_a": "P-101", "asset_b": "M-101"}


def test_asset_envelope_audit_allows_touching_faces_and_marks_missing_geometry():
    candidate_data = {
        "model": {
            "assets": [
                {"tag": "P-101", "x": 0, "y": 0, "z": 0, "length": 2, "width": 2, "height": 2},
                {"tag": "T-101", "x": 2, "y": 0, "z": 0, "length": 2, "width": 2, "height": 2},
                {"tag": "U-101", "x": 8, "y": 8},
            ]
        }
    }

    result = autonomous_agent._tool_audit_asset_envelopes(candidate_data)

    assert result["overlap_count"] == 0
    assert result["unassessed_count"] == 1
    assert "U-101" in result["unassessed_assets"][0]
    assert result["ok"] is True

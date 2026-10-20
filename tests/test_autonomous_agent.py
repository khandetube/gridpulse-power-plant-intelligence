from gridpulse import autonomous_agent


def candidate(fingerprint, gate="review_required", findings=None, mode="deterministic_prompt_parser"):
    findings = findings or [{"code": "ROUTES_MISSING", "severity": "high", "message": "No routes."}]
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
    sequence = iter([candidate("A"), candidate("B", findings=[]), candidate("B", findings=[])])
    monkeypatch.setattr(autonomous_agent, "run_design_agent", lambda *args: next(sequence))
    result = autonomous_agent.run_autonomous_design_cycle("design a plant", max_iterations=3)
    assert result["iterations_executed"] == 2
    assert result["stop_reason"] == "no_model_change_detected"
    assert result["best_candidate"]["model"]["assets"][0]["tag"] == "B"


def test_autonomous_cycle_rejects_unbounded_iterations():
    try:
        autonomous_agent.run_autonomous_design_cycle("design a plant", max_iterations=4)
    except ValueError as exc:
        assert "between 1 and 3" in str(exc)
    else:
        raise AssertionError("expected bounded iteration validation")

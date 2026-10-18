from gridpulse.cad_engine_agent import extract_requirements, run_design_agent


def test_requirement_extraction_infers_disciplines():
    result = extract_requirements("combined cycle power plant with transformer, cable tray, DCS and cooling water")
    assert "Electrical" in result["required_disciplines"]
    assert "Instrumentation" in result["required_disciplines"]
    assert "Piping" in result["required_disciplines"]
    assert "power" in result["inferred_plant_types"]


def test_agent_runs_all_stages_and_returns_critique():
    result = run_design_agent(
        "combined cycle power plant with generator, transformer, pumps and control building",
        80, 55,
        ["Mechanical", "Piping", "Electrical", "Instrumentation", "Architecture"],
        "power",
        use_llm=False,
    )
    assert result["agent"].startswith("GridPulse Engineering Design Agent")
    assert len(result["plan"]["phases"]) == 6
    assert result["model"]["assets"]
    assert "topology" in result["intelligence"]
    assert "findings" in result["critique"]
    assert result["metrics"]["assets"] == len(result["model"]["assets"])

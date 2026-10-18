from gridpulse.cad_engine import build_spec
from gridpulse.cad_engine_intelligence import analyze_design_intelligence, infer_system_topology


def test_intelligence_returns_topology_and_actions():
    spec, mode = build_spec(
        "combined cycle power plant with pumps, generator, transformer and control building",
        80, 55,
        ["Mechanical", "Piping", "Electrical", "Instrumentation", "Architecture"],
        "power",
        use_llm=False,
    )
    report = analyze_design_intelligence(spec)
    assert mode == "deterministic_prompt_parser"
    assert report["engine"].startswith("GridPulse Engineering Intelligence")
    assert report["scope"]["assets"] >= 1
    assert "nodes" in report["topology"]
    assert isinstance(report["topology"]["candidate_connections"], list)
    assert 0 <= report["readiness_score"] <= 100


def test_topology_is_traceable_and_non_destructive():
    spec, _ = build_spec("power plant", 80, 55, ["Mechanical", "Electrical"], "power", use_llm=False)
    original_tags = {a.tag for a in spec.assets}
    topology = infer_system_topology(spec)
    assert {n["id"] for n in topology["nodes"]} == original_tags
    assert topology["note"]

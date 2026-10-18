from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_design_ai_copilot_is_a_functional_local_analysis_page():
    page = (ROOT / "docs" / "design-ai-copilot.html").read_text(encoding="utf-8")
    for required in (
        'id="file"',
        'id="json"',
        'id="analyze"',
        'id="export"',
        'id="findings"',
        "function extract(doc)",
        "function run()",
        "duplicate_id",
        "invalid_geometry",
        "overlap_candidate",
        "metadata_gap",
        "gridpulse-design-intelligence-report.json",
        "No engineering-code compliance",
    ):
        assert required in page
    assert 'fetch(' not in page
    assert "XMLHttpRequest" not in page


def test_design_ai_copilot_is_reachable_from_main_and_cad():
    dashboard = (ROOT / "index.html").read_text(encoding="utf-8")
    cad = (ROOT / "docs" / "refinery-a0.html").read_text(encoding="utf-8")
    assert 'href="docs/design-ai-copilot.html"' in dashboard
    assert "design-ai-copilot.html" in cad
    assert 'id="aiCopilotLaunch"' in cad


def test_engineering_sections_link_to_shared_copilot():
    pages = (
        "mep-studio.html",
        "engineering-cad.html",
        "engineering-editor.html",
        "engineering-suite.html",
        "engineering-3d-editor.html",
        "offline-ai-console.html",
        "maintenance-console.html",
        "data-quality-review.html",
        "asset-registry.html",
        "approved-limit-review.html",
        "plant-intelligence-suite.html",
        "engineering-workbench.html",
    )
    for filename in pages:
        page = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert 'href="design-ai-copilot.html"' in page, filename

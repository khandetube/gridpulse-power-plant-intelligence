"""Smoke-test inline JavaScript in static GridPulse pages when Node.js is available."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relative_path",
    [
        "index.html",
        "docs/maintenance-console.html",
        "docs/offline-ai-console.html",
        "docs/plant-intelligence-suite.html",
    ],
)
def test_inline_javascript_syntax(relative_path: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed; GitHub Actions has a separate syntax check.")
    html = Path(relative_path).read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    assert len(scripts) == 1, f"Expected one inline script in {relative_path}"
    with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8") as handle:
        handle.write(scripts[0])
        handle.flush()
        result = subprocess.run(
            [node, "--check", handle.name],
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr

def test_main_dashboard_has_integrated_system_diagnostics() -> None:
    html = Path("index.html").read_text(encoding="utf-8")
    assert 'id="gpAiDiagnostics"' in html
    assert 'id="gpAiDiagnosticsOutput"' in html
    assert 'gpAiRequest("/ready")' in html
    assert 'gpAiRequest("/api/v1/system/diagnostics")' in html
    assert 'gpAiRequest("/api/v1/cad/llm-status")' in html
    assert 'Export diagnostics JSON' in html
    # The API key is session-only; only the API base may be stored.
    assert 'localStorage.setItem("gridpulse-api-key"' not in html


def test_dashboard_exposes_stored_series_ml_screening() -> None:
    html = Path("index.html").read_text(encoding="utf-8")
    assert 'id="gpAiLoadAnomalySeries"' in html
    assert 'id="gpAiAnomalySeries"' in html
    assert 'id="gpAiRunAnomaly"' in html
    assert 'gpAiRequest("/api/v1/observations?limit=1000")' in html
    assert 'gpAiRequest("/api/v1/analytics/anomalies?contamination=0.05"' in html
    assert "not alarms, fault diagnoses, or failure probabilities" in html


def test_dashboard_renders_anomaly_candidates_with_chartjs() -> None:
    html = Path("index.html").read_text(encoding="utf-8")
    assert "chart.js@4.4.9/dist/chart.umd.min.js" in html
    assert 'id="gpAiAnomalyChart"' in html
    assert 'new Chart(document.getElementById("gpAiAnomalyChart")' in html
    assert "MAD candidate" in html
    assert "Chart.js could not load" in html


def test_dashboard_exposes_engineering_unit_converter() -> None:
    html = Path("index.html").read_text(encoding="utf-8")
    assert 'id="gpUnitValue"' in html
    assert 'id="gpUnitFrom"' in html
    assert 'id="gpUnitTo"' in html
    assert 'id="gpUnitConvert"' in html
    assert 'gpAiRequest("/api/v1/analytics/units/convert"' in html
    assert "dimensional compatibility" in html

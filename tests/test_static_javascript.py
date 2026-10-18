"""Smoke-test inline JavaScript in static GridPulse pages when Node.js is available."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

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

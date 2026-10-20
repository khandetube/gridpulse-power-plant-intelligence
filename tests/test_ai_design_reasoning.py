from gridpulse.ai_design_reasoning import run_engineering_reasoning


def test_reasoner_flags_unresolved_route_endpoint():
    result = run_engineering_reasoning(
        {"assets": [{"id": "P-101", "tag": "P-101", "discipline": "Mechanical", "x": 0, "y": 0, "width": 2, "length": 3}],
         "routes": [{"id": "R-1", "from": "P-101", "to": "MISSING"}]}
    )
    assert result["decision"] == "review_required"
    assert any(f["code"] == "AI-003" for f in result["findings"])


def test_reasoner_does_not_invent_geometry():
    result = run_engineering_reasoning(
        {"assets": [{"id": "P-101", "tag": "P-101", "discipline": "Mechanical", "x": 0, "y": 0}], "routes": []}
    )
    assert any(f["code"] == "AI-007" for f in result["findings"])
    assert any("manufacturer" in x.lower() for x in result["limitations"])



def test_reasoner_handles_malformed_and_non_finite_geometry_without_crashing():
    result = run_engineering_reasoning(
        {
            "site_width": 20,
            "site_length": 20,
            "assets": [
                {
                    "id": "P-101",
                    "tag": "P-101",
                    "discipline": "Mechanical",
                    "x": "not-a-number",
                    "y": float("nan"),
                    "width": -2,
                    "length": float("inf"),
                    "height": 1,
                }
            ],
            "routes": [],
        }
    )
    codes = {finding["code"] for finding in result["findings"]}
    assert "AI-018" in codes
    assert "AI-019" in codes

from gridpulse.cad_change_impact import analyze_change_impact


def asset(tag, x=0):
    return {"id": tag, "tag": tag, "discipline": "Mechanical", "x": x, "y": 0, "width": 1, "length": 1, "height": 1}


def test_changed_asset_marks_explicitly_connected_route_for_review():
    before = {"assets": [asset("P-101")], "routes": [{"id": "L-1", "tag": "L-1", "from": "P-101", "to": "P-102"}]}
    after = {"assets": [asset("P-101", 5)], "routes": [{"id": "L-1", "tag": "L-1", "from": "P-101", "to": "P-102"}]}
    result = analyze_change_impact(before, after)
    assert result["changed"] is True
    assert result["asset_changes"]["modified"] == ["P-101"]
    assert result["routes_requiring_review"] == ["L-1"]


def test_added_removed_and_ambiguous_identifiers_are_reported():
    before = {"assets": [asset("P-101"), asset("P-101")], "routes": []}
    after = {"assets": [asset("P-102")], "routes": []}
    result = analyze_change_impact(before, after)
    assert "P-102" in result["asset_changes"]["added"]
    assert "P-101" in result["asset_changes"]["removed"]
    assert result["asset_changes"]["ambiguous_keys"] == ["P-101"]


def test_identical_models_have_stable_fingerprints_and_no_changes():
    model = {"assets": [asset("P-101")], "routes": []}
    a = analyze_change_impact(model, model)
    b = analyze_change_impact(model, model)
    assert a["changed"] is False
    assert a["before_fingerprint"] == a["after_fingerprint"] == b["after_fingerprint"]



def test_changed_asset_marks_route_near_its_old_or_new_footprint():
    before = {
        "assets": [asset("P-101", 0)],
        "routes": [{"id": "L-201", "tag": "L-201", "points": [[1.2, 0.5, 0], [8, 0.5, 0]], "width": 0.2}],
    }
    after = {
        "assets": [asset("P-101", 12)],
        "routes": [{"id": "L-201", "tag": "L-201", "points": [[2, 0.5, 0], [8, 0.5, 0]], "width": 0.2}],
    }
    result = analyze_change_impact(before, after)
    assert result["asset_changes"]["modified"] == ["P-101"]
    assert result["routes_requiring_review"] == ["L-201"]
    assert any("2D proximity" in warning for warning in result["warnings"])



def test_route_segment_crossing_footprint_is_flagged_even_when_endpoints_are_outside():
    before = {
        "assets": [asset("P-101", 0)],
        "routes": [{"id": "L-301", "tag": "L-301", "points": [[-5, 0.5], [8, 0.5]]}],
    }
    after = {
        "assets": [asset("P-101", 20)],
        "routes": [{"id": "L-301", "tag": "L-301", "points": [[-5, 0.5], [8, 0.5]]}],
    }
    result = analyze_change_impact(before, after)
    assert "L-301" in result["routes_requiring_review"]


def test_malformed_or_non_finite_geometry_does_not_crash_impact_analysis():
    before = {"assets": [asset("P-101", 0)], "routes": []}
    after = {
        "assets": [{"id": "P-101", "tag": "P-101", "x": "bad", "y": float("nan"),
                    "width": -1, "length": float("inf")}],
        "routes": [{"id": "L-401", "tag": "L-401", "points": [["bad", 0], [float("inf"), 1]]}],
    }
    result = analyze_change_impact(before, after)
    assert result["changed"] is True
    assert isinstance(result["routes_requiring_review"], list)



def test_workbench_schema_uses_w_h_and_pts_fields():
    before = {
        "assets": [{"id": "P-501", "tag": "P-501", "x": 0, "y": 0, "w": 2, "h": 2}],
        "routes": [{"id": "L-501", "tag": "L-501", "pts": [[-2, 1], [5, 1]]}],
    }
    after = {
        "assets": [{"id": "P-501", "tag": "P-501", "x": 10, "y": 0, "w": 2, "h": 2}],
        "routes": [{"id": "L-501", "tag": "L-501", "pts": [[-2, 1], [5, 1]]}],
    }
    result = analyze_change_impact(before, after)
    assert "L-501" in result["routes_requiring_review"]

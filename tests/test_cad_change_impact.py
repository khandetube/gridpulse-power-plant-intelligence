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

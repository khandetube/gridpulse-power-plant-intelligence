"""Tests for multi-application CAD export adapters."""
import ast
import json

from gridpulse.cad_engine import build_spec
from gridpulse.cad_engine_multiformat import (
    export_multi_application_bundle,
    export_revit_dynamo_python,
    export_3ds_max_script,
)


def test_multi_application_bundle_uses_one_validated_spec():
    spec, _ = build_spec(
        "industrial power plant with piping and electrical equipment",
        80, 55,
        ["Mechanical", "Piping", "Electrical", "Architecture"],
        "power",
        False,
    )
    bundle = export_multi_application_bundle(spec)
    assert set(bundle) == {
        "autocad_model.dxf",
        "3dsmax_generator.ms",
        "revit_dynamo_generator.py",
        "engineering_spec.json",
    }
    assert bundle["autocad_model.dxf"].startswith("0\nSECTION")
    assert "GridPulse 3ds Max generator" in bundle["3dsmax_generator.ms"]
    assert "DirectShape.CreateElement" in bundle["revit_dynamo_generator.py"]
    assert json.loads(bundle["engineering_spec.json"])["assets"]


def test_revit_script_is_valid_python_syntax_and_discloses_limits():
    spec, _ = build_spec("substation", 80, 55, ["Electrical", "Architecture"], "substation", False)
    script = export_revit_dynamo_python(spec)
    ast.parse(script)
    assert "not a native family library" in script
    assert "not auto-converted to MEP systems" in script


def test_3ds_max_script_has_assets_and_routes():
    spec, _ = build_spec("process plant", 80, 55, ["Mechanical", "Piping"], "process", False)
    script = export_3ds_max_script(spec)
    assert "for asset in spec[\"assets\"]" in script
    assert "for route in spec[\"routes\"]" in script
    assert "Conceptual model only" in script

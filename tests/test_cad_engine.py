from gridpulse.cad_engine import (
    EngineeringSpec, build_spec, review_spec, to_dxf, to_openscad, to_svg,
)
from gridpulse.cad_engine_api import GenerateCadRequest, generate_cad


def test_process_prompt_generates_editable_model_and_exports():
    spec, mode = build_spec(
        "Industrial process plant with two pumps, tank, heat exchanger, process pipes and cable tray",
        80, 55, ["Mechanical", "Piping", "Electrical", "Architecture"], "process", False,
    )
    assert mode == "deterministic_prompt_parser"
    assert len(spec.assets) >= 4
    assert len(spec.routes) >= 3
    assert "P-101A" in {item.tag for item in spec.assets}
    assert "TK-101" in {item.tag for item in spec.assets}
    assert review_spec(spec)["engineering_approval"] is False
    assert "NO_ENGINEERING_CALCULATIONS" in {f["code"] for f in review_spec(spec)["geometric_findings"]}
    assert "<svg" in to_svg(spec)
    assert "SECTION" in to_dxf(spec)
    assert "module box_at" in to_openscad(spec)
    assert "not for construction" in to_openscad(spec).lower()


def test_substation_template_generates_electrical_assets():
    spec, _ = build_spec("substation", 100, 80, ["Electrical", "Architecture"], "substation", False)
    assert any(a.tag.startswith("TR-") for a in spec.assets)
    assert any(a.tag.startswith("SWG-") for a in spec.assets)
    assert spec.site_width == 100


def test_spec_rejects_duplicate_tags():
    base = {
        "project_name": "test", "site_width": 20, "site_length": 20, "units": "m",
        "assets": [
            {"tag":"P-101","name":"Pump","discipline":"Mechanical","shape":"pump","x":1,"y":1,"length":2,"width":2,"height":2},
            {"tag":"p-101","name":"Duplicate","discipline":"Mechanical","shape":"box","x":5,"y":5,"length":2,"width":2,"height":2},
        ],
    }
    try:
        EngineeringSpec.model_validate(base)
    except Exception as exc:
        assert "unique" in str(exc).lower()
    else:
        raise AssertionError("duplicate tags must be rejected")


def test_spec_rejects_asset_outside_site():
    data = {
        "site_width": 20, "site_length": 20,
        "assets": [{"tag":"P-101","name":"Pump","discipline":"Mechanical","shape":"pump","x":19,"y":1,"length":2,"width":2,"height":2}],
    }
    try:
        EngineeringSpec.model_validate(data)
    except Exception as exc:
        assert "site boundary" in str(exc).lower()
    else:
        raise AssertionError("out-of-bound geometry must be rejected")


def test_api_generates_consistent_model():
    response = generate_cad(GenerateCadRequest(
        prompt="process plant", site_width=80, site_length=55,
        disciplines=["Mechanical", "Piping", "Electrical"], template="process", use_llm=False,
    ))
    assert response["review"]["engineering_approval"] is False
    assert response["exports"]["plan.svg"].startswith("<svg")
    assert response["exports"]["plan.dxf"].endswith("EOF\n")
    assert response["exports"]["model.scad"].startswith("// GridPulse")


def test_review_detects_actual_3d_envelope_overlap():
    spec = EngineeringSpec.model_validate({
        "site_width": 20, "site_length": 20,
        "assets": [
            {"tag":"P-101","name":"Pump","discipline":"Mechanical","shape":"pump","x":2,"y":2,"z":0,"length":4,"width":3,"height":2},
            {"tag":"M-101","name":"Motor","discipline":"Mechanical","shape":"motor","x":4,"y":3,"z":1,"length":3,"width":3,"height":2},
        ],
    })
    findings = review_spec(spec)["geometric_findings"]
    assert any(item["code"] == "ASSET_ENVELOPE_OVERLAP" for item in findings)

"""Multi-application export adapters for the shared GridPulse EngineeringSpec.

AutoCAD receives an editable DXF. 3ds Max receives a MaxScript generator.
Revit receives a Dynamo Python script which creates conceptual DirectShape
envelopes in an open Revit document; it does not synthesize a native RVT file
without running inside Revit.
"""
from __future__ import annotations

import json

from gridpulse.cad_engine import EngineeringSpec, to_dxf


def export_autocad_dxf(spec: EngineeringSpec) -> str:
    """Export the shared model as editable DXF geometry."""
    return to_dxf(spec)


def export_3ds_max_script(spec: EngineeringSpec) -> str:
    """Build a runnable .ms script for editable conceptual 3ds Max geometry."""
    payload = json.dumps(spec.model_dump(mode="json"), ensure_ascii=False)
    # MaxScript string escaping is handled by JSON's quoted string representation.
    payload_literal = json.dumps(payload, ensure_ascii=True)
    return f'''-- GridPulse 3ds Max generator; conceptual envelopes, not fabrication geometry.
-- Run this script in 3ds Max. Scene units are set to meters where supported.
local specJson = {payload_literal}
local spec = (dotNetClass "System.Web.Script.Serialization.JavaScriptSerializer").Create().DeserializeObject specJson
fn gpBox label pos dims wireColor =
(
    local obj = box length:dims[1] width:dims[2] height:dims[3] pos:pos
    obj.name = label
    obj.wirecolor = wireColor
    obj
)
fn gpRoute label pts radius wireColor =
(
    for i = 1 to (pts.count - 1) do
    (
        local a = [pts[i][1], pts[i][2], pts[i][3]]
        local b = [pts[i+1][1], pts[i+1][2], pts[i+1][3]]
        local delta = b - a
        if (length delta) > 0.001 do
        (
            local obj = cylinder radius:radius height:(length delta) sides:12
            obj.name = label + "_" + (i as string)
            obj.pos = a
            obj.rotation = (rotationTo (normalize delta) [0,0,1])
            obj.wirecolor = wireColor
        )
    )
)
-- Import through the JSON .NET serializer. All dimensions are conceptual model units.
units.systemType = #meters
for asset in spec["assets"] do
(
    local p = asset["x"] as float
    local q = asset["y"] as float
    local z = asset["z"] as float
    local l = asset["length"] as float
    local w = asset["width"] as float
    local h = asset["height"] as float
    local col = if asset["discipline"] == "Electrical" then (color 170 95 190) else (color 225 120 65)
    local obj = gpBox (asset["tag"] + "_" + asset["name"]) [p,q,z] [l,w,h] col
    obj.boxmap = true
)
for route in spec["routes"] do
(
    local pts = #()
    for p in route["points"] do append pts #(p[1] as float, p[2] as float, p[3] as float)
    local col = if route["kind"] == "cable_tray" then (color 150 80 190) else (color 40 130 220)
    gpRoute route["tag"] pts ((route["width"] as float)/2.0) col
)
format "GridPulse: created % assets and % routes. Conceptual model only.\\n" spec["assets"].count spec["routes"].count
'''


def export_revit_dynamo_python(spec: EngineeringSpec) -> str:
    """Generate Python for a Revit Dynamo Python node (IN[0] document optional)."""
    payload = json.dumps(spec.model_dump(mode="json"), ensure_ascii=False)
    encoded = repr(payload)
    return f'''# GridPulse Revit/Dynamo Python node script.
# Paste into a Dynamo Python node in Revit and run with an open project.
# Creates approximate DirectShape solids in Revit internal feet; not a native family library.
import json
import clr
clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager
clr.AddReference("RevitAPI")
from Autodesk.Revit import DB

spec = json.loads({encoded})
doc = DocumentManager.Instance.CurrentDBDocument
if doc is None:
    raise Exception("Open a Revit project before running this Dynamo script.")

# EngineeringSpec dimensions are meters by default; Revit internal length is feet.
scale = 3.280839895013123 if spec.get("units", "m") == "m" else 1.0
created = []
TransactionManager.Instance.EnsureInTransaction(doc)
try:
    for asset in spec.get("assets", []):
        x = float(asset.get("x", 0)) * scale
        y = float(asset.get("y", 0)) * scale
        z = float(asset.get("z", 0)) * scale
        lx = float(asset.get("length", 2)) * scale
        wy = float(asset.get("width", 2)) * scale
        hz = float(asset.get("height", 2)) * scale
        # Revit DirectShape requires closed valid solids; these are bounding envelopes.
        p0 = DB.XYZ(x, y, z)
        p1 = DB.XYZ(x + lx, y, z)
        p2 = DB.XYZ(x + lx, y + wy, z)
        p3 = DB.XYZ(x, y + wy, z)
        loop = DB.CurveLoop()
        loop.Append(DB.Line.CreateBound(p0, p1))
        loop.Append(DB.Line.CreateBound(p1, p2))
        loop.Append(DB.Line.CreateBound(p2, p3))
        loop.Append(DB.Line.CreateBound(p3, p0))
        solid = DB.GeometryCreationUtilities.CreateExtrusionGeometry(
            [loop], DB.XYZ.BasisZ, max(hz, 0.01)
        )
        shape = DB.DirectShape.CreateElement(
            doc, DB.ElementId(DB.BuiltInCategory.OST_GenericModel)
        )
        safe_tag = str(asset.get("tag", "ASSET"))[:60]
        shape.ApplicationId = "GridPulse"
        shape.ApplicationDataId = safe_tag
        shape.Name = safe_tag + " | " + str(asset.get("name", "Conceptual equipment"))[:80]
        shape.SetShape([solid])
        created.append(shape.Id.IntegerValue)
    # Routes are intentionally not auto-converted to MEP systems; that needs
    # Revit pipe/conduit types, connectors, levels, sizes and routing preferences.
finally:
    TransactionManager.Instance.TransactionTaskDone()

OUT = {{
    "created_element_ids": created,
    "count": len(created),
    "warnings": [
        "Conceptual bounding solids only; not manufacturer geometry.",
        "Piping/cable routes are not native Revit MEP systems.",
        "Review coordinates, levels, categories, families and engineering design before use."
    ]
}}
'''


def export_multi_application_bundle(spec: EngineeringSpec) -> dict[str, str]:
    """Return one synchronized set of outputs from the same validated model."""
    payload = json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return {
        "autocad_model.dxf": export_autocad_dxf(spec),
        "3dsmax_generator.ms": export_3ds_max_script(spec),
        "revit_dynamo_generator.py": export_revit_dynamo_python(spec),
        "engineering_spec.json": payload,
    }

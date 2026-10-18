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


def export_engineering_workbook(spec: EngineeringSpec, review: dict | None = None) -> bytes:
    """Create a real multi-sheet XLSX handoff with equipment, routes, coordinates and checks."""
    from io import BytesIO
    from math import dist
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo

    report = review or {"status": "concept_review_only", "engineering_approval": False,
                        "geometric_findings": []}
    wb = Workbook()
    summary = wb.active
    summary.title = "Project Summary"
    equipment = wb.create_sheet("Equipment")
    routes = wb.create_sheet("Routes")
    points = wb.create_sheet("Route Points")
    checks = wb.create_sheet("Design Checks")
    basis = wb.create_sheet("Design Basis")

    navy = "17365D"
    header_fill = PatternFill("solid", fgColor=navy)
    white_bold = Font(color="FFFFFF", bold=True)
    title_font = Font(size=15, bold=True, color=navy)

    summary.append(["GRIDPULSE ENGINEERING HANDOFF"])
    summary["A1"].font = title_font
    summary.append(["Project", spec.project_name])
    summary.append(["Site width", spec.site_width])
    summary.append(["Site length", spec.site_length])
    summary.append(["Units", spec.units])
    summary.append(["Equipment count", len(spec.assets)])
    summary.append(["Route count", len(spec.routes)])
    summary.append(["Route segment count", sum(max(0, len(r.points)-1) for r in spec.routes)])
    summary.append(["Design review status", report.get("status", "concept_review_only")])
    summary.append(["Engineering approval", "NO — qualified review required"])
    summary.append(["Workbook generated by", "GridPulse multi-application CAD engine"])
    summary.append(["Important limitation", "Conceptual geometry only; not approved for construction or procurement."])
    summary.freeze_panes = "A2"
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 90
    summary["A12"].alignment = Alignment(wrap_text=True, vertical="top")
    summary["B12"].alignment = Alignment(wrap_text=True, vertical="top")

    equipment_headers = ["Tag", "Name", "Discipline", "Shape", "X", "Y", "Z",
                         "Length", "Width", "Height", "Diameter", "Material", "Source", "Envelope Volume"]
    equipment.append(equipment_headers)
    for a in spec.assets:
        equipment.append([a.tag, a.name, a.discipline, a.shape, a.x, a.y, a.z,
                          a.length, a.width, a.height, a.diameter, a.material, a.source,
                          round(a.length*a.width*a.height, 4)])
    routes.append(["Tag", "Name", "Discipline", "Kind", "Nominal Size (mm)",
                   "Width", "Specification", "Point Count", "Approx. Centerline Length", "Units"])
    for r in spec.routes:
        length = sum(dist(p1, p2) for p1, p2 in zip(r.points, r.points[1:]))
        routes.append([r.tag, r.name, r.discipline, r.kind, r.nominal_size_mm,
                       r.width, r.specification, len(r.points), round(length, 4), spec.units])
    points.append(["Route Tag", "Route Name", "Point Index", "X", "Y", "Z", "Units"])
    for r in spec.routes:
        for index, (x, y, z) in enumerate(r.points, start=1):
            points.append([r.tag, r.name, index, x, y, z, spec.units])
    checks.append(["Severity", "Finding Code", "Affected Tags", "Finding / Required Action"])
    for item in report.get("geometric_findings", []):
        checks.append([item.get("severity", ""), item.get("code", ""),
                       ", ".join(item.get("items", [])), item.get("message", "")])
    if checks.max_row == 1:
        checks.append(["info", "NO_FINDINGS_RETURNED", "", "No review findings were provided."])
    basis.append(["Design Basis / Assumptions"])
    for entry in spec.design_basis:
        basis.append([entry])
    basis.append(["CRITICAL", "No calculations for pressure, flow, cable sizing, protection, grounding, fire, HVAC, structural design or pipe stress are performed by this workbook."])
    basis.append(["CRITICAL", "Confirm units, coordinates, equipment vendor dimensions, project standards and site survey before using the model."])

    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = False
        if ws.title not in ("Project Summary", "Design Basis"):
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            if ws.max_row > 1 and ws.max_column > 1:
                table_name = "GP" + "".join(ch for ch in ws.title.title() if ch.isalnum())[:20]
                table = Table(displayName=table_name, ref=ws.dimensions)
                table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2",
                    showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=False)
                ws.add_table(table)
        if ws.title not in ("Project Summary", "Design Basis"):
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = white_bold
                cell.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[1].height = 32
        for column in ws.columns:
            letter = column[0].column_letter
            max_length = max((len(str(cell.value or "")) for cell in column[:200]), default=10)
            ws.column_dimensions[letter].width = min(max(max_length + 2, 12), 52)
        for row in ws.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=(ws.title in ("Design Checks", "Design Basis", "Project Summary")))
    output = BytesIO()
    wb.save(output)
    return output.getvalue()

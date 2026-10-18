"""Multi-application export adapters for the shared GridPulse EngineeringSpec.

AutoCAD receives an editable DXF. 3ds Max receives a MaxScript generator.
Revit receives a Dynamo Python script which creates conceptual DirectShape
envelopes in an open Revit document; it does not synthesize a native RVT file
without running inside Revit.
"""
from __future__ import annotations

import base64
import json
from io import BytesIO
from math import dist

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo

from gridpulse.cad_engine import EngineeringSpec, review_spec, to_dxf


def export_autocad_dxf(spec: EngineeringSpec) -> str:
    """Export the shared model as editable DXF geometry."""
    return to_dxf(spec)


def export_3ds_max_script(spec: EngineeringSpec) -> str:
    """Generate dependency-light MaxScript with named editable equipment and route geometry."""
    def quote(value: str) -> str:
        return value.replace("\\\\", "\\\\\\\\").replace('"', '\\"').replace("\\n", " ").replace("\\r", " ")

    lines = [
        "-- GridPulse 3ds Max generator; conceptual geometry only, not fabrication-ready.",
        "units.systemType = #meters",
        "clearSelection()",
    ]
    colors = {
        "Mechanical": "(color 225 120 65)", "Piping": "(color 40 130 220)",
        "Electrical": "(color 170 95 190)", "Instrumentation": "(color 0 150 130)",
        "Fire": "(color 220 40 45)", "HVAC": "(color 40 140 185)",
        "Grounding": "(color 138 109 59)", "Lighting": "(color 213 166 0)",
        "Drainage": "(color 91 140 90)", "Architecture": "(color 99 115 129)",
    }
    for asset in spec.assets:
        label = quote(f"{asset.tag}_{asset.name}")
        x, y, z = asset.x, asset.y, asset.z
        length, width, height = asset.length, asset.width, asset.height
        color = colors.get(asset.discipline, "(color 120 140 160)")
        if asset.shape in {"cylinder", "tank", "vessel", "fan"}:
            radius = (asset.diameter / 2 if asset.diameter else min(length, width) / 2)
            lines.append(
                f'local gpObj = cylinder radius:{max(radius, 0.01):.4f} height:{max(height, 0.01):.4f} '
                f'sides:32 pos:[{x+length/2:.4f},{y+width/2:.4f},{z+height/2:.4f}]'
            )
        else:
            lines.append(
                f'local gpObj = box length:{length:.4f} width:{width:.4f} height:{height:.4f} '
                f'pos:[{x+length/2:.4f},{y+width/2:.4f},{z+height/2:.4f}]'
            )
        lines.append(f'gpObj.name = "{label}"')
        lines.append(f"gpObj.wirecolor = {color}")
    route_colors = {
        "pipe": "(color 40 130 220)", "cable_tray": "(color 170 95 190)",
        "duct": "(color 40 140 185)", "fire": "(color 220 40 45)",
        "grounding": "(color 138 109 59)",
    }
    for route in spec.routes:
        radius = max(route.width / 2, 0.01)
        color = route_colors.get(route.kind, "(color 100 130 150)")
        for index, (start, end) in enumerate(zip(route.points, route.points[1:]), start=1):
            x1, y1, z1 = start
            x2, y2, z2 = end
            label = quote(f"{route.tag}_{index}")
            lines.extend([
                f"local gpA = [{x1:.4f},{y1:.4f},{z1:.4f}]",
                f"local gpB = [{x2:.4f},{y2:.4f},{z2:.4f}]",
                "local gpDelta = gpB - gpA",
                f"if (length gpDelta) > 0.001 do (local gpRoute = cylinder radius:{radius:.4f} height:(length gpDelta) sides:12",
                "gpRoute.pos = (gpA + gpB) / 2",
                "gpRoute.rotation = (rotationTo [0,0,1] (normalize gpDelta))",
                f'gpRoute.name = "{label}"',
                f"gpRoute.wirecolor = {color})",
            ])
    lines.append(
        f'format "GridPulse created {len(spec.assets)} equipment envelopes and {sum(max(0, len(r.points)-1) for r in spec.routes)} route segments. Conceptual only.\\n"'
    )
    return "\n".join(lines) + "\n"


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
        shape_type = str(asset.get("shape", "box"))
        if shape_type in ("cylinder", "tank", "vessel", "fan"):
            radius = max(float(asset.get("diameter") or min(float(asset.get("length", 2)), float(asset.get("width", 2)))) * scale / 2, 0.01)
            profile = [DB.XYZ(x + lx/2 + radius*math.cos(2*math.pi*i/24), y + wy/2 + radius*math.sin(2*math.pi*i/24), z) for i in range(24)]
        else:
            profile = [DB.XYZ(x, y, z), DB.XYZ(x + lx, y, z), DB.XYZ(x + lx, y + wy, z), DB.XYZ(x, y + wy, z)]
        loop = DB.CurveLoop()
        for i in range(len(profile)):
            loop.Append(DB.Line.CreateBound(profile[i], profile[(i+1) % len(profile)]))
        solid = DB.GeometryCreationUtilities.CreateExtrusionGeometry(
            [loop], DB.XYZ.BasisZ, max(hz, 0.01)
        )
        shape = DB.DirectShape.CreateElement(
            doc, DB.ElementId(DB.BuiltInCategory.OST_GenericModel)
        )
        safe_tag = str(asset.get("tag", "ASSET"))[:60]
        shape.ApplicationId = "GridPulse"
        shape.ApplicationDataId = safe_tag
        mark = shape.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        if mark and not mark.IsReadOnly:
            mark.Set(safe_tag)
        comments = shape.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if comments and not comments.IsReadOnly:
            comments.Set(str(asset.get("name", "Conceptual equipment"))[:250])
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
    workbook = export_engineering_workbook(spec, review_spec(spec))
    return {
        "autocad_model.dxf": export_autocad_dxf(spec),
        "3dsmax_generator.ms": export_3ds_max_script(spec),
        "revit_dynamo_generator.py": export_revit_dynamo_python(spec),
        "engineering_spec.json": payload,
        "gridpulse_engineering_handoff.xlsx.base64": base64.b64encode(workbook).decode("ascii"),
    }


def export_engineering_workbook(spec: EngineeringSpec, review: dict | None = None) -> bytes:
    """Create a real multi-sheet XLSX handoff with equipment, routes, coordinates and checks."""
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

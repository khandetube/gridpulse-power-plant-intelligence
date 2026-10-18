"""Parametric, auditable prompt-to-CAD engine for conceptual plant layouts.

This module deliberately generates editable geometry, not a rendered picture. The
optional LLM adapter only proposes a bounded EngineeringSpec; all geometry and
exports are generated and validated deterministically here.
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.request
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

Discipline = Literal["Mechanical", "Piping", "Electrical", "Instrumentation", "Fire", "HVAC", "Grounding", "Lighting", "Drainage", "Architecture"]
Shape = Literal["box", "cylinder", "pump", "tank", "building", "heat_exchanger", "motor", "transformer", "panel", "fan", "vessel"]
RouteKind = Literal["pipe", "cable_tray", "duct", "grounding", "fire"]
MAX_ASSETS = 250
MAX_ROUTES = 500


class CadAsset(BaseModel):
    tag: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    discipline: Discipline
    shape: Shape
    x: float = Field(ge=0, le=500)
    y: float = Field(ge=0, le=500)
    z: float = Field(default=0, ge=0, le=100)
    length: float = Field(default=2, gt=0, le=100)
    width: float = Field(default=2, gt=0, le=100)
    height: float = Field(default=2, gt=0, le=100)
    diameter: float | None = Field(default=None, gt=0, le=50)
    material: str = Field(default="unspecified", max_length=80)
    source: Literal["parsed_prompt", "template", "llm_proposal"] = "template"


class CadRoute(BaseModel):
    tag: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    discipline: Discipline
    kind: RouteKind
    points: list[tuple[float, float, float]] = Field(min_length=2, max_length=100)
    width: float = Field(default=0.15, gt=0, le=5)
    nominal_size_mm: int | None = Field(default=None, ge=10, le=3000)
    specification: str = Field(default="unspecified", max_length=80)

    @model_validator(mode="after")
    def validate_points(self):
        for x, y, z in self.points:
            if not all(math.isfinite(v) for v in (x, y, z)) or not (0 <= x <= 500 and 0 <= y <= 500 and 0 <= z <= 100):
                raise ValueError("route point outside supported design envelope")
        return self


class EngineeringSpec(BaseModel):
    project_name: str = Field(default="GridPulse conceptual plant", min_length=1, max_length=160)
    site_width: float = Field(default=80, ge=10, le=500)
    site_length: float = Field(default=55, ge=10, le=500)
    units: Literal["m", "ft"] = "m"
    design_basis: list[str] = Field(default_factory=list, max_length=80)
    assets: list[CadAsset] = Field(min_length=1, max_length=MAX_ASSETS)
    routes: list[CadRoute] = Field(default_factory=list, max_length=MAX_ROUTES)

    @model_validator(mode="after")
    def validate_model(self):
        tags = [a.tag.casefold() for a in self.assets] + [r.tag.casefold() for r in self.routes]
        if len(tags) != len(set(tags)):
            raise ValueError("all asset and route tags must be unique")
        for a in self.assets:
            if a.x + a.length > self.site_width or a.y + a.width > self.site_length:
                raise ValueError(f"{a.tag} exceeds site boundary")
        for route in self.routes:
            if any(x > self.site_width or y > self.site_length for x, y, _ in route.points):
                raise ValueError(f"{route.tag} exceeds site boundary")
        return self


def _asset(tag: str, name: str, discipline: Discipline, shape: Shape, x: float, y: float,
           length: float, width: float, height: float, z: float = 0) -> CadAsset:
    return CadAsset(tag=tag, name=name, discipline=discipline, shape=shape, x=x, y=y, z=z,
                    length=length, width=width, height=height, source="template")


def build_spec(prompt: str, site_width: float = 80, site_length: float = 55,
               disciplines: list[Discipline] | None = None, template: str = "process",
               use_llm: bool = True) -> tuple[EngineeringSpec, str]:
    """Return validated design spec and provenance of the prompt interpretation."""
    prompt = prompt.strip()
    if not prompt or len(prompt) > 8000:
        raise ValueError("prompt must contain 1–8000 characters")
    if not (10 <= site_width <= 500 and 10 <= site_length <= 500):
        raise ValueError("site dimensions must be between 10 and 500 model units")
    selected = set(disciplines or ["Mechanical", "Piping", "Electrical", "Instrumentation"])
    llm_spec = _try_llm(prompt, site_width, site_length, selected, template) if use_llm else None
    if llm_spec:
        return llm_spec, "llm_structured_spec"
    spec = _template_spec(prompt, site_width, site_length, selected, template)
    return spec, "deterministic_prompt_parser"


def _template_spec(prompt: str, w: float, h: float, selected: set[str], template: str) -> EngineeringSpec:
    p = prompt.casefold()
    assets: list[CadAsset] = []
    routes: list[CadRoute] = []
    basis = [
        "Conceptual geometry generated from prompt keywords and a parametric template.",
        "No vendor dimensions, site survey, approved P&ID, cable schedule or piping specifications were supplied.",
        "Not for construction, procurement, safety certification or plant operation."
    ]
    # Explicit prompt dimensions override the supplied envelope only when safely parseable.
    # Caller-provided dimensions remain authoritative to keep all generated geometry bounded.
    cx, cy = w / 2, h / 2
    if template == "substation" or any(k in p for k in ("substation", "پست برق", "پست فشار قوی")):
        if "Architecture" in selected:
            assets.append(_asset("BLD-CTRL", "Control building", "Architecture", "building", 2, h-12, 14, 9, 4))
        for i, (name, x) in enumerate([("Transformer A", w*.27), ("Transformer B", w*.56)], 1):
            if "Electrical" in selected:
                assets.append(_asset(f"TR-{i:02d}", name, "Electrical", "transformer", x, h*.47, 5, 4, 4))
        for i, x in enumerate([w*.18, w*.36, w*.54, w*.72], 1):
            if "Electrical" in selected:
                assets.append(_asset(f"SWG-{i:02d}", "Switchgear bay", "Electrical", "box", x, h*.22, 4, 7, 3))
    elif template == "power" or any(k in p for k in ("power plant", "combined cycle", "نیروگاه", "سیکل ترکیبی")):
        defaults = [
            ("GT-01", "Gas turbine", "Mechanical", "box", w*.20, h*.46, 9, 5, 5),
            ("HRSG-01", "Heat recovery steam generator", "Mechanical", "box", w*.34, h*.43, 7, 9, 12),
            ("ST-01", "Steam turbine", "Mechanical", "box", w*.51, h*.48, 8, 5, 4),
            ("GEN-01", "Generator", "Electrical", "motor", w*.63, h*.48, 5, 3, 3),
            ("CW-01", "Cooling-water pump", "Mechanical", "pump", w*.72, h*.23, 3, 2, 2),
            ("CTRL-01", "Control building", "Architecture", "building", 2, h-12, 13, 8, 4),
            ("MCC-01", "Motor control center", "Electrical", "panel", 17, h-10, 6, 3, 2.5),
        ]
        for row in defaults:
            tag, name, disc, shape, x, y, lx, wy, z = row
            if disc in selected or (disc == "Architecture" and "Architecture" in selected):
                assets.append(_asset(tag, name, disc, shape, min(x,w-lx-1), min(y,h-wy-1), lx, wy, z))
    elif template == "water" or any(k in p for k in ("water treatment", "wastewater", "تصفیه‌خانه", "تصفیه خانه")):
        defaults = [
            ("TK-101", "Raw water tank", "Mechanical", "tank", w*.12, h*.45, 7, 7, 7),
            ("P-101A", "Feed pump A", "Mechanical", "pump", w*.30, h*.42, 3, 2, 2),
            ("P-101B", "Feed pump B", "Mechanical", "pump", w*.30, h*.26, 3, 2, 2),
            ("FLT-101", "Filter vessel", "Mechanical", "vessel", w*.48, h*.42, 5, 5, 6),
            ("TK-102", "Treated water tank", "Mechanical", "tank", w*.70, h*.42, 7, 7, 7),
        ]
        for tag,name,disc,shape,x,y,lx,wy,z in defaults:
            if disc in selected: assets.append(_asset(tag,name,disc,shape,min(x,w-lx-1),min(y,h-wy-1),lx,wy,z))
    else:
        defaults = [
            ("P-101A", "Process pump A", "Mechanical", "pump", w*.12, h*.25, 3, 2.2, 2),
            ("P-101B", "Process pump B (standby)", "Mechanical", "pump", w*.12, h*.12, 3, 2.2, 2),
            ("TK-101", "Process vessel", "Mechanical", "vessel", w*.37, h*.38, 6, 6, 7),
            ("E-101", "Heat exchanger", "Mechanical", "heat_exchanger", w*.56, h*.43, 5, 3.5, 3.5),
            ("TK-102", "Buffer tank", "Mechanical", "tank", w*.75, h*.30, 5, 5, 5),
            ("BLD-CTRL", "Control building", "Architecture", "building", 2, h-11, 12, 7, 3.5),
            ("MCC-01", "Electrical control panel", "Electrical", "panel", 17, h-9, 4, 2, 2.4),
            ("FAN-01", "Ventilation fan", "HVAC", "fan", w*.78, h*.70, 2, 2, 2),
        ]
        for tag,name,disc,shape,x,y,lx,wy,z in defaults:
            if disc in selected:
                assets.append(_asset(tag,name,disc,shape,min(x,w-lx-1),min(y,h-wy-1),lx,wy,z))
    # Never return an empty model when the user selected a narrow set of disciplines.
    if not assets:
        assets.append(_asset("GEN-001", "Generic equipment placeholder", "Mechanical", "box", 2, 2, 2, 2, 2))
        basis.append("No selected-discipline template assets matched; one generic placeholder was emitted.")
    # Routes are explicitly schematic polylines; they are not hydraulically/electrically sized.
    if "Piping" in selected:
        pipes = [("P-1001", "Process line", "pipe", 0.25), ("CW-1001", "Cooling water", "pipe", 0.2)]
        for idx, (tag, name, kind, size) in enumerate(pipes):
            y = h*(.54 + idx*.06)
            routes.append(CadRoute(tag=tag, name=name, discipline="Piping", kind=kind,
                points=[(w*.16,y,1.5),(w*.32,y,1.5),(w*.48,y,2.0),(w*.62,y,2.0),(w*.76,y,1.5)],
                width=size, nominal_size_mm=150 if idx == 0 else 100, specification="CONCEPT-UNSPECIFIED"))
    if "Electrical" in selected:
        routes.append(CadRoute(tag="CT-1001", name="Main cable tray", discipline="Electrical",
            kind="cable_tray", points=[(w*.12,h*.82,3),(w*.28,h*.82,3),(w*.28,h*.68,3),(w*.68,h*.68,3),(w*.68,h*.52,3)],
            width=0.45, specification="CONCEPT-UNSPECIFIED"))
    if "Grounding" in selected:
        routes.append(CadRoute(tag="GND-001", name="Grounding ring (conceptual)", discipline="Grounding",
            kind="grounding", points=[(1,1,0),(w-1,1,0),(w-1,h-1,0),(1,h-1,0),(1,1,0)], width=.08))
    if "Fire" in selected:
        routes.append(CadRoute(tag="FIRE-001", name="Fire main (conceptual)", discipline="Fire",
            kind="fire", points=[(2,2,.5),(w-2,2,.5),(w-2,h-2,.5),(2,h-2,.5)], width=.18))
    if "HVAC" in selected:
        routes.append(CadRoute(tag="DUCT-001", name="HVAC duct route (conceptual)", discipline="HVAC",
            kind="duct", points=[(2,h-5,3),(w*.3,h-5,3),(w*.3,h*.7,3),(w*.7,h*.7,3)], width=.35))
    if "Lighting" in selected:
        for i in range(1, 5):
            x = w*i/5
            routes.append(CadRoute(tag=f"LGT-{i:02d}", name="Lighting circuit route", discipline="Lighting",
                kind="cable_tray", points=[(x,2,5),(x,h-2,5)], width=.06, specification="CONCEPT-UNSPECIFIED"))
    if "Drainage" in selected:
        routes.append(CadRoute(tag="DRN-001", name="Drainage route (conceptual)", discipline="Drainage",
            kind="pipe", points=[(2,2,.2),(w*.5,2,.1),(w-2,2,.1)], width=.15, specification="GRAVITY-NOT-CALCULATED"))
    # Include explicit caveats rather than silently suggesting these routes were calculated.
    basis += [
        "Pipe diameters, cable tray sizes, elevations and routes are placeholders unless explicitly approved.",
        "No hydraulic, stress, short-circuit, protection, grounding resistance, HVAC load, fire-code or structural calculations were performed."
    ]
    return EngineeringSpec(project_name=f"GridPulse · {template} concept", site_width=w, site_length=h,
        design_basis=basis, assets=assets[:MAX_ASSETS], routes=routes[:MAX_ROUTES])


def _try_llm(prompt: str, w: float, h: float, selected: set[str], template: str) -> EngineeringSpec | None:
    """Optional OpenAI-compatible JSON-spec adapter; fail safely to deterministic mode."""
    base = os.environ.get("GRIDPULSE_LLM_BASE_URL", "").strip().rstrip("/")
    key = os.environ.get("GRIDPULSE_LLM_API_KEY", "").strip()
    model = os.environ.get("GRIDPULSE_LLM_MODEL", "").strip()
    if not (base and key and model):
        return None
    schema_hint = {
        "project_name": "string", "site_width": w, "site_length": h, "units": "m",
        "design_basis": ["assumptions and missing engineering inputs"],
        "assets": [{"tag":"P-101","name":"pump","discipline":"Mechanical","shape":"pump","x":2,"y":2,"z":0,"length":3,"width":2,"height":2,"diameter":None,"material":"unspecified","source":"llm_proposal"}],
        "routes": [{"tag":"P-1001","name":"conceptual route","discipline":"Piping","kind":"pipe","points":[[2,2,1],[5,2,1]],"width":0.2,"nominal_size_mm":100,"specification":"unspecified"}]
    }
    system = ("Convert the user request into a conceptual industrial layout JSON matching the provided schema. "
              "Return JSON only. Do not claim engineering calculations. Use only these disciplines: " +
              ", ".join(sorted(selected)) + ". Keep every coordinate inside site bounds. Mark assets source=llm_proposal. "
              "Do not invent real plant telemetry, standards compliance, vendor facts, or approvals. "
              "Use schematic routes only. Schema example: " + json.dumps(schema_hint))
    body = json.dumps({"model": model, "temperature": 0.1, "messages": [
        {"role":"system","content":system},
        {"role":"user","content":f"Template={template}; site={w}x{h} m. Prompt: {prompt}"}
    ], "response_format":{"type":"json_object"}}).encode()
    req = urllib.request.Request(base + "/chat/completions", data=body, headers={
        "Authorization": "Bearer " + key, "Content-Type":"application/json"
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=18) as response:
            result = json.loads(response.read(1_000_000))
        text = result["choices"][0]["message"]["content"]
        raw = json.loads(text)
        raw["site_width"], raw["site_length"] = w, h
        raw["units"] = "m"
        # Do not allow an LLM to silently add unrequested disciplines.
        raw["assets"] = [a for a in raw.get("assets", []) if a.get("discipline") in selected]
        raw["routes"] = [r for r in raw.get("routes", []) if r.get("discipline") in selected]
        return EngineeringSpec.model_validate(raw)
    except (OSError, urllib.error.URLError, TimeoutError, KeyError, IndexError, TypeError,
            ValueError, ValidationError):
        return None


def to_openscad(spec: EngineeringSpec) -> str:
    """Create an editable parametric OpenSCAD source file in millimetre coordinates."""
    lines = [
        "// GridPulse conceptual CAD export — not for construction.",
        "// Units: millimetres. Dimensions are converted from the model's declared units.",
        f"site_w = {spec.site_width * (1000 if spec.units == 'm' else 304.8):.3f};",
        f"site_l = {spec.site_length * (1000 if spec.units == 'm' else 304.8):.3f};",
        "module box_at(x,y,z,l,w,h){ translate([x,y,z]) cube([l,w,h]); }",
        "module cylinder_at(x,y,z,d,h){ translate([x,y,z]) cylinder(d=d,h=h,$fn=48); }",
        "color([0.12,0.22,0.30,0.18]) translate([0,0,-5]) cube([site_w,site_l,5]);",
    ]
    scale = 1000 if spec.units == "m" else 304.8
    for a in spec.assets:
        x,y,z,l,w,h = [v*scale for v in (a.x,a.y,a.z,a.length,a.width,a.height)]
        safe_tag = re.sub(r"[^A-Za-z0-9_-]", "_", a.tag)
        lines.append(f"// {safe_tag} — {a.name} — {a.discipline}; conceptual envelope")
        if a.shape in {"cylinder","tank","vessel"}:
            d = (a.diameter or min(a.length,a.width))*scale
            lines.append(f"color([0.82,0.55,0.22]) translate([{x+l/2:.3f},{y+w/2:.3f},{z:.3f}]) cylinder(d={d:.3f},h={h:.3f},$fn=48);")
        elif a.shape == "pump":
            lines.append(f"color([0.85,0.42,0.20]) box_at({x:.3f},{y:.3f},{z:.3f},{l:.3f},{w:.3f},{h*.65:.3f});")
            lines.append(f"color([0.48,0.57,0.65]) translate([{x+l*.72:.3f},{y+w/2:.3f},{z+h*.325:.3f}]) rotate([90,0,0]) cylinder(d={min(w,h)*.45*scale:.3f},h={w*.7*scale:.3f},center=true,$fn=32);")
        elif a.shape == "heat_exchanger":
            lines.append(f"color([0.24,0.56,0.75]) box_at({x:.3f},{y:.3f},{z:.3f},{l:.3f},{w:.3f},{h:.3f});")
            lines.append(f"color([0.72,0.78,0.82]) translate([{x+l/2:.3f},{y+w/2:.3f},{z+h/2:.3f}]) rotate([90,0,0]) cylinder(d={min(w,h)*.55*scale:.3f},h={w*1.12*scale:.3f},center=true,$fn=48);")
        else:
            lines.append(f"color([0.27,0.55,0.73]) box_at({x:.3f},{y:.3f},{z:.3f},{l:.3f},{w:.3f},{h:.3f});")
    for r in spec.routes:
        points = [[round(v*scale,3) for v in p] for p in r.points]
        radius = max(r.width*scale/2, 8)
        for idx in range(len(points)-1):
            a,b=points[idx],points[idx+1]
            dx,dy,dz=[b[i]-a[i] for i in range(3)]
            length=math.sqrt(dx*dx+dy*dy+dz*dz)
            if length <= 0: continue
            yaw=math.degrees(math.atan2(dy,dx))
            pitch=math.degrees(math.atan2(dz,math.hypot(dx,dy)))
            color = "[0.15,0.70,0.72]" if r.kind=="pipe" else "[0.70,0.30,0.78]" if r.kind=="cable_tray" else "[0.83,0.24,0.20]"
            lines.append(f"// {r.tag} — {r.name} — schematic, un-sized")
            lines.append(f"color({color}) translate([{a[0]:.3f},{a[1]:.3f},{a[2]:.3f}]) rotate([0,-{pitch:.4f},{yaw:.4f}]) cylinder(r={radius:.3f},h={length:.3f},$fn=16);")
    return "\n".join(lines) + "\n"


def to_dxf(spec: EngineeringSpec) -> str:
    """Minimal ASCII DXF R12 writer for 2D plan footprints and schematic route centerlines."""
    out = ["0","SECTION","2","HEADER","9","$INSUNITS","70","6","0","ENDSEC","0","SECTION","2","ENTITIES"]
    scale = 1000 if spec.units == "m" else 304.8
    def line(x1,y1,x2,y2,layer):
        out.extend(["0","LINE","8",layer,"10",f"{x1*scale:.3f}","20",f"{y1*scale:.3f}","30","0","11",f"{x2*scale:.3f}","21",f"{y2*scale:.3f}","31","0"])
    def text(x,y,label,layer="TAGS"):
        label = label.replace("\n"," ").replace("\r"," ")[:64]
        out.extend(["0","TEXT","8",layer,"10",f"{x*scale:.3f}","20",f"{y*scale:.3f}","30","0","40","250","1",label])
    for a in spec.assets:
        x,y,l,w=a.x,a.y,a.length,a.width
        layer=re.sub(r"[^A-Za-z0-9_-]","_",a.discipline.upper())[:31]
        line(x,y,x+l,y,layer); line(x+l,y,x+l,y+w,layer)
        line(x+l,y+w,x,y+w,layer); line(x,y+w,x,y,layer)
        text(x,y,a.tag)
    for r in spec.routes:
        layer=re.sub(r"[^A-Za-z0-9_-]","_",r.discipline.upper())[:31]
        for a,b in zip(r.points,r.points[1:]): line(a[0],a[1],b[0],b[1],layer)
        text(r.points[0][0],r.points[0][1],r.tag)
    out.extend(["0","ENDSEC","0","EOF"])
    return "\n".join(out) + "\n"


def to_svg(spec: EngineeringSpec) -> str:
    """Generate a scalable, layer-coloured plan preview from the same object model."""
    scale=12
    margin=40
    width,height=spec.site_width*scale+2*margin,spec.site_length*scale+2*margin
    colors={"Mechanical":"#df7834","Piping":"#1976d2","Electrical":"#9b59b6","Instrumentation":"#008f83","Fire":"#e53935","HVAC":"#2c8cbb","Grounding":"#8a6d3b","Lighting":"#d5a600","Drainage":"#5b8c5a","Architecture":"#637381"}
    e=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">', '<rect width="100%" height="100%" fill="#f7fafc"/>', f'<text x="{margin}" y="22" font-size="13" fill="#182433">{_xml(spec.project_name)} — CONCEPT ONLY</text>', f'<rect x="{margin}" y="{margin}" width="{spec.site_width*scale}" height="{spec.site_length*scale}" fill="none" stroke="#34495e" stroke-width="2"/>']
    def xy(x,y): return margin+x*scale, margin+(spec.site_length-y)*scale
    for a in spec.assets:
        x,y=xy(a.x,a.y+a.width); c=colors.get(a.discipline,"#637381")
        if a.shape in {"cylinder","tank","vessel"}:
            rx=a.length*scale/2; ry=a.width*scale/2
            e.append(f'<ellipse cx="{x+rx:.2f}" cy="{y+ry:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" fill="{c}" fill-opacity=".24" stroke="{c}"/>')
        else:
            e.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{a.length*scale:.2f}" height="{a.width*scale:.2f}" fill="{c}" fill-opacity=".20" stroke="{c}" stroke-width="1.5"/>')
        e.append(f'<text x="{x+3:.2f}" y="{y+13:.2f}" font-size="10" fill="#17202a">{_xml(a.tag)}</text>')
    for r in spec.routes:
        pts=[]
        for x,y,z in r.points:
            px,py=xy(x,y); pts.append(f"{px:.2f},{py:.2f}")
        c=colors.get(r.discipline,"#444")
        e.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{c}" stroke-width="{max(1.2,r.width*3):.2f}" stroke-linejoin="round" stroke-linecap="round"/>')
        x,y=xy(*r.points[0][:2]); e.append(f'<text x="{x+3:.2f}" y="{y-3:.2f}" font-size="8" fill="{c}">{_xml(r.tag)}</text>')
    e.append("</svg>")
    return "\n".join(e)


def _xml(text: str) -> str:
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def review_spec(spec: EngineeringSpec) -> dict:
    """Geometric screening only; intentionally not a code or engineering approval."""
    findings=[]
    assets=spec.assets
    for i,a in enumerate(assets):
        for b in assets[i+1:]:
            overlap_x=min(a.x+a.length,b.x+b.length)-max(a.x,b.x)
            overlap_y=min(a.y+a.width,b.y+b.width)-max(a.y,b.y)
            overlap_z=min(a.z+a.height,b.z+b.height)-max(a.z,b.z)
            if overlap_x>0 and overlap_y>0 and overlap_z>0:
                findings.append({"severity":"warning","code":"ASSET_ENVELOPE_OVERLAP","items":[a.tag,b.tag],
                    "message":"Bounding envelopes overlap in 3D; verify geometry, clearances and maintenance access."})
    if not spec.routes:
        findings.append({"severity":"info","code":"NO_ROUTES","items":[],"message":"No system routes were generated."})
    findings.extend([
        {"severity":"critical","code":"NO_ENGINEERING_CALCULATIONS","items":[],"message":"No process, hydraulic, structural, electrical protection, grounding, fire, HVAC or stress calculations were performed."},
        {"severity":"critical","code":"NO_APPROVED_SOURCE_DATA","items":[],"message":"Model has no verified site survey, vendor geometry, approved P&IDs or design standards."}
    ])
    return {"status":"concept_review_only","asset_count":len(spec.assets),"route_count":len(spec.routes),
        "geometric_findings":findings,"engineering_approval":False,
        "exports":["JSON","SVG","DXF-R12","OpenSCAD"],"model_units":spec.units}

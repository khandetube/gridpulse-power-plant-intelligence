"""Evidence-first engineering reasoning; never fabricates missing values."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
CORE = {"mechanical", "piping", "electrical", "instrumentation"}

@dataclass(frozen=True)
class ReasoningFinding:
    code: str
    severity: str
    discipline: str
    title: str
    evidence: str
    action: str
    confidence: float

class EngineeringReasoner:
    """Deterministic, reproducible reasoning over model evidence and requirements."""
    def __init__(self, model: dict[str, Any] | None, requirements: dict[str, Any] | None = None):
        self.model = model or {}
        self.requirements = requirements or {}
        self.assets = self.model.get("assets", []) or []
        self.routes = self.model.get("routes", []) or []
        self.findings: list[ReasoningFinding] = []

    def add(self, code, severity, discipline, title, evidence, action, confidence=0.95):
        self.findings.append(ReasoningFinding(code, severity, discipline, title, evidence, action, confidence))

    def tags(self):
        return {str(a.get("tag", a.get("id", ""))).strip() for a in self.assets if str(a.get("tag", a.get("id", ""))).strip()}

    def endpoints(self):
        out = set()
        for r in self.routes:
            for key in ("from", "to", "source", "target", "from_tag", "to_tag"):
                if r.get(key): out.add(str(r[key]).strip())
        return out

    def assess(self) -> dict[str, Any]:
        tags = self.tags()
        if not self.assets:
            self.add("AI-001", "critical", "general", "No engineering assets", "Model contains zero assets.", "Provide explicit equipment or regenerate the model.", 1.0)
        elif not self.routes:
            self.add("AI-002", "high", "coordination", "No connectivity model", f"{len(self.assets)} assets exist but no routes are defined.", "Define process, electrical, control or utility connectivity, or explicitly document it as out of scope.", .99)

        orphaned = sorted(x for x in self.endpoints() if x not in tags)
        if orphaned:
            self.add("AI-003", "high", "coordination", "Route endpoint is unresolved", f"Unknown endpoint tags: {', '.join(orphaned[:12])}.", "Resolve every route endpoint against a unique asset tag before export.", .99)

        ids = [str(a.get("id", "")) for a in self.assets]
        dup = sorted({x for x in ids if x and ids.count(x) > 1})
        if dup:
            self.add("AI-004", "high", "coordination", "Duplicate asset identifiers", f"Duplicate IDs: {', '.join(dup[:12])}.", "Assign globally unique asset IDs before export.", 1.0)

        present = {str(a.get("discipline", "")).casefold() for a in self.assets}
        expected = {str(x).casefold() for x in self.requirements.get("required_disciplines", [])} or CORE
        missing = sorted(expected - present)
        if missing:
            self.add("AI-005", "medium", "multidiscipline", "Required discipline coverage is incomplete", f"Missing asset disciplines: {', '.join(missing)}.", "Confirm scope or add explicit engineering objects.", .93)

        route_discs = {str(r.get("discipline", "")).casefold() for r in self.routes}
        for d in sorted(expected & {"piping", "electrical", "instrumentation"}):
            if d in present and d not in route_discs:
                self.add("AI-012", "medium", d, "Discipline has no route representation", f"{d} assets exist without a {d} route network.", "Confirm connectivity or add the appropriate route network.", .91)

        sw, sl = self.model.get("site_width"), self.model.get("site_length")
        for a in self.assets:
            tag = str(a.get("tag", a.get("id", "unknown")))
            for f in ("x", "y"):
                if a.get(f) is None:
                    self.add("AI-006", "medium", str(a.get("discipline", "general")), "Asset position is incomplete", f"{tag} has no {f} coordinate.", "Provide an explicit coordinate or run the placement solver.", .99)
            for f in ("width", "length", "height"):
                if a.get(f) is None:
                    self.add("AI-007", "medium", str(a.get("discipline", "general")), "Asset geometry is incomplete", f"{tag} has no {f}.", "Provide manufacturer/project geometry before execution-grade export.", .99)
            if sw is not None and a.get("x") is not None and a.get("length") is not None and float(a["x"])+float(a["length"]) > float(sw):
                self.add("AI-013", "high", str(a.get("discipline", "general")), "Asset exceeds site width", f"{tag} extends beyond the declared site width.", "Move or resize using approved project geometry.", .99)
            if sl is not None and a.get("y") is not None and a.get("width") is not None and float(a["y"])+float(a["width"]) > float(sl):
                self.add("AI-014", "high", str(a.get("discipline", "general")), "Asset exceeds site length", f"{tag} extends beyond the declared site length.", "Move or resize using approved project geometry.", .99)

        for r in self.routes:
            pts = r.get("points") or []
            if len(pts) < 2:
                self.add("AI-015", "high", str(r.get("discipline", "general")), "Route geometry is incomplete", f"{r.get('tag','unknown')} has fewer than two points.", "Provide a valid route polyline.", 1.0)
            elif len({tuple(p) for p in pts if isinstance(p, (list, tuple)) and len(p) == 3}) < 2:
                self.add("AI-016", "medium", str(r.get("discipline", "general")), "Route collapses to one location", f"{r.get('tag','unknown')} has no meaningful span.", "Rebuild the route from verified endpoints.", .99)
            if r.get("kind") == "pipe" and r.get("nominal_size_mm") is None:
                self.add("AI-017", "medium", "piping", "Pipe route has no nominal size", f"{r.get('tag','unknown')} has no nominal_size_mm.", "Supply the approved piping specification before hydraulic/stress use.", .99)

        params = self.requirements.get("explicit_parameters", {})
        required_params = self.requirements.get("required_parameters", []) or []
        missing_params = [str(x) for x in required_params if str(x) not in params]
        if missing_params:
            self.add("AI-008", "high", "general", "Required engineering inputs are missing", f"Missing parameters: {', '.join(missing_params[:15])}.", "Request the design-basis inputs; do not substitute assumed values.", .98)

        basis = " ".join(map(str, self.model.get("design_basis", []) or [])).casefold()
        if not basis or any(x in basis for x in ("not supplied", "unspecified", "placeholder", "conceptual")):
            self.add("AI-009", "medium", "general", "Design basis remains open", "Model contains conceptual or unspecified design-basis statements.", "Attach approved codes, criteria, survey and vendor data before execution use.", .97)

        objective = str(self.requirements.get("objective", "")).casefold()
        if any(x in objective for x in ("for construction", "ifc", "اجرایی", "ساخت", "construction")):
            self.add("AI-010", "high", "general", "Execution intent conflicts with evidence", "The request asks for execution-grade output while the model remains evidence-gated.", "Require verified geometry, calculations, design basis and discipline sign-off before release.", .99)

        connected = self.endpoints()
        if tags and connected and len(tags & connected) / len(tags) < .5:
            self.add("AI-011", "medium", "coordination", "Most assets lack explicit connectivity", f"Only {len(tags & connected)} of {len(tags)} asset tags appear in route endpoints.", "Complete the connectivity model or document intentionally isolated equipment.", .88)

        self.findings.sort(key=lambda f: (RANK.get(f.severity, 9), f.code))
        critical = sum(f.severity == "critical" for f in self.findings)
        blockers = sum(f.severity in {"critical", "high"} for f in self.findings)
        score = max(0, min(100, round(100-critical*25-blockers*8-max(0, len(self.findings)-blockers)*3)))
        decision = "blocked" if critical else "review_required" if blockers else "screening_passed"
        actions=[]; seen=set()
        for f in self.findings:
            if f.action not in seen:
                actions.append({"priority":f.severity,"code":f.code,"action":f.action}); seen.add(f.action)
            if len(actions)>=15: break
        return {
            "engine":"GridPulse Engineering Reasoner v0.2",
            "mode":"deterministic-evidence-first",
            "score":score,"decision":decision,"finding_count":len(self.findings),
            "severity_counts":{s:sum(f.severity==s for f in self.findings) for s in RANK},
            "findings":[asdict(f) for f in self.findings],"action_queue":actions,
            "next_actions":[x["action"] for x in actions],
            "trace":{"assets_examined":len(self.assets),"routes_examined":len(self.routes),"required_disciplines":sorted(expected),"explicit_parameter_count":len(params)},
            "limitations":["No missing engineering value is fabricated.","Deterministic reasoning is auditable but is not an engineering approval authority or a substitute for an external LLM.","Execution-grade dimensions, codes, manufacturer data, survey data and discipline calculations remain required.","screening_passed is not code compliance or construction approval."],
        }

def run_engineering_reasoning(model: dict[str, Any], requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    return EngineeringReasoner(model, requirements).assess()

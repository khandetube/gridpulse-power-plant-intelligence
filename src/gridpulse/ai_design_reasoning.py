"""Deterministic AI-style engineering reasoning layer for GridPulse.

This module does not invent engineering values. It converts explicit requirements and
model evidence into traceable decisions, missing-input questions, topology findings,
and a prioritized action queue. It is intentionally deterministic so every decision
can be audited and reproduced.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


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
    """Traceable reasoning over a model; no fabricated engineering parameters."""

    def __init__(self, model: dict[str, Any], requirements: dict[str, Any] | None = None):
        self.model = model or {}
        self.requirements = requirements or {}
        self.assets = self.model.get("assets", []) or []
        self.routes = self.model.get("routes", []) or []
        self.findings: list[ReasoningFinding] = []

    def _add(self, code: str, severity: str, discipline: str, title: str,
             evidence: str, action: str, confidence: float = 0.95) -> None:
        self.findings.append(ReasoningFinding(code, severity, discipline, title,
                                               evidence, action, confidence))

    def _asset_tags(self) -> set[str]:
        return {str(a.get("tag", a.get("id", ""))).strip() for a in self.assets}

    def assess(self) -> dict[str, Any]:
        tags = self._asset_tags()
        route_endpoints: set[str] = set()
        for route in self.routes:
            for key in ("from", "to", "source", "target", "from_tag", "to_tag"):
                value = route.get(key)
                if value:
                    route_endpoints.add(str(value).strip())

        if not self.assets:
            self._add("AI-001", "critical", "general", "No engineering assets",
                      "The model contains zero assets.",
                      "Provide or generate an explicit equipment model before design review.", 1.0)
        if self.assets and not self.routes:
            self._add("AI-002", "high", "piping", "No connectivity model",
                      f"{len(self.assets)} assets exist but no routes are defined.",
                      "Define process, electrical, control or utility connections before coordination.", 0.99)

        orphaned = sorted(x for x in route_endpoints if x and x not in tags)
        if orphaned:
            self._add("AI-003", "high", "coordination", "Route endpoint is unresolved",
                      f"Endpoints not found in the asset registry: {', '.join(orphaned[:12])}.",
                      "Resolve every route endpoint against a unique equipment tag.", 0.99)

        ids = [str(a.get("id", "")) for a in self.assets]
        duplicate_ids = sorted({x for x in ids if x and ids.count(x) > 1})
        if duplicate_ids:
            self._add("AI-004", "high", "coordination", "Duplicate asset identifiers",
                      f"Duplicate IDs: {', '.join(duplicate_ids[:12])}.",
                      "Assign globally unique asset IDs before export.", 1.0)

        disciplines = {str(a.get("discipline", "")).lower() for a in self.assets}
        expected = {"mechanical", "piping", "electrical", "instrumentation"}
        missing = sorted(x for x in expected if x not in disciplines)
        if missing:
            self._add("AI-005", "medium", "multidiscipline", "Discipline coverage is incomplete",
                      f"No assets were detected for: {', '.join(missing)}.",
                      "Confirm whether these disciplines are out of scope or add their engineering objects.", 0.93)

        for asset in self.assets:
            tag = str(asset.get("tag", asset.get("id", "unknown")))
            for field in ("x", "y"):
                value = asset.get(field)
                if value is None:
                    self._add("AI-006", "medium", str(asset.get("discipline", "general")),
                              "Asset position is incomplete", f"{tag} has no {field} coordinate.",
                              "Provide an explicit coordinate or run the placement solver.", 0.99)
            for field in ("width", "length"):
                value = asset.get(field)
                if value is None:
                    self._add("AI-007", "medium", str(asset.get("discipline", "general")),
                              "Asset geometry is incomplete", f"{tag} has no {field}.",
                              "Provide manufacturer/project geometry before execution-grade export.", 0.99)

        self.findings.sort(key=lambda f: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f.severity, 4))
        blockers = sum(f.severity in {"critical", "high"} for f in self.findings)
        score = max(0, round(100 - len(self.findings) * 4 - blockers * 5))
        return {
            "engine": "GridPulse Engineering Reasoner v0.1",
            "mode": "deterministic-traceable",
            "score": score,
            "decision": "blocked" if any(f.severity == "critical" for f in self.findings) else
                        "review_required" if blockers else "screening_passed",
            "finding_count": len(self.findings),
            "findings": [asdict(f) for f in self.findings],
            "next_actions": [f.action for f in self.findings[:10]],
            "limitations": [
                "No missing engineering value is fabricated.",
                "This is a screening/reasoning layer, not an engineering approval authority.",
                "Execution-grade dimensions, codes and manufacturer data remain required.",
            ],
        }


def run_engineering_reasoning(model: dict[str, Any], requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    return EngineeringReasoner(model, requirements).assess()

"""Bounded autonomous design-review loop with evidence-based stopping conditions.

The controller orchestrates existing design, calculation, reasoning and quality tools.
It never treats a conceptual model as construction-approved and never invents missing inputs.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from gridpulse.cad_engine import EngineeringSpec
from gridpulse.cad_engine_agent import run_design_agent

_GATE_RANK = {"screening_passed": 0, "coordination_review": 1, "review_required": 2, "blocked": 3}


def _fingerprint(model: dict[str, Any]) -> str:
    encoded = json.dumps(model, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _quality_key(result: dict[str, Any]) -> tuple[int, int, int]:
    gate = result.get("quality_gate", {})
    reasoning = result.get("ai_reasoning", {})
    return (
        _GATE_RANK.get(str(gate.get("gate")), 3),
        int(gate.get("counts", {}).get("critical", 0)) * 100
        + int(gate.get("counts", {}).get("high", 0)) * 10
        + int(gate.get("counts", {}).get("medium", 0)),
        int(reasoning.get("finding_count", 0)),
    )


def _tool_validate_model(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate the candidate against the project's typed EngineeringSpec schema."""
    try:
        spec = EngineeringSpec.model_validate(candidate.get("model", {}))
    except (ValidationError, TypeError, ValueError) as exc:
        return {"tool": "validate_model", "ok": False, "error": str(exc)[:500]}
    return {
        "tool": "validate_model",
        "ok": True,
        "asset_count": len(spec.assets),
        "route_count": len(spec.routes),
        "discipline_count": len({item.discipline for item in spec.assets} | {item.discipline for item in spec.routes}),
    }


def _tool_audit_quality_evidence(candidate: dict[str, Any]) -> dict[str, Any]:
    """Check that the quality report carries a structurally consistent evidence list."""
    gate = candidate.get("quality_gate")
    if not isinstance(gate, dict):
        return {"tool": "audit_quality_evidence", "ok": False, "error": "quality_gate is missing or invalid"}
    findings = gate.get("findings", [])
    actions = gate.get("action_queue", [])
    if not isinstance(findings, list) or not isinstance(actions, list):
        return {"tool": "audit_quality_evidence", "ok": False, "error": "findings/action_queue must be lists"}
    return {
        "tool": "audit_quality_evidence",
        "ok": True,
        "finding_count": len(findings),
        "action_count": len(actions),
        "gate": gate.get("gate", "unknown"),
    }


def _tool_audit_finite_geometry(candidate: dict[str, Any]) -> dict[str, Any]:
    """Independently screen numeric geometry fields for non-finite values."""
    model = candidate.get("model", {})
    invalid: list[str] = []
    for index, asset in enumerate(model.get("assets", [])):
        if not isinstance(asset, dict):
            invalid.append(f"assets[{index}] is not an object")
            continue
        for field in ("x", "y", "z", "width", "length", "height", "rotation"):
            value = asset.get(field)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            ):
                invalid.append(f"assets[{index}].{field} is not a finite number")
    for index, route in enumerate(model.get("routes", [])):
        if not isinstance(route, dict):
            invalid.append(f"routes[{index}] is not an object")
            continue
        points = route.get("points", route.get("pts", []))
        if not isinstance(points, list):
            invalid.append(f"routes[{index}] points is not a list")
            continue
        for point_index, point in enumerate(points):
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                invalid.append(f"routes[{index}].points[{point_index}] is malformed")
                continue
            for coordinate in point[:3]:
                if (
                    isinstance(coordinate, bool)
                    or not isinstance(coordinate, (int, float))
                    or not math.isfinite(coordinate)
                ):
                    invalid.append(f"routes[{index}].points[{point_index}] has non-finite coordinates")
                    break
    return {"tool": "audit_finite_geometry", "ok": not invalid, "issues": invalid[:20], "issue_count": len(invalid)}


def _tool_audit_asset_envelopes(candidate: dict[str, Any]) -> dict[str, Any]:
    """Independently detect positive-volume overlaps between axis-aligned asset envelopes.

    This is a screening heuristic, not a substitute for discipline-specific 3D clash detection.
    Assets missing any required coordinate/dimension are reported as unassessed, not assumed clear.
    """
    model = candidate.get("model", {})
    assets = model.get("assets", [])
    if not isinstance(assets, list):
        return {"tool": "audit_asset_envelopes", "ok": False, "error": "assets must be a list"}

    boxes: list[dict[str, Any]] = []
    unassessed: list[str] = []
    invalid: list[str] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            invalid.append(f"assets[{index}] is not an object")
            continue
        tag = str(asset.get("tag", asset.get("id", f"asset-{index}")))
        fields = ("x", "y", "z", "length", "width", "height")
        values: dict[str, float] = {}
        missing = []
        for field in fields:
            value = asset.get(field)
            if value is None:
                missing.append(field)
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                invalid.append(f"{tag}.{field} is not finite numeric geometry")
            else:
                values[field] = float(value)
        if missing:
            unassessed.append(f"{tag}: missing {', '.join(missing)}")
            continue
        if any(values[field] < 0 for field in ("length", "width", "height")):
            invalid.append(f"{tag}: negative envelope dimension")
            continue
        boxes.append({
            "tag": tag,
            "x0": values["x"], "x1": values["x"] + values["length"],
            "y0": values["y"], "y1": values["y"] + values["width"],
            "z0": values["z"], "z1": values["z"] + values["height"],
        })

    overlaps: list[dict[str, str]] = []
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            intersects = all(
                min(first[upper], second[upper]) - max(first[lower], second[lower]) > 1e-9
                for lower, upper in (("x0", "x1"), ("y0", "y1"), ("z0", "z1"))
            )
            if intersects:
                overlaps.append({"asset_a": first["tag"], "asset_b": second["tag"]})

    issues = invalid + [
        f"Potential 3D envelope overlap: {item['asset_a']} / {item['asset_b']}"
        for item in overlaps
    ]
    return {
        "tool": "audit_asset_envelopes",
        "ok": not issues and not unassessed,
        "status": "clear" if not issues and not unassessed else ("incomplete" if not issues else "issues_found"),
        "overlap_count": len(overlaps),
        "overlaps": overlaps[:50],
        "invalid_geometry": invalid[:20],
        "unassessed_assets": unassessed[:50],
        "unassessed_count": len(unassessed),
        "note": "Axis-aligned bounding-box screening only; rotation, access clearances, insulation, maintenance envelopes and discipline-specific rules are not modeled.",
    }


_TOOL_REGISTRY: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "validate_model": _tool_validate_model,
    "audit_quality_evidence": _tool_audit_quality_evidence,
    "audit_finite_geometry": _tool_audit_finite_geometry,
    "audit_asset_envelopes": _tool_audit_asset_envelopes,
}


def _execute_review_tools(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the allowlisted, read-only review tools and retain an auditable result."""
    return [_TOOL_REGISTRY[name](candidate) for name in _TOOL_REGISTRY]


def run_autonomous_design_cycle(
    prompt: str,
    site_width: float = 80,
    site_length: float = 55,
    disciplines: list[str] | None = None,
    template: str = "process",
    use_llm: bool = True,
    max_iterations: int = 3,
) -> dict[str, Any]:
    """Run bounded design → critique → revise cycles and retain the best evidenced candidate."""
    if not 1 <= max_iterations <= 3:
        raise ValueError("max_iterations must be between 1 and 3")

    trace: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    best_key: tuple[int, int, int] | None = None
    best_tool_failures = 0
    seen: set[str] = set()
    working_prompt = prompt.strip()
    stop_reason = "iteration_limit_reached"

    for iteration in range(1, max_iterations + 1):
        candidate = run_design_agent(
            working_prompt, site_width, site_length, disciplines, template, use_llm
        )
        tool_results = _execute_review_tools(candidate)
        tool_failures = sum(not item.get("ok", False) for item in tool_results)
        fingerprint = _fingerprint(candidate["model"])
        repeated = fingerprint in seen
        seen.add(fingerprint)
        key = (*_quality_key(candidate)[:2], _quality_key(candidate)[2] + tool_failures * 1000)
        improved = best_key is None or key < best_key
        if improved:
            best, best_key = candidate, key
            best_tool_failures = tool_failures

        gate = candidate.get("quality_gate", {})
        findings = gate.get("findings", []) or []
        actions = gate.get("action_queue", []) or []
        trace.append({
            "iteration": iteration,
            "model_fingerprint_sha256": fingerprint,
            "interpretation_mode": candidate.get("interpretation_mode"),
            "quality_gate": gate.get("gate", "unknown"),
            "finding_count": len(findings),
            "improved_best_candidate": improved,
            "repeated_model": repeated,
            "tool_audit": tool_results,
            "tool_failure_count": tool_failures,
            "top_findings": [
                {"code": item.get("code"), "severity": item.get("severity"), "message": item.get("message")}
                for item in findings[:8]
            ],
        })

        if (
            gate.get("gate") == "screening_passed"
            and not candidate.get("ai_reasoning", {}).get("finding_count")
            and tool_failures == 0
        ):
            stop_reason = "all_available_screening_checks_passed"
            break
        if repeated:
            stop_reason = "no_model_change_detected"
            break
        if not use_llm or candidate.get("interpretation_mode") != "llm_structured_spec":
            stop_reason = "llm_not_configured_or_not_used; deterministic screening cannot autonomously revise the model"
            break
        if iteration == max_iterations:
            break

        # Feed only traceable review evidence into the next bounded model proposal.
        feedback = "\n".join(
            f"- [{item.get('severity', 'medium')}] {item.get('code', 'REVIEW')}: "
            f"{item.get('message', '')}"
            for item in findings[:12]
        )
        requested_actions = "\n".join(
            f"- {item.get('code', 'ACTION')}: {item.get('action', '')}"
            for item in actions[:12]
        )
        audit_feedback: list[str] = []
        for audit in tool_results:
            if audit.get("ok", False):
                continue
            tool_name = str(audit.get("tool", "review_tool"))
            for overlap in audit.get("overlaps", [])[:12]:
                audit_feedback.append(
                    f"- [independent audit] {tool_name}: potential 3D envelope overlap "
                    f"between {overlap.get('asset_a')} and {overlap.get('asset_b')}; "
                    "revise only if verified geometry supports a safe change."
                )
            for issue in audit.get("issues", [])[:12]:
                audit_feedback.append(f"- [independent audit] {tool_name}: {issue}")
            for issue in audit.get("invalid_geometry", [])[:12]:
                audit_feedback.append(f"- [independent audit] {tool_name}: {issue}")
            for item in audit.get("unassessed_assets", [])[:12]:
                audit_feedback.append(
                    f"- [independent audit] {tool_name}: geometry not assessed ({item}); "
                    "request authoritative dimensions or explicitly keep the issue unresolved."
                )
            if not any(key in audit for key in ("overlaps", "issues", "invalid_geometry")):
                audit_feedback.append(
                    f"- [independent audit] {tool_name}: {audit.get('error', 'audit failed')}"
                )
        combined_feedback = "\\n".join(
            part for part in (feedback, "\\n".join(audit_feedback)) if part
        )
        working_prompt = (
            f"{prompt.strip()}\n\nAUTONOMOUS REVIEW ITERATION {iteration + 1}: "
            "Revise the proposed conceptual EngineeringSpec only where evidence supports a change. "
            "Do not invent missing design-basis, vendor, code, survey, or process values. "
            "Preserve all explicit user constraints. Reported issues to address:\n"
            f"{combined_feedback}\nAction queue:\n{requested_actions}\n"
            "If a finding cannot be resolved without authoritative input, leave it unresolved and explicit."
        )

    assert best is not None
    return {
        "agent": "GridPulse Bounded Autonomous Engineering Supervisor v0.1",
        "execution_mode": "bounded-plan-propose-review-revise-with-read-only-tool-registry",
        "status": "screening_passed" if stop_reason == "all_available_screening_checks_passed" and best_tool_failures == 0 else "completed_with_findings",
        "iterations_requested": max_iterations,
        "iterations_executed": len(trace),
        "stop_reason": stop_reason,
        "best_candidate_quality": best.get("quality_gate", {}).get("gate"),
        "best_candidate": best,
        "execution_trace": trace,
        "autonomy_limits": [
            "The loop is bounded to at most three iterations and stops on repeated model fingerprints.",
            "Revision requires a configured OpenAI-compatible LLM; without it, only deterministic screening runs.",
            "A screening result is not engineering approval, code compliance, or authorization for construction or plant control.",
            "The internal allowlisted tool registry validates the typed model, audits quality evidence, screens finite geometry, and flags axis-aligned 3D envelope overlaps; incomplete asset envelopes fail closed; tools are read-only.",
            "External tools, live telemetry, SCADA/dispatch, procurement, and file-system actions are not autonomously connected by this controller.",
        ],
    }

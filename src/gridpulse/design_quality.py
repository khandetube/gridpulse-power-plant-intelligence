"""Deterministic, traceable design-quality gate for GridPulse.

This module does not certify code compliance or modify engineering inputs. It
surfaces contradictory, out-of-range, incomplete, or untraceable results so an
engineer can resolve them explicitly.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evaluate_design_quality(
    model: dict[str, Any],
    calculations: dict[str, Any],
    advanced_calculations: dict[str, Any],
    intelligence: dict[str, Any],
    requirements: dict[str, Any],
) -> dict[str, Any]:
    """Create a deterministic quality gate, audit fingerprint, and action queue."""
    findings: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    def add(code: str, severity: str, message: str, action: str, evidence: Any = None) -> None:
        findings.append({"code": code, "severity": severity, "message": message, "evidence": evidence})
        actions.append({"priority": {"critical": 0, "high": 1, "medium": 2, "low": 3}[severity],
                        "code": code, "action": action, "evidence": evidence})

    assets = model.get("assets", []) or []
    routes = model.get("routes", []) or []
    if not assets:
        add("MODEL_EMPTY", "critical", "The model contains no assets.", "Resolve prompt interpretation and generate a non-empty model.")
    if len(assets) == 1:
        add("MODEL_SINGLE_ASSET", "high", "A single asset cannot demonstrate system coordination.", "Add explicitly required equipment and verify the resulting connections.")
    if not routes:
        add("ROUTES_MISSING", "high", "No routes are available for route-level coordination review.", "Specify actual route endpoints and disciplines; do not infer process connectivity as approved.")

    ids: list[str] = []
    duplicate_ids: list[str] = []
    for item in [*assets, *routes]:
        if not isinstance(item, dict):
            add("MODEL_ITEM_INVALID", "high", "A model item is not a structured object.", "Inspect model generation and schema validation.")
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            add("MODEL_ID_MISSING", "high", "A model item has no stable identifier.", "Assign a unique stable ID before downstream export.")
        elif item_id in ids:
            duplicate_ids.append(item_id)
        ids.append(item_id)
        for field in ("x", "y", "z", "length", "width", "height", "diameter"):
            value = item.get(field)
            if value is not None and not _finite_number(value):
                add("GEOMETRY_NONFINITE", "high", f"Item {item_id or '(no ID)'} has a non-finite {field}.", "Correct the explicit geometry value and regenerate exports.", {"item_id": item_id, "field": field})
            elif field in ("length", "width", "height", "diameter") and _finite_number(value) and value < 0:
                add("GEOMETRY_NEGATIVE", "high", f"Item {item_id or '(no ID)'} has negative {field}.", "Correct the dimension from approved source data.", {"item_id": item_id, "field": field, "value": value})
    if duplicate_ids:
        add("MODEL_DUPLICATE_IDS", "high", "Duplicate model identifiers can break references and exports.", "Make all asset and route IDs unique.", sorted(set(duplicate_ids)))

    calc_items = (calculations.get("calculations", []) or []) + (advanced_calculations.get("calculations", []) or [])
    calc_ids = [str(c.get("id", "")) for c in calc_items if isinstance(c, dict)]
    duplicates = sorted({cid for cid in calc_ids if cid and calc_ids.count(cid) > 1})
    if duplicates:
        add("CALC_DUPLICATE_IDS", "high", "Calculation IDs are not unique across calculation layers.", "Namespace calculation IDs and preserve stable references.", duplicates)

    insufficient = sum(1 for c in calc_items if isinstance(c, dict) and c.get("status") == "insufficient_input")
    failed = sum(1 for c in calc_items if isinstance(c, dict) and c.get("status") in ("fail", "error"))
    if insufficient:
        add("CALC_INPUT_GAPS", "medium", f"{insufficient} calculation(s) are blocked by missing or invalid inputs.", "Supply verified values with units and provenance; do not substitute defaults.", {"count": insufficient})
    if failed:
        add("CALC_FAILURES", "high", f"{failed} calculation(s) report failure or error status.", "Investigate the reported calculation and resolve the cause before using its outputs.", {"count": failed})

    rules = (calculations.get("rule_checks", []) or []) + (advanced_calculations.get("rule_checks", []) or [])
    rule_failures = [r for r in rules if isinstance(r, dict) and r.get("status") == "fail"]
    if rule_failures:
        add("RULE_CHECK_FAILURES", "high", f"{len(rule_failures)} rule check(s) failed.", "Review each failed rule against the explicitly supplied design basis and applicable code edition.", [r.get("id") for r in rule_failures])

    unknowns = requirements.get("unknowns", []) or []
    if unknowns:
        add("DESIGN_BASIS_OPEN", "medium", "The requirements record contains unresolved design-basis or interface unknowns.", "Resolve project design basis, codes, vendor data and authoritative interfaces.", unknowns)

    # Stable canonical hash enables comparisons between runs; timestamp deliberately excluded.
    canonical = json.dumps(model, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    actions.sort(key=lambda item: (item["priority"], item["code"]))
    for action in actions:
        action["priority"] = ("critical", "high", "medium", "low")[action["priority"]]

    critical = sum(1 for f in findings if f["severity"] == "critical")
    high = sum(1 for f in findings if f["severity"] == "high")
    gate = "blocked" if critical or failed or rule_failures else "review_required" if high or findings else "screening_passed"
    return {
        "engine": "GridPulse Design Quality Gate v0.1",
        "gate": gate,
        "model_fingerprint_sha256": fingerprint,
        "counts": {
            "assets": len(assets), "routes": len(routes), "calculations": len(calc_items),
            "calculations_insufficient_input": insufficient, "calculations_failed": failed,
            "rule_failures": len(rule_failures), "findings": len(findings),
            "critical": critical, "high": high, "medium": sum(1 for f in findings if f["severity"] == "medium"),
        },
        "findings": findings,
        "action_queue": actions,
        "limitations": [
            "This is a structural and traceability gate, not an engineering safety score or code-compliance certificate.",
            "A stable fingerprint detects model changes; it does not prove correctness.",
            "All geometry, connections, calculation inputs and applicable code requirements require qualified discipline review.",
        ],
    }

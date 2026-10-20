"""Model-to-model change impact analysis for GridPulse.

Compares stable asset/route identifiers and reports downstream objects that may
need re-review. It does not claim physical causality beyond explicit connectivity.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _index(items: list[dict[str, Any]], key_fields: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in items:
        key = next((str(item.get(field)).strip() for field in key_fields if item.get(field) not in (None, "")), "")
        if key:
            # Duplicate keys are preserved as an explicit ambiguity marker.
            if key in result:
                result[key] = {"__duplicate_key__": True}
            else:
                result[key] = item
    return result


def _endpoint_set(route: dict[str, Any]) -> set[str]:
    return {str(route[k]).strip() for k in ("from", "to", "source", "target", "from_tag", "to_tag") if route.get(k) not in (None, "")}


def _route_near_asset(route: dict[str, Any], asset: dict[str, Any], tolerance: float = 0.5) -> bool:
    """Approximate 2D plan proximity; intentionally not a clash/clearance check."""
    try:
        x, y = float(asset["x"]), float(asset["y"])
        width, length = float(asset["width"]), float(asset["length"])
        buffer = max(tolerance, float(route.get("width", 0) or 0))
        for point in route.get("points", []) or []:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            px, py = float(point[0]), float(point[1])
            if x - buffer <= px <= x + length + buffer and y - buffer <= py <= y + width + buffer:
                return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return False


def analyze_change_impact(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic added/removed/modified objects and connected review scope."""
    old_assets = _index(before.get("assets", []) or [], ("id", "tag"))
    new_assets = _index(after.get("assets", []) or [], ("id", "tag"))
    old_routes = _index(before.get("routes", []) or [], ("id", "tag"))
    new_routes = _index(after.get("routes", []) or [], ("id", "tag"))

    def compare(old: dict[str, dict[str, Any]], new: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
        added = sorted(set(new) - set(old))
        removed = sorted(set(old) - set(new))
        modified = sorted(k for k in set(old) & set(new) if _fingerprint(old[k]) != _fingerprint(new[k]))
        ambiguous = sorted(k for k in set(old) | set(new) if old.get(k, {}).get("__duplicate_key__") or new.get(k, {}).get("__duplicate_key__"))
        return {"added": added, "removed": removed, "modified": modified, "ambiguous_keys": ambiguous}

    asset_changes = compare(old_assets, new_assets)
    route_changes = compare(old_routes, new_routes)
    changed_assets = set(asset_changes["added"] + asset_changes["removed"] + asset_changes["modified"])
    changed_routes = set(route_changes["added"] + route_changes["removed"] + route_changes["modified"])

    affected_routes = []
    changed_asset_models = [
        asset for key, asset in old_assets.items() if key in changed_assets and not asset.get("__duplicate_key__")
    ] + [
        asset for key, asset in new_assets.items() if key in changed_assets and not asset.get("__duplicate_key__")
    ]
    for tag, route in new_routes.items():
        explicit_link = bool(_endpoint_set(route) & changed_assets)
        geometric_proximity = any(_route_near_asset(route, asset) for asset in changed_asset_models)
        if tag in changed_routes or explicit_link or geometric_proximity:
            affected_routes.append(tag)
    for tag, route in old_routes.items():
        explicit_link = bool(_endpoint_set(route) & changed_assets)
        geometric_proximity = any(_route_near_asset(route, asset) for asset in changed_asset_models)
        if tag not in new_routes and (explicit_link or geometric_proximity):
            affected_routes.append(tag)
    affected_routes = sorted(set(affected_routes))

    warnings = []
    if asset_changes["ambiguous_keys"] or route_changes["ambiguous_keys"]:
        warnings.append("Duplicate stable identifiers make some comparisons ambiguous; resolve identifiers before relying on this report.")
    if changed_assets or changed_routes:
        warnings.append("Impact is based on object diffs, explicit endpoints and approximate 2D proximity of route points to changed asset footprints; this is not a clash/clearance check and hidden dependencies may be missed.")
    if not changed_assets and not changed_routes:
        warnings.append("No differences were detected for indexed assets/routes; unindexed objects and external dependencies are not assessed.")

    return {
        "engine": "GridPulse Change Impact Analyzer v1.0",
        "mode": "deterministic-model-diff",
        "before_fingerprint": _fingerprint(before),
        "after_fingerprint": _fingerprint(after),
        "changed": bool(changed_assets or changed_routes),
        "summary": {
            "assets_added": len(asset_changes["added"]),
            "assets_removed": len(asset_changes["removed"]),
            "assets_modified": len(asset_changes["modified"]),
            "routes_added": len(route_changes["added"]),
            "routes_removed": len(route_changes["removed"]),
            "routes_modified": len(route_changes["modified"]),
            "routes_requiring_review": len(affected_routes),
        },
        "asset_changes": asset_changes,
        "route_changes": route_changes,
        "routes_requiring_review": affected_routes,
        "recommended_actions": [
            *([f"Review changed asset(s): {', '.join(sorted(changed_assets)[:20])}."] if changed_assets else []),
            *([f"Recheck route(s): {', '.join(affected_routes[:20])}."] if affected_routes else []),
            *([ "Resolve duplicate identifiers before accepting the change report."] if asset_changes["ambiguous_keys"] or route_changes["ambiguous_keys"] else []),
        ],
        "warnings": warnings,
        "limitations": [
            "Route-to-asset proximity uses a simple 2D footprint buffer; it is not a clash, clearance, elevation or physical dependency solver.",
            "No engineering value, approval, or code-compliance claim is generated.",
            "A qualified discipline review remains required for safety-critical changes.",
        ],
    }

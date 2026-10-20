# CAD Change Impact Analysis

Endpoint: `POST /api/v1/cad/impact-analysis`

Request body contains two validated `EngineeringSpec` objects: `before` and `after`.

The analyzer compares assets and routes by stable `id` (falling back to `tag`), creates SHA-256 fingerprints, identifies added/removed/modified objects, and flags routes whose explicit endpoints reference changed assets or whose route points fall within a conservative 2D buffer of a changed asset footprint. Duplicate stable identifiers are reported as ambiguous rather than silently trusted.

Example request shape:

```json
{
  "before": {"project_name": "example", "assets": [], "routes": []},
  "after": {"project_name": "example", "assets": [], "routes": []}
}
```

Use the complete schema emitted by `POST /api/v1/cad/generate` in real requests; the abbreviated example above is illustrative only and may not satisfy model validation.

## Boundaries

- This is deterministic change tracking, not a physical simulation or a generative AI model.
- Impact propagation uses explicit endpoint fields where present, plus approximate 2D route-point proximity to changed asset footprints. This is not a 3D clash, elevation, access-clearance or physical dependency solver.
- Changes may affect unstored dependencies such as loads, protection coordination, supports, access/maintenance clearances, hydraulics, controls or cable sizing.
- Reports identify objects for re-review; they do not approve changes or assert code compliance.

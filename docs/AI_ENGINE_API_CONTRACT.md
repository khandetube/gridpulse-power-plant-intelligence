# AI Engine API Contract

The CAD UI should consume AI reasoning as model data, not as decorative status badges.

Expected reasoning payload:

```json
{
  "engine": "GridPulse Engineering Reasoner v0.1",
  "decision": "review_required",
  "score": 72,
  "finding_count": 3,
  "findings": [
    {
      "code": "AI-003",
      "severity": "high",
      "discipline": "coordination",
      "title": "Route endpoint is unresolved",
      "evidence": "...",
      "action": "Resolve every route endpoint...",
      "confidence": 0.99
    }
  ],
  "next_actions": ["..."],
  "limitations": ["..."]
}
```

The UI can use this contract to focus the model on a finding, select affected assets, and prevent an execution-grade export while blockers remain.

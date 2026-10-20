# AI Engineering Engine Roadmap

Implemented now:
- evidence-first deterministic reasoning
- topology endpoint validation
- duplicate asset detection
- multidisciplinary coverage screening
- geometry completeness screening
- severity-ranked findings and next actions

Next integration layers:
1. connect reasoner to `run_design_agent`
2. expose findings through `/api/v1/cad/agent`
3. allow UI to focus/select affected model objects
4. block execution-grade export when quality gate is blocked
5. add graph-based topology reasoning
6. add clash resolution proposals with explicit assumptions
7. add scenario comparison and design-change impact analysis

The roadmap deliberately separates reasoning from approval. AI recommendations remain auditable and require project-authoritative inputs.

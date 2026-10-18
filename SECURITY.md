# Security Policy

## Supported version

Security fixes are applied to the default branch while this project is in active development. There is no production support SLA.

## Reporting a vulnerability

Please do not publish secrets, API keys, private operational data, plant network details, or exploit steps in a public issue.

Use GitHub's private vulnerability reporting feature for this repository when available. If private reporting is unavailable, contact the repository maintainer privately through GitHub before sharing technical details publicly. Include the affected file/endpoint, impact, reproducible steps using synthetic data, and any suggested mitigation.

## Deployment warning

GridPulse is an actively developed research and engineering decision-support project. It has not undergone an independent penetration test and must not be exposed directly to the public internet or connected to operational technology. The static GitHub Pages dashboard is public; never place API keys, credentials, confidential plant data, or private endpoint tokens in its HTML or browser storage.

The API container is configured for production-mode authentication and binds to loopback via Compose. Operators must configure a unique high-entropy `GRIDPULSE_API_KEY`, keep it outside source control, restrict host access, and use a reviewed TLS/network boundary before any remote deployment.

# Recon QA roadmap

Recon is alpha software. The current priority is a dependable path from an OpenAPI document to an understandable test report.

## Current

- OpenAPI 3.x and Swagger 2.0 discovery
- Schema-driven API test generation
- Bounded concurrent execution and stateful request chaining
- Optional Playwright page discovery and browser checks
- Deterministic failure classification and self-contained HTML/JSON reports
- Optional LLM-assisted test generation and failure analysis
- Local reproducible demo and PyPI distribution

## Next

- Validate clean installation on Windows, macOS, and Linux
- Expand real-world OpenAPI compatibility fixtures
- Improve authentication setup and document unsupported flows
- Add copy-paste CI examples for GitHub Actions
- Make reports easier to compare between runs
- Document stable extension points for custom checks

## Exploring

- Importing existing API test collections
- Team-oriented report history
- Framework-specific remediation hints

Priorities should follow reproducible user reports rather than feature count. Please open an issue with a sanitized spec or minimal example when possible.

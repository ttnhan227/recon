# Changelog

All notable changes to **Recon** (`recon-qa`) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.1] - 2026-08-30

### Added
- **Multi-Provider AI Engine**: Added direct lightweight REST integrations for Google Gemini (`gemini-2.5-flash`), OpenAI (`gpt-4o`), Anthropic Claude (`claude-3-5-sonnet`), Mistral (`mistral-large`), and local Ollama (`llama3`).
- **Parallel AI Root Cause Analysis**: Upgraded RCA to run instant deterministic categorization across 100% of test failures while executing deep AI diagnostic hypotheses concurrently (< 2s).
- **Playwright Browser Crawling**: Autonomous UI exploration mode (`--browser`) detecting interactive buttons, forms, links, and capturing visual failure states.
- **Automated CI/CD Workflow**: Added GitHub Actions release pipeline with automated testing, packaging, and PyPI distribution.

### Fixed
- Fixed property lookup reference in failure analysis sampling.
- Fixed JSON delimiter handling when parsing structured LLM responses.
- Improved report path discovery and automatic browser launching across operating systems.

---

## [0.1.0] - 2026-08-28

### Added
- **Autonomous Discovery**: OpenAPI 3.0 / 3.1 / Swagger auto-detection and endpoint parameter extraction.
- **Combinatorial Test Generator**: Automatic planning of Happy Path, Boundary (overflow/empty values), Negative (type mismatch), Validation, and Security test suites.
- **Concurrent Worker Pool**: Bounded async test execution with real-time latency and status telemetry.
- **HTML & JSON Reporting**: Standalone interactive HTML dashboard and machine-readable execution logs.
- **CLI Suite**: `scan`, `generate`, `test`, `analyze`, `report`, `doctor`, `providers`, and `serve-demo` commands.

# Changelog

All notable changes to **Recon** (`recon-qa`) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.2] - 2026-08-31

### Added
- **Centralized Project-Scoped Storage (`~/.recon/reports/{project}/`)**: Automatically isolates test reports and SQLite database into `~/.recon/reports/{project}/` and `~/.recon/recon.db` using intelligent project slug detection, keeping target repositories completely clean.
- **Centralized Patch Backup Storage (`~/.recon/backups/{project}/`)**: `.recon.bak` backup files generated during self-healing are stored in `~/.recon/backups/{project}/` instead of cluttering target source trees.
- **Fast Incremental Testing (`recon test --failed-only` / `-f`)**: Re-executes only previously failed test cases loaded directly from `latest.json` or SQLite history for ultra-fast delta regression cycles.
- **Adaptive LLM Rate-Limit Backoff (HTTP 429 Resilience)**: Added automatic exponential backoff retry mechanisms across Gemini, OpenAI, Claude, Mistral, and OpenAI-Compatible API providers when encountering HTTP 429 rate limit errors.
- **AST-Level Compilation Safety Gate**: Python AST syntax and compilation verification ensures generated self-healing patches never introduce syntax errors before applying to target code.

### Fixed
- **Windows SQLite URI Normalization**: Fixed Windows path backslashes causing `[Errno 11001] getaddrinfo failed` DNS lookup errors on SQLite database URLs.
- **Unified Diff Fuzzy Matcher**: Improved patch applier hunk matching for multiline string blocks and docstrings.
- **CLI Import & Path Resolution**: Fixed missing `TestStep` import in CLI test runner and improved path resolution for reports.

---

## [0.1.1] - 2026-08-30

### Added
- **Autonomous Self-Healing (`recon fix`)**: Automated codebase scanning, controller/schema localization, Unified Diff patch synthesis, safe backup creation (`.recon.bak`), and single-test re-verification.
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

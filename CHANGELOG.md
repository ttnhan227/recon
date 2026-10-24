# Changelog

All notable changes to **Recon** (`recon-qa`) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] - 2026-10-25

### Added
- **Autonomous QA & Engineering Agent (`recon agent`)**: Natural language goal execution and interactive chat mode (`ReconMasterAgent`) coupled with autonomous browser agent (`ReconBrowserAgent`) capable of navigating, filling forms, and verifying web applications with Playwright.
- **Autonomous Self-Healing Code Repair (`recon fix`)**: Automatically locates defect handler source files and lines via AST/regex parsing, synthesizes minimal, targeted bug fixes using LLM reasoning, and renders colorized unified diffs.
- **Streamlined 7-Command CLI**: Simplified CLI down to 7 essential, focused commands (`test`, `agent`, `fix`, `report`, `config`, `demo`, `doctor`), emphasizing the 1-command testing workflow (`recon test <target>`).
- **Modern 2026 AI Model Catalog**: Built-in support and pre-configured defaults for current frontier and efficient models:
  - **Google Gemini**: `gemini-3.5-flash`, `gemini-3.8-flash`, `gemini-4-argon`, `gemini-3.5-flash-lite`, `gemini-3.6-flash`.
  - **OpenAI**: `gpt-6-luna`, `gpt-6.1-sol`, `gpt-6-astra`.
  - **Anthropic**: `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-5-5`, `claude-fable-5-1`.
  - **Mistral**: `mistral-medium-latest`, `codestral-latest`, `mistral-large-latest`, `mistral-small-latest`.
  - **DeepSeek**: `deepseek-chat` (V3), `deepseek-reasoner` (R1).
- **Unified Local & Cloud Model Architecture**: Zero-key local model support via Ollama (`http://127.0.0.1:11434/v1`), LM Studio, and vLLM with hot-switching via `recon config use <provider>` and `recon config model <model>`.
- **System Diagnostics (`recon doctor`)**: Added comprehensive diagnostics verifying Python runtime, Playwright Chromium binaries, Docker CLI, SQLite persistence, and AI connectivity.

### Fixed
- **Windows Process-Tree Cleanup**: Implemented process tree termination (`taskkill /F /T`) for demo application servers on Windows to prevent orphaned background Uvicorn worker processes from retaining ports.
- **Windows Unicode Encoding**: Hardened Rich console stream output to UTF-8 with `legacy_windows=False` to prevent `charmap` codec crashes on Windows consoles with Unicode icons.
- **Descriptive HTTP Error Diagnostics**: Added structured HTTP error formatting (`_format_http_error`) to parse provider response bodies, surfacing clear status codes and messages (401 invalid key, 403 billing, 429 rate limit, 503 high demand, timeouts) instead of blank exception strings.
- **CI Non-Interactive Stdin Handling**: Added non-interactive tty detection in `recon fix` and `ensure_api_key_configured` to prevent hanging in headless automation or CI pipelines.
- **Report Path Resolution**: Enhanced report resolution in `recon report` and `recon fix` to search across target project slug, working directory slug, and centralized `~/.recon/reports/`.

---

## [0.2.2] - 2026-10-19

### Added
- **Topological Wave Execution**: Bounded worker pool partitions test cases into deterministic dependency tiers (Wave 1: POST root entities, Wave 2: GET list queries, Wave 3: details/validation/boundary, Wave 4: destructive DELETE cleanups, Wave 5: browser checks) to eliminate state race conditions.
- **Markdown Test Reporter**: Added `MarkdownReporter` (`recon.reporting.markdown_reporter`) for CI pipelines and pull request comments, outputting structured run summaries and failure breakdowns.
- **Comprehensive Audit Regression Test Suite**: Added `tests/unit/test_audit_fixes.py` verifying worker pool exception isolation, schema cycle handling, security redaction, and assertion logic.

### Fixed
- **WorkerPool Test Loss Prevention**: Captured unhandled exceptions within worker coroutines, recording them as explicit `TestStatus.ERROR` results with `FailureCategory.INFRASTRUCTURE_ERROR` rather than silently dropping tests from the final count.
- **OpenAPI Circular `$ref` Protection**: Implemented recursion cycle detection in `resolve_ref` and `_resolve_schema` to prevent `RecursionError` crashes on recursive schemas, and added fallback handling for relative server URLs.
- **Sensitive Credential & URL Scrubbing**: Expanded redaction to catch compound key variants (`database_master_password`, `jwt_private_key`, `client_secret`, etc.), scrubbed embedded PEM private key blocks from string payloads, and added `redact_url` to strip sensitive credentials and query tokens from HTTP traces and logs.
- **Browser Automation Resource Cleanup & Assertion Enforcement**: Wrapped Playwright browser lifecycle in a `try...finally: await browser.close()` block to prevent orphan browser processes on aborted steps, and implemented full evaluation of browser step assertions (`RESPONSE_TIME_MS`, `TEXT_VISIBLE`, `ELEMENT_EXISTS`, `URL_MATCHES`).
- **Case-Insensitive HTTP Header Matching**: Normalized HTTP headers to lowercase in `evaluate_assertion` to avoid false assertion failures caused by case sensitivity differences across servers.
- **Status Code Assertion Null Guard**: Guarded against null response status codes in `STATUS_CODE` assertions to prevent false passes when `ne` operators are evaluated against failed connections.
- **Security Failure Classification**: Fixed failure classifier to accurately categorize unauthorized route access failures as `AUTHENTICATION_FAILURE` or `AUTHORIZATION_FAILURE` instead of generic assertion failures.

---

## [0.2.1] - 2026-09-24

### Added
- **One-command local demo**: `recon demo` starts the bundled defective application, runs a deterministic API test suite, and produces an HTML report without external services or an API key.
- **Installed-wheel CI smoke test**: CI now builds and validates both distributions, installs the wheel into a clean environment, and checks the packaged CLI.
- **Open-source project guides**: Added the MIT license, contribution guide, public roadmap, and structured GitHub issue forms.

### Changed
- Reworked the README around a verified two-minute quick start, real commands, safety guidance, current limitations, and a copy-paste CI example.
- Moved pytest and pytest-asyncio out of runtime dependencies and into the development extra.
- Renamed the CLI's failure summary so deterministic analysis is not incorrectly labeled as AI output.

### Fixed
- Ensured the Docker image copies package sources before installing the project.
- Made generated registration workspace names unique across repeated test runs.

---

## [0.1.3] - 2026-08-31

### Added
- **Autonomous Auth & Session Chaining**: Automatically discovers `/api/v1/auth/register` and `/api/v1/auth/login` endpoints on target APIs, creates a synthetic test user session, and extracts the JWT `access_token` into all downstream secured routes when no manual `-H "Authorization: ..."` header is provided.
- **Visibility-Aware Browser Scanning & Smart Selectors**: Playwright crawler now checks real-time DOM element visibility (`is_visible: bool`) and generates accessible text-based selectors (`button:has-text(...)` or `[aria-label=...]`) to prevent unclickable hidden elements inside closed tabs/modals from timing out.
- **Format-Aware Semantic Data Synthesizer**: Auto-generates valid `uuid4` IDs for all path parameters and JSON fields ending in `_id` or `id` (e.g. `workspace_id`, `document_id`) to prevent strict Pydantic/FastAPI UUID validation rejections.
- **Centralized Test Suite Storage (`~/.recon/suites/{project}/`)**: `recon generate` automatically saves test plans to `~/.recon/suites/{project}/test_suite.json`, keeping target project repositories clean.

### Fixed
- **Settings Environment Isolation**: Configured Recon to read exclusively from `~/.recon/.env` so target projects' `.env` files (e.g., PostgreSQL / MySQL connection strings) never collide with Recon's internal database.
- **Resilient AI Exploratory JSON Parsing**: Added regex extraction, code fence stripping, and automatic trailing comma cleanup so LLM test case generation never fails on formatting delimiters.
- **DiscoveredPage Schema Alignment**: Fixed missing attributes (`console_errors`, `buttons`, `links`) in `recon scan` UI table rendering.

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

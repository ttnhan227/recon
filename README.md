<p align="center">
  <img src="docs/assets/banner.svg" alt="Recon Banner" width="100%">
</p>

<p align="center">
  <strong>An automated API testing and root-cause analysis platform that discovers OpenAPI endpoints, plans multi-category test suites, executes with bounded concurrency, and diagnoses failures with AI.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/recon-qa/"><img src="https://img.shields.io/pypi/v/recon-qa.svg" alt="PyPI Version"></a>
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Playwright-Async-45ba4b.svg" alt="Playwright">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</p>

---

## Platform Visual Preview

| Autonomous CLI Test Runner | Interactive HTML Report & RCA |
|:---:|:---:|
| ![Recon Terminal Execution](docs/screenshots/recon-terminal.png) | ![Interactive HTML Report](docs/screenshots/recon-report.png) |

---

## ⚡ Quick Demo (Proof in Action)

```bash
# 1. Install directly from PyPI
pip install recon-qa

# 2. Run automated test suite against any running API or OpenAPI spec
recon test https://petstore.swagger.io/v2/swagger.json --concurrency 4
```

```text
+-----------------------------------------------------------------------------+
| Recon AI QA Agent                                                           |
| Target: https://petstore.swagger.io/v2/swagger.json | Concurrency: 4        |
+-----------------------------------------------------------------------------+
[INFO] Auto-detected OpenAPI specification at swagger.json
[INFO] Generated 24 test cases (Happy Path, Boundary, Validation, Auth)
[INFO] Executing 24 tests with concurrency=4
 PASSED API-001 [POST /v2/pet] Happy Path - Valid Request (42ms)
 PASSED API-002 [GET /v2/pet/findByStatus] Happy Path - Valid Status (38ms)
 FAILED API-003 [POST /v2/pet] Boundary - Empty Body (55ms) - HTTP 400
 PASSED API-004 [GET /v2/user/login] Auth - Valid Credentials (21ms)
 ...
[INFO] Root Cause Analysis Engine:
 ↳ Identified missing required property in payload for /v2/pet (Confidence: 92%)
 ↳ Suggested Fix: Ensure required 'name' and 'photoUrls' fields are provided in request body

+------------------------- Recon Test Run Completed --------------------------+
| Execution Summary                                                           |
|   Total Tests : 24  |  Passed : 22  |  Failed : 2  |  Pass Rate : 91.7%     |
|   HTML Report : reports/run-20260828-095131-1b5354/report.html              |
|   Latest Link : reports/latest.html                                         |
+-----------------------------------------------------------------------------+
```

---

## Architecture & Pipeline

Recon coordinates automated endpoint discovery, test matrix generation, bounded async workers, and dual-layer failure classification.

### End-to-End Execution Flow

```text
Target Application URL / OpenAPI Spec
        │
        ▼
  Discovery Engine ──► OpenAPI 3.x / Swagger Parser & Playwright Crawler
        │
        ▼
  Autonomous Dynamic Auth ──► Schema-driven Auto-Registration & Bearer Token Injection
        │
        ▼
  DAG Test Planner & Ordering
        │
        ├── 1. Root Entity Creation (POST endpoints ──► Harvest IDs into StatePool)
        ├── 2. Stateful Query / Detail Operations (Substitute real entity IDs into {params})
        ├── 3. Boundary & Validation Checks (Empty strings, zero values, negative IDs)
        ├── 4. Strict Enum & Schema Violations (Negative type and enum assertion probes)
        └── 5. Security & Error Handling (401/403 credential rejection & 404 handling)
        │
        ▼
  Async Worker Pool (Bounded Concurrency: 4–16 workers)
        │
        ├── API Runner with Dynamic DAG State Substitution
        └── Browser Runner (Playwright headless DOM navigation)
        │
        ▼
  Evidence Collector (HTTP traces, responses, DOM logs)
        │
        ├── Deterministic Failure Classifier (HTTP 4xx/5xx, timeouts, assertions)
        └── AI Root-Cause Analyzer (Fact extraction ──► Hypothesis ──► Suggested Fix)
        │
        ▼
  Self-Contained Interactive HTML Report + JSON Telemetry
```

### Core Services

| Module | Technology | Role |
|---|---|---|
| Discovery Engine | Pydantic v2 + httpx | Auto-detects OpenAPI 3.0, 3.1 & Swagger 2.0 specs |
| Test Planner & DAG | Python 3.12 AST | Generates categorized test matrices with topological dependency ordering |
| State Pool Engine | Thread-Safe StateStore | Harvests created entity IDs and injects them into downstream test routes |
| Autonomous Auth | Schema-Fuzzed Auth | Pre-flight registration & login flow with recursive JWT token extraction |
| Concurrency Pool | `asyncio` + WorkerPool | Bounded parallel test execution (4–16 workers) |
| RCA Engine | Deterministic + LLM | Rule-based failure classification & AI remediation recommendations |
| Reporting | Jinja2 + Tailwind CSS | Standalone interactive HTML reports with assertion step diffs |
| CLI Interface | Typer + Rich | Colorized terminal telemetry and interactive progress meters |

### Key Infrastructure Decisions

- **Deterministic Testing First** — AI operates as an analytical reasoning layer, not an unpredictable execution engine. Tests pass/fail on concrete assertions.
- **Stateful DAG Dependency Chaining** — Solves synthetic 404s by executing entity creation endpoints first, storing generated IDs in a runtime `StatePool`, and substituting real IDs into dependent `GET`/`PUT` routes.
- **Autonomous Authentication Lifecycle** — Automatically discovers registration/login schemas, registers a test entity, and propagates `Authorization: Bearer <token>` across all protected endpoints.
- **Strict OpenAPI 3.0/3.1 Constraint Fuzzing** — Adheres strictly to `enum`, `minimum`, `maximum`, `minLength`, `format` (`uuid`, `email`, `currency`, `date-time`) specifications for robust validation and negative test matrices.
- **Bounded Worker Pool** — Prevents server overload by capping concurrent asynchronous HTTP connections via asyncio queues.
- **Provider-Agnostic LLM Engine** — Seamless support for Google Gemini, OpenAI, Anthropic Claude, Mistral AI, Ollama, DeepSeek, and custom endpoints.
- **Self-Contained HTML Reports** — Zero external CSS/JS CDN dependencies; all styles, charts, and diffs are inline for offline auditing.

---

## Features

- **Automated OpenAPI Discovery**: Parses OpenAPI 3.0, 3.1, and Swagger 2.0 schemas into strongly-typed parameter trees.
- **Stateful Chaining (DAG)**: Automatically feeds created entity IDs from `POST` responses into subsequent `GET`, `PUT`, and `DELETE` requests.
- **Autonomous Dynamic Auth**: Pre-flight registration and login flow automatically extracts Bearer JWT tokens.
- **Multi-Category Test Suites**: Generates Happy Path, Validation, Boundary, Negative, and Authentication test suites automatically.
- **Asynchronous Execution Pool**: Runs tests in parallel with configurable worker limits (`--concurrency 4-16`).
- **Dual-Layer Root Cause Analysis**: Pairs deterministic HTTP error categorization with confidence-scored AI diagnosis.
- **Multi-Provider AI Intelligence**: Seamless out-of-the-box support for Google Gemini, OpenAI, Claude, Mistral, Ollama, and DeepSeek.
- **Actionable Remediation**: Produces concrete code-fix and payload adjustment recommendations.
- **Interactive HTML & JSON Reports**: Comprehensive dashboard with execution timelines, failure taxonomy, and step traces.

---

## Tech Stack

- **Core Engine**: Python 3.12, Pydantic v2, httpx, asyncio
- **CLI & UX**: Typer, Rich
- **Browser Automation**: Playwright Async
- **Analysis & AI**: Google Gemini, OpenAI, Claude, Mistral, Ollama, DeepSeek
- **Persistence & Reports**: SQLAlchemy, SQLite, Jinja2, HTML5/CSS3
- **Distribution**: PyPI (`recon-qa`)

---

## Getting Started

### 1. Installation

```bash
# Core CLI + AI testing (includes Google Gemini, OpenAI, Claude, Mistral, Ollama)
pip install recon-qa

# With Playwright browser testing support
pip install "recon-qa[browser]"
playwright install chromium
```

### 2. Run Test Suite Against an API

```bash
# Basic test execution with autonomous auth & DAG chaining
recon test http://localhost:8000

# With bounded concurrency & custom OpenAPI path
recon test http://localhost:8000 --spec /api/v1/openapi.json --concurrency 8

# With explicit authorization header if using pre-existing static token
recon test http://localhost:8000 --header "Authorization: Bearer <your-token>"

# With AI Root-Cause Analysis enabled
recon test http://localhost:8000 --ai
```

---

## Testing & Quality Assurance

```bash
# Run unit & integration test suites
pytest tests/ -v

# Run with coverage report
pytest --cov=recon tests/
```

---

## License

MIT

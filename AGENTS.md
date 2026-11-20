# AGENTS.md — Recon QA Contributor & Project Agent Guide

## 1. Project Overview

**Recon QA** (`D:\projects\recon`, package `recon-qa` v`0.3.2`) is a Python 3.12 automated API and browser testing pipeline with deterministic root-cause analysis and optional REST LLM adapters:
- **`recon/common/`:** `config.py` (`ReconSettings`), `models.py`, `security.py` (SSRF & redaction), `exceptions.py`.
- **`recon/discovery/` & `recon/planning/`:** `openapi.py`, `web_crawler.py` (Playwright + `httpx`/`BeautifulSoup` fallback), `schema_fuzzer.py`, `generator.py`.
- **`recon/orchestration/` & `recon/execution/`:** `orchestrator.py`, `state_pool.py`, `worker_pool.py` (5-wave DAG), `api/runner.py`, `api/assertions.py`, `browser/runner.py`, `browser/agent.py`.
- **`recon/analysis/`, `recon/llm/`, `recon/healing/`, `recon/agent/`:** Deterministic RCA, zero-SDK `httpx` LLM providers, AST-validated `PatchApplier`, `ReconMasterAgent`.
- **`recon/apps/`:** Typer CLI (`apps/cli/main.py`, `config_cli.py`, `doctor.py`) and FastAPI server (`apps/api/server.py`).

## 2. Engineering & Safety Boundaries

- **Deterministic Core:** Pass/fail status, schema fuzzing, and deterministic RCA must never depend on an LLM.
- **SSRF & Redaction:** Enforce `validate_target_url()` and `redact_headers`/`redact_sensitive_data` consistently across API runners, browser agents, and self-healing verification.
- **Isolation:** Keep test runs isolated from `~/.recon/recon.db` and `./reports` (use temp paths/fixtures in `tests/`).
- **Documentation & Scope:** Own project-level code, tests, focused commits, and project docs. Do **not** modify `D:\projects\engineering-operations\*` or change central backlog priorities.

## 3. Build, Lint, Typecheck, and Test Commands

Run from `D:\projects\recon`:

```powershell
# Inner-loop targeted pytest
python -m pytest -p no:cacheprovider tests/<test_file>.py

# Full test suite (pre-commit)
python -m pytest -p no:cacheprovider -v tests/

# Static checks (all must pass with 0 issues)
ruff check .
ruff format --check .
mypy recon
```

## 4. Verification & Reporting Notes

- Baseline `pytest` uses FastAPI ASGI + in-memory `aiosqlite` (`84` tests).
- Explicitly report any gaps in live `CliRunner` or live Playwright `WebCrawler`/`BrowserTestRunner` coverage if not exercised.

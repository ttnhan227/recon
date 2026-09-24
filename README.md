<p align="center">
  <img src="https://raw.githubusercontent.com/ttnhan227/recon/main/docs/assets/banner.svg" alt="Recon QA" width="100%">
</p>

<p align="center">
  <strong>Turn an OpenAPI spec into executable API checks and an HTML failure report.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/recon-qa/"><img src="https://img.shields.io/pypi/v/recon-qa.svg" alt="PyPI version"></a>
  <a href="https://github.com/ttnhan227/recon/actions/workflows/ci.yml"><img src="https://github.com/ttnhan227/recon/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <img src="https://img.shields.io/pypi/pyversions/recon-qa.svg" alt="Supported Python versions">
  <a href="https://github.com/ttnhan227/recon/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT license"></a>
</p>

Recon QA discovers endpoints, derives test cases from their schemas, executes them with bounded concurrency, and writes self-contained HTML and JSON reports. It works without an AI account; LLM-assisted generation and failure analysis are optional.

> **Use Recon only on applications you own or are explicitly authorized to test.** Generated requests can create, update, or delete data described by the target API.

## Try it in two minutes

Requires Python 3.12 or newer.

```bash
python -m pip install recon-qa
recon demo
```

`recon demo` starts an intentionally defective application on your machine, tests it, and produces a real report without an API key or external service. Finding failures is the expected successful outcome.

<p align="center">
  <img src="https://raw.githubusercontent.com/ttnhan227/recon/main/docs/assets/demo.gif" alt="Recon QA local demo: installation, OpenAPI discovery, generated checks, detected defects, and HTML report" width="900">
</p>

```bash
recon report
```

That opens the latest report in your browser, with every generated check, observed response, assertion, and failure classification available for review.

## Test your own API

For an application that exposes OpenAPI at a conventional path such as `/openapi.json` or `/swagger.json`:

```bash
recon test http://localhost:8000 --no-ai
```

Pass a non-standard local or remote specification explicitly:

```bash
recon test http://localhost:8000 --spec ./openapi.yaml --no-ai
```

Common options:

```bash
# Include browser discovery and checks
python -m pip install "recon-qa[browser]"
python -m playwright install chromium
recon test http://localhost:8000 --browser --no-ai

# Supply authentication without storing it in Recon configuration
recon test http://localhost:8000 \
  --header "Authorization: Bearer <token>" \
  --no-ai

# Limit a run to selected routes
recon test http://localhost:8000 \
  --include "/api/orders*" \
  --exclude "/api/admin*" \
  --no-ai
```

On PowerShell, replace the trailing `\` characters with backticks or put the command on one line.

Reports are stored under `~/.recon/reports/` by default. Use `--report-dir` to choose another location. A test run exits with code `1` when it finds failed checks, which makes the command useful as a CI quality gate.

## What Recon checks

- Discovers OpenAPI 3.x and Swagger 2.0 operations.
- Generates happy-path, validation, boundary, negative, and authentication cases.
- Uses schema constraints including types, enums, numeric ranges, string lengths, and formats.
- Orders dependent operations and can reuse IDs returned by earlier requests.
- Applies bounded asynchronous concurrency.
- Classifies HTTP, timeout, assertion, and security-related failures.
- Produces standalone HTML reports and machine-readable JSON results.
- Optionally crawls pages and runs Playwright browser checks.
- Optionally asks a configured LLM for additional cases and failure explanations.

Recon is intended to expose suspicious behavior for review. It is not a proof of correctness, a replacement for application-specific tests, or a substitute for a professional security assessment.

## Useful commands

```text
recon demo                 Run the reproducible local example
recon scan <target>        Discover API routes and optional web pages
recon generate <target>    Write the generated test suite as JSON
recon test <target>        Run discovery, generation, execution, and reporting
recon report               Open the latest HTML report
recon doctor               Check the local runtime and optional browser setup
recon providers            Show available AI provider configuration
recon --help               Show every command and option
```

## Optional AI analysis

The default provider is `mock`, a deterministic offline implementation used for development and demonstrations. Real providers are opt-in and use your own credentials.

```bash
recon set-key
recon use openai
recon test http://localhost:8000 --ai
```

Supported REST integrations include Gemini, OpenAI, Anthropic, Mistral, Ollama, and other OpenAI-compatible endpoints. Use `recon providers` to inspect the active configuration. Keep credentials in environment variables or Recon's local configuration—never commit them.

## CI example

```yaml
name: API quality
on: [push, pull_request]

jobs:
  recon:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install recon-qa
      - run: recon test http://127.0.0.1:8000 --no-ai
```

Start your application in an earlier step and upload the chosen report directory as an artifact if the report should be retained.

## How the pipeline fits together

```text
OpenAPI document / application URL
              │
              ▼
       Endpoint discovery
              │
              ▼
  Schema-driven test generation
              │
              ▼
 Stateful, bounded execution ───── optional Playwright checks
              │
              ▼
 Deterministic classification ──── optional LLM analysis
              │
              ▼
        HTML + JSON reports
```

The LLM layer does not decide whether deterministic assertions passed or failed.

## Current limitations

- Python 3.12 or newer is required.
- Authentication discovery handles common flows but cannot infer every custom login or multi-factor workflow.
- Generated payloads are schema-driven and may not satisfy undocumented business rules.
- Browser support requires the `browser` extra and a separate Chromium installation.
- OpenAPI documents that rely heavily on vendor extensions may need a reduced reproduction and compatibility fix.
- The project is alpha software; review generated requests before pointing it at data-bearing environments.

## Development

```bash
git clone https://github.com/ttnhan227/recon.git
cd recon
python -m pip install -e ".[browser,dev]"
python -m playwright install chromium

ruff check .
ruff format --check .
mypy recon tests
pytest -q
python -m build
```

See the [contribution guide](https://github.com/ttnhan227/recon/blob/main/CONTRIBUTING.md) before proposing a change, the [roadmap](https://github.com/ttnhan227/recon/blob/main/ROADMAP.md) for current priorities, and the [changelog](https://github.com/ttnhan227/recon/blob/main/CHANGELOG.md) for release history.

## Feedback wanted

If you try Recon against a real API, please share what worked, what blocked you, and the framework or OpenAPI generator you used in the [trial feedback form](https://github.com/ttnhan227/recon/issues/new?template=feedback.yml). Sanitized minimal specifications are especially useful. See the [technical walkthrough](https://github.com/ttnhan227/recon/blob/main/docs/introducing-recon-qa.md) for a concise explanation you can share with another developer.

## License

Recon QA is available under the [MIT License](https://github.com/ttnhan227/recon/blob/main/LICENSE).

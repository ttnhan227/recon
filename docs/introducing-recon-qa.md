# From OpenAPI to a useful QA report in one command

API teams often have an OpenAPI document but still rely on a narrow set of hand-written happy-path checks. The specification already describes routes, payload types, required fields, enums, and numeric or string constraints. Recon QA turns that information into executable checks and a report a developer can inspect.

## See the complete workflow locally

```bash
python -m pip install recon-qa
recon demo
```

The demo does not call a hosted service or require an AI key. It starts a deliberately defective FastAPI application on localhost, discovers its OpenAPI document, generates schema-driven checks, executes them, and writes an HTML report.

In the verified `0.2.1` demo run, Recon generated 35 checks and identified two deliberately planted problems:

1. An order endpoint returned HTTP 500 when an optional currency value was empty.
2. An endpoint described as protected returned secrets without rejecting missing credentials.

These are not hard-coded demo assertions. They travel through the same discovery, planning, execution, classification, and reporting pipeline used for another target.

## Run it against an application you control

```bash
recon test http://localhost:8000 --no-ai
```

If the OpenAPI document is not exposed at a conventional URL, specify it:

```bash
recon test http://localhost:8000 --spec ./openapi.yaml --no-ai
```

Recon exits with status `1` when it finds failed checks, so it can act as a CI quality gate. The HTML report is self-contained for easy artifact upload or local review.

## Where AI fits—and where it does not

Pass and fail decisions come from deterministic HTTP and schema assertions. LLM integrations are optional and can propose additional exploratory cases or explain observed failures. A real provider is never required for the core workflow.

## Honest limitations

Generated data cannot infer undocumented business rules. Custom authentication and multi-factor workflows may require explicit headers or application-specific setup. Browser checks need the optional Playwright installation. Generated requests may mutate target data, so Recon must only be used against systems you own or are authorized to test.

## Help shape the next release

Try the local demo first. If you then run Recon against a real API, use the [trial feedback form](https://github.com/ttnhan227/recon/issues/new?template=feedback.yml) to share the framework or OpenAPI generator, where the workflow succeeded, and the first point of friction. Sanitized minimal specifications are the most useful compatibility reports.

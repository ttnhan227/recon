# Contributing to Recon QA

Thanks for helping make automated API testing easier to adopt.

## Before you start

- Use Recon only against systems you own or are authorized to test.
- For a bug, include the Recon version, Python version, command, expected behavior, and sanitized output.
- For a larger change, open an issue first so effort is not duplicated.

## Local development

```bash
git clone https://github.com/ttnhan227/recon.git
cd recon
python -m venv .venv
```

Activate the environment, then install development dependencies:

```bash
python -m pip install -e ".[browser,dev]"
python -m playwright install chromium
```

Run the checks used by CI:

```bash
ruff check .
ruff format --check .
mypy recon tests
pytest -q
python -m build
```

## Pull requests

Keep changes focused. Add or update tests for behavior changes, update user-facing documentation when commands change, and avoid committing API keys, generated reports, databases, or `.env` files.

By contributing, you agree that your contribution is licensed under the MIT License.

from __future__ import annotations

import httpx
import pytest

from recon.apps.api.server import api_app
from recon.common.config import settings


@pytest.mark.asyncio
async def test_api_server_get_run_report_404():
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/runs/nonexistent-run-9999/report")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_server_get_run_report_success(tmp_path):
    # Setup mock report
    run_id = "test-run-api-001"
    run_dir = tmp_path / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_file = run_dir / "report.html"
    report_file.write_text(
        "<!DOCTYPE html><html><body>Report Content</body></html>", encoding="utf-8"
    )

    orig_reports_dir = settings.reports_dir
    settings.reports_dir = tmp_path
    try:
        transport = httpx.ASGITransport(app=api_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get(f"/api/v1/runs/{run_id}/report")
            assert resp.status_code == 200
            assert "text/html" in resp.headers["content-type"]
            assert "Report Content" in resp.text
    finally:
        settings.reports_dir = orig_reports_dir


def test_cli_serve_api_help():
    from typer.testing import CliRunner

    from recon.apps.cli.main import app as cli_app

    runner = CliRunner()
    result = runner.invoke(cli_app, ["serve-api", "--help"])
    assert result.exit_code == 0
    assert "port" in result.output.lower()


@pytest.mark.asyncio
async def test_api_server_post_runs_error_mapping_and_bounds(monkeypatch):
    from recon.common.exceptions import DiscoveryError, SSRFSecurityError, TargetUnreachableError

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Invalid concurrency bounds
        bad_conc = await client.post(
            "/api/v1/runs",
            json={"target_url": "http://localhost:8000", "concurrency": 0},
        )
        assert bad_conc.status_code == 422

        bad_conc_high = await client.post(
            "/api/v1/runs",
            json={"target_url": "http://localhost:8000", "concurrency": 64},
        )
        assert bad_conc_high.status_code == 422

        # SSRFSecurityError -> 400
        async def raise_ssrf(*args, **kwargs):
            raise SSRFSecurityError("Blocked metadata IP")

        monkeypatch.setattr("recon.apps.api.server.TestOrchestrator.run_pipeline", raise_ssrf)
        r_ssrf = await client.post("/api/v1/runs", json={"target_url": "http://169.254.169.254"})
        assert r_ssrf.status_code == 400

        # DiscoveryError -> 422
        async def raise_disc(*args, **kwargs):
            raise DiscoveryError("Invalid OpenAPI spec")

        monkeypatch.setattr("recon.apps.api.server.TestOrchestrator.run_pipeline", raise_disc)
        r_disc = await client.post("/api/v1/runs", json={"target_url": "http://localhost:8000"})
        assert r_disc.status_code == 422

        # TargetUnreachableError -> 502
        async def raise_unreach(*args, **kwargs):
            raise TargetUnreachableError("Connection refused")

        monkeypatch.setattr("recon.apps.api.server.TestOrchestrator.run_pipeline", raise_unreach)
        r_unreach = await client.post("/api/v1/runs", json={"target_url": "http://localhost:8000"})
        assert r_unreach.status_code == 502


@pytest.mark.asyncio
async def test_api_server_rejects_traversal_run_id():
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/runs/..etc..passwd/report")
        assert resp.status_code == 400

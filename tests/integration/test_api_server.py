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
        for bad_id in ("..etc..passwd", "run-", ".hidden", "run*"):
            resp = await client.get(f"/api/v1/runs/{bad_id}/report")
            assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_server_x_trace_id_response_header():
    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Error response 404
        resp_404 = await client.get("/api/v1/runs/nonexistent-run-1234")
        assert resp_404.status_code == 404
        assert "x-trace-id" in resp_404.headers
        trace_id_val = resp_404.headers["x-trace-id"]
        assert len(trace_id_val) == 32
        assert int(trace_id_val, 16) > 0


@pytest.mark.asyncio
async def test_api_server_incoming_traceparent_propagation():
    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    incoming_span_id = "00f067aa0ba902b7"
    traceparent_header = f"00-{incoming_trace_id}-{incoming_span_id}-01"

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/v1/runs/nonexistent-run-5678",
            headers={"traceparent": traceparent_header},
        )
        assert resp.status_code == 404
        assert "x-trace-id" in resp.headers
        # Propagated trace_id should match the incoming traceparent trace_id
        assert resp.headers["x-trace-id"] == incoming_trace_id


@pytest.mark.asyncio
async def test_api_server_post_runs_payload_trace_id(monkeypatch):
    from datetime import datetime, timezone

    from recon.common.models import RunSummary

    fake_summary = RunSummary(
        run_id="run-api-trace-001",
        target_url="http://localhost:8000",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=1.23,
        total=1,
        passed=1,
        trace_id="1234567890abcdef1234567890abcdef",
    )

    async def fake_run(*args, **kwargs):
        return fake_summary, []

    monkeypatch.setattr("recon.apps.api.server.TestOrchestrator.run_pipeline", fake_run)

    transport = httpx.ASGITransport(app=api_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/v1/runs", json={"target_url": "http://localhost:8000"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "1234567890abcdef1234567890abcdef"
        assert "x-trace-id" in resp.headers

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

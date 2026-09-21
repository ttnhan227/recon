import httpx
import pytest

from recon.demo_app.main import app
from recon.discovery.openapi import OpenAPIParser
from recon.orchestration.orchestrator import TestOrchestrator
from recon.planning.generator import TestSuiteGenerator


@pytest.mark.asyncio
async def test_full_pipeline_against_demo_app_schema(tmp_path):
    # 1. Ingest OpenAPI schema from demo app
    openapi_dict = app.openapi()
    parser = OpenAPIParser(openapi_dict, source_url="http://testserver/openapi.json")
    discovered_app = parser.parse(base_url="http://testserver")

    assert len(discovered_app.endpoints) >= 5

    # 2. Plan test suite
    planner = TestSuiteGenerator(discovered_app)
    suite = planner.generate_suite()
    assert len(suite) >= 8

    # 3. Execute via Orchestrator using in-memory SQLite and tmp report dir
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        orchestrator = TestOrchestrator(
            concurrency=4,
            output_dir=tmp_path / "reports",
            enable_ai=True,
            db_url="sqlite+aiosqlite:///:memory:",
            external_api_client=client,
        )

        summary, results = await orchestrator.run_pipeline(
            target_url="http://testserver",
            custom_tests=suite,
        )

    # 4. Assertions on results
    assert summary.total == len(suite)
    assert summary.total > 0
    # Must have detected intentional failures (500 on /api/orders missing currency, auth check on admin secrets)
    assert summary.failed > 0
    assert summary.exit_code == 1

    # Verify reports were written to disk
    run_dir = tmp_path / "reports" / f"run-{summary.run_id}"
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "results.json").exists()
    assert (run_dir / "report.html").exists()
    assert (tmp_path / "reports" / "latest.html").exists()

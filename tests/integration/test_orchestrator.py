import httpx
import pytest

from recon.common.models import (
    AssertionType,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStatus,
    TestStep,
    TestType,
)
from recon.orchestration.worker_pool import WorkerPool
from tests.conftest import test_app as app


@pytest.mark.asyncio
async def test_worker_pool_concurrency_execution():
    completed_tests = []

    async def on_complete(test, res):
        completed_tests.append(res.test_id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        pool = WorkerPool(
            concurrency=3,
            run_id="test-pool-run",
            api_client=client,
            on_test_complete=on_complete,
        )

        # Mock test cases against /api/health
        tests = [
            TestCase(
                id=f"MOCK-{i}",
                name=f"Mock Test {i}",
                category=TestCategory.HAPPY_PATH,
                test_type=TestType.API,
                target="http://test/api/health",
                steps=[
                    TestStep(
                        name=f"Step {i}",
                        endpoint="http://test/api/health",
                        assertions=[
                            StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=200)
                        ],
                    )
                ],
            )
            for i in range(5)
        ]

        results = await pool.execute_suite(tests)
        assert len(results) == 5
        assert len(completed_tests) == 5
        assert all(r.status == TestStatus.PASSED for r in results)


@pytest.mark.asyncio
async def test_orchestrator_mock_provider_skips_bogus_exploratory_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI

    from recon.discovery.models import DiscoveredApplication, DiscoveredEndpoint
    from recon.llm.failure_analyzer import AIFailureAnalyzer
    from recon.llm.provider import MockProvider
    from recon.llm.test_generator import AITestGenerator
    from recon.orchestration.orchestrator import TestOrchestrator

    ping_app = FastAPI()
    requested_paths: list[str] = []

    @ping_app.get("/ping")
    async def ping():
        requested_paths.append("/ping")
        return {"ok": True}

    @ping_app.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def catch_all(full_path: str):
        requested_paths.append(f"/{full_path}")
        return {"detail": "not found"}

    async def fake_discover(**kwargs):
        return DiscoveredApplication(
            target_url="http://test",
            base_url="http://test",
            endpoints=[
                DiscoveredEndpoint(path="/ping", method="GET", summary="Ping"),
            ],
        )

    monkeypatch.setattr(
        "recon.orchestration.orchestrator.discover_application",
        fake_discover,
    )

    transport = httpx.ASGITransport(app=ping_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        orchestrator = TestOrchestrator(
            concurrency=2,
            output_dir=tmp_path / "reports",
            enable_ai=True,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'recon.db'}",
            external_api_client=client,
        )
        orchestrator.ai_generator = AITestGenerator(provider=MockProvider())
        orchestrator.ai_analyzer = AIFailureAnalyzer(provider=MockProvider())
        assert isinstance(orchestrator.ai_generator.provider, MockProvider)
        summary, _results = await orchestrator.run_pipeline(
            target_url="http://test",
            enable_browser=False,
        )

    assert summary.total >= 1
    assert "/api/users" not in requested_paths
    assert "/api/orders" not in requested_paths

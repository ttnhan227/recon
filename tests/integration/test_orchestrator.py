import pytest
import httpx
from recon.common.models import (
    AssertionType,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStatus,
    TestStep,
    TestType,
)
from recon.demo_app.main import app
from recon.orchestration.worker_pool import WorkerPool


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
                        assertions=[StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=200)],
                    )
                ],
            )
            for i in range(5)
        ]

        results = await pool.execute_suite(tests)
        assert len(results) == 5
        assert len(completed_tests) == 5
        assert all(r.status == TestStatus.PASSED for r in results)

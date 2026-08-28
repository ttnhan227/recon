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
from recon.execution.api.runner import APITestRunner


@pytest.mark.asyncio
async def test_api_runner_health_check_passes():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        runner = APITestRunner(client=client)

        step = TestStep(
            name="Health Check",
            step_type="http_request",
            endpoint="http://test/api/health",
            method="GET",
            assertions=[
                StepAssertion(
                    assertion_type=AssertionType.STATUS_CODE,
                    expected=200,
                    operator="eq",
                ),
                StepAssertion(
                    assertion_type=AssertionType.JSON_PATH_EQUALS,
                    target="status",
                    expected="ok",
                ),
            ],
        )
        tc = TestCase(
            id="INT-001",
            name="Verify Health Check Endpoint",
            category=TestCategory.HAPPY_PATH,
            test_type=TestType.API,
            target="http://test/api/health",
            method="GET",
            steps=[step],
        )

        res = await runner.execute_test(tc)
        assert res.status == TestStatus.PASSED
        assert len(res.step_results) == 1
        assert res.failure_evidence is None


@pytest.mark.asyncio
async def test_api_runner_detects_500_failure():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        runner = APITestRunner(client=client)

        # Submit order without currency -> returns 500
        step = TestStep(
            name="Submit Order Without Currency",
            step_type="http_request",
            endpoint="http://test/api/orders",
            method="POST",
            body={"item_id": "ITEM-100", "quantity": 1},
            headers={"Content-Type": "application/json"},
            assertions=[
                StepAssertion(
                    assertion_type=AssertionType.STATUS_CODE,
                    expected=[200, 201],
                    operator="in",
                )
            ],
        )
        tc = TestCase(
            id="INT-002",
            name="Submit Order",
            category=TestCategory.HAPPY_PATH,
            test_type=TestType.API,
            target="http://test/api/orders",
            method="POST",
            steps=[step],
        )

        res = await runner.execute_test(tc)
        assert res.status == TestStatus.FAILED
        assert res.failure_evidence is not None
        assert res.failure_evidence.http_traces[0].response_status == 500

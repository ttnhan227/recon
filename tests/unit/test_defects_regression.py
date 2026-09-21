from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from recon.common.models import (
    AssertionType,
    FailureCategory,
    FailureEvidence,
    StepAssertion,
    StepResult,
    TestCase,
    TestCategory,
    TestResult,
    TestStatus,
    TestStep,
    TestType,
)
from recon.execution.browser.evidence import BrowserEvidenceCollector
from recon.execution.browser.runner import BrowserTestRunner
from recon.healing.engine import SelfHealingEngine
from recon.healing.locator import CodeLocator
from recon.healing.patcher import AIPatchGenerator
from recon.llm.provider import MockProvider
from recon.orchestration.orchestrator import TestOrchestrator
from recon.orchestration.state_pool import StatePool


def test_state_pool_specific_key_priority():
    """Verify that specific keys like userId are not masked by generic id fallback."""
    pool = StatePool.get_instance()
    pool.reset()

    # Store user-100 first
    pool.store_entity("userId", "user-100")
    # Store order-200 second (which also goes to generic id pool)
    pool.store_entity("orderId", "order-200")

    # get_latest("userId") must return user-100, NOT order-200
    assert pool.get_latest("userId") == "user-100"
    assert pool.get_latest("orderId") == "order-200"
    # Generic id should return the latest stored entity
    assert pool.get_latest("id") == "order-200"

    # Dynamic arbitrary key
    pool.store_entity("customTenantId", "tenant-xyz")
    assert pool.get_latest("customTenantId") == "tenant-xyz"


def test_state_pool_url_substitution_logic():
    """Verify URL substitution for path params and dummy UUIDs."""
    pool = StatePool.get_instance()
    pool.reset()

    pool.store_entity("orderId", "order-abc-123")
    url = "http://localhost:8000/api/orders/{orderId}"
    substituted = pool.substitute_url(url)
    assert substituted == "http://localhost:8000/api/orders/order-abc-123"

    url_dummy = "http://localhost:8000/api/orders/00000000-0000-0000-0000-000000000001"
    sub_dummy = pool.substitute_url(url_dummy)
    assert sub_dummy == "http://localhost:8000/api/orders/order-abc-123"


def test_browser_evidence_no_name_error():
    """Verify handle_request_failed does not raise NameError when called."""
    collector = BrowserEvidenceCollector(run_id="test-run-123", output_dir=tempfile.gettempdir())

    mock_req = MagicMock()
    mock_req.url = "http://localhost:8000/api/broken"
    mock_req.method = "POST"
    mock_req.failure = "net::ERR_CONNECTION_REFUSED"
    mock_req.response.return_value = None

    # Should not raise NameError
    collector.handle_request_failed(mock_req)

    assert len(collector.network_errors) == 1
    err = collector.network_errors[0]
    assert err.url == "http://localhost:8000/api/broken"
    assert err.method == "POST"
    assert "ERR_CONNECTION_REFUSED" in err.error_text


def test_browser_evidence_page_error_handling():
    """Verify handle_page_error captures uncaught JS exceptions into both page_errors and console_logs."""
    collector = BrowserEvidenceCollector(run_id="test-run-123", output_dir=tempfile.gettempdir())

    exc_text = "TypeError: Cannot read properties of undefined (reading 'token')"
    collector.handle_page_error(exc_text)

    assert len(collector.page_errors) == 1
    assert exc_text in collector.page_errors[0]

    assert len(collector.console_logs) == 1
    log = collector.console_logs[0]
    assert log.level == "error"
    assert "Uncaught Exception" in log.text
    assert "TypeError" in log.text

    # Failure category determination
    runner = BrowserTestRunner()
    step_res = StepResult(
        step_name="click login", status=TestStatus.FAILED, error_message="Step failed"
    )
    cat = runner._determine_failure_category(step_res, collector.console_logs)
    assert cat == FailureCategory.APPLICATION_ERROR


def test_code_locator_matches_leading_slash_and_parameters():
    """Verify CodeLocator finds routes with leading slashes and path parameters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        app_file = tmp_path / "main.py"
        app_file.write_text(
            """from fastapi import FastAPI

app = FastAPI()

@app.get("/api/admin/secrets")
async def get_secrets():
    return {"secret": "recon-secret"}

@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    return {"order_id": order_id}

@app.post("/api/orders")
async def create_order(payload: dict):
    return {"status": "ok"}
""",
            encoding="utf-8",
        )

        locator = CodeLocator(repo_dir=tmp_path)

        # 1. Route with leading slash and multiple segments
        ctx_admin = locator.locate_endpoint("GET", "/api/admin/secrets")
        assert len(ctx_admin) > 0
        assert ctx_admin[0].function_name == "get_secrets"
        assert ctx_admin[0].file_path == app_file

        # 2. Route with parameter
        ctx_order = locator.locate_endpoint("GET", "/api/orders/12345")
        assert len(ctx_order) > 0
        assert ctx_order[0].function_name == "get_order"

        # 3. POST Route
        ctx_create = locator.locate_endpoint("POST", "/api/orders")
        assert len(ctx_create) > 0
        assert ctx_create[0].function_name == "create_order"


@pytest.mark.asyncio
async def test_mock_provider_generates_code_patch():
    """Verify MockProvider supports code patch generation prompts."""
    provider = MockProvider()
    generator = AIPatchGenerator(provider=provider)

    with tempfile.TemporaryDirectory() as tmpdir:
        src_file = Path(tmpdir) / "app.py"
        src_file.write_text(
            """def process_order(order):
    currency_code = order.currency.upper()
    return {"currency": currency_code}
""",
            encoding="utf-8",
        )

        from recon.healing.locator import LocatedContext

        context = LocatedContext(
            file_path=src_file,
            relative_path="app.py",
            line_number=2,
            matched_pattern="process_order",
            full_content=src_file.read_text(encoding="utf-8"),
            snippet=src_file.read_text(encoding="utf-8"),
            function_name="process_order",
        )

        res = TestResult(
            test_id="API-099",
            test_name="[POST /api/orders] Boundary - missing currency",
            category=TestCategory.BOUNDARY,
            test_type=TestType.API,
            status=TestStatus.FAILED,
            failure_evidence=FailureEvidence(
                failure_category=FailureCategory.APPLICATION_ERROR,
                message="AttributeError: 'NoneType' object has no attribute 'upper'",
            ),
        )

        patch = await generator.generate_patch(res, context)
        assert patch is not None
        assert patch.test_id == "API-099"
        assert '(order.currency or "USD").upper()' in patch.modified_content
        assert patch.diff != ""


@pytest.mark.asyncio
async def test_healing_engine_load_results_handles_directory_and_prefix():
    """Verify load_results works when target is a directory or has run- prefix."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        run_dir = tmp_path / "run-20260910-120000-abcdef"
        run_dir.mkdir()

        res_json = run_dir / "results.json"
        sample_res = [
            {
                "test_id": "API-001",
                "test_name": "[GET /health] Happy Path",
                "category": "HAPPY_PATH",
                "test_type": "API",
                "status": "PASSED",
                "duration_ms": 12.5,
                "started_at": "2026-09-10T00:00:00Z",
                "completed_at": "2026-09-10T00:00:00Z",
                "step_results": [],
            }
        ]
        import json

        res_json.write_text(json.dumps(sample_res), encoding="utf-8")

        engine = SelfHealingEngine(repo_dir=tmp_path)
        loaded = await engine.load_results(str(run_dir))
        assert len(loaded) == 1
        assert loaded[0].test_id == "API-001"
        assert loaded[0].status == TestStatus.PASSED


@pytest.mark.asyncio
async def test_orchestrator_filter_test_ids_preserves_assertions():
    """Verify filter_test_ids filters tests while retaining their full assertions."""
    orchestrator = TestOrchestrator()

    test1 = TestCase(
        id="API-001",
        name="[GET /items] Happy Path",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
        target="http://localhost:8000/items",
        steps=[
            TestStep(
                name="GET /items",
                step_type="http_request",
                endpoint="http://localhost:8000/items",
                assertions=[
                    StepAssertion(
                        assertion_type=AssertionType.STATUS_CODE, expected=200, operator="eq"
                    )
                ],
            )
        ],
    )
    test2 = TestCase(
        id="API-002",
        name="[POST /items] Happy Path",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
        target="http://localhost:8000/items",
        steps=[
            TestStep(
                name="POST /items",
                step_type="http_request",
                endpoint="http://localhost:8000/items",
                assertions=[
                    StepAssertion(
                        assertion_type=AssertionType.STATUS_CODE, expected=201, operator="eq"
                    )
                ],
            )
        ],
    )

    # When custom_tests is passed with filter_test_ids={"API-002"}
    summary, results = await orchestrator.run_pipeline(
        target_url="http://localhost:8000",
        custom_tests=[test1, test2],
        filter_test_ids={"API-002"},
    )

    # Only API-002 should have run
    assert summary.total == 1
    assert results[0].test_id == "API-002"
    # Verify the test retained its step assertion
    assert len(test2.steps[0].assertions) == 1
    assert test2.steps[0].assertions[0].expected == 201

"""
Unit regression tests verifying engineering audit fixes across Recon.

Covers:
1. WorkerPool worker failure isolation (no dropped test results on crash).
2. WorkerPool topological wave execution ordering.
3. OpenAPI circular $ref cycle detection without RecursionError.
4. Security: Compound sensitive key redaction, PEM private key scrubbing, URL query redaction.
5. Case-insensitive header assertions and status code null guards.
6. Browser assertion evaluation logic.
7. Authentication / Authorization failure classification.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from recon.analysis.classifier import DeterministicFailureClassifier
from recon.common.exceptions import DiscoveryError, TargetUnreachableError
from recon.common.models import (
    AssertionType,
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    NetworkError,
    StepAssertion,
    StepResult,
    TestCase,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.common.security import redact_sensitive_data, redact_url
from recon.discovery.endpoint_detector import discover_application
from recon.discovery.openapi import OpenAPIParser
from recon.execution.api.assertions import evaluate_assertion
from recon.execution.browser.runner import BrowserTestRunner
from recon.orchestration.worker_pool import WorkerPool


# -----------------------------------------------------------------------------
# 1. WorkerPool Worker Exception Isolation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_worker_pool_catches_unhandled_runner_exception_without_losing_results():
    """Verify that if an unhandled exception occurs inside a worker during test execution,
    the pool catches it and returns an ERROR TestResult rather than dropping the test.
    """
    failing_test = TestCase(
        id="test_crash_1",
        name="Crashing Test",
        target="http://localhost:8000/api/crash",
        method="GET",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
    )

    pool = WorkerPool(concurrency=2)
    # Simulate an unhandled driver or internal error during runner execution
    setattr(
        pool.api_runner,
        "execute_test",
        AsyncMock(side_effect=RuntimeError("Hardware or driver crash")),
    )

    results = await pool.execute_suite([failing_test])

    assert len(results) == 1
    res = results[0]
    assert res.test_id == "test_crash_1"
    assert res.status == TestStatus.ERROR
    assert res.failure_evidence is not None
    assert res.failure_evidence.failure_category == FailureCategory.INFRASTRUCTURE_ERROR
    assert (
        "Worker caught unhandled execution exception: Hardware or driver crash"
        in res.failure_evidence.message
    )


@pytest.mark.asyncio
async def test_worker_pool_wave_partitioning_order():
    """Verify that WorkerPool partitions tests into creation (POST), read (GET), and deletion (DELETE) waves."""
    post_test = TestCase(
        id="test_post",
        name="Create User",
        target="http://localhost:8000/api/users",
        method="POST",
        category=TestCategory.HAPPY_PATH,
    )
    get_test = TestCase(
        id="test_get",
        name="Get User",
        target="http://localhost:8000/api/users",
        method="GET",
        category=TestCategory.HAPPY_PATH,
    )
    delete_test = TestCase(
        id="test_delete",
        name="Delete User",
        target="http://localhost:8000/api/users/123",
        method="DELETE",
        category=TestCategory.HAPPY_PATH,
    )

    execution_order = []

    async def fake_execute(test_case):
        execution_order.append(test_case.id)
        return TestResult(
            test_id=test_case.id,
            test_name=test_case.name,
            category=test_case.category,
            test_type=test_case.test_type,
            status=TestStatus.PASSED,
            duration_ms=5.0,
        )

    pool = WorkerPool(concurrency=1)
    setattr(pool.api_runner, "execute_test", AsyncMock(side_effect=fake_execute))

    # Pass in reverse order: DELETE, GET, POST
    results = await pool.execute_suite([delete_test, get_test, post_test])

    assert len(results) == 3
    # Waves: Wave 1 (POST) must finish before Wave 2 (GET), which finishes before Wave 4 (DELETE)
    assert execution_order == ["test_post", "test_get", "test_delete"]


# -----------------------------------------------------------------------------
# 2. OpenAPI Circular Reference Cycle Detection
# -----------------------------------------------------------------------------
def test_openapi_circular_ref_cycle_detection():
    """Verify that circular self-referencing schemas do not trigger infinite recursion."""
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "Circular API", "version": "1.0"},
        "paths": {
            "/nodes": {
                "post": {
                    "operationId": "createNode",
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Node"}}
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "parent": {"$ref": "#/components/schemas/Node"},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Node"},
                        },
                    },
                }
            }
        },
    }

    parser = OpenAPIParser(spec, source_url="http://localhost:8000/openapi.json")
    app = parser.parse(base_url="http://localhost:8000")

    assert len(app.endpoints) == 1
    ep = app.endpoints[0]
    assert ep.path == "/nodes"
    assert ep.method == "POST"
    # Schema should have resolved name, and parent should not cause RecursionError
    assert ep.request_body_schema is not None
    assert ep.request_body_schema.get("type") == "object"
    assert "properties" in ep.request_body_schema
    assert "name" in ep.request_body_schema["properties"]


# -----------------------------------------------------------------------------
# 3. Security: Compound Key, Private Key, and URL Redaction
# -----------------------------------------------------------------------------
def test_redact_sensitive_compound_keys_and_tokens():
    """Verify that compound sensitive keys (e.g. database_master_password, jwt_private_key) are redacted."""
    data = {
        "username": "admin",
        "database_master_password": "supersecretpassword",
        "jwt_private_key": "privatekeyvalue",
        "user_auth_token": "token12345",
        "client_secret": "myclientsecret",
        "safe_key": "safe_value",
    }

    redacted = redact_sensitive_data(data)
    assert redacted["username"] == "admin"
    assert redacted["safe_key"] == "safe_value"
    assert redacted["database_master_password"] == "***REDACTED***"
    assert redacted["jwt_private_key"] == "***REDACTED***"
    assert redacted["user_auth_token"] == "***REDACTED***"
    assert redacted["client_secret"] == "***REDACTED***"


def test_redact_pem_private_keys_in_strings():
    """Verify that PEM private key text embedded in strings is scrubbed."""
    raw_str = (
        "Here is the key: -----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEowIBAAKCAQEA0Y8vj6...\n"
        "-----END RSA PRIVATE KEY-----\n"
        "Configured successfully."
    )
    redacted = redact_sensitive_data(raw_str)
    assert "***REDACTED PRIVATE KEY***" in redacted
    assert "MIIEowIBAAKCAQEA0Y8vj6" not in redacted


def test_redact_url_credentials_and_query_parameters():
    """Verify that URL credentials and sensitive query params are redacted."""
    url = "https://user:mypassword@example.com/api/v1/data?token=xyz123&format=json&api_key=98765"
    sanitized = redact_url(url)
    assert "mypassword" not in sanitized
    assert "xyz123" not in sanitized
    assert "98765" not in sanitized
    assert "token=" in sanitized
    assert "REDACTED" in sanitized
    assert "format=json" in sanitized
    assert "example.com/api/v1/data" in sanitized


# -----------------------------------------------------------------------------
# 4. Case-Insensitive Header Assertions & Status Code Null Guard
# -----------------------------------------------------------------------------
def test_case_insensitive_header_assertion():
    """Verify HTTP response headers are matched case-insensitively."""
    assertion = StepAssertion(
        assertion_type=AssertionType.HEADER_CONTAINS,
        target="content-type",
        expected="application/json",
        operator="contains",
    )

    result = evaluate_assertion(
        assertion,
        status_code=200,
        headers={"Content-Type": "application/json; charset=utf-8"},
        json_body={"status": "ok"},
        raw_text='{"status": "ok"}',
        latency_ms=10.0,
    )
    assert result.passed is True
    assert result.actual == "application/json; charset=utf-8"


def test_status_code_assertion_guard_against_null():
    """Verify that a missing or null status code fails gracefully instead of false pass."""
    assertion = StepAssertion(
        assertion_type=AssertionType.STATUS_CODE,
        expected=500,
        operator="ne",
    )

    result = evaluate_assertion(
        assertion,
        status_code=None,  # e.g. network failure before receiving response
        headers={},
        json_body=None,
        raw_text="",
        latency_ms=0.0,
    )
    assert result.passed is False
    assert "Request failed without a response status code" in (result.message or "")


# -----------------------------------------------------------------------------
# 5. Browser Step Assertion Evaluation Logic
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_browser_step_assertion_evaluation():
    """Verify browser runner assertion evaluation logic for response time, visibility, and URL matching."""
    runner = BrowserTestRunner()

    mock_page = AsyncMock()
    mock_page.url = "http://localhost:8000/dashboard"
    mock_page.content = AsyncMock(return_value="<html><body>Welcome back, Admin!</body></html>")
    mock_page.query_selector = AsyncMock(return_value=MagicMock())

    assertions = [
        StepAssertion(
            assertion_type=AssertionType.RESPONSE_TIME_MS,
            expected=1000,
            operator="lte",
        ),
        StepAssertion(
            assertion_type=AssertionType.TEXT_VISIBLE,
            expected="Welcome",
        ),
        StepAssertion(
            assertion_type=AssertionType.URL_MATCHES,
            expected="dashboard",
        ),
    ]

    # 1. Matching conditions
    results = await runner._evaluate_browser_assertions(
        page=mock_page,
        assertions=assertions,
        status_code=200,
        duration_ms=450.0,
    )
    assert len(results) == 3
    assert all(r.passed for r in results)

    # 2. Failing condition (latency > 1000ms)
    failing_results = await runner._evaluate_browser_assertions(
        page=mock_page,
        assertions=assertions,
        status_code=200,
        duration_ms=1500.0,
    )
    assert failing_results[0].passed is False
    assert "exceeded limit 1000" in (failing_results[0].message or "")


# -----------------------------------------------------------------------------
# 6. Auth Failure Classification
# -----------------------------------------------------------------------------
def test_failure_classifier_unauthorized_auth_failure():
    """Verify that an unauthorized access test (expecting 401/403 but got 200) is classified as auth failure."""
    assertion = StepAssertion(
        assertion_type=AssertionType.STATUS_CODE,
        expected=401,
        operator="eq",
    )
    assertion_result = evaluate_assertion(
        assertion,
        status_code=200,
        headers={"Content-Type": "application/json"},
        json_body={"secret": "leaked"},
        raw_text='{"secret": "leaked"}',
        latency_ms=15.0,
    )
    assert assertion_result.passed is False

    step_result = StepResult(
        step_name="Probe Admin Secrets",
        status=TestStatus.FAILED,
        duration_ms=15.0,
        assertion_results=[assertion_result],
    )

    trace = HTTPTrace(
        request_method="GET",
        request_url="http://localhost:8000/api/admin/secrets",
        response_status=200,
        response_body={"secret": "leaked"},
    )

    test_result = TestResult(
        test_id="SEC-001",
        test_name="Unauthenticated Admin Access Check",
        category=TestCategory.AUTHENTICATION,
        test_type=TestType.API,
        status=TestStatus.FAILED,
        step_results=[step_result],
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.UNKNOWN,
            message="Expected status 401, got 200",
            http_traces=[trace],
        ),
    )

    classified = DeterministicFailureClassifier.classify(test_result)
    assert classified == FailureCategory.AUTHENTICATION_FAILURE


# -----------------------------------------------------------------------------
# 7. Pre-flight Connectivity & Network Error Classification
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_preflight_connectivity_raises_target_unreachable_error(monkeypatch):
    """Verify that unreachable hosts fail immediately with TargetUnreachableError instead of slow crawling."""
    import httpx

    async def mock_get(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(TargetUnreachableError) as exc_info:
        await discover_application("http://localhost:9999")

    assert "Connection was refused or timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_discover_application_without_spec_or_browser_raises_discovery_error(monkeypatch):
    """Verify that a running server without OpenAPI raises DiscoveryError when browser crawling is disabled."""
    import httpx

    async def mock_get(self, url, *args, **kwargs):
        return httpx.Response(404, request=httpx.Request("GET", str(url)))

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    with pytest.raises(DiscoveryError) as exc_info:
        await discover_application(
            "http://localhost:8000", spec_path_or_url=None, enable_browser=False
        )

    assert "No OpenAPI specification detected" in str(exc_info.value)


def test_failure_classifier_connection_refused_network_error():
    """Verify that browser or HTTP connection refusals are classified as NETWORK_ERROR."""
    result = TestResult(
        test_id="UI-002",
        test_name="Dashboard Load",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.BROWSER,
        status=TestStatus.FAILED,
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.UNKNOWN,
            message="Browser action failed: Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:9999/",
            network_errors=[
                NetworkError(
                    url="http://127.0.0.1:9999/",
                    error_text="net::ERR_CONNECTION_REFUSED",
                )
            ],
        ),
    )

    classified = DeterministicFailureClassifier.classify(result)
    assert classified == FailureCategory.NETWORK_ERROR


# -----------------------------------------------------------------------------
# 8. Kebab-Case Path Parameter State Substitution
# -----------------------------------------------------------------------------
def test_state_pool_kebab_case_substitution():
    """Verify that StatePool substitutes kebab-case path parameters like {order-id} and {item-sku}."""
    from recon.orchestration.state_pool import StatePool

    pool = StatePool.get_instance()
    pool.reset()

    pool.store_entity("order-id", "ord-kebab-999")
    pool.store_entity("item-sku", "SKU-XYZ-456")

    url = "http://localhost:8000/api/orders/{order-id}/items/{item-sku}"
    substituted = pool.substitute_url(url)
    assert substituted == "http://localhost:8000/api/orders/ord-kebab-999/items/SKU-XYZ-456"


# -----------------------------------------------------------------------------
# 9. 404 / 405 Classification as HTTP_ERROR
# -----------------------------------------------------------------------------
def test_classify_404_and_405_as_http_error():
    """Verify that HTTP 404 Not Found and 405 Method Not Allowed are classified as HTTP_ERROR."""
    for code in (404, 405):
        trace = HTTPTrace(
            request_method="GET",
            request_url=f"http://localhost:8000/api/missing-{code}",
            response_status=code,
            response_body={"detail": f"Status {code}"},
        )
        result = TestResult(
            test_id=f"API-{code}",
            test_name=f"Endpoint Check {code}",
            category=TestCategory.HAPPY_PATH,
            test_type=TestType.API,
            status=TestStatus.FAILED,
            failure_evidence=FailureEvidence(
                failure_category=FailureCategory.UNKNOWN,
                message=f"HTTP {code} returned",
                http_traces=[trace],
            ),
        )
        classified = DeterministicFailureClassifier.classify(result)
        assert classified == FailureCategory.HTTP_ERROR


# -----------------------------------------------------------------------------
# 10. CLI Target Normalization
# -----------------------------------------------------------------------------
def test_normalize_cli_target():
    """Verify normalize_cli_target prepends http:// when scheme is omitted."""
    from recon.apps.cli.main import normalize_cli_target

    assert normalize_cli_target("localhost:8000") == "http://localhost:8000"
    assert normalize_cli_target("127.0.0.1:3000") == "http://127.0.0.1:3000"
    assert normalize_cli_target("http://localhost:8000") == "http://localhost:8000"
    assert normalize_cli_target("https://api.example.com") == "https://api.example.com"
    assert normalize_cli_target("  localhost:8080/api  ") == "http://localhost:8080/api"


# -----------------------------------------------------------------------------
# 11. Doctor Check Playwright Optional Extra Handling
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_doctor_playwright_optional_handling(monkeypatch):
    """Verify recon doctor treats missing Playwright as optional when testing API environments."""
    import builtins

    from recon.apps.cli.doctor import run_doctor

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "playwright" in name:
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    healthy = await run_doctor()
    assert healthy is True

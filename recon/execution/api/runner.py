from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any
import httpx

from recon.common.config import settings
from recon.common.logging import current_test_id, logger
from recon.common.models import (
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    StepResult,
    TestCase,
    TestResult,
    TestStatus,
)
from recon.common.security import redact_headers, redact_sensitive_data, validate_target_url
from recon.execution.api.assertions import evaluate_assertion
from recon.orchestration.state_pool import StatePool


class APITestRunner:
    """Deterministic HTTP API test execution engine with DAG state chaining."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._external_client = client

    async def execute_test(self, test: TestCase) -> TestResult:
        """Executes an API TestCase across its steps."""
        current_test_id.set(test.id)
        started_at = datetime.now(timezone.utc)
        start_time = time.perf_counter()
        step_results: list[StepResult] = []
        http_traces: list[HTTPTrace] = []
        overall_status = TestStatus.PASSED
        failure_evidence: FailureEvidence | None = None
        retries_done = 0

        client_to_use = self._external_client or httpx.AsyncClient(
            timeout=test.timeout_seconds,
            follow_redirects=True,
            verify=False,
        )

        try:
            for step in test.steps:
                step_res, trace, error_detail = await self._execute_step(
                    client=client_to_use,
                    step=step,
                    test=test,
                    max_retries=test.retries,
                )
                step_results.append(step_res)
                if trace:
                    http_traces.append(trace)

                if step_res.status in (TestStatus.FAILED, TestStatus.ERROR):
                    overall_status = step_res.status
                    # Collect failure evidence
                    cat = self._determine_failure_category(step_res, trace, error_detail)
                    failure_evidence = FailureEvidence(
                        failure_category=cat,
                        message=step_res.error_message or "API step assertion or request failed",
                        failed_step=step.name,
                        http_traces=http_traces,
                        stack_trace=error_detail.get("stack_trace"),
                        system_logs=[f"Step '{step.name}' failed with status {step_res.status}"],
                    )
                    break

        except Exception as e:
            overall_status = TestStatus.ERROR
            failure_evidence = FailureEvidence(
                failure_category=FailureCategory.UNKNOWN,
                message=f"Unhandled exception during test execution: {e}",
                http_traces=http_traces,
                stack_trace=str(e),
            )
        finally:
            if not self._external_client:
                await client_to_use.aclose()

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        completed_at = datetime.now(timezone.utc)

        return TestResult(
            test_id=test.id,
            test_name=test.name,
            category=test.category,
            test_type=test.test_type,
            status=overall_status,
            duration_ms=round(duration_ms, 2),
            started_at=started_at,
            completed_at=completed_at,
            step_results=step_results,
            failure_evidence=failure_evidence,
            retries_attempted=retries_done,
        )

    async def _execute_step(
        self,
        client: httpx.AsyncClient,
        step: Any,
        test: TestCase | None = None,
        max_retries: int = 0,
    ) -> tuple[StepResult, HTTPTrace | None, dict[str, Any]]:
        """Executes a single HTTP step with dynamic DAG state substitution, retries and assertion evaluations."""
        state_pool = StatePool.get_instance()
        endpoint = step.endpoint or ""
        method = (step.method or "GET").upper()
        headers = dict(step.headers)
        params = dict(step.params)
        body = step.body

        # Dynamic State Substitution (only for Happy Path and exploratory tests, preserving explicit 404/negative test inputs)
        is_happy = test and test.category.value in ("happy_path", "exploratory")
        if is_happy:
            endpoint = state_pool.substitute_url(endpoint)
            body = state_pool.substitute_payload(body)

        # Validate URL security / SSRF
        validate_target_url(endpoint)

        step_start = time.perf_counter()
        attempt = 0
        last_exception: Exception | None = None
        response: httpx.Response | None = None

        while attempt <= max_retries:
            try:
                # Prepare JSON body if dict or list
                json_kwarg = body if isinstance(body, (dict, list)) else None
                content_kwarg = str(body).encode() if body is not None and json_kwarg is None else None

                req_start = time.perf_counter()
                response = await client.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    params=params,
                    json=json_kwarg,
                    content=content_kwarg,
                    timeout=step.timeout_seconds,
                )
                latency_ms = (time.perf_counter() - req_start) * 1000.0
                break
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as ex:
                last_exception = ex
                attempt += 1
                if attempt <= max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                else:
                    break

        step_duration = (time.perf_counter() - step_start) * 1000.0

        # Case 1: Request totally failed (network / timeout error)
        if response is None:
            err_msg = f"HTTP request failed after {attempt} attempts: {last_exception}"
            err_trace = HTTPTrace(
                request_method=method,
                request_url=endpoint,
                request_headers=redact_headers(headers),
                request_body=redact_sensitive_data(body),
                response_status=None,
                response_body=str(last_exception),
                latency_ms=round(step_duration, 2),
            )
            return (
                StepResult(
                    step_name=step.name,
                    status=TestStatus.FAILED if isinstance(last_exception, httpx.TimeoutException) else TestStatus.ERROR,
                    duration_ms=round(step_duration, 2),
                    error_message=err_msg,
                    http_trace=err_trace,
                ),
                err_trace,
                {"error": str(last_exception), "exception_type": type(last_exception).__name__},
            )

        # Parse response
        resp_status = response.status_code
        resp_headers = dict(response.headers)
        raw_text = response.text
        json_body: Any = None
        try:
            json_body = response.json()
            # Harvest entities into StatePool for downstream DAG tests
            if resp_status in (200, 201):
                state_pool.harvest(json_body)
        except Exception:
            json_body = None

        trace = HTTPTrace(
            request_method=method,
            request_url=str(response.url),
            request_headers=redact_headers(headers),
            request_body=redact_sensitive_data(body),
            response_status=resp_status,
            response_headers=redact_headers(resp_headers),
            response_body=redact_sensitive_data(json_body if json_body is not None else raw_text[:2000]),
            latency_ms=round(latency_ms, 2),
        )

        # Evaluate assertions
        assertion_results = []
        step_passed = True
        failed_msgs = []

        for assertion in step.assertions:
            res = evaluate_assertion(
                assertion=assertion,
                status_code=resp_status,
                headers=resp_headers,
                json_body=json_body,
                raw_text=raw_text,
                latency_ms=latency_ms,
            )
            assertion_results.append(res)
            if not res.passed:
                step_passed = False
                if res.message:
                    failed_msgs.append(res.message)

        status = TestStatus.PASSED if step_passed else TestStatus.FAILED
        err_msg = "; ".join(failed_msgs) if failed_msgs else None

        return (
            StepResult(
                step_name=step.name,
                status=status,
                duration_ms=round(step_duration, 2),
                assertion_results=assertion_results,
                error_message=err_msg,
                http_trace=trace,
            ),
            trace,
            {"status_code": resp_status, "body": raw_text[:1000]},
        )

    def _determine_failure_category(
        self, step_res: StepResult, trace: HTTPTrace | None, detail: dict[str, Any]
    ) -> FailureCategory:
        """Determines initial deterministic failure category."""
        if not trace or trace.response_status is None:
            if "timeout" in (step_res.error_message or "").lower():
                return FailureCategory.TIMEOUT
            return FailureCategory.NETWORK_ERROR

        status = trace.response_status
        if status == 500:
            return FailureCategory.APPLICATION_ERROR
        elif status == 401:
            return FailureCategory.AUTHENTICATION_FAILURE
        elif status == 403:
            return FailureCategory.AUTHORIZATION_FAILURE
        elif status == 422 or status == 400:
            return FailureCategory.VALIDATION_FAILURE
        elif status >= 500:
            return FailureCategory.HTTP_ERROR

        # If status was 200 or unexpected but assertions failed
        return FailureCategory.ASSERTION_FAILURE

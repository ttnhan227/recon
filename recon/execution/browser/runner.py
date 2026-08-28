from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recon.common.logging import current_test_id, logger
from recon.common.models import (
    AssertionResult,
    AssertionType,
    FailureCategory,
    FailureEvidence,
    ScreenshotEvidence,
    StepResult,
    TestCase,
    TestResult,
    TestStatus,
)
from recon.common.security import validate_target_url
from recon.execution.browser.evidence import BrowserEvidenceCollector


class BrowserTestRunner:
    """Executes browser automation tests using Playwright."""

    def __init__(self, run_id: str = "default", output_dir: Path | str = "./reports"):
        self.run_id = run_id
        self.output_dir = output_dir

    async def execute_test(self, test: TestCase) -> TestResult:
        """Executes a browser test case across all interaction steps."""
        current_test_id.set(test.id)
        started_at = datetime.now(timezone.utc)
        start_time = time.perf_counter()
        step_results: list[StepResult] = []
        overall_status = TestStatus.PASSED
        failure_evidence: FailureEvidence | None = None
        evidence_collector = BrowserEvidenceCollector(self.run_id, self.output_dir)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return TestResult(
                test_id=test.id,
                test_name=test.name,
                category=test.category,
                test_type=test.test_type,
                status=TestStatus.ERROR,
                duration_ms=0.0,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                failure_evidence=FailureEvidence(
                    failure_category=FailureCategory.TEST_CONFIGURATION_ERROR,
                    message="Playwright is not installed. Install with `pip install playwright && playwright install chromium`.",
                ),
            )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    ignore_https_errors=True,
                )
                page = await context.new_page()

                # Attach listeners for console and network errors
                page.on("console", evidence_collector.handle_console)
                page.on("requestfailed", evidence_collector.handle_request_failed)

                for step in test.steps:
                    step_res, failed = await self._execute_browser_step(
                        page=page,
                        step=step,
                        evidence_collector=evidence_collector,
                    )
                    step_results.append(step_res)

                    if failed:
                        overall_status = step_res.status
                        # Take screenshot upon failure
                        screenshot = await evidence_collector.capture_screenshot(
                            page, step.name, suffix="fail"
                        )
                        cat = self._determine_failure_category(
                            step_res, evidence_collector.console_logs
                        )
                        failure_evidence = FailureEvidence(
                            failure_category=cat,
                            message=step_res.error_message or "Browser step failed",
                            failed_step=step.name,
                            console_errors=evidence_collector.console_logs,
                            network_errors=evidence_collector.network_errors,
                            screenshots=[screenshot] if screenshot else [],
                            system_logs=[f"Failed at step: {step.name}"],
                        )
                        break

                # If test passed all steps, check for critical console errors (e.g. Uncaught TypeError)
                if overall_status == TestStatus.PASSED:
                    uncaught_errors = [
                        c for c in evidence_collector.console_logs if c.level == "error"
                    ]
                    if uncaught_errors:
                        # Mark as failed due to unhandled console errors
                        overall_status = TestStatus.FAILED
                        screenshot = await evidence_collector.capture_screenshot(
                            page, "console_errors", suffix="error"
                        )
                        err_texts = "; ".join(e.text for e in uncaught_errors[:3])
                        failure_evidence = FailureEvidence(
                            failure_category=FailureCategory.APPLICATION_ERROR,
                            message=f"Detected unhandled JavaScript console errors: {err_texts}",
                            failed_step="Console Check",
                            console_errors=evidence_collector.console_logs,
                            network_errors=evidence_collector.network_errors,
                            screenshots=[screenshot] if screenshot else [],
                        )

                await browser.close()

        except Exception as e:
            overall_status = TestStatus.ERROR
            failure_evidence = FailureEvidence(
                failure_category=FailureCategory.BROWSER_ERROR,
                message=f"Browser execution failed: {e}",
                stack_trace=str(e),
            )

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
        )

    async def _execute_browser_step(
        self,
        page: Any,
        step: Any,
        evidence_collector: BrowserEvidenceCollector,
    ) -> tuple[StepResult, bool]:
        step_start = time.perf_counter()
        stype = step.step_type
        timeout_ms = int(step.timeout_seconds * 1000)

        try:
            if stype == "browser_navigate":
                target_url = step.endpoint or ""
                validate_target_url(target_url)
                resp = await page.goto(
                    target_url, timeout=timeout_ms, wait_until="domcontentloaded"
                )
                status_code = resp.status if resp else 200
                duration_ms = (time.perf_counter() - step_start) * 1000.0

                # Evaluate step assertions
                assertion_results = []
                for a in step.assertions:
                    if a.assertion_type == AssertionType.STATUS_CODE:
                        passed = status_code in (a.expected if isinstance(a.expected, list) else [a.expected])
                        assertion_results.append(
                            AssertionResult(
                                assertion_type=AssertionType.STATUS_CODE,
                                passed=passed,
                                target="status_code",
                                expected=a.expected,
                                actual=status_code,
                                message=f"Page returned status {status_code}" if not passed else None,
                            )
                        )

                failed = any(not ar.passed for ar in assertion_results)
                return (
                    StepResult(
                        step_name=step.name,
                        status=TestStatus.FAILED if failed else TestStatus.PASSED,
                        duration_ms=round(duration_ms, 2),
                        assertion_results=assertion_results,
                        error_message="Page navigation status mismatch" if failed else None,
                    ),
                    failed,
                )

            elif stype == "browser_fill":
                selector = step.selector
                value = step.value or ""
                await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                await page.fill(selector, value)
                duration_ms = (time.perf_counter() - step_start) * 1000.0
                return (
                    StepResult(
                        step_name=step.name,
                        status=TestStatus.PASSED,
                        duration_ms=round(duration_ms, 2),
                    ),
                    False,
                )

            elif stype == "browser_click":
                selector = step.selector
                await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                await page.click(selector)
                # Brief pause for DOM reactions
                await asyncio.sleep(0.3)
                duration_ms = (time.perf_counter() - step_start) * 1000.0
                return (
                    StepResult(
                        step_name=step.name,
                        status=TestStatus.PASSED,
                        duration_ms=round(duration_ms, 2),
                    ),
                    False,
                )

            elif stype == "browser_screenshot":
                screenshot = await evidence_collector.capture_screenshot(page, step.name)
                duration_ms = (time.perf_counter() - step_start) * 1000.0
                return (
                    StepResult(
                        step_name=step.name,
                        status=TestStatus.PASSED,
                        duration_ms=round(duration_ms, 2),
                    ),
                    False,
                )

            else:
                # Unknown step type fallback
                duration_ms = (time.perf_counter() - step_start) * 1000.0
                return (
                    StepResult(
                        step_name=step.name,
                        status=TestStatus.PASSED,
                        duration_ms=round(duration_ms, 2),
                    ),
                    False,
                )

        except Exception as e:
            duration_ms = (time.perf_counter() - step_start) * 1000.0
            is_timeout = "timeout" in str(e).lower()
            return (
                StepResult(
                    step_name=step.name,
                    status=TestStatus.FAILED if is_timeout else TestStatus.ERROR,
                    duration_ms=round(duration_ms, 2),
                    error_message=f"Browser action failed: {e}",
                ),
                True,
            )

    def _determine_failure_category(
        self, step_res: StepResult, console_logs: list[Any]
    ) -> FailureCategory:
        err = (step_res.error_message or "").lower()
        if "timeout" in err:
            return FailureCategory.TIMEOUT
        if any("typeerror" in c.text.lower() or "referenceerror" in c.text.lower() for c in console_logs):
            return FailureCategory.APPLICATION_ERROR
        if "assertion" in err:
            return FailureCategory.ASSERTION_FAILURE
        return FailureCategory.BROWSER_ERROR

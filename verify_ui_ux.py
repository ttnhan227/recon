import asyncio
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

from recon.common.models import (
    ConsoleLog,
    FailureAnalysis,
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    Hypothesis,
    RunSummary,
    ScreenshotEvidence,
    StepResult,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.reporting.html_reporter import HTMLReporter


async def run_verification():
    print("=== Starting Comprehensive UI/UX Verification ===")
    output_dir = Path("reports/ui_audit_verification")
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = output_dir / "screenshots"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # 1. Generate a dummy screenshot image for evidence embedding
    dummy_sc_path = evidence_dir / "sample_failure.png"
    dummy_sc_path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    # 2. Render report with realistic data
    now = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id="audit-verify-2026",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        total=3,
        passed=1,
        failed=2,
        errors=0,
        exit_code=1,
        duration_seconds=4.12,
        failure_breakdown={"ApplicationError": 1, "BrowserError": 1},
        category_breakdown={
            "HAPPY_PATH": {"PASSED": 1},
            "ERROR_HANDLING": {"FAILED": 1},
            "SECURITY": {"FAILED": 1},
        },
    )

    results = [
        TestResult(
            test_id="TEST-API-001",
            test_name="Health Ping Endpoint",
            test_type=TestType.API,
            category=TestCategory.HAPPY_PATH,
            status=TestStatus.PASSED,
            duration_ms=45,
            step_results=[
                StepResult(
                    step_name="GET /api/health",
                    status=TestStatus.PASSED,
                    duration_ms=45,
                    http_trace=HTTPTrace(
                        request_method="GET",
                        request_url="http://localhost:8000/api/health",
                        response_status=200,
                        response_body={"status": "ok", "service": "recon-qa"},
                    ),
                )
            ],
        ),
        TestResult(
            test_id="TEST-API-002",
            test_name="Create Order Without Currency (500 Error)",
            test_type=TestType.API,
            category=TestCategory.ERROR_HANDLING,
            status=TestStatus.FAILED,
            duration_ms=310,
            step_results=[
                StepResult(
                    step_name="POST /api/orders",
                    status=TestStatus.FAILED,
                    duration_ms=310,
                    error_message="NullReferenceException: Object reference not set",
                    http_trace=HTTPTrace(
                        request_method="POST",
                        request_url="http://localhost:8000/api/orders",
                        request_body={"item_id": "ITEM-100", "quantity": 1},
                        response_status=500,
                        response_body={"detail": "NullReferenceException"},
                    ),
                )
            ],
            failure_analysis=FailureAnalysis(
                confidence_score=0.94,
                observed_facts=[
                    "Server returned status 500",
                    "currency parameter omitted in request",
                ],
                hypotheses=[
                    Hypothesis(
                        hypothesis="NullReferenceException thrown at PaymentGateway.ValidateCurrency",
                        confidence=0.96,
                        explanation="Backend code assumes currency is always present despite OpenAPI saying optional",
                    )
                ],
                suggested_fix="if not order.currency: currency = 'USD'",
            ),
        ),
        TestResult(
            test_id="TEST-UI-003",
            test_name="User Login Flow - Broken JS Event Handler",
            test_type=TestType.BROWSER,
            category=TestCategory.SECURITY,
            status=TestStatus.FAILED,
            duration_ms=850,
            failure_evidence=FailureEvidence(
                failure_category=FailureCategory.BROWSER_ERROR,
                message="Uncaught TypeError: Cannot read properties of undefined (reading 'token')",
                console_errors=[
                    ConsoleLog(
                        level="error",
                        text="Uncaught TypeError: Cannot read properties of undefined (reading 'token')",
                        location="http://localhost:8000/",
                    )
                ],
                stack_trace="TypeError: Cannot read properties of undefined (reading 'token')\n    at HTMLButtonElement.<anonymous> (index.html:105)",
                screenshots=[
                    ScreenshotEvidence(
                        name="login_failure",
                        step_name="Click Login",
                        file_path=str(dummy_sc_path),
                        step_index=1,
                    )
                ],
            ),
        ),
    ]

    reporter = HTMLReporter(output_dir=output_dir)
    report_file = reporter.write_report(summary, results)
    print(f"Generated report at: {report_file.resolve()}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        report_url = report_file.resolve().as_uri()

        viewports = [
            ("desktop", 1280, 800),
            ("tablet", 768, 1024),
            ("mobile", 375, 667),
        ]

        print("\n--- Verifying HTML Report across viewports ---")
        for name, w, h in viewports:
            page = await browser.new_page(viewport={"width": w, "height": h})
            await page.goto(report_url)

            # Check horizontal scroll / overflow
            scroll_width = await page.evaluate("document.documentElement.scrollWidth")
            client_width = await page.evaluate("document.documentElement.clientWidth")
            assert scroll_width <= client_width + 1, (
                f"Horizontal overflow on {name}: {scroll_width} > {client_width}"
            )

            # Capture screenshot
            sc_dest = evidence_dir / f"report_{name}.png"
            await page.screenshot(path=str(sc_dest), full_page=True)
            print(
                f"[{name.upper()}] Viewport {w}x{h}: verified no overflow. Saved screenshot: {sc_dest}"
            )
            await page.close()

        # Interactive feature verification on Report page
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(report_url)

        # 1. Skip link test
        await page.keyboard.press("Tab")
        focused_id = await page.evaluate("document.activeElement.className")
        assert "skip-link" in focused_id, f"Expected skip link to receive focus, got {focused_id}"

        # 2. Theme toggle test & Light theme screenshot
        is_dark_before = await page.evaluate("document.documentElement.classList.contains('dark')")
        await page.click("#themeToggle")
        is_dark_after = await page.evaluate("document.documentElement.classList.contains('dark')")
        assert is_dark_before != is_dark_after, "Theme toggle did not switch dark class"
        sc_light = evidence_dir / "report_light.png"
        await page.screenshot(path=str(sc_light), full_page=True)
        print(f"Captured light theme screenshot: {sc_light}")
        await page.click("#themeToggle")  # Toggle back to dark

        # 3. Expand All & Failure Details Screenshot
        await page.click("#btnExpandAll")
        all_expanded = await page.evaluate(
            "Array.from(document.querySelectorAll('.test-body')).every(el => !el.hasAttribute('hidden'))"
        )
        assert all_expanded, "Expected all test bodies to be open after Expand All"
        sc_expanded = evidence_dir / "report_expanded_details.png"
        await page.screenshot(path=str(sc_expanded), full_page=True)
        print(f"Captured expanded diagnostics screenshot: {sc_expanded}")

        # 4. Collapse All
        await page.click("#btnCollapseAll")
        all_hidden = await page.evaluate(
            "Array.from(document.querySelectorAll('.test-body')).every(el => el.hasAttribute('hidden'))"
        )
        assert all_hidden, "Expected all test bodies to be hidden after Collapse All"

        # 5. Filters
        await page.click("#filter-failed")
        displayed_failed = await page.evaluate(
            "document.querySelectorAll('#testList .test-row').length"
        )
        assert displayed_failed == 2, f"Expected 2 failed tests, got {displayed_failed}"
        live_text = await page.text_content("#filterStatus")
        assert "Showing 2 of 3 tests" in live_text

        # 6. Search
        await page.fill("#searchInput", "health")
        displayed_search = await page.evaluate(
            "document.querySelectorAll('#testList .test-row').length"
        )
        # Since health is PASSED and filter is FAILED, should be 0
        assert displayed_search == 0
        await page.click("#filter-all")
        displayed_all_search = await page.evaluate(
            "document.querySelectorAll('#testList .test-row').length"
        )
        assert displayed_all_search == 1

        # 7. Sort Dropdown
        await page.fill("#searchInput", "")
        await page.select_option("#sortSelect", "duration-desc")
        first_test_id = await page.evaluate(
            "document.querySelector('#testList .test-id').textContent"
        )
        # TEST-UI-003 took 850ms, so it should be first when sorted by duration descending
        assert first_test_id == "TEST-UI-003", f"Expected TEST-UI-003 first, got {first_test_id}"

        # 8. Copy button test
        await page.click("#btnExpandAll")
        copy_btn = await page.query_selector(".btn-copy")
        assert copy_btn is not None
        await copy_btn.click()
        await asyncio.sleep(0.2)
        btn_text = await copy_btn.text_content()
        assert "Copied" in btn_text

        # 9. Keyboard shortcut '/' test
        await page.click("h1")  # defocus
        await page.keyboard.press("/")
        focused_search = await page.evaluate("document.activeElement.id")
        assert focused_search == "searchInput", (
            f"Expected searchInput focused on '/', got {focused_search}"
        )

        # 10. Copy cURL and Shortcuts Dialog check & Screenshot
        shortcuts_btn = await page.query_selector("#btnShortcuts")
        assert shortcuts_btn is not None
        await page.click("#btnShortcuts")
        is_modal_open = await page.evaluate("document.getElementById('shortcutsModal').open")
        assert is_modal_open, "Expected shortcuts modal to be open"
        sc_shortcuts = evidence_dir / "report_shortcuts.png"
        await page.screenshot(path=str(sc_shortcuts))
        print(f"Captured shortcuts modal screenshot: {sc_shortcuts}")
        await page.keyboard.press("Escape")

        print("Report interactive actions and shortcuts verified successfully!")
        await browser.close()

    print("\n=== UI/UX Verification Completed Successfully! ===")


if __name__ == "__main__":
    asyncio.run(run_verification())

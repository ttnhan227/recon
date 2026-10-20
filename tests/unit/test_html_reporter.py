from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from recon.common.models import (
    ConsoleLog,
    FailureAnalysis,
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    Hypothesis,
    RunSummary,
    StepResult,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.reporting.html_reporter import HTMLReporter


def test_html_reporter_semantic_structure_and_landmarks(tmp_path: Path):
    reporter = HTMLReporter(output_dir=tmp_path)
    now = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id="audit-run-001",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        total=2,
        passed=1,
        failed=1,
        errors=0,
        exit_code=1,
        duration_seconds=3.45,
        failure_breakdown={"ApplicationError": 1},
        category_breakdown={"HAPPY_PATH": {"PASSED": 1}, "ERROR_HANDLING": {"FAILED": 1}},
    )

    results = [
        TestResult(
            test_id="TEST-001",
            test_name="Place Order - Success",
            test_type=TestType.API,
            category=TestCategory.HAPPY_PATH,
            status=TestStatus.PASSED,
            duration_ms=120,
        ),
        TestResult(
            test_id="TEST-002",
            test_name="Place Order - Missing Currency (500)",
            test_type=TestType.API,
            category=TestCategory.ERROR_HANDLING,
            status=TestStatus.FAILED,
            duration_ms=250,
            step_results=[
                StepResult(
                    step_name="POST /api/orders",
                    status=TestStatus.FAILED,
                    duration_ms=250,
                    error_message="500 Internal Server Error",
                    http_trace=HTTPTrace(
                        request_method="POST",
                        request_url="http://localhost:8000/api/orders",
                        response_status=500,
                        response_body={"detail": "NullReferenceException"},
                    ),
                )
            ],
            failure_analysis=FailureAnalysis(
                confidence_score=0.92,
                observed_facts=["HTTP 500 returned on /api/orders"],
                hypotheses=[
                    Hypothesis(
                        hypothesis="Server threw unhandled NullReferenceException when currency was None",
                        confidence=0.95,
                        explanation="PaymentGateway.ValidateCurrency dereferences currency without null check",
                    )
                ],
                suggested_fix="Check if currency is None before dereferencing in PaymentGateway.ValidateCurrency",
            ),
        ),
    ]

    report_path = reporter.write_report(summary, results)
    assert report_path.exists()
    assert (tmp_path / "latest.html").exists()

    content = report_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")

    # 1. HTML document declaration and language
    assert soup.html is not None
    assert soup.html.get("lang") == "en"

    # 2. Viewport meta tag
    viewport = soup.find("meta", attrs={"name": "viewport"})
    assert viewport is not None
    assert "width=device-width" in viewport["content"]

    # 3. Skip link
    skip_link = soup.find("a", class_="skip-link")
    assert skip_link is not None
    assert skip_link["href"] == "#main-content"

    # 4. Landmarks: header, main, footer, dialog
    header = soup.find("header", class_="report-header")
    assert header is not None
    assert header.get("role") == "banner"

    main = soup.find("main", id="main-content")
    assert main is not None
    assert main.get("role") == "main"

    footer = soup.find("footer", class_="report-footer")
    assert footer is not None
    assert footer.get("role") == "contentinfo"

    modal = soup.find("dialog", id="screenshotModal")
    assert modal is not None
    assert modal.get("aria-labelledby") == "modalTitle"

    # 5. Heading hierarchy
    h1 = soup.find("h1")
    assert h1 is not None
    assert "QA Test Report" in h1.text

    h2s = soup.find_all("h2")
    assert len(h2s) >= 2  # Executive Metrics, Test Execution Results

    # 6. ARIA attributes & Controls
    search_input = soup.find("input", id="searchInput")
    assert search_input is not None
    assert search_input.get("type") == "search"
    search_label = soup.find("label", attrs={"for": "searchInput"})
    assert search_label is not None

    filter_status = soup.find("div", id="filterStatus")
    assert filter_status is not None
    assert filter_status.get("aria-live") == "polite"

    # 7. Batch buttons, theme toggle, and sort controls
    expand_all = soup.find("button", id="btnExpandAll")
    collapse_all = soup.find("button", id="btnCollapseAll")
    theme_toggle = soup.find("button", id="themeToggle")
    sort_select = soup.find("select", id="sortSelect")
    assert expand_all is not None
    assert collapse_all is not None
    assert theme_toggle is not None
    assert sort_select is not None

    # 8. Interactive test filter buttons
    btn_all = soup.find("button", id="filter-all")
    assert btn_all is not None
    assert btn_all.get("aria-pressed") == "true"

    # 9. Progress bar
    progress_bar = soup.find("div", class_="progress-bar-container")
    assert progress_bar is not None
    assert progress_bar.get("role") == "progressbar"


def test_html_reporter_handles_zero_failures(tmp_path: Path):
    reporter = HTMLReporter(output_dir=tmp_path)
    now = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id="audit-run-perfect",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        total=5,
        passed=5,
        failed=0,
        errors=0,
        exit_code=0,
        duration_seconds=1.2,
        failure_breakdown={},
        category_breakdown={"HAPPY_PATH": {"PASSED": 5}},
    )

    results = [
        TestResult(
            test_id=f"TEST-00{i}",
            test_name=f"Health Ping {i}",
            test_type=TestType.API,
            category=TestCategory.HAPPY_PATH,
            status=TestStatus.PASSED,
            duration_ms=20,
        )
        for i in range(1, 6)
    ]

    report_path = reporter.write_report(summary, results)
    content = report_path.read_text(encoding="utf-8")

    assert "Zero Failures Detected" in content
    assert "Pass Rate: 100.0%" in content


def test_html_reporter_renders_console_and_stack_trace_evidence(tmp_path: Path):
    reporter = HTMLReporter(output_dir=tmp_path)
    now = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id="audit-run-evidence",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        total=1,
        passed=0,
        failed=1,
        errors=0,
        exit_code=1,
        duration_seconds=2.1,
        failure_breakdown={"BrowserError": 1},
        category_breakdown={"SECURITY": {"FAILED": 1}},
    )

    results = [
        TestResult(
            test_id="TEST-ERR-001",
            test_name="Client JS Exception Detection",
            test_type=TestType.BROWSER,
            category=TestCategory.SECURITY,
            status=TestStatus.FAILED,
            duration_ms=450,
            failure_evidence=FailureEvidence(
                failure_category=FailureCategory.BROWSER_ERROR,
                message="Uncaught TypeError in login event handler",
                console_errors=[
                    ConsoleLog(
                        level="error",
                        text="Uncaught TypeError: Cannot read token of undefined",
                        location="http://localhost:8000/main.js",
                    )
                ],
                stack_trace="Traceback:\n  at HTMLButtonElement.onclick (index.html:105)",
            ),
        )
    ]

    report_path = reporter.write_report(summary, results)
    content = report_path.read_text(encoding="utf-8")

    assert "Browser Console Errors" in content
    assert "Uncaught TypeError: Cannot read token of undefined" in content
    assert "Diagnostic Stack Trace" in content
    assert "Copy Stack Trace" in content

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from recon.common.models import (
    FailureCategory,
    FailureEvidence,
    RunSummary,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.reporting.markdown_reporter import MarkdownReporter


def test_markdown_reporter_generates_valid_content(tmp_path: Path):
    reporter = MarkdownReporter(output_dir=tmp_path)
    now = datetime.now(timezone.utc)

    summary = RunSummary(
        run_id="run-test-123",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        duration_seconds=3.45,
        total=5,
        passed=4,
        failed=1,
        skipped=0,
        errors=0,
        failure_breakdown={"APPLICATION_ERROR": 1},
        category_breakdown={"HAPPY_PATH": {"total": 5, "passed": 4}},
        exit_code=1,
    )

    failed_result = TestResult(
        test_id="res-1",
        test_name="GET /api/users",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
        status=TestStatus.FAILED,
        duration_ms=250.0,
        failure_evidence=FailureEvidence(
            message="Internal Server Error: Database connection lost",
            failure_category=FailureCategory.APPLICATION_ERROR,
        ),
    )

    markdown = reporter.generate_markdown(summary, [failed_result])

    assert "# Recon QA Test Run Summary: [FAILED]" in markdown
    assert "http://localhost:8000" in markdown
    assert "3.45s" in markdown
    assert "| 5 | 4 | 1 | 0 | 0 | **FAIL** |" in markdown
    assert "| `APPLICATION_ERROR` | 1 |" in markdown
    assert "GET /api/users" in markdown
    assert "Database connection lost" in markdown


def test_markdown_reporter_writes_summary_and_latest(tmp_path: Path, monkeypatch):
    step_summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary_file))

    reporter = MarkdownReporter(output_dir=tmp_path)
    now = datetime.now(timezone.utc)

    summary = RunSummary(
        run_id="run-456",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        duration_seconds=1.2,
        total=2,
        passed=2,
        failed=0,
        skipped=0,
        errors=0,
        failure_breakdown={},
        category_breakdown={"HAPPY_PATH": {"total": 2, "passed": 2}},
        exit_code=0,
    )

    written_path = reporter.write_report(summary, [])

    assert written_path.exists()
    assert (tmp_path / "latest.md").exists()
    assert step_summary_file.exists()
    assert "[PASSED]" in step_summary_file.read_text(encoding="utf-8")

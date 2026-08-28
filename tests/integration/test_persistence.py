import pytest
from datetime import datetime, timezone
from recon.common.models import RunSummary, TestCase, TestCategory, TestResult, TestStatus, TestType
from recon.persistence.database import DatabaseManager


@pytest.mark.asyncio
async def test_database_persistence_sqlite_in_memory():
    db = DatabaseManager(db_url="sqlite+aiosqlite:///:memory:")
    await db.init_db()

    now = datetime.now(timezone.utc)
    summary = RunSummary(
        run_id="run-test-123",
        target_url="http://localhost:8000",
        started_at=now,
        completed_at=now,
        duration_seconds=2.5,
        total=2,
        passed=1,
        failed=1,
        exit_code=1,
    )

    results = [
        TestResult(
            test_id="API-001",
            test_name="Health Check",
            category=TestCategory.HAPPY_PATH,
            test_type=TestType.API,
            status=TestStatus.PASSED,
            duration_ms=15.0,
            started_at=now,
            completed_at=now,
        ),
        TestResult(
            test_id="API-002",
            test_name="Order Missing Currency",
            category=TestCategory.HAPPY_PATH,
            test_type=TestType.API,
            status=TestStatus.FAILED,
            duration_ms=25.0,
            started_at=now,
            completed_at=now,
        ),
    ]

    await db.save_run(summary, results)

    loaded_summary = await db.get_run_summary("run-test-123")
    assert loaded_summary is not None
    assert loaded_summary.run_id == "run-test-123"
    assert loaded_summary.total == 2
    assert loaded_summary.passed == 1

    loaded_results = await db.get_run_results("run-test-123")
    assert len(loaded_results) == 2
    assert loaded_results[0].test_id == "API-001"
    assert loaded_results[1].test_id == "API-002"

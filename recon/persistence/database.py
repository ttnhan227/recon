from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, desc

from recon.common.config import settings
from recon.common.models import RunSummary, TestResult
from recon.persistence.models import Base, TestResultRecord, TestRunRecord


class DatabaseManager:
    """Manages async database connections and migrations."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or settings.database_url
        self.engine = create_async_engine(self.db_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self) -> None:
        """Creates database schema tables if they don't already exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Disposes the SQLAlchemy async engine connection pool."""
        await self.engine.dispose()

    async def save_run(self, summary: RunSummary, results: list[TestResult]) -> None:
        """Persists a test run and its detailed results."""
        await self.init_db()
        async with self.session_factory() as session:
            async with session.begin():
                run_rec = TestRunRecord(
                    run_id=summary.run_id,
                    target_url=summary.target_url,
                    started_at=summary.started_at,
                    completed_at=summary.completed_at,
                    duration_seconds=summary.duration_seconds,
                    total=summary.total,
                    passed=summary.passed,
                    failed=summary.failed,
                    skipped=summary.skipped,
                    errors=summary.errors,
                    exit_code=summary.exit_code,
                    summary_json=summary.model_dump_json(),
                )
                session.add(run_rec)

                for res in results:
                    fail_cat = (
                        res.failure_evidence.failure_category.value
                        if res.failure_evidence
                        else None
                    )
                    res_rec = TestResultRecord(
                        run_id=summary.run_id,
                        test_id=res.test_id,
                        test_name=res.test_name,
                        category=res.category.value,
                        test_type=res.test_type.value,
                        status=res.status.value,
                        duration_ms=res.duration_ms,
                        failure_category=fail_cat,
                        result_json=res.model_dump_json(),
                    )
                    session.add(res_rec)

    async def get_run_summary(self, run_id: str) -> RunSummary | None:
        """Retrieves RunSummary by run_id."""
        await self.init_db()
        async with self.session_factory() as session:
            stmt = select(TestRunRecord).where(TestRunRecord.run_id == run_id)
            res = await session.execute(stmt)
            rec = res.scalars().first()
            if rec and rec.summary_json:
                return RunSummary.model_validate_json(rec.summary_json)
            return None

    async def get_run_results(self, run_id: str) -> list[TestResult]:
        """Retrieves all TestResults for a run_id."""
        await self.init_db()
        async with self.session_factory() as session:
            stmt = select(TestResultRecord).where(TestResultRecord.run_id == run_id)
            res = await session.execute(stmt)
            records = res.scalars().all()
            return [TestResult.model_validate_json(r.result_json) for r in records]

    async def list_runs(self, limit: int = 10) -> list[RunSummary]:
        """Lists recent test runs."""
        await self.init_db()
        async with self.session_factory() as session:
            stmt = select(TestRunRecord).order_by(desc(TestRunRecord.started_at)).limit(limit)
            res = await session.execute(stmt)
            records = res.scalars().all()
            runs = []
            for r in records:
                if r.summary_json:
                    runs.append(RunSummary.model_validate_json(r.summary_json))
            return runs

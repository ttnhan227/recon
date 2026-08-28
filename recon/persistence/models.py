from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TestRunRecord(Base):
    """Stores high-level summary of a test execution run."""

    __tablename__ = "test_runs"

    run_id = Column(String(64), primary_key=True, index=True)
    target_url = Column(String(512), nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    duration_seconds = Column(Float, default=0.0)
    total = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    errors = Column(Integer, default=0)
    exit_code = Column(Integer, default=0)
    summary_json = Column(Text, nullable=True)


class TestResultRecord(Base):
    """Stores individual test result, evidence, and failure analysis."""

    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), index=True, nullable=False)
    test_id = Column(String(64), nullable=False)
    test_name = Column(String(256), nullable=False)
    category = Column(String(64), nullable=False)
    test_type = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    duration_ms = Column(Float, default=0.0)
    failure_category = Column(String(64), nullable=True)
    result_json = Column(Text, nullable=False)

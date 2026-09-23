from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from recon.common.config import settings
from recon.common.models import RunSummary
from recon.orchestration.orchestrator import TestOrchestrator
from recon.persistence.database import DatabaseManager

api_app = FastAPI(
    title="Recon QA API",
    description="HTTP API for triggering remote test runs, webhooks, and retrieving test reports.",
    version=settings.version,
)


class TriggerRunRequest(BaseModel):
    target_url: str = Field(description="Target application URL")
    spec_url: str | None = None
    enable_browser: bool = False
    concurrency: int = 4
    enable_ai: bool = True
    tags: list[str] | None = None


@api_app.post("/api/v1/runs", response_model=dict[str, Any])
async def trigger_test_run(req: TriggerRunRequest):
    """Executes a full QA test run and returns run summary."""
    orchestrator = TestOrchestrator(
        concurrency=req.concurrency,
        enable_ai=req.enable_ai,
    )
    summary, results = await orchestrator.run_pipeline(
        target_url=req.target_url,
        spec_path_or_url=req.spec_url,
        enable_browser=req.enable_browser,
        tags=req.tags,
    )
    return {
        "run_id": summary.run_id,
        "target_url": summary.target_url,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "exit_code": summary.exit_code,
        "duration_seconds": summary.duration_seconds,
        "failure_breakdown": summary.failure_breakdown,
    }


@api_app.get("/api/v1/runs/{run_id}", response_model=RunSummary)
async def get_run_details(run_id: str):
    """Retrieves RunSummary for a specific run_id."""
    db = DatabaseManager()
    try:
        summary = await db.get_run_summary(run_id)
        if not summary:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return summary
    finally:
        await db.close()

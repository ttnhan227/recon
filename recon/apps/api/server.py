from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from recon.common.config import get_project_slug, settings
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
    project_slug = get_project_slug(req.target_url)
    out_dir = (settings.reports_dir / project_slug).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    orchestrator = TestOrchestrator(
        concurrency=req.concurrency,
        output_dir=out_dir,
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
        clean_id = run_id.removeprefix("run-")
        summary = await db.get_run_summary(clean_id)
        if not summary:
            summary = await db.get_run_summary(f"run-{clean_id}")
        if not summary:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return summary
    finally:
        await db.close()


@api_app.get("/api/v1/runs/{run_id}/report", response_class=HTMLResponse)
async def get_run_report(run_id: str):
    """Retrieves the standalone HTML test report for a specific run_id."""
    clean_id = run_id.removeprefix("run-")
    search_dirs = [settings.reports_dir, Path("./reports").resolve()]

    report_file: Path | None = None
    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        direct = s_dir / f"run-{clean_id}" / "report.html"
        if direct.exists():
            report_file = direct
            break
        matches = list(s_dir.glob(f"**/run-{clean_id}/report.html"))
        if matches:
            report_file = matches[0]
            break

    if not report_file or not report_file.exists():
        raise HTTPException(status_code=404, detail=f"HTML report for run {run_id} not found")

    return HTMLResponse(content=report_file.read_text(encoding="utf-8"))

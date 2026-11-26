from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from recon.common.config import get_project_slug, settings
from recon.common.exceptions import DiscoveryError, SSRFSecurityError, TargetUnreachableError
from recon.common.models import RunSummary
from recon.common.telemetry import extract_trace_context, get_current_trace_ids, get_tracer
from recon.orchestration.orchestrator import TestOrchestrator
from recon.persistence.database import DatabaseManager

api_app = FastAPI(
    title="Recon QA API",
    description="HTTP API for triggering remote test runs, webhooks, and retrieving test reports.",
    version=settings.version,
)


@api_app.middleware("http")
async def tracing_middleware(request: Request, call_next: Any) -> Response:
    """Extracts incoming W3C traceparent, opens a server span, and sets X-Trace-Id on all responses."""
    tracer = get_tracer("recon.api_server")
    extracted_context = extract_trace_context(dict(request.headers))
    method = request.method
    path = request.url.path

    with tracer.start_as_current_span(
        f"{method} {path}",
        context=extracted_context,
        attributes={
            "http.method": method,
            "http.route": path,
        },
    ) as span:
        trace_id, _ = get_current_trace_ids()
        try:
            response = await call_next(request)
            if trace_id:
                response.headers["X-Trace-Id"] = trace_id
            span.set_attribute("http.status_code", response.status_code)
            return response
        except Exception:
            span.set_attribute("http.status_code", 500)
            raise


@api_app.exception_handler(SSRFSecurityError)
async def _ssrf_exception_handler(_request: Request, exc: SSRFSecurityError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@api_app.exception_handler(DiscoveryError)
async def _discovery_exception_handler(_request: Request, exc: DiscoveryError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@api_app.exception_handler(TargetUnreachableError)
async def _unreachable_exception_handler(
    _request: Request, exc: TargetUnreachableError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


def _validate_run_id(run_id: str) -> str:
    """Rejects path-traversal, glob injection, or malformed run IDs before filesystem lookup."""
    if not run_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    if not run_id.removeprefix("run-"):
        raise HTTPException(status_code=400, detail="Invalid run_id")
    return run_id


class TriggerRunRequest(BaseModel):
    target_url: str = Field(description="Target application URL")
    spec_url: str | None = None
    enable_browser: bool = False
    concurrency: int = Field(default=4, ge=1, le=32)
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
        "trace_id": summary.trace_id,
    }


@api_app.get("/api/v1/runs/{run_id}", response_model=RunSummary)
async def get_run_details(run_id: str):
    """Retrieves RunSummary for a specific run_id."""
    _validate_run_id(run_id)
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
    _validate_run_id(run_id)
    clean_id = run_id.removeprefix("run-")
    search_dirs = [settings.reports_dir, Path("./reports").resolve()]

    report_file: Path | None = None
    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        resolved_base = s_dir.resolve()
        direct = (s_dir / f"run-{clean_id}" / "report.html").resolve()
        if direct.is_relative_to(resolved_base) and direct.exists():
            report_file = direct
            break
        matches = [
            m.resolve()
            for m in s_dir.glob(f"**/run-{clean_id}/report.html")
            if m.resolve().is_relative_to(resolved_base)
        ]
        if matches:
            report_file = matches[0]
            break

    if not report_file or not report_file.exists():
        raise HTTPException(status_code=404, detail=f"HTML report for run {run_id} not found")

    return HTMLResponse(content=report_file.read_text(encoding="utf-8"))

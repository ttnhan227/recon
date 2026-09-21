from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recon.common.models import ConsoleLog, NetworkError, ScreenshotEvidence


class BrowserEvidenceCollector:
    """Collects screenshots, console errors, and network errors for browser executions."""

    def __init__(self, run_id: str, output_dir: Path | str = "./reports"):
        self.run_id = run_id
        self.output_dir = Path(output_dir) / f"run-{run_id}" / "screenshots"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.console_logs: list[ConsoleLog] = []
        self.network_errors: list[NetworkError] = []
        self.screenshots: list[ScreenshotEvidence] = []
        self.page_errors: list[str] = []

    def handle_console(self, msg: Any) -> None:
        """Playwright console event callback."""
        level = msg.type
        text = msg.text
        location = str(msg.location) if hasattr(msg, "location") else None
        self.console_logs.append(
            ConsoleLog(
                level=level,
                text=text,
                location=location,
                timestamp=datetime.now(timezone.utc),
            )
        )

    def handle_page_error(self, exc: Any) -> None:
        """Playwright pageerror event callback for uncaught JS runtime exceptions."""
        err_msg = str(exc)
        self.page_errors.append(err_msg)
        self.console_logs.append(
            ConsoleLog(
                level="error",
                text=f"Uncaught Exception: {err_msg}",
                location=None,
                timestamp=datetime.now(timezone.utc),
            )
        )

    def handle_request_failed(self, req: Any) -> None:
        """Playwright requestfailed event callback."""
        failure_text = str(req.failure) if hasattr(req, "failure") else "Request failed"
        status_code = None
        try:
            res = req.response() if callable(getattr(req, "response", None)) else None
            status_code = res.status if res else None
        except Exception:
            status_code = None
        req_url = str(getattr(req, "url", ""))
        req_method = str(getattr(req, "method", "GET"))
        self.network_errors.append(
            NetworkError(
                url=req_url,
                method=req_method,
                error_text=str(failure_text),
                status_code=status_code,
                timestamp=datetime.now(timezone.utc),
            )
        )

    async def capture_screenshot(
        self, page: Any, step_name: str, suffix: str = "failure"
    ) -> ScreenshotEvidence | None:
        """Captures full-page PNG screenshot and saves to reports directory."""
        try:
            clean_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in step_name)[:40]
            ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            file_name = f"{clean_name}_{suffix}_{ts}.png"
            file_path = self.output_dir / file_name

            await page.screenshot(path=str(file_path), full_page=True)

            evidence = ScreenshotEvidence(
                name=file_name,
                file_path=str(file_path),
                step_name=step_name,
                timestamp=datetime.now(timezone.utc),
            )
            self.screenshots.append(evidence)
            return evidence
        except Exception:
            return None

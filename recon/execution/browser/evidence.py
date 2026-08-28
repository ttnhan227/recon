from __future__ import annotations

import os
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

    def handle_request_failed(self, req: Any) -> None:
        """Playwright requestfailed event callback."""
        url = req.url
        method = req.method
        failure_text = req.failure if hasattr(req, "failure") else "Request failed"
        status_code = req.response.status if hasattr(req, "response") and req.response else None
        self.network_errors.append(
            NetworkError(
                url=url,
                method=method,
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

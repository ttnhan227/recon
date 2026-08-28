from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from rich.console import Console
from rich.logging import RichHandler

from recon.common.config import settings

# Context variables for request tracing & correlation IDs
current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("run_id", default=None)
current_test_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("test_id", default=None)
current_worker_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("worker_id", default=None)

console = Console(stderr=True)


class JSONLogFormatter(logging.Formatter):
    """Structured JSON formatter outputting timestamp, correlation IDs, log level, and message."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        run_id = current_run_id.get()
        if run_id:
            log_obj["run_id"] = run_id

        test_id = current_test_id.get()
        if test_id:
            log_obj["test_id"] = test_id

        worker_id = current_worker_id.get()
        if worker_id:
            log_obj["worker_id"] = worker_id

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        # Merge any extra attributes
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_obj.update(record.extra_data)

        return json.dumps(log_obj)


def setup_logger(name: str = "recon") -> logging.Logger:
    """Configures and returns a logger instance according to settings."""
    logger = logging.getLogger(name)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if not logger.handlers:
        if settings.json_logs:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JSONLogFormatter())
            logger.addHandler(handler)
        else:
            handler = RichHandler(
                console=console,
                show_time=True,
                show_level=True,
                show_path=False,
                rich_tracebacks=True,
            )
            logger.addHandler(handler)

    return logger


logger = setup_logger("recon")

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from recon import __version__


def get_recon_home() -> Path:
    """Returns ~/.recon base directory and ensures it exists."""
    recon_home = Path.home() / ".recon"
    recon_home.mkdir(parents=True, exist_ok=True)
    return recon_home


def get_project_slug(target: str | None = None, cwd: Path | None = None) -> str:
    """Derives a clean project slug from current working directory or target URL."""
    generic_names = {
        "projects",
        "workspace",
        "workspaces",
        "src",
        "app",
        "server",
        "client",
        "code",
        "home",
        "users",
        "runner",
        "work",
        "documents",
        "desktop",
        "downloads",
        "tmp",
        "temp",
        "root",
    }

    # 1. Check current working directory or explicit cwd first
    curr = cwd if cwd is not None else Path.cwd()
    try:
        if cwd is None:
            curr = curr.resolve()
    except Exception:
        pass

    while curr and curr.name:
        name = curr.name.rstrip(":")
        if name.lower() not in generic_names and name:
            clean = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower()).strip("_")
            if clean:
                return clean
        if curr.parent == curr:
            break
        curr = curr.parent

    # 2. If working directory was generic, fallback to target URL
    if target:
        try:
            parsed = urlparse(target)
            host = (parsed.hostname or "").replace(".", "_")
            port = f"_{parsed.port}" if parsed.port else ""
            if host:
                return f"{host}{port}".lower()
        except Exception:
            pass

    return "default"


class ReconSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RECON_",
        env_file=(".env", str(Path.home() / ".recon" / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "Recon QA"
    version: str = __version__
    log_level: str = "INFO"
    json_logs: bool = False

    # Execution defaults
    default_concurrency: int = Field(default=4, ge=1, le=32)
    default_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    default_retries: int = Field(default=0, ge=0, le=5)
    max_response_size_bytes: int = Field(default=5 * 1024 * 1024)  # 5 MB

    # Paths & Persistence: Centralized in ~/.recon by default
    reports_dir: Path = Field(default_factory=lambda: get_recon_home() / "reports")
    database_url: str = Field(
        default_factory=lambda: f"sqlite+aiosqlite:///{get_recon_home().as_posix()}/recon.db"
    )
    redis_url: str | None = None

    # Security
    allow_localhost: bool = True
    allowed_hosts: list[str] = Field(default_factory=list)
    blocked_hosts: list[str] = Field(
        default_factory=lambda: [
            "169.254.169.254",  # AWS/GCP/Azure Metadata
            "metadata.google.internal",
            "100.100.100.200",  # Alibaba metadata
        ]
    )
    redact_sensitive_headers: list[str] = Field(
        default_factory=lambda: [
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "x-api-key",
            "api-key",
            "x-auth-token",
            "access_token",
            "secret",
        ]
    )
    redact_sensitive_keys: list[str] = Field(
        default_factory=lambda: [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "access_token",
            "private_key",
            "credit_card",
            "cvv",
        ]
    )

    # LLM Settings
    llm_provider: str = Field(
        default="mock"
    )  # mock, gemini, openai, mistral, anthropic, custom / compatible
    gemini_api_key: str | None = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    openai_api_key: str | None = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    mistral_api_key: str | None = Field(default_factory=lambda: os.getenv("MISTRAL_API_KEY"))
    anthropic_api_key: str | None = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    llm_base_url: str | None = Field(
        default_factory=lambda: os.getenv("OPENAI_BASE_URL") or os.getenv("RECON_LLM_BASE_URL")
    )
    gemini_model: str = "gemini-2.5-flash"
    openai_model: str = "gpt-4o-mini"
    mistral_model: str = "mistral-small-latest"
    anthropic_model: str = "claude-3-5-haiku-20241022"
    custom_model: str = Field(default="default", alias="RECON_LLM_MODEL")
    llm_temperature: float = 0.2


# Singleton instance
settings = ReconSettings()

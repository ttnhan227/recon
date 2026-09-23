from __future__ import annotations

import shutil
import sys

import httpx
from rich.console import Console
from rich.table import Table

from recon.common.config import settings

console = Console()


async def run_doctor(target_url: str | None = None) -> bool:
    """Performs system diagnostic checks and prints status table."""
    table = Table(title="Recon QA - System Diagnostics", title_style="bold cyan")
    table.add_column("Component", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Details", style="magenta")

    all_healthy = True

    # 1. Python Environment
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 12):
        table.add_row("Python Version", "[green]OK[/green]", f"Python {py_ver}")
    else:
        table.add_row(
            "Python Version", "[yellow]WARN[/yellow]", f"Python {py_ver} (3.12+ recommended)"
        )

    # 2. Playwright & Chromium
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # Check if chromium can launch
            browser = await p.chromium.launch(headless=True)
            await browser.close()
        table.add_row("Playwright & Chromium", "[green]OK[/green]", "Headless Chromium ready")
    except Exception as e:
        all_healthy = False
        table.add_row("Playwright & Chromium", "[red]FAIL[/red]", f"Browser check failed: {e}")

    # 3. Docker CLI
    docker_bin = shutil.which("docker")
    if docker_bin:
        table.add_row("Docker CLI", "[green]OK[/green]", f"Found at {docker_bin}")
    else:
        table.add_row("Docker CLI", "[yellow]OPTIONAL[/yellow]", "Docker not detected on PATH")

    # 4. Database Connection
    try:
        from recon.persistence.database import DatabaseManager

        db = DatabaseManager()
        await db.init_db()
        await db.close()
        table.add_row("Persistence (DB)", "[green]OK[/green]", f"{settings.database_url}")
    except Exception as e:
        all_healthy = False
        table.add_row("Persistence (DB)", "[red]FAIL[/red]", f"Database connection error: {e}")

    # 5. LLM Configuration
    provider_name = settings.llm_provider.lower()
    if provider_name == "gemini":
        has_key = bool(settings.gemini_api_key)
        status_str = "[green]CONFIGURED[/green]" if has_key else "[yellow]NO KEY[/yellow]"
        table.add_row(
            "AI Provider (Gemini)",
            status_str,
            f"Key present: {has_key} (Model: {settings.gemini_model})",
        )
    elif provider_name == "mistral":
        has_key = bool(settings.mistral_api_key)
        status_str = "[green]CONFIGURED[/green]" if has_key else "[yellow]NO KEY[/yellow]"
        table.add_row(
            "AI Provider (Mistral)",
            status_str,
            f"Key present: {has_key} (Model: {settings.mistral_model})",
        )
    elif provider_name == "openai":
        has_key = bool(settings.openai_api_key)
        status_str = "[green]CONFIGURED[/green]" if has_key else "[yellow]NO KEY[/yellow]"
        table.add_row(
            "AI Provider (OpenAI)",
            status_str,
            f"Key present: {has_key} (Model: {settings.openai_model})",
        )
    elif provider_name in ("anthropic", "claude"):
        has_key = bool(settings.anthropic_api_key)
        status_str = "[green]CONFIGURED[/green]" if has_key else "[yellow]NO KEY[/yellow]"
        table.add_row(
            "AI Provider (Anthropic)",
            status_str,
            f"Key present: {has_key} (Model: {settings.anthropic_model})",
        )
    elif provider_name in ("ollama", "custom", "compatible"):
        base_url = settings.llm_base_url or "http://localhost:11434/v1"
        table.add_row(
            "AI Provider (Compatible)",
            "[green]CONFIGURED[/green]",
            f"Base URL: {base_url} (Model: {settings.custom_model})",
        )
    else:
        table.add_row(
            "AI Provider (Mock)",
            "[green]MOCK READY[/green]",
            "Deterministic offline LLM simulation",
        )

    # 6. Target Connectivity (if specified)
    if target_url:
        try:
            async with httpx.AsyncClient(timeout=4.0, verify=False) as client:
                resp = await client.get(target_url)
                table.add_row(
                    "Target Reachability",
                    "[green]OK[/green]",
                    f"{target_url} returned HTTP {resp.status_code}",
                )
        except Exception as e:
            all_healthy = False
            table.add_row(
                "Target Reachability", "[red]FAIL[/red]", f"Cannot connect to {target_url}: {e}"
            )

    console.print(table)
    return all_healthy

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from recon.common.config import settings

console = Console()
config_app = typer.Typer(name="config", help="Manage AI providers, API keys, and active model selection.")

GLOBAL_CONFIG_DIR = Path.home() / ".recon"
GLOBAL_ENV_PATH = GLOBAL_CONFIG_DIR / ".env"
LOCAL_ENV_PATH = Path(".env")

PROVIDER_KEY_MAP = {
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "ollama": "RECON_LLM_BASE_URL",
    "custom": "OPENAI_API_KEY",
}

PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "mistral": "mistral-small-latest",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "ollama": "llama3.2",
    "custom": "default",
    "mock": "offline-rules",
}


def _parse_file(p: Path) -> dict[str, str]:
    if not p.exists():
        return {}
    data = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip().strip("\"'")
    return data


def read_env_file() -> dict[str, str]:
    """Reads global ~/.recon/.env, overlaying local .env if present."""
    combined = _parse_file(GLOBAL_ENV_PATH)
    combined.update(_parse_file(LOCAL_ENV_PATH))
    return combined


def update_env_file(updates: dict[str, str], is_local: bool = False) -> Path:
    """Updates config in ~/.recon/.env (default global) or .env (if local)."""
    target_path = LOCAL_ENV_PATH if is_local else GLOBAL_ENV_PATH

    if not is_local:
        GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = []
    if target_path.exists():
        lines = target_path.read_text(encoding="utf-8").splitlines()

    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                updated_keys.add(k)
                continue
        new_lines.append(line)

    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}")

    target_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return target_path


def mask_key(val: str | None) -> str:
    if not val:
        return "[dim]None[/dim]"
    if len(val) <= 8:
        return "***"
    return f"{val[:4]}...{val[-4:]}"


@config_app.command("list")
def list_providers():
    """Lists all supported AI providers, configuration status, and active provider."""
    env_data = read_env_file()
    active_provider = (env_data.get("RECON_LLM_PROVIDER") or settings.llm_provider).lower()

    table = Table(title="Recon AI Providers & Configuration", title_style="bold cyan")
    table.add_column("Active", justify="center", style="bold green", width=10)
    table.add_column("Provider", style="bold white", width=14)
    table.add_column("Status", justify="center", width=16)
    table.add_column("Configured Key", style="yellow", width=18)
    table.add_column("Default Model", style="cyan")

    all_providers = ["gemini", "mistral", "openai", "anthropic", "ollama", "custom", "mock"]

    for p in all_providers:
        is_active = (p == active_provider)
        active_mark = "[bold green]* ACTIVE[/bold green]" if is_active else ""

        if p == "mock":
            status_str = "[green]READY (Built-in)[/green]"
            key_str = "[dim]N/A[/dim]"
        elif p == "ollama":
            url_val = env_data.get("RECON_LLM_BASE_URL") or settings.llm_base_url or "http://localhost:11434/v1"
            status_str = "[green]READY (Local)[/green]" if is_active else "[dim]OPTIONAL[/dim]"
            key_str = f"[dim]{url_val}[/dim]"
        else:
            env_var_name = PROVIDER_KEY_MAP.get(p, "")
            key_val_raw = env_data.get(env_var_name) or os.getenv(env_var_name)
            if key_val_raw:
                status_str = "[green]CONFIGURED[/green]"
                key_str = mask_key(key_val_raw)
            else:
                status_str = "[yellow]NOT SET[/yellow]"
                key_str = "[dim]None[/dim]"

        default_model = PROVIDER_DEFAULT_MODELS.get(p, "default")
        table.add_row(active_mark, p.capitalize(), status_str, key_str, default_model)

    console.print(table)
    console.print(f"\n[dim]Global config:[/dim] [cyan]{GLOBAL_ENV_PATH}[/cyan]")
    if LOCAL_ENV_PATH.exists():
        console.print(f"[dim]Local override:[/dim] [cyan]{LOCAL_ENV_PATH.resolve()}[/cyan]")
    console.print("\n[dim]To switch provider: [bold]recon use <provider>[/bold][/dim]")
    console.print("[dim]To set an API key:   [bold]recon set-key [provider][/bold][/dim]")


@config_app.command("set-key")
def set_key(
    provider: Annotated[Optional[str], typer.Argument(help="Provider name: gemini, mistral, openai, anthropic, ollama")] = None,
    key: Annotated[Optional[str], typer.Option("--key", "-k", help="API Key value (optional, prompts if omitted)")] = None,
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Custom model name")] = None,
    set_active: Annotated[bool, typer.Option("--use/--no-use", help="Set as the active provider")] = True,
    local: Annotated[bool, typer.Option("--local", help="Save to local project .env instead of global ~/.recon/.env")] = False,
):
    """Interactively sets or updates an AI provider API key. Saved globally to ~/.recon/.env by default."""
    if not provider:
        console.print("[bold cyan]Select an AI Provider to configure:[/bold cyan]")
        console.print("  1. [bold green]Gemini[/bold green] (Google GenAI - Fast & Free Tier)")
        console.print("  2. [bold magenta]Mistral[/bold magenta] (Mistral AI / Codestral)")
        console.print("  3. [bold blue]OpenAI[/bold blue] (GPT-4o-mini / GPT-4o)")
        console.print("  4. [bold yellow]Anthropic[/bold yellow] (Claude 3.5 Haiku / Sonnet)")
        console.print("  5. [bold cyan]Ollama[/bold cyan] (Local Offline LLMs)")
        console.print("  6. [bold white]Custom / Other[/bold white] (DeepSeek, Groq, OpenRouter)")

        choice = Prompt.ask("Enter choice (1-6)", choices=["1", "2", "3", "4", "5", "6"], default="1")
        mapping = {"1": "gemini", "2": "mistral", "3": "openai", "4": "anthropic", "5": "ollama", "6": "custom"}
        provider = mapping[choice]

    provider = provider.lower()
    updates = {}

    if provider == "ollama":
        base_url = key or Prompt.ask("Enter Ollama Base URL", default="http://localhost:11434/v1")
        updates["RECON_LLM_BASE_URL"] = base_url
    else:
        env_var_name = PROVIDER_KEY_MAP.get(provider, f"{provider.upper()}_API_KEY")
        if not key:
            key = Prompt.ask(f"Enter API Key for [bold]{provider.capitalize()}[/bold]", password=True)
        if not key:
            console.print("[red]Error: API Key cannot be empty.[/red]")
            raise typer.Exit(1)
        updates[env_var_name] = key

    if model:
        updates[f"RECON_{provider.upper()}_MODEL"] = model

    if set_active:
        updates["RECON_LLM_PROVIDER"] = provider

    saved_path = update_env_file(updates, is_local=local)
    scope_str = "Local project (.env)" if local else f"Global (~/.recon/.env)"

    console.print(Panel(
        f"[bold green]OK: Successfully configured {provider.capitalize()}![/bold green]\n\n"
        f"  [dim]Provider:[/dim] [bold white]{provider}[/bold white]\n"
        f"  [dim]Scope:[/dim]    [magenta]{scope_str}[/magenta]\n"
        f"  [dim]Saved to:[/dim] [cyan]{saved_path.resolve()}[/cyan]\n"
        f"  [dim]Active:[/dim]   [green]{'Yes (Active)' if set_active else 'No'}[/green]",
        border_style="green",
        title="AI Configuration Updated"
    ))


@config_app.command("use")
def use_provider(
    provider: Annotated[str, typer.Argument(help="Provider name to activate: gemini, mistral, openai, anthropic, ollama, mock")],
    local: Annotated[bool, typer.Option("--local", help="Save to local project .env instead of global ~/.recon/.env")] = False,
):
    """Quickly switches the active AI provider."""
    p = provider.lower()
    valid = ["gemini", "mistral", "openai", "anthropic", "claude", "ollama", "custom", "mock"]
    if p not in valid:
        console.print(f"[red]Unknown provider '{provider}'. Valid choices: {', '.join(valid)}[/red]")
        raise typer.Exit(1)

    if p == "claude":
        p = "anthropic"

    saved_path = update_env_file({"RECON_LLM_PROVIDER": p}, is_local=local)
    console.print(f"[bold green]Switched active AI provider to:[/bold green] [bold cyan]{p.capitalize()}[/bold cyan] [dim]({saved_path})[/dim]")

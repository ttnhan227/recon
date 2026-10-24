from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from recon.common.config import settings
from recon.common.logging import console

config_app = typer.Typer(
    name="config", help="Manage AI providers, API keys, and active model selection."
)

GLOBAL_CONFIG_DIR = Path.home() / ".recon"
GLOBAL_ENV_PATH = GLOBAL_CONFIG_DIR / ".env"
LOCAL_ENV_PATH = Path(".env")

PROVIDER_KEY_MAP = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "ollama": "RECON_LLM_BASE_URL",
    "custom": "OPENAI_API_KEY",
}

PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openai": "gpt-6-luna",
    "anthropic": "claude-sonnet-5-5",
    "deepseek": "deepseek-chat",
    "mistral": "mistral-medium-latest",
    "ollama": "qwen3-coder:30b",
    "custom": "default",
    "mock": "offline-rules",
}

PROVIDER_AVAILABLE_MODELS: dict[str, list[tuple[str, str]]] = {
    "anthropic": [
        ("claude-sonnet-5-5", "Recommended - Best balance of coding quality, speed and cost"),
        ("claude-opus-5-5", "Deep debugging, hard multi-step logic"),
        ("claude-haiku-5-5", "Fast and cheap, for high-volume checks"),
        ("claude-fable-5-1", "Top tier, with extra safety measures for biology, cybersecurity and LLM R&D"),
    ],
    "openai": [
        ("gpt-6-luna", "Recommended - Cheapest and fastest, $0.10 in / $0.50 out per 1M tokens, 1.05M context"),
        ("gpt-6.1-sol", "Near-flagship quality at $2 / $10"),
        ("gpt-6-astra", "Flagship for complex reasoning and coding, $10 / $50"),
    ],
    "gemini": [
        ("gemini-3.8-flash", "Recommended - Stable, built for software engineering and agents"),
        ("gemini-4-argon", "Stable flagship reasoning model, 1M context"),
        ("gemini-3.5-flash-lite", "Cheapest and fastest current model"),
        ("gemini-3.6-flash", "Previous-generation Flash, still stable"),
    ],
    "mistral": [
        ("mistral-medium-latest", "Recommended - Medium 3.5, frontier multimodal model optimized for agentic and coding use cases"),
        ("codestral-latest", "Codestral 25.08, for code completion and fill-in-the-middle"),
        ("mistral-large-latest", "Large 4, general-purpose multimodal"),
        ("mistral-small-latest", "Small 4, a hybrid instruct, reasoning and coding model"),
    ],
    "deepseek": [
        ("deepseek-chat", "Recommended - DeepSeek-V3 high-intelligence coding & general reasoning"),
        ("deepseek-reasoner", "DeepSeek-R1 frontier reasoning model with native thinking trace"),
    ],
    "ollama": [
        ("qwen3-coder:30b", "Recommended - Best local coding agent, ~19 GB, 256K context, needs 24 GB+ GPU"),
        ("qwen3.6:27b", "Newer Qwen, ~17 GB, 256K context"),
        ("gpt-oss:20b", "Runs on about 16 GB RAM"),
        ("gemma4:26b", "Google open model, for laptops with 16 GB RAM"),
    ],
    "custom": [
        ("default", "Default model configured on your compatible LLM endpoint"),
    ],
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
    table.add_column("Provider", style="bold white", width=12)
    table.add_column("Status", justify="center", width=16)
    table.add_column("Configured Key", style="yellow", overflow="fold")
    table.add_column("Default Model", style="cyan", overflow="fold")

    all_providers = ["gemini", "openai", "anthropic", "deepseek", "mistral", "ollama", "custom", "mock"]

    for p in all_providers:
        is_active = p == active_provider
        active_mark = "[bold green]* ACTIVE[/bold green]" if is_active else ""

        if p == "mock":
            status_str = "[green]READY (Built-in)[/green]"
            key_str = "[dim]N/A[/dim]"
        elif p == "ollama":
            url_val = (
                env_data.get("RECON_LLM_BASE_URL")
                or settings.llm_base_url
                or "http://localhost:11434/v1"
            )
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
    console.print("\n[dim]To switch provider: [bold]recon config use <provider>[/bold][/dim]")
    console.print("[dim]To switch model:    [bold]recon config model <model>[/bold][/dim]")
    console.print("[dim]To set an API key:  [bold]recon config set-key [provider][/bold][/dim]")


def test_api_key_connection(provider_name: str, api_key: str, model: str | None = None) -> tuple[bool, str]:
    """Sends a fast test completion request to verify that the API key is valid and working."""
    p_name = provider_name.lower()
    from recon.llm.provider import (
        AnthropicProvider,
        GeminiProvider,
        MistralProvider,
        OpenAICompatibleProvider,
        OpenAIProvider,
    )

    try:
        if p_name == "gemini":
            provider = GeminiProvider(api_key=api_key, model=model or "gemini-3.8-flash")
        elif p_name == "openai":
            provider = OpenAIProvider(api_key=api_key, model=model or "gpt-6-luna")
        elif p_name in ("anthropic", "claude"):
            provider = AnthropicProvider(api_key=api_key, model=model or "claude-haiku-5-5")
        elif p_name == "deepseek":
            provider = OpenAICompatibleProvider(
                api_key=api_key,
                base_url="https://api.deepseek.com/v1",
                model=model or "deepseek-chat",
            )
        elif p_name == "mistral":
            provider = MistralProvider(api_key=api_key, model=model or "mistral-small-latest")
        elif p_name in ("ollama", "custom", "compatible"):
            base_url = api_key if "http" in api_key else "http://localhost:11434/v1"
            provider = OpenAICompatibleProvider(api_key="ollama", base_url=base_url, model=model or "qwen3-coder:30b")
        elif p_name == "mock":
            return True, "Mock provider ready."
        else:
            return True, "Unknown provider; skipped validation."

        asyncio.run(provider.complete("Say ok"))
        return True, "API connection verified successfully!"
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg or "unauthorized" in err_msg.lower() or "invalid_api_key" in err_msg.lower():
            return False, "Invalid API Key: 401 Unauthorized from provider."
        elif "403" in err_msg or "permission" in err_msg.lower():
            return False, "Access Denied: 403 Forbidden. Check your account billing or permissions."
        elif "connect" in err_msg.lower():
            return False, f"Connection Failed: Could not reach {p_name} endpoint ({e})."
        return False, f"Verification failed: {e}"


@config_app.command("set-key")
def set_key(
    provider: Annotated[
        Optional[str],
        typer.Argument(help="Provider name: gemini, mistral, openai, anthropic, ollama"),
    ] = None,
    key: Annotated[
        Optional[str],
        typer.Option("--key", "-k", help="API Key value (optional, prompts if omitted)"),
    ] = None,
    model: Annotated[Optional[str], typer.Option("--model", "-m", help="Custom model name")] = None,
    set_active: Annotated[
        bool, typer.Option("--use/--no-use", help="Set as the active provider")
    ] = True,
    verify: Annotated[
        bool, typer.Option("--verify/--no-verify", help="Verify the API key by testing the connection")
    ] = True,
    local: Annotated[
        bool,
        typer.Option("--local", help="Save to local project .env instead of global ~/.recon/.env"),
    ] = False,
):
    """Interactively sets or updates an AI provider API key. Saved globally to ~/.recon/.env by default."""
    if not provider:
        console.print("[bold cyan]Select an AI Provider to configure:[/bold cyan]")
        console.print("  1. [bold yellow]Anthropic[/bold yellow] (claude-sonnet-5-5, claude-opus-5-5, claude-haiku-5-5)")
        console.print("  2. [bold blue]OpenAI[/bold blue] (gpt-6-luna, gpt-6.1-sol, gpt-6-astra)")
        console.print("  3. [bold green]Gemini[/bold green] (gemini-3.8-flash, gemini-4-argon, gemini-3.5-flash-lite)")
        console.print("  4. [bold magenta]Mistral[/bold magenta] (mistral-medium-latest, codestral-latest)")
        console.print("  5. [bold cyan]DeepSeek[/bold cyan] (deepseek-chat, deepseek-reasoner)")
        console.print("  6. [bold white]Ollama[/bold white] (qwen3-coder:30b, qwen3.6:27b, gpt-oss:20b)")
        console.print("  7. [bold dim]Custom / Other[/bold dim] (Groq, OpenRouter, Together, vLLM)")

        choice = Prompt.ask(
            "Enter choice (1-7)", choices=["1", "2", "3", "4", "5", "6", "7"], default="1"
        )
        mapping = {
            "1": "anthropic",
            "2": "openai",
            "3": "gemini",
            "4": "mistral",
            "5": "deepseek",
            "6": "ollama",
            "7": "custom",
        }
        provider = mapping[choice]

    provider = provider.lower()
    updates: dict[str, str] = {}

    if provider == "ollama":
        base_url = key or Prompt.ask("Enter Ollama Base URL", default="http://localhost:11434/v1")
        updates["RECON_LLM_BASE_URL"] = str(base_url)
        val_for_test = str(base_url)
    else:
        env_var_name = PROVIDER_KEY_MAP.get(provider, f"{provider.upper()}_API_KEY")
        if not key:
            key = Prompt.ask(
                f"Enter API Key for [bold]{provider.capitalize()}[/bold]", password=True
            )
        if not key:
            console.print("[red]Error: API Key cannot be empty.[/red]")
            raise typer.Exit(1)
        updates[env_var_name] = str(key)
        val_for_test = str(key)

    if not model:
        models = PROVIDER_AVAILABLE_MODELS.get(provider, [])
        if models:
            console.print(f"\n[bold cyan]Select a model for {provider.capitalize()}:[/bold cyan]")
            for idx, (m_id, m_desc) in enumerate(models, 1):
                console.print(f"  {idx}. [bold green]{m_id}[/bold green] - [dim]{m_desc}[/dim]")
            console.print(f"  {len(models) + 1}. [yellow]Custom[/yellow] (enter your own model name)")

            choices = [str(i) for i in range(1, len(models) + 2)]
            model_choice = Prompt.ask("Choose model", choices=choices, default="1")
            chosen_idx = int(model_choice) - 1
            if chosen_idx < len(models):
                model = models[chosen_idx][0]
            else:
                model = Prompt.ask("Enter custom model name")
        else:
            model = PROVIDER_DEFAULT_MODELS.get(provider, "default")

    updates[f"RECON_{provider.upper()}_MODEL"] = str(model)

    if set_active:
        updates["RECON_LLM_PROVIDER"] = provider

    # Live verification of the key before saving!
    if verify:
        with console.status(f"[bold cyan]Verifying API key with {provider.capitalize()}...[/bold cyan]"):
            is_valid, verify_msg = test_api_key_connection(provider, val_for_test, model=model)

        if not is_valid:
            console.print(f"\n[bold red]❌ API Key Verification Failed:[/bold red] {verify_msg}")
            console.print("[yellow]The key was NOT saved. Please check your credentials and try again.[/yellow]")
            raise typer.Exit(1)

        console.print(f"[bold green]✓ Verified connection with {provider.capitalize()} successfully![/bold green]")

    saved_path = update_env_file(updates, is_local=local)
    scope_str = "Local project (.env)" if local else "Global (~/.recon/.env)"

    console.print(
        Panel(
            f"[bold green]OK: Successfully configured {provider.capitalize()}![/bold green]\n\n"
            f"  [dim]Provider:[/dim] [bold white]{provider}[/bold white]\n"
            f"  [dim]Scope:[/dim]    [magenta]{scope_str}[/magenta]\n"
            f"  [dim]Saved to:[/dim] [cyan]{saved_path.resolve()}[/cyan]\n"
            f"  [dim]Active:[/dim]   [green]{'Yes (Active)' if set_active else 'No'}[/green]",
            border_style="green",
            title="AI Configuration Updated",
        )
    )


@config_app.command("use")
def use_provider(
    provider: Annotated[
        str,
        typer.Argument(
            help="Provider name to activate: gemini, mistral, openai, anthropic, ollama, mock"
        ),
    ],
    local: Annotated[
        bool,
        typer.Option("--local", help="Save to local project .env instead of global ~/.recon/.env"),
    ] = False,
):
    """Quickly switches the active AI provider."""
    p = provider.lower()
    valid = ["gemini", "mistral", "openai", "anthropic", "claude", "deepseek", "ollama", "custom", "mock"]
    if p not in valid:
        console.print(
            f"[red]Unknown provider '{provider}'. Valid choices: {', '.join(valid)}[/red]"
        )
        raise typer.Exit(1)

    if p == "claude":
        p = "anthropic"

    saved_path = update_env_file({"RECON_LLM_PROVIDER": p}, is_local=local)
    console.print(
        f"[bold green]Switched active AI provider to:[/bold green] [bold cyan]{p.capitalize()}[/bold cyan] [dim]({saved_path})[/dim]"
    )


@config_app.command("model")
def set_model_command(
    model: Annotated[Optional[str], typer.Argument(help="Model identifier to activate")] = None,
    provider: Annotated[Optional[str], typer.Option("--provider", "-p", help="Target provider")] = None,
    local: Annotated[bool, typer.Option("--local", help="Save to local project .env instead of global ~/.recon/.env")] = False,
):
    """Interactively select or switch the active AI model for your provider."""
    env_data = read_env_file()
    active_provider = (provider or env_data.get("RECON_LLM_PROVIDER") or settings.llm_provider).lower()

    if (active_provider == "mock" or active_provider not in PROVIDER_AVAILABLE_MODELS) and not provider:
        # Check if user has any provider key configured
        for p, key_var in PROVIDER_KEY_MAP.items():
            if env_data.get(key_var) or os.getenv(key_var):
                active_provider = p
                break
        else:
            console.print("[bold cyan]Which provider would you like to select a model for?[/bold cyan]")
            console.print("  1. [bold yellow]Anthropic[/bold yellow] (claude-sonnet-5-5, claude-opus-5-5)")
            console.print("  2. [bold blue]OpenAI[/bold blue] (gpt-6-luna, gpt-6.1-sol, gpt-6-astra)")
            console.print("  3. [bold green]Gemini[/bold green] (gemini-3.8-flash, gemini-4-argon)")
            console.print("  4. [bold magenta]Mistral[/bold magenta] (mistral-medium-latest, codestral-latest)")
            console.print("  5. [bold cyan]DeepSeek[/bold cyan] (deepseek-chat, deepseek-reasoner)")
            console.print("  6. [bold white]Ollama[/bold white] (qwen3-coder:30b, gpt-oss:20b)")
            p_choice = Prompt.ask("Choose provider (1-6)", choices=["1", "2", "3", "4", "5", "6"], default="1")
            p_map = {"1": "anthropic", "2": "openai", "3": "gemini", "4": "mistral", "5": "deepseek", "6": "ollama"}
            active_provider = p_map[p_choice]

    models = PROVIDER_AVAILABLE_MODELS.get(active_provider, [])
    if not model:
        if models:
            console.print(f"\n[bold cyan]Select active model for {active_provider.capitalize()}:[/bold cyan]")
            for idx, (m_id, m_desc) in enumerate(models, 1):
                console.print(f"  {idx}. [bold green]{m_id}[/bold green] - [dim]{m_desc}[/dim]")
            console.print(f"  {len(models) + 1}. [yellow]Custom[/yellow] (enter your own model name)")

            choices = [str(i) for i in range(1, len(models) + 2)]
            choice = Prompt.ask("Choose model", choices=choices, default="1")
            idx = int(choice) - 1
            if idx < len(models):
                model = models[idx][0]
            else:
                model = Prompt.ask("Enter custom model identifier")
        else:
            model = Prompt.ask(f"Enter model identifier for {active_provider}")

    update_key = f"RECON_{active_provider.upper()}_MODEL"
    saved_path = update_env_file({update_key: str(model)}, is_local=local)
    console.print(
        f"[bold green]✓ Switched active model for {active_provider.capitalize()} to:[/bold green] [bold cyan]{model}[/bold cyan] [dim]({saved_path})[/dim]"
    )

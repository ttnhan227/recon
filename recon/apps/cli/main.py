from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from recon.apps.cli.config_cli import config_app, list_providers, set_key, use_provider
from recon.apps.cli.doctor import run_doctor
from recon.common.config import get_project_slug, get_recon_home, settings
from recon.common.logging import console
from recon.common.models import TestCase, TestResult, TestStatus
from recon.discovery.endpoint_detector import discover_application
from recon.orchestration.orchestrator import TestOrchestrator
from recon.persistence.database import DatabaseManager
from recon.planning.generator import TestSuiteGenerator

app = typer.Typer(
    name="recon",
    help="Recon QA: API and browser test generation with failure analysis",
    no_args_is_help=True,
)

# Add 'recon config' subcommands
app.add_typer(config_app, name="config")

# Top-level shortcuts for convenience
app.command("set-key", help="Shortcut to interactively set/update an AI API key.")(set_key)
app.command("use", help="Shortcut to switch the active AI provider.")(use_provider)
app.command("providers", help="Shortcut to list all supported AI providers and active status.")(
    list_providers
)


@app.command("scan")
def scan_command(
    target: Annotated[str, typer.Argument(help="Target URL (e.g. http://localhost:8000)")],
    spec: Annotated[
        Optional[str], typer.Option("--spec", "-s", help="Path or URL to OpenAPI specification")
    ] = None,
    browser: Annotated[
        bool, typer.Option("--browser", "-b", help="Enable browser-based web crawling")
    ] = False,
):
    """Inspects target application, discovering routes, API endpoints, and interactive elements."""
    console.print(f"[bold cyan]Scanning target:[/bold cyan] {target}")

    async def _run():
        with console.status("[bold green]Discovering application assets..."):
            discovered = await discover_application(
                target, spec_path_or_url=spec, enable_browser=browser
            )

        table = Table(
            title=f"Discovered Endpoints ({len(discovered.endpoints)})", title_style="bold blue"
        )
        table.add_column("Method", style="bold green", width=8)
        table.add_column("Path", style="cyan")
        table.add_column("Parameters", style="magenta")
        table.add_column("Request Body", style="yellow")
        table.add_column("Summary", style="white")

        for ep in discovered.endpoints:
            params_str = ", ".join(p.name for p in ep.parameters) or "-"
            has_body = "Yes (JSON)" if ep.request_body_schema else "No"
            table.add_row(ep.method, ep.path, params_str, has_body, ep.summary or "-")

        console.print(table)

        if discovered.pages:
            p_table = Table(
                title=f"Discovered Web Pages ({len(discovered.pages)})", title_style="bold green"
            )
            p_table.add_column("URL", style="cyan")
            p_table.add_column("Title", style="white")
            p_table.add_column("Forms", justify="center")
            p_table.add_column("Buttons", justify="center")
            p_table.add_column("Links", justify="center")
            p_table.add_column("Console Errors", justify="center")

            for page in discovered.pages:
                err_count = len(page.console_errors)
                p_table.add_row(
                    page.url,
                    page.title or "-",
                    str(len(page.forms)),
                    str(len(page.buttons)),
                    str(len(page.links)),
                    f"[red]{err_count}[/red]" if err_count > 0 else "[green]0[/green]",
                )
            console.print(p_table)

    asyncio.run(_run())


@app.command("generate")
def generate_command(
    target: Annotated[str, typer.Argument(help="Target URL or host")],
    spec: Annotated[
        Optional[str], typer.Option("--spec", "-s", help="Path or URL to OpenAPI spec")
    ] = None,
    output: Annotated[
        Optional[Path],
        typer.Option("--output", "-o", help="Output JSON path for generated test suite"),
    ] = None,
    browser: Annotated[
        bool, typer.Option("--browser", "-b", help="Enable browser crawling")
    ] = False,
):
    """Plans test suite including happy-path, boundary fuzzing, negative validation, and security probes."""
    console.print(f"[bold cyan]Planning test suite for:[/bold cyan] {target}")

    async def _run():
        with console.status("[bold green]Discovering endpoints and generating test suite..."):
            app_meta = await discover_application(
                target, spec_path_or_url=spec, enable_browser=browser
            )
            planner = TestSuiteGenerator(app_meta)
            tests = planner.generate_suite()

        if output:
            out_path = output
        else:
            project_slug = get_project_slug(target)
            suites_dir = get_recon_home() / "suites" / project_slug
            suites_dir.mkdir(parents=True, exist_ok=True)
            out_path = suites_dir / "test_suite.json"

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps([t.model_dump(mode="json") for t in tests], indent=2), encoding="utf-8"
        )
        console.print(
            f"[green]✓ Generated {len(tests)} test cases saved to [bold]{out_path}[/bold][/green]"
        )

    asyncio.run(_run())


def parse_headers(header_list: list[str] | None) -> dict[str, str]:
    if not header_list:
        return {}
    parsed = {}
    for h in header_list:
        if ":" in h:
            k, v = h.split(":", 1)
            parsed[k.strip()] = v.strip()
    return parsed


@app.command("test")
def test_command(
    target: Annotated[str, typer.Argument(help="Target application URL or host")],
    spec: Annotated[
        Optional[str], typer.Option("--spec", "-s", help="Path or URL to OpenAPI specification")
    ] = None,
    browser: Annotated[
        bool, typer.Option("--browser", "-b", help="Enable Playwright browser test runner")
    ] = False,
    concurrency: Annotated[
        int, typer.Option("--concurrency", "-c", help="Concurrent worker count")
    ] = 4,
    ai: Annotated[
        bool, typer.Option("--ai/--no-ai", help="Enable AI test generation and failure analysis")
    ] = True,
    header: Annotated[
        Optional[list[str]],
        typer.Option(
            "--header",
            "-H",
            help="Custom HTTP headers to send (e.g. -H 'Authorization: Bearer token')",
        ),
    ] = None,
    include: Annotated[
        Optional[list[str]],
        typer.Option(
            "--include", "-i", help="Filter tests to matching paths (e.g. -i '/api/orders*')"
        ),
    ] = None,
    exclude: Annotated[
        Optional[list[str]],
        typer.Option(
            "--exclude", "-e", help="Exclude matching paths from testing (e.g. -e '/api/admin*')"
        ),
    ] = None,
    report_dir: Annotated[
        Optional[Path],
        typer.Option("--report-dir", "-r", help="Directory for JSON and HTML reports"),
    ] = None,
    failed_only: Annotated[
        bool, typer.Option("--failed-only", "-f", help="Re-test only previously failing test cases")
    ] = False,
    tag: Annotated[
        Optional[list[str]], typer.Option("--tag", "-t", help="Filter tests by tag")
    ] = None,
):
    """Discover a target, generate tests, execute them, classify failures, and write reports."""
    project_slug = get_project_slug(target)
    actual_report_dir = (report_dir or (settings.reports_dir / project_slug)).resolve()
    parsed_hdrs = parse_headers(header)
    hdr_info = (
        f" | [dim]Auth/Headers:[/dim] [green]{len(parsed_hdrs)} set[/green]" if parsed_hdrs else ""
    )
    include_info = f" | [dim]Filter:[/dim] [yellow]{', '.join(include)}[/yellow]" if include else ""
    failed_info = " | [bold magenta]Failed-Only Mode[/bold magenta]" if failed_only else ""

    console.print(
        Panel(
            f"[bold white]Recon QA[/bold white] (Project: [cyan]{project_slug}[/cyan])\n"
            f"[dim]Target:[/dim] [cyan]{target}[/cyan] | [dim]Concurrency:[/dim] [yellow]{concurrency}[/yellow] | [dim]Browser:[/dim] [magenta]{browser}[/magenta] | [dim]AI:[/dim] [green]{ai}[/green]{hdr_info}{include_info}{failed_info}",
            border_style="cyan",
        )
    )

    async def _run():
        filter_test_ids: set[str] | None = None

        if failed_only:
            # Load previous failing test results
            latest_json = actual_report_dir / "latest.json"
            if not latest_json.exists():
                latest_json = Path("./reports/latest.json")

            if not latest_json.exists():
                console.print(
                    f"[yellow]No previous test results found in {actual_report_dir}. Running full suite...[/yellow]"
                )
            else:
                data = json.loads(latest_json.read_text(encoding="utf-8"))
                results_data = data.get("results", data) if isinstance(data, dict) else data
                failing_results = [
                    TestResult.model_validate(r)
                    for r in results_data
                    if r.get("status") in (TestStatus.FAILED.value, TestStatus.ERROR.value)
                ]

                if not failing_results:
                    console.print(
                        "[bold green]✓ No previously failed tests found for this project! All tests were passing.[/bold green]"
                    )
                    return 0

                console.print(
                    f"[bold cyan]Incremental Re-Test: Running {len(failing_results)} previously failed test(s)...[/bold cyan]"
                )
                filter_test_ids = {fr.test_id for fr in failing_results}

        orchestrator = TestOrchestrator(
            concurrency=concurrency,
            output_dir=actual_report_dir,
            enable_ai=ai,
        )

        async def on_progress(test: TestCase, res: TestResult):
            status_color = "green" if res.status == TestStatus.PASSED else "red"
            fail_msg = f" - {res.failure_evidence.message}" if res.failure_evidence else ""
            console.print(
                f" [{status_color}]{res.status.value:<6}[/{status_color}] [bold]{res.test_id}[/bold] {res.test_name} ({res.duration_ms:.0f}ms){fail_msg}"
            )

        summary, results = await orchestrator.run_pipeline(
            target_url=target,
            spec_path_or_url=spec,
            enable_browser=browser,
            headers=parsed_hdrs,
            include_paths=include,
            exclude_paths=exclude,
            tags=tag,
            filter_test_ids=filter_test_ids,
            on_progress=on_progress,
        )

        # Print Summary Panel
        pass_rate = round((summary.passed / summary.total * 100) if summary.total > 0 else 0, 1)
        summary_panel_color = "green" if summary.failed == 0 and summary.errors == 0 else "red"

        console.print()
        console.print(
            Panel(
                f"[bold]Execution Summary[/bold]\n\n"
                f"  Total Tests : [bold]{summary.total}[/bold]\n"
                f"  Passed      : [bold green]{summary.passed}[/bold green]\n"
                f"  Failed      : [bold red]{summary.failed + summary.errors}[/bold red]\n"
                f"  Pass Rate   : [bold {summary_panel_color}]{pass_rate}%[/bold {summary_panel_color}]\n"
                f"  Duration    : {summary.duration_seconds:.2f}s\n"
                f"  HTML Report : [cyan]{actual_report_dir}/run-{summary.run_id}/report.html[/cyan]\n"
                f"  Latest Link : [cyan]{actual_report_dir}/latest.html[/cyan]",
                title="[bold]Recon Test Run Completed[/bold]",
                border_style=summary_panel_color,
            )
        )

        # Failure breakdown table if failures exist
        if summary.failure_breakdown:
            table = Table(title="Failure Taxonomy Breakdown", title_style="bold red")
            table.add_column("Category", style="yellow")
            table.add_column("Count", justify="right", style="bold red")
            for k, v in summary.failure_breakdown.items():
                table.add_row(k, str(v))
            console.print(table)

        # Print top failure analysis if available
        failed_results = [
            r
            for r in results
            if r.failure_analysis
            and (r.status == TestStatus.FAILED or r.status == TestStatus.ERROR)
        ]
        if failed_results:
            console.print("\n[bold cyan]Failure Analysis Highlights:[/bold cyan]")
            for fr in failed_results[:2]:
                fa = fr.failure_analysis
                if fa:
                    hypo = fa.hypotheses[0].hypothesis if fa.hypotheses else "Unknown"
                    console.print(
                        Panel(
                            f"[bold red]Test Failed:[/bold red] {fr.test_name}\n"
                            f"[bold yellow]Likely Cause:[/bold yellow] {hypo}\n"
                            f"[bold green]Suggested Fix:[/bold green] {fa.suggested_fix or 'N/A'}\n"
                            f"[dim]Confidence: {int(fa.confidence_score * 100)}%[/dim]",
                            border_style="yellow",
                        )
                    )

        return summary.exit_code

    code = asyncio.run(_run())
    raise typer.Exit(code=code)


@app.command("analyze")
def analyze_command(
    target_or_run_id: Annotated[
        str, typer.Argument(help="Run ID or path to results.json")
    ] = "latest",
):
    """Performs deep failure analysis on existing test results."""

    async def _run():
        path = Path(target_or_run_id)
        if target_or_run_id == "latest" and not path.exists():
            project_slug = get_project_slug()
            central_latest = settings.reports_dir / project_slug / "latest.json"
            path = central_latest if central_latest.exists() else Path("./reports/latest.json")

        results: list[TestResult] = []

        if path.exists() and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "results" in data:
                data = data["results"]
            results = [TestResult.model_validate(item) for item in data]
        else:
            db = DatabaseManager()
            try:
                results = await db.get_run_results(target_or_run_id)
            finally:
                await db.close()

        if not results:
            console.print(f"[red]No test results found for '{target_or_run_id}'[/red]")
            return

        failed = [r for r in results if r.status in (TestStatus.FAILED, TestStatus.ERROR)]
        console.print(f"[bold cyan]Analyzing {len(failed)} failures from test run...[/bold cyan]")

        from recon.llm.failure_analyzer import AIFailureAnalyzer

        analyzer = AIFailureAnalyzer()

        for f in failed:
            analysis = await analyzer.analyze_failure(f)
            console.print(
                Panel(
                    f"[bold red]Test:[/bold red] {f.test_name} ({f.test_id})\n"
                    f"[bold white]Observed Facts:[/bold white]\n"
                    + "\n".join(f"  • {fact}" for fact in analysis.observed_facts)
                    + "\n\n"
                    "[bold yellow]Root Cause Hypothesis:[/bold yellow] "
                    + (analysis.hypotheses[0].hypothesis if analysis.hypotheses else "N/A")
                    + "\n\n"
                    f"[bold green]Suggested Fix:[/bold green] {analysis.suggested_fix or 'N/A'}",
                    title=f"Failure Analysis: {f.test_id}",
                    border_style="red",
                )
            )

    asyncio.run(_run())


@app.command("fix")
def fix_command(
    target_or_run_id: Annotated[
        str, typer.Argument(help="Run ID or path to results.json")
    ] = "latest",
    repo: Annotated[
        Optional[Path],
        typer.Option("--repo", "-r", help="Path to target application source code repository"),
    ] = None,
    test_id: Annotated[
        Optional[str],
        typer.Option("--test-id", "-t", help="Specific failing test ID to fix (e.g. API-015)"),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option(
            "--apply", "-a", help="Automatically apply patches without interactive confirmation"
        ),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option(
            "--verify", "-v", help="Auto-verify the fix by re-running test against target"
        ),
    ] = True,
):
    """Generate and optionally apply reviewable patches for selected test failures."""
    from recon.healing.engine import SelfHealingEngine

    async def _run():
        engine = SelfHealingEngine(repo_dir=repo)
        results = await engine.load_results(target_or_run_id)
        if not results:
            console.print(f"[red]No test results found for '{target_or_run_id}'[/red]")
            raise typer.Exit(code=1)

        fixed = await engine.heal_failures(
            results=results,
            test_id_filter=test_id,
            auto_apply=apply,
            auto_verify=verify,
        )
        raise typer.Exit(code=0 if fixed > 0 else 1)

    asyncio.run(_run())


@app.command("report")
def report_command(
    target_or_run_id: Annotated[
        str, typer.Argument(help="Run ID or path to results.json/report.html")
    ] = "latest",
    report_dir: Annotated[
        Optional[Path], typer.Option("--report-dir", "-r", help="Custom report directory")
    ] = None,
):
    """Views or opens the latest HTML report for the active project."""
    target_path = Path(target_or_run_id)
    target_html: Path | None = None

    project_slug = get_project_slug()
    search_dirs = []
    if report_dir:
        search_dirs.append(report_dir)
    search_dirs.extend(
        [
            settings.reports_dir / project_slug,
            settings.reports_dir,
            Path("./reports"),
        ]
    )

    if target_path.exists() and target_path.suffix == ".html":
        target_html = target_path
    elif target_or_run_id == "latest":
        for s_dir in search_dirs:
            if (s_dir / "latest.html").exists():
                target_html = s_dir / "latest.html"
                break
    else:
        for s_dir in search_dirs:
            candidate = s_dir / f"run-{target_or_run_id}" / "report.html"
            if candidate.exists():
                target_html = candidate
                break

    if not target_html:
        # Fallback: check most recently modified html file across all search directories
        for s_dir in search_dirs:
            if s_dir.exists():
                html_files = list(s_dir.glob("**/*.html"))
                if html_files:
                    target_html = max(html_files, key=lambda p: p.stat().st_mtime)
                    break

    if target_html and target_html.exists():
        console.print(f"[green]Report available at: [bold]{target_html.resolve()}[/bold][/green]")
        import webbrowser

        try:
            webbrowser.open(target_html.resolve().as_uri())
        except Exception:
            pass
    else:
        console.print(
            f"[yellow]No existing report found for project '{project_slug}'. Run `recon test <target>` first.[/yellow]"
        )


@app.command("doctor")
def doctor_command(
    target: Annotated[
        Optional[str], typer.Option("--target", "-t", help="Check connectivity to a target URL")
    ] = None,
):
    """Runs system diagnostics to verify dependencies, browsers, DB, and network reachability."""
    healthy = asyncio.run(run_doctor(target_url=target))
    raise typer.Exit(code=0 if healthy else 1)


@app.command("serve-demo")
def serve_demo_command(
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on")] = 8000,
    host: Annotated[str, typer.Option("--host", "-h", help="Host interface")] = "127.0.0.1",
):
    """Starts the built-in vulnerable Demo Target Application for reproducible testing."""
    import uvicorn

    console.print(
        f"[bold green]Starting Recon Demo Target Application at http://{host}:{port}[/bold green]"
    )
    console.print(f"[dim]OpenAPI Docs: http://{host}:{port}/docs[/dim]")
    console.print(f"[dim]Web Interface: http://{host}:{port}/[/dim]\n")
    uvicorn.run("recon.demo_app.main:app", host=host, port=port, log_level="info")


@app.command("demo")
def demo_command(
    port: Annotated[
        int, typer.Option("--port", "-p", help="Local port for the temporary demo application")
    ] = 8765,
    browser: Annotated[
        bool, typer.Option("--browser", "-b", help="Also exercise browser discovery and checks")
    ] = False,
    report_dir: Annotated[
        Optional[Path], typer.Option("--report-dir", "-r", help="Directory for demo reports")
    ] = None,
):
    """Runs the intentionally broken local demo and produces a sample HTML report."""
    import subprocess
    import sys
    import time

    import httpx

    target = f"http://127.0.0.1:{port}"
    actual_report_dir = (report_dir or (settings.reports_dir / get_project_slug(target))).resolve()
    actual_report_dir.mkdir(parents=True, exist_ok=True)
    latest_report = actual_report_dir / "latest.html"
    previous_report_mtime = latest_report.stat().st_mtime_ns if latest_report.exists() else None

    console.print(
        Panel(
            "Recon will start a local application containing known defects, test it, "
            "and generate an HTML report. No API key or external target is required.",
            title="[bold cyan]Recon QA local demo[/bold cyan]",
            border_style="cyan",
        )
    )

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "recon.demo_app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            if server.poll() is not None:
                console.print(
                    f"[red]The demo application could not start on port {port}. "
                    "Choose another port with --port.[/red]"
                )
                raise typer.Exit(code=1)
            try:
                response = httpx.get(f"{target}/api/health", timeout=0.5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        else:
            console.print("[red]Timed out while starting the local demo application.[/red]")
            raise typer.Exit(code=1)

        command = [
            sys.executable,
            "-m",
            "recon.apps.cli.main",
            "test",
            target,
            "--no-ai",
            "--report-dir",
            str(actual_report_dir),
        ]
        if browser:
            command.append("--browser")

        completed = subprocess.run(command, check=False)
        report_was_created = latest_report.exists() and (
            previous_report_mtime is None
            or latest_report.stat().st_mtime_ns > previous_report_mtime
        )
        if completed.returncode not in (0, 1) or not report_was_created:
            console.print("[red]The demo run did not produce a report.[/red]")
            raise typer.Exit(code=1)

        report_command_hint = "recon report"
        if report_dir:
            report_command_hint += f' --report-dir "{actual_report_dir}"'

        console.print(
            Panel(
                f"[bold green]Demo complete.[/bold green] Recon intentionally found defects.\n"
                f"HTML report: [bold]{latest_report}[/bold]\n\n"
                f"Run [cyan]{report_command_hint}[/cyan] to open this report.",
                border_style="green",
            )
        )
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


@app.command("serve-api")
def serve_api_command(
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on")] = 8080,
    host: Annotated[str, typer.Option("--host", "-h", help="Host interface")] = "127.0.0.1",
):
    """Starts the Recon FastAPI REST API Server."""
    import uvicorn

    console.print(f"[bold green]Starting Recon API Server at http://{host}:{port}[/bold green]")
    console.print(f"[dim]Interactive API Docs: http://{host}:{port}/docs[/dim]\n")
    uvicorn.run("recon.apps.api.server:api_app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()

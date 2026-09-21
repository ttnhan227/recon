from __future__ import annotations

import json
import re
from pathlib import Path

from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

from recon.common.config import get_project_slug, settings
from recon.common.logging import console
from recon.common.models import TestResult, TestStatus
from recon.healing.applier import PatchApplier
from recon.healing.locator import CodeLocator
from recon.healing.patcher import AIPatchGenerator
from recon.persistence.database import DatabaseManager


class SelfHealingEngine:
    """Orchestrates test failure inspection, source code location, patch generation, and auto-verification."""

    def __init__(
        self,
        repo_dir: Path | str | None = None,
        patch_generator: AIPatchGenerator | None = None,
    ):
        self.repo_dir = (Path(repo_dir) if repo_dir else Path.cwd()).resolve()
        self.locator = CodeLocator(self.repo_dir)
        self.patch_generator = patch_generator or AIPatchGenerator()
        self.applier = PatchApplier()

    async def load_results(self, target_or_run_id: str = "latest") -> list[TestResult]:
        """Loads test results from centralized or local reports, directories, or SQLite database."""
        path = Path(target_or_run_id)
        if path.exists() and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "results" in data:
                data = data["results"]
            return [TestResult.model_validate(item) for item in data]

        if path.exists() and path.is_dir():
            for cand in (path / "results.json", path / "report.json"):
                if cand.exists():
                    data = json.loads(cand.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "results" in data:
                        data = data["results"]
                    return [TestResult.model_validate(item) for item in data]

        if target_or_run_id == "latest":
            # 1. Check centralized project reports
            project_slug = get_project_slug(cwd=self.repo_dir)
            central_latest = settings.reports_dir / project_slug / "latest.json"
            if central_latest.exists():
                data = json.loads(central_latest.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "results" in data:
                    data = data["results"]
                return [TestResult.model_validate(item) for item in data]

            # 2. Check local ./reports/latest.json
            local_latest = Path("./reports/latest.json")
            if local_latest.exists():
                data = json.loads(local_latest.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "results" in data:
                    data = data["results"]
                return [TestResult.model_validate(item) for item in data]

        # Check local ./reports/run-{id} or ./reports/{id}
        for cand_dir in (
            Path("./reports") / target_or_run_id,
            Path("./reports") / f"run-{target_or_run_id}",
            Path("./reports") / target_or_run_id.removeprefix("run-"),
        ):
            if cand_dir.exists() and cand_dir.is_dir():
                for cand_file in (cand_dir / "results.json", cand_dir / "report.json"):
                    if cand_file.exists():
                        data = json.loads(cand_file.read_text(encoding="utf-8"))
                        if isinstance(data, dict) and "results" in data:
                            data = data["results"]
                        return [TestResult.model_validate(item) for item in data]

        db = DatabaseManager()
        try:
            results = await db.get_run_results(target_or_run_id)
            if not results and target_or_run_id.startswith("run-"):
                results = await db.get_run_results(target_or_run_id.removeprefix("run-"))
            if not results and not target_or_run_id.startswith("run-"):
                results = await db.get_run_results(f"run-{target_or_run_id}")
            return results
        finally:
            await db.close()

    @staticmethod
    def extract_method_and_path(test_name: str) -> tuple[str, str] | None:
        """Extracts HTTP method and path from test names like '[POST /api/v1/auth/login] Boundary...'"""
        match = re.search(r"\[([A-Z]+)\s+([^\]]+)\]", test_name)
        if match:
            return match.group(1), match.group(2)
        return None

    async def heal_failures(
        self,
        results: list[TestResult],
        test_id_filter: str | None = None,
        auto_apply: bool = False,
        auto_verify: bool = True,
    ) -> int:
        """Processes failing tests with deduplication, generates patches, and optionally applies/verifies them."""
        all_failed = [
            r
            for r in results
            if r.status in (TestStatus.FAILED, TestStatus.ERROR)
            and (not test_id_filter or r.test_id == test_id_filter)
        ]

        if not all_failed:
            console.print("[green]✓ No matching failures found to fix![/green]")
            return 0

        # Smart Failure Clustering: Deduplicate by (Method + Path) to prevent sending redundant AI calls for the same function
        clustered: dict[tuple[str, str], TestResult] = {}
        for r in all_failed:
            mp = self.extract_method_and_path(r.test_name)
            if not mp:
                continue
            # Prioritize server 500 errors over others
            is_500 = False
            if r.failure_evidence and r.failure_evidence.http_traces:
                is_500 = r.failure_evidence.http_traces[0].response_status == 500

            if mp not in clustered or is_500:
                clustered[mp] = r

        target_failures = list(clustered.values())
        console.print(
            f"\n[bold cyan]Autonomous Self-Healing: Grouped {len(all_failed)} failure(s) into {len(target_failures)} unique endpoint fix(es)[/bold cyan]"
        )
        console.print(f"[dim]Target repository:[/dim] {self.repo_dir}\n")

        fixed_count = 0

        for res in target_failures:
            mp = self.extract_method_and_path(res.test_name)
            if not mp:
                continue

            method, path = mp
            console.print(
                f"[bold yellow]Searching source code for endpoint:[/bold yellow] [bold]{method} {path}[/bold] ({res.test_id})"
            )

            contexts = self.locator.locate_endpoint(method, path)
            if not contexts:
                console.print(
                    f"  [dim red]✗ Could not locate handler file in repository for {method} {path}[/dim red]\n"
                )
                continue

            best_ctx = contexts[0]
            console.print(
                f"  [green]✓ Located handler:[/green] [bold]{best_ctx.relative_path}[/bold] (line {best_ctx.line_number})"
            )

            with console.status(f"[bold green]Synthesizing patch for {res.test_id}..."):
                patch = await self.patch_generator.generate_patch(res, best_ctx)

            if not patch or not patch.diff.strip():
                console.print(
                    f"  [yellow]⚠ AI could not produce a valid diff for {best_ctx.relative_path}[/yellow]\n"
                )
                continue

            # Render Diff in Terminal
            console.print(
                Panel(
                    Syntax(patch.diff, "diff", theme="monokai", line_numbers=False),
                    title=f"[bold green]Proposed Fix for {res.test_id}: {best_ctx.relative_path}[/bold green]",
                    subtitle=f"[dim]{patch.explanation}[/dim]",
                    border_style="cyan",
                )
            )

            should_apply = auto_apply
            if not auto_apply:
                should_apply = Confirm.ask(
                    f"Apply this fix to [bold]{best_ctx.relative_path}[/bold]?", default=False
                )

            if should_apply:
                backup = self.applier.apply_patch(patch)
                if backup:
                    console.print(
                        f"[bold green]✓ Patch successfully applied to {best_ctx.relative_path}[/bold green]"
                    )
                    fixed_count += 1

                    if auto_verify and res.failure_evidence and res.failure_evidence.http_traces:
                        trace = res.failure_evidence.http_traces[0]
                        console.print(f"[dim]Re-verifying fix against {trace.request_url}...[/dim]")
                        # Minimal re-run check
                        try:
                            import httpx

                            async with httpx.AsyncClient(timeout=10.0) as client:
                                resp = await client.request(
                                    method=method,
                                    url=trace.request_url,
                                    headers=trace.request_headers,
                                    json=trace.request_body
                                    if isinstance(trace.request_body, (dict, list))
                                    else None,
                                    content=trace.request_body
                                    if isinstance(trace.request_body, str)
                                    else None,
                                )
                                if resp.status_code != 500:
                                    console.print(
                                        f"[bold green]✓ VERIFICATION PASSED: Endpoint returned HTTP {resp.status_code} (Clean response, no 500 crash!)[/bold green]\n"
                                    )
                                else:
                                    console.print(
                                        "[bold yellow]⚠ Verification returned HTTP 500: Further refinements may be needed.[/bold yellow]\n"
                                    )
                        except Exception as ve:
                            console.print(f"[dim]Verification ping completed: {ve}[/dim]\n")
            else:
                console.print(f"[dim]Skipped applying patch for {res.test_id}[/dim]\n")

        console.print(
            f"[bold cyan]Self-Healing Run Completed:[/bold cyan] {fixed_count} file(s) updated."
        )
        return fixed_count

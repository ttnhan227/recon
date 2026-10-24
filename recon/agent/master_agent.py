from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax

from recon.common.logging import console
from recon.common.models import (
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)
from recon.discovery.endpoint_detector import discover_application
from recon.execution.browser.agent import ReconBrowserAgent
from recon.healing.applier import PatchApplier
from recon.healing.locator import CodeLocator
from recon.healing.patcher import AIPatchGenerator
from recon.llm.provider import LLMProvider, get_llm_provider

MASTER_SYSTEM_PROMPT = """You are Recon's Autonomous Master QA Engineer and Pair Programmer.
You help developers test, audit, and fix their software using natural English instructions.

You have access to the following tool capabilities:

1. BROWSER:
   {"tool": "browser", "url": "<target_url>", "goal": "<what_to_do_in_browser>"}
   Use this for end-to-end user journeys, UI testing, checking web pages, and filling forms.

2. API_PROBE:
   {"tool": "api_probe", "url": "<target_url>", "endpoint": "<path>", "method": "GET|POST|PUT|DELETE", "payload": {...}}
   Use this to test backend endpoints, send HTTP requests, and inspect responses or status codes.

3. CODE_FIX:
   {"tool": "code_fix", "defect_description": "<description>", "endpoint": "<path_or_route>", "method": "GET|POST|..."}
   Use this to search the codebase for the file causing a bug, generate an AST-validated patch, and fix it.

4. SCAN:
   {"tool": "scan", "url": "<target_url>"}
   Use this to discover all OpenAPI endpoints and web pages on an application.

5. REPLY:
   {"tool": "reply", "message": "<your_conversational_response_to_the_user>"}
   Use this to respond to the user once tasks are completed or when you need clarification.

RULES:
- Always choose the most direct tool to address the user's intent.
- If a target URL or port is mentioned in the prompt (e.g. localhost:8000, http://127.0.0.1:3000), extract and use it.
- If testing reveals a defect and the user asked to fix it, follow up by invoking the CODE_FIX tool.
- Output ONLY valid JSON conforming to one of the tool schemas above. No markdown code blocks, no preamble.
"""


def extract_url_from_text(text: str) -> str | None:
    """Extracts URL or localhost reference from natural language input."""
    # Match standard http/https URL
    url_match = re.search(r'https?://[^\s\'"<>]+', text)
    if url_match:
        return url_match.group(0).rstrip(".,;!?:")

    # Match localhost:port or 127.0.0.1:port
    local_match = re.search(r'(?:localhost|127\.0\.0\.1)(?::\d+)?(?:/[^\s\'"<>]*)?', text)
    if local_match:
        return f"http://{local_match.group(0)}".rstrip(".,;!?:")

    return None


class ReconMasterAgent:
    """Master conversational agent coordinating browser, API, discovery, and self-healing tools."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        repo_dir: Path | str | None = None,
        output_dir: Path | str = "./reports",
    ):
        self.provider = provider or get_llm_provider()
        self.repo_dir = (Path(repo_dir) if repo_dir else Path.cwd()).resolve()
        self.output_dir = Path(output_dir)
        self.locator = CodeLocator(self.repo_dir)
        self.patch_generator = AIPatchGenerator(self.provider)
        self.patch_applier = PatchApplier()
        self.default_target: str | None = None

    async def _execute_browser(self, url: str, goal: str, headless: bool = True) -> dict[str, Any]:
        """Runs the autonomous browser agent."""
        console.print(f"[bold cyan]🌐 Launching Browser Agent for:[/bold cyan] {url}")
        agent = ReconBrowserAgent(provider=self.provider, output_dir=self.output_dir)
        report = await agent.run(start_url=url, goal=goal, headless=headless)
        return {
            "status": report.status.value,
            "final_url": report.final_url,
            "summary": report.summary,
            "errors": report.errors_detected,
            "steps_count": len(report.steps),
        }

    async def _execute_api_probe(
        self,
        url: str,
        endpoint: str,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Probes a backend API endpoint."""
        target_url = url.rstrip("/") + "/" + endpoint.lstrip("/")
        console.print(f"[bold cyan]🔍 Probing API:[/bold cyan] [bold green]{method.upper()}[/bold green] {target_url}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.request(
                    method=method.upper(),
                    url=target_url,
                    json=payload if method.upper() in ("POST", "PUT", "PATCH") else None,
                )
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text[:200]

                is_success = 200 <= resp.status_code < 400
                st_color = "green" if is_success else "red"
                console.print(f"[{st_color}]Status: {resp.status_code}[/{st_color}]")

                return {
                    "status_code": resp.status_code,
                    "response": data,
                    "success": is_success,
                }
            except httpx.ConnectError:
                console.print(f"[bold red]❌ Connection Refused:[/bold red] Cannot reach {target_url}")
                console.print("[yellow]Please verify that your server is running and the port is correct![/yellow]")
                return {
                    "status_code": 0,
                    "error": f"Connection refused to {target_url}",
                    "success": False,
                }
            except Exception as e:
                console.print(f"[bold red]Request failed:[/bold red] {e}")
                return {"status_code": 0, "error": str(e), "success": False}

    async def _execute_scan(self, url: str) -> dict[str, Any]:
        """Scans endpoints and web pages."""
        console.print(f"[bold cyan]🔎 Scanning Application Assets:[/bold cyan] {url}")
        app_data = await discover_application(url, enable_browser=True)
        return {
            "endpoints_found": len(app_data.endpoints),
            "pages_found": len(app_data.pages),
            "endpoints": [f"{ep.method} {ep.path}" for ep in app_data.endpoints[:10]],
            "pages": [p.url for p in app_data.pages[:5]],
        }

    async def _execute_code_fix(
        self,
        defect_description: str,
        endpoint: str | None = None,
        method: str | None = None,
    ) -> dict[str, Any]:
        """Locates buggy source code and proposes an AST-validated patch."""
        console.print(f"[bold yellow]🛠️ Inspecting source code for defect:[/bold yellow] {defect_description}")

        contexts = []
        if endpoint and method:
            contexts = self.locator.locate_endpoint(method, endpoint)

        if not contexts:
            # Fallback scan across Python files in repo
            for py_file in self.repo_dir.rglob("*.py"):
                if "test" in py_file.name or ".venv" in str(py_file):
                    continue
                try:
                    content = py_file.read_text(encoding="utf-8")
                    if endpoint and endpoint in content:
                        from recon.healing.locator import LocatedContext
                        contexts.append(LocatedContext(file_path=py_file, line_number=1, preview_snippet=content[:500]))
                        break
                except Exception:
                    continue

        if not contexts:
            console.print("[yellow]Could not locate relevant source file in repository.[/yellow]")
            return {"success": False, "reason": "Source file not found"}

        ctx = contexts[0]
        console.print(f"[dim]Found file:[/dim] [cyan]{ctx.file_path.relative_to(self.repo_dir)}[/cyan]")

        dummy_result = TestResult(
            test_id="agent-fix",
            test_name=f"Defect: {defect_description}",
            category=TestCategory.ERROR_HANDLING,
            test_type=TestType.API,
            status=TestStatus.FAILED,
            failure_evidence=FailureEvidence(
                category=FailureCategory.APPLICATION_ERROR,
                message=defect_description,
                http_trace=HTTPTrace(
                    method=method or "POST",
                    url=endpoint or "/",
                    status_code=500,
                ),
            ),
        )

        patch = await self.patch_generator.generate_patch(dummy_result, ctx)
        if not patch:
            return {"success": False, "reason": "Could not generate patch"}

        console.print("\n[bold green]Proposed Patch:[/bold green]")
        console.print(Syntax(patch.diff, "diff", theme="monokai", line_numbers=True))

        applied_path = self.patch_applier.apply_patch(patch)
        if applied_path:
            console.print(f"[bold green]✓ Patch successfully applied to {applied_path.name}[/bold green]")
            return {"success": True, "file": str(applied_path), "explanation": patch.explanation}
        else:
            return {"success": False, "reason": "Patch failed syntax validation"}

    def _parse_llm_tool_choice(self, text: str) -> dict[str, Any]:
        """Cleans and parses the tool selection JSON from the LLM."""
        clean = text.strip()
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
            if match:
                clean = match.group(1).strip()
        try:
            return json.loads(clean)
        except Exception:
            return {"tool": "reply", "message": text}

    async def execute_prompt(
        self, prompt: str, headless: bool = True, interactive: bool = False
    ) -> str:
        """Processes a natural language prompt, plans tools, and returns the response."""
        extracted_url = extract_url_from_text(prompt)
        if not extracted_url and not self.default_target:
            if any(k in prompt.lower() for k in ("test", "browse", "page", "cart", "checkout", "api", "login", "endpoint")):
                if interactive:
                    extracted_url = Prompt.ask("[bold cyan]Enter target URL[/bold cyan]", default="http://localhost:8000")
                else:
                    console.print("[dim]No URL found in prompt; defaulting to http://localhost:8000[/dim]")
                    extracted_url = "http://localhost:8000"

        extracted_url = extracted_url or self.default_target or "http://localhost:8000"
        self.default_target = extracted_url

        planning_prompt = (
            f"User Instruction: \"{prompt}\"\n"
            f"Repository Directory: {self.repo_dir}\n"
            f"Detected Target URL: {extracted_url}\n\n"
            f"Select the best tool to address this instruction."
        )

        raw_plan = await self.provider.complete(planning_prompt, system_prompt=MASTER_SYSTEM_PROMPT)
        plan = self._parse_llm_tool_choice(raw_plan)
        tool_name = plan.get("tool", "").lower()

        if tool_name == "browser":
            target_url = plan.get("url") or extracted_url
            goal = plan.get("goal") or prompt
            res = await self._execute_browser(target_url, goal, headless=headless)
            if res["errors"] and ("fix" in prompt.lower() or "repair" in prompt.lower()):
                console.print("[yellow]Errors detected in browser. Triggering code fix...[/yellow]")
                await self._execute_code_fix(defect_description=str(res["errors"][0]))
            return f"Browser task finished. {res['summary']} (Final URL: {res['final_url']})"

        elif tool_name == "api_probe":
            target_url = plan.get("url") or extracted_url
            endpoint = plan.get("endpoint") or "/"
            method = plan.get("method") or "GET"
            payload = plan.get("payload")
            res = await self._execute_api_probe(target_url, endpoint, method, payload)

            if not res.get("success") and ("fix" in prompt.lower() or "repair" in prompt.lower()):
                console.print(f"[yellow]API returned error status ({res.get('status_code')}). Triggering code fix...[/yellow]")
                fix_res = await self._execute_code_fix(
                    defect_description=f"Endpoint {method} {endpoint} returned {res.get('status_code')}",
                    endpoint=endpoint,
                    method=method,
                )
                if fix_res.get("success"):
                    return f"Tested {method} {endpoint} (got {res.get('status_code')}), located the bug, and successfully patched the source code ({fix_res.get('file')})!"
            return f"API probe to {method} {endpoint} returned HTTP {res.get('status_code')}."

        elif tool_name == "scan":
            target_url = plan.get("url") or extracted_url
            res = await self._execute_scan(target_url)
            return f"Scanned {target_url}: Discovered {res['endpoints_found']} endpoints and {res['pages_found']} web pages."

        elif tool_name == "code_fix":
            defect_desc = plan.get("defect_description") or prompt
            endpoint = plan.get("endpoint")
            method = plan.get("method")
            res = await self._execute_code_fix(defect_desc, endpoint, method)
            if res.get("success"):
                return f"Located and patched the defect: {res.get('explanation')}"
            return f"Could not complete code patch: {res.get('reason')}"

        else:
            return plan.get("message", "Task completed.")

    async def run_interactive(self, headless: bool = True):
        """Runs the interactive conversational REPL loop."""
        console.print(
            Panel(
                "[bold cyan]🤖 Recon Autonomous QA Assistant[/bold cyan]\n"
                "[dim]Ask me to test, browse, audit, or patch your code in plain English.\n"
                "Type [bold]exit[/bold] or [bold]quit[/bold] to return to the shell.[/dim]",
                border_style="cyan",
            )
        )

        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]").strip()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[dim]Ending interactive Recon session. Goodbye![/dim]")
                break

            try:
                reply = await self.execute_prompt(user_input, headless=headless, interactive=True)
                console.print(f"\n[bold cyan]Recon:[/bold cyan] {reply}")
            except Exception as e:
                console.print(f"[bold red]Error executing instruction:[/bold red] {e}")

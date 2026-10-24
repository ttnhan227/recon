from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.panel import Panel

from recon.common.logging import console, logger
from recon.common.models import (
    AgentAction,
    AgentExecutionReport,
    AgentInteractiveElement,
    AgentPageObservation,
    AgentStep,
    TestStatus,
)
from recon.execution.browser.evidence import BrowserEvidenceCollector
from recon.llm.provider import LLMProvider, get_llm_provider

OBSERVER_JS = """
() => {
    const isVisible = (el) => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 &&
               style.visibility !== 'hidden' && style.display !== 'none' &&
               style.opacity !== '0';
    };

    const elements = [];
    const candidates = document.querySelectorAll(
        'a[href], button, input:not([type="hidden"]), select, textarea, [role="button"], [onclick]'
    );
    let idCounter = 1;

    for (const el of candidates) {
        if (!isVisible(el)) continue;

        const tag = el.tagName.toLowerCase();
        let text = (
            el.innerText ||
            el.value ||
            el.placeholder ||
            el.getAttribute('aria-label') ||
            el.title ||
            ''
        ).trim();
        text = text.replace(/\\s+/g, ' ').slice(0, 80);

        // Skip empty non-inputs
        if (!text && tag !== 'input' && tag !== 'select') continue;

        let selector = '';
        if (el.id) {
            selector = `#${CSS.escape(el.id)}`;
        } else if (el.getAttribute('data-testid')) {
            selector = `[data-testid="${CSS.escape(el.getAttribute('data-testid'))}"]`;
        } else if (tag === 'a' && el.getAttribute('href')) {
            const href = el.getAttribute('href');
            if (text && text.length < 35) {
                selector = `a:has-text("${text.replace(/"/g, '\\\\"')}")`;
            } else {
                selector = `a[href="${href}"]`;
            }
        } else if (tag === 'button' && text && text.length < 35) {
            selector = `button:has-text("${text.replace(/"/g, '\\\\"')}")`;
        } else if (tag === 'input' && el.name) {
            selector = `input[name="${el.name}"]`;
        } else if (tag === 'input' && el.placeholder) {
            selector = `input[placeholder="${el.placeholder}"]`;
        } else {
            selector = tag;
        }

        elements.push({
            id: idCounter++,
            tag: tag,
            text: text,
            selector: selector,
            element_type: el.getAttribute('type') || null,
            href: el.getAttribute('href') || null,
            role: el.getAttribute('role') || null
        });

        if (elements.length >= 60) break;
    }
    return elements;
}
"""

SYSTEM_PROMPT = """You are Recon's Autonomous QA Browser Agent.
Your objective is to achieve the user's high-level goal on the website while validating stability.

At each step, you receive:
- The user's goal
- The current URL and page title
- A list of visible interactive elements (buttons, links, inputs) with their selectors and text
- Any recent console/network errors detected

You must decide the NEXT SINGLE ACTION. Supported actions:
1. {"action": "click", "selector": "<selector>", "thought": "<reasoning>"}
2. {"action": "fill", "selector": "<selector>", "value": "<text>", "thought": "<reasoning>"}
3. {"action": "navigate", "url": "<url>", "thought": "<reasoning>"}
4. {"action": "scroll", "thought": "<reasoning>"}
5. {"action": "wait", "seconds": 2.0, "thought": "<reasoning>"}
6. {"action": "finish", "thought": "<explanation of how goal was achieved>"}
7. {"action": "fail", "thought": "<explanation of why goal cannot be achieved>"}

Rules:
- Prefer selectors from the interactive elements list. If selecting by text, ensure the text matches the element.
- When the goal is met or the target page/information is found, IMMEDIATELY return action "finish".
- Output ONLY valid JSON, with no markdown code blocks or additional text.
"""


class ReconBrowserAgent:
    """Autonomous goal-directed browser agent that plans and executes interactions."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        run_id: str | None = None,
        output_dir: Path | str = "./reports",
    ):
        self.provider = provider or get_llm_provider()
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(output_dir)
        self.screenshots_dir = self.output_dir / f"agent-{self.run_id}" / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def observe_page(
        self, page: Any, evidence: BrowserEvidenceCollector
    ) -> AgentPageObservation:
        """Extracts visible interactive elements and current page metadata."""
        url = page.url
        title = await page.title()

        try:
            raw_elements = await page.evaluate(OBSERVER_JS)
            elements = [AgentInteractiveElement(**el) for el in raw_elements]
        except Exception as e:
            logger.warning(f"Error extracting interactive elements: {e}")
            elements = []

        recent_errs = [log.text for log in evidence.console_logs[-5:] if log.level == "error"]
        return AgentPageObservation(
            url=url,
            title=title,
            interactive_elements=elements,
            recent_errors=recent_errs,
        )

    def _parse_action(self, response_text: str) -> AgentAction:
        """Parses and sanitizes LLM response into an AgentAction."""
        clean = response_text.strip()
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
            if match:
                clean = match.group(1).strip()

        try:
            data = json.loads(clean)
            return AgentAction(**data)
        except Exception as e:
            logger.warning(f"Failed to parse LLM action JSON ({e}). Raw: {clean}")
            return AgentAction(
                action="finish",
                thought="Could not parse LLM action JSON; stopping agent.",
            )

    async def _execute_action(
        self, page: Any, action: AgentAction, timeout_ms: int = 8000
    ) -> tuple[bool, str | None]:
        """Executes the chosen Playwright action with error handling and smart fallbacks."""
        act = action.action.lower()

        try:
            if act == "click":
                selector = action.selector or ""
                try:
                    await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                    await page.click(selector, timeout=timeout_ms)
                except Exception:
                    # Smart fallback: if selector had text, try locator by text directly
                    text_match = re.search(r':has-text\("([^"]+)"\)', selector)
                    if text_match:
                        raw_text = text_match.group(1)
                        await page.get_by_text(raw_text).first.click(timeout=timeout_ms)
                    else:
                        raise
                await asyncio.sleep(0.5)
                return True, None

            elif act == "fill":
                selector = action.selector or ""
                value = action.value or ""
                await page.wait_for_selector(selector, timeout=timeout_ms, state="visible")
                await page.fill(selector, value, timeout=timeout_ms)
                return True, None

            elif act == "navigate":
                target_url = action.url or ""
                await page.goto(target_url, timeout=timeout_ms, wait_until="domcontentloaded")
                return True, None

            elif act == "scroll":
                await page.evaluate("window.scrollBy(0, window.innerHeight * 0.75)")
                await asyncio.sleep(0.4)
                return True, None

            elif act == "wait":
                secs = action.seconds or 2.0
                await asyncio.sleep(secs)
                return True, None

            elif act in ("finish", "fail"):
                return True, None

            else:
                return False, f"Unknown action: {act}"

        except Exception as e:
            return False, str(e)

    async def run(
        self,
        start_url: str,
        goal: str,
        max_steps: int = 10,
        headless: bool = True,
    ) -> AgentExecutionReport:
        """Executes the ReAct browser agent loop toward the given goal."""
        from playwright.async_api import async_playwright

        start_time = time.perf_counter()
        steps: list[AgentStep] = []
        evidence = BrowserEvidenceCollector(run_id=self.run_id, output_dir=self.output_dir)

        console.print("[bold cyan]🤖 Recon Agent Initializing[/bold cyan]")
        console.print(f"[bold]Target URL:[/bold] {start_url}")
        console.print(f"[bold]Goal:[/bold] {goal}")
        console.print(f"[bold]Mode:[/bold] {'Headless' if headless else 'Visible Browser'}")

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=headless)
            except Exception as e:
                err_str = str(e).lower()
                if "executable doesn't exist" in err_str or "playwright install" in err_str:
                    console.print(
                        Panel(
                            "[bold red]❌ Chromium Browser Not Installed[/bold red]\n\n"
                            "Playwright requires browser binaries to interact with web pages.\n\n"
                            "Install Chromium by running:\n"
                            "  [bold cyan]python -m playwright install chromium[/bold cyan]",
                            title="[bold red]Playwright Error[/bold red]",
                            border_style="red",
                        )
                    )
                    return AgentExecutionReport(
                        goal=goal,
                        start_url=start_url,
                        final_url=start_url,
                        status=TestStatus.ERROR,
                        summary="Chromium browser binary is missing. Run 'python -m playwright install chromium'.",
                    )
                raise

            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            page = await context.new_page()

            # Attach defect and error listeners
            page.on("console", evidence.handle_console)
            page.on("pageerror", evidence.handle_page_error)
            page.on("requestfailed", evidence.handle_request_failed)

            console.print(f"[dim]Navigating to initial page: {start_url}[/dim]")
            try:
                await page.goto(start_url, timeout=15000, wait_until="domcontentloaded")
            except Exception as e:
                err_str = str(e)
                if "ERR_CONNECTION_REFUSED" in err_str or "ConnectionRefused" in err_str:
                    console.print(
                        f"\n[bold red]❌ Connection Refused:[/bold red] Cannot reach {start_url}"
                    )
                    console.print(
                        "[yellow]Please verify that your local development server is running![/yellow]"
                    )
                elif "Timeout" in err_str or "timeout" in err_str.lower():
                    console.print(
                        f"\n[bold red]❌ Timeout reaching:[/bold red] {start_url} (waited 15s)"
                    )
                else:
                    console.print(f"\n[bold red]❌ Navigation error:[/bold red] {e}")

                await browser.close()
                return AgentExecutionReport(
                    goal=goal,
                    start_url=start_url,
                    final_url=start_url,
                    status=TestStatus.FAILED,
                    summary=f"Failed to connect to {start_url}: {e}",
                    errors_detected=[str(e)],
                )

            await asyncio.sleep(0.5)

            final_status = TestStatus.PASSED
            summary = ""
            last_action_sig: str | None = None
            last_url = page.url
            consecutive_repeats = 0
            stagnation_hint = ""

            for step_num in range(1, max_steps + 1):
                step_start = time.perf_counter()
                obs = await self.observe_page(page, evidence)

                # Format prompt for the LLM
                element_summary = [
                    f"[{el.id}] <{el.tag}> '{el.text}' -> selector: `{el.selector}`"
                    for el in obs.interactive_elements[:45]
                ]
                elements_str = (
                    "\n".join(element_summary)
                    if element_summary
                    else "(No interactive elements found)"
                )

                prompt = (
                    f"User Goal: {goal}\n\n"
                    f"Current URL: {obs.url}\n"
                    f"Page Title: {obs.title}\n\n"
                    f"Visible Interactive Elements:\n{elements_str}\n\n"
                    f"Recent Console Errors:\n{json.dumps(obs.recent_errors)}\n"
                )
                if stagnation_hint:
                    prompt += f"\n[CRITICAL NOTE]: {stagnation_hint}\n"

                prompt += f"\nStep {step_num} of {max_steps}. What is the next action?"

                # Get LLM decision
                raw_response = await self.provider.complete(prompt, system_prompt=SYSTEM_PROMPT)
                action = self._parse_action(raw_response)

                console.print(f"\n[bold yellow]Step {step_num}:[/bold yellow] {action.thought}")
                console.print(
                    f"[cyan]Action:[/cyan] [bold]{action.action.upper()}[/bold] {action.selector or action.url or action.value or ''}"
                )

                # Stagnation loop detection: if same action & selector repeated with no URL change
                action_sig = f"{action.action.lower()}:{action.selector or action.url or ''}"
                if (
                    action_sig == last_action_sig
                    and page.url == last_url
                    and action.action.lower() not in ("finish", "fail", "wait")
                ):
                    consecutive_repeats += 1
                    if consecutive_repeats >= 2:
                        stagnation_hint = (
                            f"Action '{action_sig}' was already attempted and did not change the page state. "
                            "Do NOT repeat this action. Choose another element, scroll, or conclude."
                        )
                else:
                    consecutive_repeats = 0
                    stagnation_hint = ""

                last_action_sig = action_sig
                last_url = page.url

                # Check termination actions before DOM execution
                if action.action.lower() == "finish":
                    final_status = TestStatus.PASSED
                    summary = action.thought
                    screenshot_file = self.screenshots_dir / f"step_{step_num}_finish.png"
                    await page.screenshot(path=str(screenshot_file), full_page=False)
                    steps.append(
                        AgentStep(
                            step_number=step_num,
                            action=action,
                            url=page.url,
                            duration_ms=round((time.perf_counter() - step_start) * 1000, 2),
                            status=TestStatus.PASSED,
                            screenshot_path=str(screenshot_file),
                        )
                    )
                    break

                if action.action.lower() == "fail":
                    final_status = TestStatus.FAILED
                    summary = action.thought
                    screenshot_file = self.screenshots_dir / f"step_{step_num}_fail.png"
                    await page.screenshot(path=str(screenshot_file), full_page=False)
                    steps.append(
                        AgentStep(
                            step_number=step_num,
                            action=action,
                            url=page.url,
                            duration_ms=round((time.perf_counter() - step_start) * 1000, 2),
                            status=TestStatus.FAILED,
                            screenshot_path=str(screenshot_file),
                        )
                    )
                    break

                # Execute action
                success, err_msg = await self._execute_action(page, action)
                step_screenshot: Path | None = self.screenshots_dir / f"step_{step_num}.png"
                try:
                    await page.screenshot(path=str(step_screenshot), full_page=False)
                except Exception:
                    step_screenshot = None

                step_duration = round((time.perf_counter() - step_start) * 1000, 2)
                step_status = TestStatus.PASSED if success else TestStatus.FAILED

                if not success:
                    console.print(f"[bold red]❌ Action failed:[/bold red] {err_msg}")
                else:
                    console.print(f"[green]✓ Action executed[/green] (Current URL: {page.url})")

                steps.append(
                    AgentStep(
                        step_number=step_num,
                        action=action,
                        url=page.url,
                        duration_ms=step_duration,
                        status=step_status,
                        screenshot_path=str(step_screenshot) if step_screenshot else None,
                        error=err_msg,
                    )
                )

            final_url = page.url
            await browser.close()

        total_duration = round(time.perf_counter() - start_time, 2)
        all_errors = [e for e in evidence.page_errors]
        for req_err in evidence.network_errors:
            all_errors.append(f"Network request failed: {req_err.url} ({req_err.error_text})")

        if not summary:
            summary = f"Completed {len(steps)} steps toward goal."

        report = AgentExecutionReport(
            goal=goal,
            start_url=start_url,
            final_url=final_url,
            status=final_status,
            steps=steps,
            errors_detected=all_errors,
            summary=summary,
            duration_seconds=total_duration,
        )

        return report

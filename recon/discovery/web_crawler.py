from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

from recon.common.exceptions import DiscoveryError
from recon.common.logging import logger
from recon.common.security import is_safe_target_url
from recon.discovery.models import (
    DiscoveredApplication,
    DiscoveredButton,
    DiscoveredForm,
    DiscoveredFormField,
    DiscoveredPage,
)


class WebCrawler:
    """Discovers web routes, interactive elements, forms, buttons, and console errors using Playwright or HTML parser."""

    def __init__(
        self,
        base_url: str,
        max_depth: int = 2,
        max_pages: int = 10,
        timeout_seconds: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.timeout_seconds = timeout_seconds
        self.visited_urls: set[str] = set()
        self.discovered_pages: list[DiscoveredPage] = []
        parsed = urlparse(self.base_url)
        self.base_domain = parsed.netloc

    def _is_same_domain(self, url: str) -> bool:
        """Checks if URL belongs to the target domain."""
        parsed = urlparse(url)
        return not parsed.netloc or parsed.netloc.lower() == self.base_domain.lower()

    async def crawl(self) -> DiscoveredApplication:
        """Runs the crawler starting from base_url."""
        # Try Playwright first for dynamic JS discovery; fallback to HTTP + BeautifulSoup if browser fails
        try:
            from playwright.async_api import async_playwright
            return await self._crawl_with_playwright()
        except Exception as e:
            logger.warning(f"Playwright web crawl unavailable ({e}), falling back to static HTML crawler.")
            return await self._crawl_with_http()

    async def _crawl_with_playwright(self) -> DiscoveredApplication:
        from playwright.async_api import async_playwright

        queue: list[tuple[str, int]] = [(self.base_url, 0)]
        self.visited_urls.add(self.base_url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )

            while queue and len(self.discovered_pages) < self.max_pages:
                current_url, depth = queue.pop(0)
                page = await context.new_page()

                console_errors: list[str] = []
                network_errors: list[str] = []

                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on(
                    "requestfailed",
                    lambda req: network_errors.append(
                        f"{req.method} {req.url} - {req.failure}"
                    ),
                )

                try:
                    logger.info(f"Crawling {current_url} (depth={depth})")
                    response = await page.goto(
                        current_url,
                        timeout=int(self.timeout_seconds * 1000),
                        wait_until="domcontentloaded",
                    )
                    status_code = response.status if response else 200
                    title = await page.title()
                    content = await page.content()

                    # Extract forms, buttons, links, inputs
                    discovered_page = self._parse_html_content(
                        current_url, content, status_code, title, console_errors, network_errors
                    )
                    self.discovered_pages.append(discovered_page)

                    # Discover new links to visit
                    if depth < self.max_depth:
                        for link in discovered_page.links:
                            norm_link = link.split("#")[0].rstrip("/")
                            if (
                                norm_link
                                and norm_link not in self.visited_urls
                                and self._is_same_domain(norm_link)
                            ):
                                is_safe, _ = is_safe_target_url(norm_link)
                                if is_safe:
                                    self.visited_urls.add(norm_link)
                                    queue.append((norm_link, depth + 1))

                except Exception as e:
                    logger.warning(f"Failed to crawl {current_url}: {e}")
                    self.discovered_pages.append(
                        DiscoveredPage(
                            url=current_url,
                            status_code=500,
                            console_errors=[f"Navigation error: {e}"],
                        )
                    )
                finally:
                    await page.close()

            await browser.close()

        return DiscoveredApplication(
            target_url=self.base_url,
            title=f"Web Application at {self.base_url}",
            spec_source="playwright_crawler",
            pages=self.discovered_pages,
            metadata={"crawled_pages_count": len(self.discovered_pages)},
        )

    async def _crawl_with_http(self) -> DiscoveredApplication:
        queue: list[tuple[str, int]] = [(self.base_url, 0)]
        self.visited_urls.add(self.base_url)

        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
            while queue and len(self.discovered_pages) < self.max_pages:
                current_url, depth = queue.pop(0)
                try:
                    resp = await client.get(current_url)
                    discovered_page = self._parse_html_content(
                        current_url, resp.text, resp.status_code, None, [], []
                    )
                    self.discovered_pages.append(discovered_page)

                    if depth < self.max_depth:
                        for link in discovered_page.links:
                            norm_link = link.split("#")[0].rstrip("/")
                            if (
                                norm_link
                                and norm_link not in self.visited_urls
                                and self._is_same_domain(norm_link)
                            ):
                                is_safe, _ = is_safe_target_url(norm_link)
                                if is_safe:
                                    self.visited_urls.add(norm_link)
                                    queue.append((norm_link, depth + 1))
                except Exception as e:
                    logger.warning(f"Static crawl error for {current_url}: {e}")
                    self.discovered_pages.append(
                        DiscoveredPage(url=current_url, status_code=500, console_errors=[str(e)])
                    )

        return DiscoveredApplication(
            target_url=self.base_url,
            title=f"Web Application at {self.base_url}",
            spec_source="http_crawler",
            pages=self.discovered_pages,
            metadata={"crawled_pages_count": len(self.discovered_pages)},
        )

    def _parse_html_content(
        self,
        url: str,
        html: str,
        status_code: int,
        title: str | None,
        console_errors: list[str],
        network_errors: list[str],
    ) -> DiscoveredPage:
        soup = BeautifulSoup(html, "html.parser")
        page_title = title or (soup.title.string if soup.title and soup.title.string else "")

        # Extract links
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href and not href.startswith(("javascript:", "mailto:", "tel:")):
                abs_url = urljoin(url, href)
                links.append(abs_url)

        # Extract forms
        forms: list[DiscoveredForm] = []
        for form_idx, form in enumerate(soup.find_all("form")):
            form_action = urljoin(url, form.get("action", ""))
            form_method = form.get("method", "GET").upper()
            form_id = form.get("id")
            form_selector = f"#{form_id}" if form_id else f"form:nth-of-type({form_idx + 1})"

            fields: list[DiscoveredFormField] = []
            for inp in form.find_all(["input", "select", "textarea"]):
                name = inp.get("name") or inp.get("id") or ""
                if not name:
                    continue
                tag = inp.name
                input_type = inp.get("type", "text") if tag == "input" else tag
                required = inp.has_attr("required")
                placeholder = inp.get("placeholder")
                default_val = inp.get("value")

                options: list[str] = []
                if tag == "select":
                    for opt in inp.find_all("option"):
                        val = opt.get("value") or opt.text
                        if val:
                            options.append(val.strip())

                inp_id = inp.get("id")
                selector = f"#{inp_id}" if inp_id else f"[name='{name}']"

                fields.append(
                    DiscoveredFormField(
                        name=name,
                        field_type=input_type,
                        required=required,
                        placeholder=placeholder,
                        default_value=default_val,
                        options=options,
                        selector=selector,
                    )
                )

            # Submit button
            submit_btn = form.find("button", type="submit") or form.find("input", type="submit")
            submit_selector = None
            if submit_btn:
                btn_id = submit_btn.get("id")
                submit_selector = (
                    f"#{btn_id}" if btn_id else f"{form_selector} button[type='submit'], {form_selector} input[type='submit']"
                )

            forms.append(
                DiscoveredForm(
                    action=form_action,
                    method=form_method,
                    selector=form_selector,
                    fields=fields,
                    submit_selector=submit_selector,
                    location_url=url,
                )
            )

        # Extract interactive buttons outside forms
        buttons: list[DiscoveredButton] = []
        for btn_idx, btn in enumerate(soup.find_all("button")):
            text = btn.get_text(strip=True)
            btn_id = btn.get("id")
            selector = f"#{btn_id}" if btn_id else f"button:nth-of-type({btn_idx + 1})"
            buttons.append(
                DiscoveredButton(
                    text=text or f"Button {btn_idx + 1}",
                    selector=selector,
                    button_type=btn.get("type", "button"),
                )
            )

        return DiscoveredPage(
            url=url,
            title=page_title,
            status_code=status_code,
            forms=forms,
            buttons=buttons,
            links=list(set(links)),
            console_errors=console_errors,
            network_errors=network_errors,
        )

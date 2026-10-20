from __future__ import annotations

from urllib.parse import urljoin

import httpx

from recon.common.exceptions import DiscoveryError, TargetUnreachableError
from recon.common.logging import logger
from recon.common.security import validate_target_url
from recon.discovery.models import DiscoveredApplication
from recon.discovery.openapi import OpenAPIParser
from recon.discovery.web_crawler import WebCrawler

OPENAPI_PROBE_PATHS = [
    "/openapi.json",
    "/swagger.json",
    "/api/openapi.json",
    "/api/v1/openapi.json",
    "/v3/api-docs",
    "/api-docs",
    "/docs/openapi.json",
]


async def discover_application(
    target_url: str,
    spec_path_or_url: str | None = None,
    enable_browser: bool = False,
) -> DiscoveredApplication:
    """
    Main entry point for discovery.
    1. Validates target_url for security / SSRF.
    2. If spec_path_or_url is provided, parses it as OpenAPI.
    3. Otherwise probes target_url for OpenAPI JSON endpoints.
    4. If browser is enabled or no OpenAPI spec is found, crawls web pages.
    """
    validate_target_url(target_url)

    # 1. Explicit spec
    if spec_path_or_url:
        if spec_path_or_url.startswith("http://") or spec_path_or_url.startswith("https://"):
            logger.info(f"Loading OpenAPI specification from URL: {spec_path_or_url}")
            parser = await OpenAPIParser.from_url(spec_path_or_url)
            app = parser.parse(base_url=target_url)
        else:
            logger.info(f"Loading OpenAPI specification from local file: {spec_path_or_url}")
            parser = OpenAPIParser.from_file(spec_path_or_url)
            app = parser.parse(base_url=target_url)

        if enable_browser:
            logger.info(f"Running web crawl on {target_url} alongside OpenAPI discovery...")
            crawler = WebCrawler(target_url)
            web_app = await crawler.crawl()
            app.pages = web_app.pages

        return app

    # 2. Probe for OpenAPI
    base = target_url.rstrip("/")
    async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
        # Pre-flight reachability check: fast probe to determine if target host is listening
        try:
            await client.get(base)
        except (httpx.ConnectError, httpx.ConnectTimeout) as conn_err:
            logger.error(f"Cannot connect to target {target_url}: {conn_err}")
            raise TargetUnreachableError(
                f"Cannot connect to target '{target_url}'. Connection was refused or timed out. "
                "Ensure the target server is running and accessible."
            ) from conn_err
        except Exception:
            # 4xx/5xx or SSL warnings mean the host at least responded or TCP connected
            pass

        for probe in OPENAPI_PROBE_PATHS:
            probe_url = urljoin(base + "/", probe.lstrip("/"))
            try:
                resp = await client.get(probe_url)
                if resp.status_code == 200 and (
                    "json" in resp.headers.get("content-type", "")
                    or resp.text.strip().startswith("{")
                ):
                    logger.info(f"Auto-detected OpenAPI specification at {probe_url}")
                    parser = await OpenAPIParser.from_url(probe_url)
                    app = parser.parse(base_url=base)
                    if enable_browser:
                        crawler = WebCrawler(base)
                        web_app = await crawler.crawl()
                        app.pages = web_app.pages
                    return app
            except Exception:
                continue

    # 3. Fallback to Web Crawling if enabled
    if enable_browser:
        logger.info(f"No OpenAPI spec found at {target_url}. Starting web application crawler...")
        crawler = WebCrawler(base)
        return await crawler.crawl()

    # 4. If neither OpenAPI nor browser crawling requested, raise clean informative error
    raise DiscoveryError(
        f"No OpenAPI specification detected at '{target_url}'. "
        "Provide an explicit specification via `--spec <path/url>` or enable web crawling via `--browser`."
    )

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from recon.common.logging import logger
from recon.common.models import (
    AssertionType,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStep,
    TestType,
)
from recon.common.security import is_safe_target_url
from recon.discovery.models import DiscoveredApplication
from recon.llm.provider import LLMProvider, get_llm_provider

SYSTEM_PROMPT = """You are an expert Security and QA Engineer.
Given the application's discovered endpoints and parameters, propose 2-4 high-value exploratory edge case test cases.
Categories to explore:
- Extreme boundary length / Unicode inputs
- Unexpected / prototype pollution / extra fields
- Type confusion / negative payload variants

Return valid JSON conforming to this schema:
{
  "test_cases": [
    {
      "name": "Edge case test name",
      "category": "BOUNDARY",
      "method": "POST",
      "target": "/api/users",
      "body": {"field": "val"},
      "expected_status": [200, 201, 400, 422]
    }
  ]
}
Do NOT return markdown or commentary, only valid JSON.
"""


class AITestGenerator:
    """Proposes additional exploratory test cases using LLMs with strict safety validation."""

    def __init__(self, provider: LLMProvider | None = None):
        self.provider = provider or get_llm_provider()

    async def generate_exploratory_tests(
        self, app: DiscoveredApplication, base_id_num: int = 100
    ) -> list[TestCase]:
        """Generates additional verified test cases via LLM."""
        if not app.endpoints:
            return []

        # Build application overview for LLM
        summary_endpoints = []
        for ep in app.endpoints[:10]:
            summary_endpoints.append({
                "path": ep.path,
                "method": ep.method,
                "summary": ep.summary,
                "params": [p.name for p in ep.parameters],
                "has_body": ep.request_body_schema is not None,
            })

        prompt = f"Target Application Base URL: {app.target_url}\nEndpoints:\n{json.dumps(summary_endpoints, indent=2)}"

        try:
            raw_response = await self.provider.complete(prompt, system_prompt=SYSTEM_PROMPT)
            clean_json = raw_response.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\n?", "", clean_json)
                clean_json = re.sub(r"\n?```$", "", clean_json)

            data = json.loads(clean_json)
            proposed_list = data.get("test_cases", [])

            validated_tests: list[TestCase] = []
            base_url = app.target_url.rstrip("/")

            for idx, p in enumerate(proposed_list):
                name = str(p.get("name", f"AI Exploratory Test {idx + 1}"))
                cat_str = str(p.get("category", "EXPLORATORY")).upper()
                category = getattr(TestCategory, cat_str, TestCategory.EXPLORATORY)
                method = str(p.get("method", "GET")).upper()
                raw_target = str(p.get("target", "/"))

                # Strict validation: allowed HTTP methods only
                if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    continue

                full_url = urljoin(base_url + "/", raw_target.lstrip("/"))
                is_safe, _ = is_safe_target_url(full_url)
                if not is_safe:
                    continue

                body = p.get("body")
                expected_status = p.get("expected_status", [200, 201, 400, 422])
                if not isinstance(expected_status, list):
                    expected_status = [expected_status]

                step = TestStep(
                    name=f"AI Step: {name}",
                    step_type="http_request",
                    endpoint=full_url,
                    method=method,
                    body=body,
                    headers={"Content-Type": "application/json"} if body is not None else {},
                    assertions=[
                        StepAssertion(
                            assertion_type=AssertionType.STATUS_CODE,
                            expected=expected_status,
                            operator="in",
                            message=f"Expected status in {expected_status}, server returned unexpected code",
                        )
                    ],
                )

                validated_tests.append(
                    TestCase(
                        id=f"AI-{base_id_num + idx:03d}",
                        name=name,
                        description=f"AI-generated exploratory test for {method} {raw_target}",
                        category=category,
                        test_type=TestType.API,
                        target=full_url,
                        method=method,
                        steps=[step],
                        tags=["ai_generated", "exploratory"],
                    )
                )

            return validated_tests

        except Exception as e:
            logger.warning(f"AI Test generation skipped: {e}")
            return []

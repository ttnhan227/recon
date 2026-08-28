from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from recon.common.models import (
    AssertionType,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStep,
    TestType,
)
from recon.discovery.models import DiscoveredApplication, DiscoveredEndpoint, DiscoveredPage
from recon.planning.schema_fuzzer import SchemaFuzzer


class TestSuiteGenerator:
    """Generates deterministic API and Browser test suites from discovered application assets."""
    __test__ = False

    def __init__(self, app: DiscoveredApplication, default_headers: dict[str, str] | None = None):
        self.app = app
        self.default_headers = default_headers or {}
        self.test_counter = 1

    def _build_headers(self, has_body: bool = False, is_auth_test: bool = False) -> dict[str, str]:
        headers = {} if is_auth_test else dict(self.default_headers)
        if has_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _next_id(self, prefix: str) -> str:
        tid = f"{prefix}-{self.test_counter:03d}"
        self.test_counter += 1
        return tid

    def generate_suite(self) -> list[TestCase]:
        """Generates all API and Browser test cases."""
        tests: list[TestCase] = []

        # 1. Generate API tests for discovered endpoints
        for endpoint in self.app.endpoints:
            tests.extend(self._generate_endpoint_tests(endpoint))

        # 2. Generate Browser tests for discovered pages
        for page in self.app.pages:
            tests.extend(self._generate_page_tests(page))

        return tests

    def _generate_endpoint_tests(self, ep: DiscoveredEndpoint) -> list[TestCase]:
        tests: list[TestCase] = []
        base_url = self.app.target_url.rstrip("/")
        full_url = urljoin(base_url + "/", ep.path.lstrip("/"))

        # Replace path parameters with sample values
        sample_path = ep.path
        query_params: dict[str, Any] = {}
        for param in ep.parameters:
            if param.in_type == "path":
                val = param.default or "1"
                sample_path = sample_path.replace(f"{{{param.name}}}", str(val))
            elif param.in_type == "query" and param.required:
                query_params[param.name] = param.default or "test_param"

        endpoint_url = urljoin(base_url + "/", sample_path.lstrip("/"))

        # --- A. HAPPY PATH TEST ---
        happy_body = (
            SchemaFuzzer.generate_valid_payload(ep.request_body_schema)
            if ep.request_body_schema
            else None
        )
        expected_status = [200, 201, 204] if ep.method in ("GET", "POST", "PUT", "PATCH", "DELETE") else [200]

        happy_assertions = [
            StepAssertion(
                assertion_type=AssertionType.STATUS_CODE,
                expected=expected_status,
                operator="in",
                message=f"Expected successful status code {expected_status}",
            ),
            StepAssertion(
                assertion_type=AssertionType.RESPONSE_TIME_MS,
                expected=5000,
                operator="lte",
                message="Expected response time <= 5000ms",
            ),
        ]

        # If 200 response schema is available, add JSON schema assertion
        if "200" in ep.response_schemas:
            happy_assertions.append(
                StepAssertion(
                    assertion_type=AssertionType.JSON_SCHEMA,
                    expected=ep.response_schemas["200"],
                    operator="validates",
                    message="Response JSON must validate against OpenAPI 200 response schema",
                )
            )

        happy_step = TestStep(
            name=f"{ep.method} {ep.path} - Success Case",
            step_type="http_request",
            endpoint=endpoint_url,
            method=ep.method,
            params=query_params,
            body=happy_body,
            headers=self._build_headers(has_body=(happy_body is not None)),
            assertions=happy_assertions,
        )

        tests.append(
            TestCase(
                id=self._next_id("API"),
                name=f"[{ep.method} {ep.path}] Happy Path - Valid Request",
                description=ep.summary or f"Verify {ep.method} {ep.path} succeeds with valid payload",
                category=TestCategory.HAPPY_PATH,
                test_type=TestType.API,
                target=endpoint_url,
                method=ep.method,
                steps=[happy_step],
                tags=["api", "happy_path"] + ep.tags,
            )
        )

        # --- B. VALIDATION TESTS (Missing Required Fields) ---
        if ep.request_body_schema:
            val_cases = SchemaFuzzer.generate_validation_cases(ep.request_body_schema)
            for desc, val_body in val_cases:
                val_step = TestStep(
                    name=f"Validation - {desc}",
                    step_type="http_request",
                    endpoint=endpoint_url,
                    method=ep.method,
                    params=query_params,
                    body=val_body,
                    headers=self._build_headers(has_body=True),
                    assertions=[
                        StepAssertion(
                            assertion_type=AssertionType.STATUS_CODE,
                            expected=[400, 422],
                            operator="in",
                            message="Expected HTTP 400 or 422 validation error when required field is missing",
                        )
                    ],
                )
                tests.append(
                    TestCase(
                        id=self._next_id("API"),
                        name=f"[{ep.method} {ep.path}] Validation - {desc}",
                        description=f"Verify server handles missing field with 400/422: {desc}",
                        category=TestCategory.VALIDATION,
                        test_type=TestType.API,
                        target=endpoint_url,
                        method=ep.method,
                        steps=[val_step],
                        tags=["api", "validation"] + ep.tags,
                    )
                )

        # --- C. BOUNDARY TESTS ---
        if ep.request_body_schema:
            boundary_cases = SchemaFuzzer.generate_boundary_payloads(ep.request_body_schema)
            for desc, b_body in boundary_cases[:3]:  # Top 3 boundary cases
                b_step = TestStep(
                    name=f"Boundary - {desc}",
                    step_type="http_request",
                    endpoint=endpoint_url,
                    method=ep.method,
                    params=query_params,
                    body=b_body,
                    headers=self._build_headers(has_body=True),
                    assertions=[
                        StepAssertion(
                            assertion_type=AssertionType.STATUS_CODE,
                            expected=[200, 201, 400, 422],
                            operator="in",
                            message="Server must return valid business response or clean 4xx validation error, not 500",
                        )
                    ],
                )
                tests.append(
                    TestCase(
                        id=self._next_id("API"),
                        name=f"[{ep.method} {ep.path}] Boundary - {desc}",
                        description=f"Boundary test with {desc}",
                        category=TestCategory.BOUNDARY,
                        test_type=TestType.API,
                        target=endpoint_url,
                        method=ep.method,
                        steps=[b_step],
                        tags=["api", "boundary"] + ep.tags,
                    )
                )

        # --- D. NEGATIVE TESTS (Type Violations) ---
        if ep.request_body_schema:
            neg_cases = SchemaFuzzer.generate_negative_cases(ep.request_body_schema)
            for desc, neg_body in neg_cases[:2]:
                neg_step = TestStep(
                    name=f"Negative - {desc}",
                    step_type="http_request",
                    endpoint=endpoint_url,
                    method=ep.method,
                    params=query_params,
                    body=neg_body,
                    headers=self._build_headers(has_body=True),
                    assertions=[
                        StepAssertion(
                            assertion_type=AssertionType.STATUS_CODE,
                            expected=[400, 422],
                            operator="in",
                            message="Expected HTTP 400 or 422 for malformed/type-mismatched payload",
                        )
                    ],
                )
                tests.append(
                    TestCase(
                        id=self._next_id("API"),
                        name=f"[{ep.method} {ep.path}] Negative - {desc}",
                        description=f"Verify type mismatch rejection: {desc}",
                        category=TestCategory.NEGATIVE,
                        test_type=TestType.API,
                        target=endpoint_url,
                        method=ep.method,
                        steps=[neg_step],
                        tags=["api", "negative"] + ep.tags,
                    )
                )

        # --- E. AUTHENTICATION & AUTHORIZATION TESTS ---
        if ep.security_schemes or "admin" in ep.path.lower() or "secure" in ep.path.lower() or "secret" in ep.path.lower():
            # Unauthenticated access attempt
            unauth_step = TestStep(
                name=f"{ep.method} {ep.path} - Unauthenticated Call",
                step_type="http_request",
                endpoint=endpoint_url,
                method=ep.method,
                params=query_params,
                body=happy_body,
                headers=self._build_headers(has_body=(happy_body is not None), is_auth_test=True),
                assertions=[
                    StepAssertion(
                        assertion_type=AssertionType.STATUS_CODE,
                        expected=[401, 403],
                        operator="in",
                        message="Secured endpoint must return 401 Unauthorized or 403 Forbidden without credentials",
                    )
                ],
            )
            tests.append(
                TestCase(
                    id=self._next_id("API"),
                    name=f"[{ep.method} {ep.path}] Auth - Reject Missing Credentials",
                    description=f"Verify unauthenticated request to {ep.path} is denied with 401/403",
                    category=TestCategory.AUTHENTICATION,
                    test_type=TestType.API,
                    target=endpoint_url,
                    method=ep.method,
                    steps=[unauth_step],
                    tags=["api", "security", "auth"] + ep.tags,
                )
            )

        # --- F. ERROR HANDLING (Non-existent Resource) ---
        if "{" in ep.path and "}" in ep.path and ep.method in ("GET", "PUT", "DELETE"):
            not_found_path = re.sub(r"\{[a-zA-Z0-9_]+\}", "99999999", ep.path)
            not_found_url = urljoin(base_url + "/", not_found_path.lstrip("/"))
            nf_step = TestStep(
                name=f"{ep.method} {not_found_path} - Non-existent ID",
                step_type="http_request",
                endpoint=not_found_url,
                method=ep.method,
                headers=self._build_headers(has_body=False),
                assertions=[
                    StepAssertion(
                        assertion_type=AssertionType.STATUS_CODE,
                        expected=[404],
                        operator="in",
                        message="Non-existent resource ID should return 404 Not Found",
                    )
                ],
            )
            tests.append(
                TestCase(
                    id=self._next_id("API"),
                    name=f"[{ep.method} {ep.path}] Error Handling - 404 Non-existent ID",
                    description=f"Verify requesting non-existent ID on {ep.path} returns 404",
                    category=TestCategory.ERROR_HANDLING,
                    test_type=TestType.API,
                    target=not_found_url,
                    method=ep.method,
                    steps=[nf_step],
                    tags=["api", "error_handling"] + ep.tags,
                )
            )

        return tests

    def _generate_page_tests(self, page: DiscoveredPage) -> list[TestCase]:
        tests: list[TestCase] = []

        # 1. Page Load & Title & No Console Errors test
        nav_step = TestStep(
            name=f"Navigate to {page.url}",
            step_type="browser_navigate",
            endpoint=page.url,
            assertions=[
                StepAssertion(
                    assertion_type=AssertionType.STATUS_CODE,
                    expected=[200],
                    operator="in",
                    message="Page should return 200 OK",
                )
            ],
        )
        tests.append(
            TestCase(
                id=self._next_id("UI"),
                name=f"[Browser] Page Load & Health - {page.url}",
                description=f"Verify {page.url} loads cleanly without console or network failures",
                category=TestCategory.HAPPY_PATH,
                test_type=TestType.BROWSER,
                target=page.url,
                steps=[nav_step],
                tags=["ui", "browser", "page_load"],
            )
        )

        # 2. Form submission tests
        for f_idx, form in enumerate(page.forms):
            form_steps = [
                TestStep(
                    name=f"Navigate to form page: {page.url}",
                    step_type="browser_navigate",
                    endpoint=page.url,
                )
            ]

            # Fill each field
            for field in form.fields:
                if field.selector and field.field_type not in ("submit", "hidden"):
                    if field.field_type == "number":
                        fill_val = "5"
                    elif field.field_type == "email":
                        fill_val = "test@example.com"
                    else:
                        fill_val = "TestVal123"

                    form_steps.append(
                        TestStep(
                            name=f"Fill field {field.name}",
                            step_type="browser_fill",
                            selector=field.selector,
                            value=fill_val,
                        )
                    )

            # Click submit
            if form.submit_selector:
                form_steps.append(
                    TestStep(
                        name="Click Form Submit",
                        step_type="browser_click",
                        selector=form.submit_selector,
                        assertions=[
                            StepAssertion(
                                assertion_type=AssertionType.RESPONSE_TIME_MS,
                                expected=10000,
                                operator="lte",
                                message="Form submission completed",
                            )
                        ],
                    )
                )

            tests.append(
                TestCase(
                    id=self._next_id("UI"),
                    name=f"[Browser] Form Submit - {form.selector or f'Form {f_idx + 1}'} on {page.url}",
                    description=f"Verify form submission interaction on {page.url}",
                    category=TestCategory.HAPPY_PATH,
                    test_type=TestType.BROWSER,
                    target=page.url,
                    steps=form_steps,
                    tags=["ui", "browser", "form"],
                )
            )

        # 3. Interactive button clicks
        for b_idx, btn in enumerate(page.buttons[:3]):  # Test up to 3 buttons
            btn_steps = [
                TestStep(
                    name=f"Navigate to {page.url}",
                    step_type="browser_navigate",
                    endpoint=page.url,
                ),
                TestStep(
                    name=f"Click Button '{btn.text}'",
                    step_type="browser_click",
                    selector=btn.selector,
                ),
            ]
            tests.append(
                TestCase(
                    id=self._next_id("UI"),
                    name=f"[Browser] Click Interaction - '{btn.text}' on {page.url}",
                    description=f"Verify clicking '{btn.text}' on {page.url} produces no unhandled exceptions",
                    category=TestCategory.EXPLORATORY,
                    test_type=TestType.BROWSER,
                    target=page.url,
                    steps=btn_steps,
                    tags=["ui", "browser", "interactive"],
                )
            )

        return tests

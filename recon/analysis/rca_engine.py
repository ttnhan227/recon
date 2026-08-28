from __future__ import annotations

from typing import Any
from recon.common.models import (
    FailureAnalysis,
    FailureCategory,
    Hypothesis,
    TestCase,
    TestResult,
)


class RootCauseAnalyzer:
    """Performs deterministic root-cause analysis by extracting facts, forming hypotheses, and suggesting fixes."""

    @classmethod
    def analyze(cls, result: TestResult, original_test: TestCase | None = None) -> FailureAnalysis:
        evidence = result.failure_evidence
        facts: list[str] = []
        hypotheses: list[Hypothesis] = []
        suggested_fix: str | None = None
        confidence = 0.70

        if not evidence:
            return FailureAnalysis(
                observed_facts=["No failure evidence captured."],
                hypotheses=[
                    Hypothesis(
                        hypothesis="Test execution passed or encountered an unknown state.",
                        confidence=1.0,
                        explanation="No failure details available.",
                    )
                ],
                confidence_score=1.0,
            )

        # 1. Extract Observed Facts
        cat = evidence.failure_category
        facts.append(f"Failure classified as: {cat.value}")

        if evidence.failed_step:
            facts.append(f"Failed at step: '{evidence.failed_step}'")

        if evidence.http_traces:
            last_trace = evidence.http_traces[-1]
            if last_trace.response_status:
                facts.append(
                    f"HTTP {last_trace.request_method} {last_trace.request_url} returned status code {last_trace.response_status}"
                )
            else:
                facts.append(
                    f"HTTP {last_trace.request_method} {last_trace.request_url} failed with network/timeout error"
                )

            if last_trace.response_body:
                body_str = str(last_trace.response_body)
                if len(body_str) < 300:
                    facts.append(f"Response body: {body_str}")
                else:
                    facts.append(f"Response body snippet: {body_str[:300]}...")

        for console_log in evidence.console_errors:
            facts.append(f"Browser console [{console_log.level}]: {console_log.text}")

        for net_err in evidence.network_errors:
            facts.append(f"Browser network failure: {net_err.method} {net_err.url} - {net_err.error_text}")

        # 2. Derive Hypotheses and Suggested Fixes
        if cat == FailureCategory.APPLICATION_ERROR:
            # Check for specific known failure patterns
            body_text = str(evidence.http_traces[-1].response_body if evidence.http_traces else "").lower()
            console_text = " ".join(c.text.lower() for c in evidence.console_errors)

            if "currency" in body_text or (original_test and "currency" in original_test.name.lower()):
                hypotheses.append(
                    Hypothesis(
                        hypothesis="Backend attempts to access 'currency' field on payment/order object without validating its presence.",
                        confidence=0.88,
                        explanation="Server returned 500 when request body omitted the required currency attribute.",
                    )
                )
                suggested_fix = "Add schema validation or default fallback check for 'currency' before accessing order data."
                confidence = 0.88
            elif "cannot read propert" in console_text or "typeerror" in console_text:
                hypotheses.append(
                    Hypothesis(
                        hypothesis="Frontend JavaScript accessed an undefined DOM element or property during event handling.",
                        confidence=0.85,
                        explanation=f"Browser console logged unhandled TypeError: {console_text[:150]}",
                    )
                )
                suggested_fix = "Verify element existence or optional chaining (`?.`) before dereferencing properties in frontend scripts."
                confidence = 0.85
            else:
                hypotheses.append(
                    Hypothesis(
                        hypothesis="Server encountered an unhandled exception or internal crash.",
                        confidence=0.75,
                        explanation=f"Server returned 500 with payload: {body_text[:150]}",
                    )
                )
                suggested_fix = "Wrap route handler in defensive try/except block and return a structured 4xx validation response instead of 500."
                confidence = 0.75

        elif cat == FailureCategory.AUTHENTICATION_FAILURE:
            hypotheses.append(
                Hypothesis(
                    hypothesis="Endpoint is protected but rejected credentials or missing token header.",
                    confidence=0.90,
                    explanation="Endpoint responded with HTTP 401 Unauthorized.",
                )
            )
            suggested_fix = "Provide valid Authorization: Bearer <token> or configure public endpoint bypass if intended to be open."
            confidence = 0.90

        elif cat == FailureCategory.AUTHORIZATION_FAILURE:
            hypotheses.append(
                Hypothesis(
                    hypothesis="Client has insufficient permissions or role to access the requested resource.",
                    confidence=0.90,
                    explanation="Endpoint responded with HTTP 403 Forbidden.",
                )
            )
            suggested_fix = "Grant required role/scope in identity provider or update endpoint RBAC policies."
            confidence = 0.90

        elif cat == FailureCategory.VALIDATION_FAILURE:
            hypotheses.append(
                Hypothesis(
                    hypothesis="Request payload violated data constraints or required schema definitions.",
                    confidence=0.85,
                    explanation="Endpoint rejected input with 400 Bad Request or 422 Unprocessable Entity.",
                )
            )
            suggested_fix = "Ensure payload strictly conforms to OpenAPI requestBody schema."
            confidence = 0.85

        elif cat == FailureCategory.TIMEOUT:
            hypotheses.append(
                Hypothesis(
                    hypothesis="Operation exceeded maximum time limit due to slow database queries, backend deadlock, or unrendered DOM elements.",
                    confidence=0.80,
                    explanation="Execution was aborted after reaching the configured timeout limit.",
                )
            )
            suggested_fix = "Optimize database queries, introduce asynchronous background processing, or increase step timeout."
            confidence = 0.80

        elif cat == FailureCategory.BROWSER_ERROR:
            hypotheses.append(
                Hypothesis(
                    hypothesis="Target selector or interactable DOM element was not visible or not attached to the DOM.",
                    confidence=0.82,
                    explanation=f"Playwright locator failed: {evidence.message}",
                )
            )
            suggested_fix = "Update selector to match active DOM ID/class or wait for element visibility before clicking/typing."
            confidence = 0.82

        else:
            hypotheses.append(
                Hypothesis(
                    hypothesis=f"Test assertion failed: {evidence.message}",
                    confidence=0.70,
                    explanation="Observed response differed from expected criteria in test specification.",
                )
            )
            suggested_fix = "Review expected test criteria against current application specifications."

        return FailureAnalysis(
            observed_facts=facts,
            hypotheses=hypotheses,
            suggested_fix=suggested_fix,
            confidence_score=confidence,
        )

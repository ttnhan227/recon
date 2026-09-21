from __future__ import annotations

import re

from recon.common.models import (
    FailureCategory,
    TestResult,
    TestStatus,
)

STACK_TRACE_PATTERNS = [
    r"traceback \(most recent call last\):",
    r"nullpointerexception",
    r"nullreferenceexception",
    r"cannot read propert",
    r"uncaught typeerror",
    r"syntaxerror",
    r"attributeerror",
    r"keyerror",
    r"indexerror",
    r"zerodivisionerror",
    r"internal server error",
    r"sqlalchemy\.exc\.",
    r"psycopg2\.",
    r"java\.lang\.",
]


class DeterministicFailureClassifier:
    """Classifies test failures based on HTTP traces, status codes, error payloads, and browser logs."""

    @classmethod
    def classify(cls, result: TestResult) -> FailureCategory:
        """Determines the most accurate FailureCategory for a given TestResult."""
        if result.status == TestStatus.PASSED:
            return FailureCategory.UNKNOWN

        evidence = result.failure_evidence
        if not evidence:
            return FailureCategory.UNKNOWN

        msg = (evidence.message or "").lower()
        stack = (evidence.stack_trace or "").lower()
        system_logs = " ".join(evidence.system_logs).lower()

        # Check console errors first
        for console_log in evidence.console_errors:
            c_text = console_log.text.lower()
            if any(p in c_text for p in ["typeerror", "referenceerror", "syntaxerror", "uncaught"]):
                return FailureCategory.APPLICATION_ERROR

        # Check HTTP traces
        if evidence.http_traces:
            last_trace = evidence.http_traces[-1]
            status = last_trace.response_status
            body_str = str(last_trace.response_body or "").lower()

            if status is None:
                if "timeout" in msg or "timed out" in msg:
                    return FailureCategory.TIMEOUT
                return FailureCategory.NETWORK_ERROR

            if status == 500:
                return FailureCategory.APPLICATION_ERROR

            if status in (502, 503, 504):
                return FailureCategory.HTTP_ERROR

            if status == 401:
                return FailureCategory.AUTHENTICATION_FAILURE

            if status == 403:
                return FailureCategory.AUTHORIZATION_FAILURE

            if status in (400, 422):
                return FailureCategory.VALIDATION_FAILURE

            # Check if 500 stack trace was leaked in a 200/400 body
            for pattern in STACK_TRACE_PATTERNS:
                if re.search(pattern, body_str):
                    return FailureCategory.APPLICATION_ERROR

        # Check for stack traces in error message or stack_trace
        combined_text = f"{msg} {stack} {system_logs}"
        for pattern in STACK_TRACE_PATTERNS:
            if re.search(pattern, combined_text):
                return FailureCategory.APPLICATION_ERROR

        # Browser specific errors
        if "locator" in msg or "selector" in msg or "element not found" in msg:
            return FailureCategory.BROWSER_ERROR

        if "timeout" in msg or "timed out" in msg:
            return FailureCategory.TIMEOUT

        if "connection refused" in msg or "network error" in msg or "dns" in msg:
            return FailureCategory.NETWORK_ERROR

        # Check assertion results
        for step in result.step_results:
            for ar in step.assertion_results:
                if not ar.passed:
                    return FailureCategory.ASSERTION_FAILURE

        return FailureCategory.UNKNOWN

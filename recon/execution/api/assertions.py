from __future__ import annotations

import re
from typing import Any
import jsonschema

from recon.common.models import AssertionResult, AssertionType, StepAssertion


def extract_json_path(data: Any, path: str) -> Any:
    """
    Extracts value from JSON object using dot notation or JSONPath like '$.data.user.id' or 'data.items.0.name'.
    """
    if not isinstance(data, (dict, list)):
        return None

    clean_path = path.lstrip("$.").strip()
    if not clean_path:
        return data

    parts = clean_path.split(".")
    curr: Any = data

    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
            curr = curr[int(part)]
        else:
            return None

    return curr


def evaluate_assertion(
    assertion: StepAssertion,
    status_code: int | None,
    headers: dict[str, str],
    json_body: Any,
    raw_text: str,
    latency_ms: float,
) -> AssertionResult:
    """Evaluates a single StepAssertion against HTTP response data."""
    op = assertion.operator.lower()
    expected = assertion.expected

    # 1. STATUS_CODE
    if assertion.assertion_type == AssertionType.STATUS_CODE:
        actual = status_code
        if isinstance(expected, list):
            passed = actual in expected
        elif op == "eq" or op == "in":
            passed = actual == expected or (isinstance(expected, (list, tuple, set)) and actual in expected)
        elif op == "ne":
            passed = actual != expected
        else:
            passed = actual == expected

        msg = (
            assertion.message
            if assertion.message and not passed
            else (f"Status {actual} {'matched' if passed else 'did not match'} expected {expected}")
        )
        return AssertionResult(
            assertion_type=AssertionType.STATUS_CODE,
            passed=passed,
            target="status_code",
            expected=expected,
            actual=actual,
            message=msg if not passed else None,
        )

    # 2. RESPONSE_TIME_MS
    elif assertion.assertion_type == AssertionType.RESPONSE_TIME_MS:
        actual = latency_ms
        if op == "lte" or op == "lt":
            passed = actual <= expected
        else:
            passed = actual <= expected

        msg = f"Response time {actual:.1f}ms exceeds threshold {expected}ms"
        return AssertionResult(
            assertion_type=AssertionType.RESPONSE_TIME_MS,
            passed=passed,
            target="latency_ms",
            expected=expected,
            actual=round(actual, 2),
            message=msg if not passed else None,
        )

    # 3. JSON_SCHEMA
    elif assertion.assertion_type == AssertionType.JSON_SCHEMA:
        actual = json_body
        if not isinstance(expected, dict):
            return AssertionResult(
                assertion_type=AssertionType.JSON_SCHEMA,
                passed=False,
                expected=expected,
                actual=actual,
                message="Expected schema is not a valid dictionary.",
            )
        try:
            jsonschema.validate(instance=json_body, schema=expected)
            passed = True
            msg = None
        except jsonschema.ValidationError as err:
            passed = False
            msg = f"JSON Schema Validation Error: {err.message} at path '{'.'.join(str(p) for p in err.path)}'"
        except Exception as ex:
            passed = False
            msg = f"Schema validation failed with error: {ex}"

        return AssertionResult(
            assertion_type=AssertionType.JSON_SCHEMA,
            passed=passed,
            target="json_schema",
            expected="JSONSchema validation",
            actual="Schema error" if not passed else "Schema valid",
            message=msg,
        )

    # 4. JSON_PATH_EQUALS / JSON_PATH_EXISTS / JSON_PATH_CONTAINS
    elif assertion.assertion_type in (
        AssertionType.JSON_PATH_EQUALS,
        AssertionType.JSON_PATH_EXISTS,
        AssertionType.JSON_PATH_CONTAINS,
    ):
        target_path = assertion.target or "$"
        actual_val = extract_json_path(json_body, target_path)

        if assertion.assertion_type == AssertionType.JSON_PATH_EXISTS:
            passed = actual_val is not None
            msg = f"Expected JSON path '{target_path}' to exist, but was not found."
        elif assertion.assertion_type == AssertionType.JSON_PATH_CONTAINS:
            passed = actual_val is not None and str(expected) in str(actual_val)
            msg = f"Expected '{target_path}' ({actual_val}) to contain '{expected}'"
        else:
            if op == "eq":
                passed = actual_val == expected
            elif op == "ne":
                passed = actual_val != expected
            elif op == "contains":
                passed = actual_val is not None and str(expected) in str(actual_val)
            else:
                passed = actual_val == expected
            msg = f"Expected '{target_path}' to equal '{expected}', got '{actual_val}'"

        return AssertionResult(
            assertion_type=assertion.assertion_type,
            passed=passed,
            target=target_path,
            expected=expected,
            actual=actual_val,
            message=msg if not passed else None,
        )

    # 5. BODY_CONTAINS
    elif assertion.assertion_type == AssertionType.BODY_CONTAINS:
        passed = str(expected) in raw_text
        msg = f"Expected response body to contain '{expected}'"
        return AssertionResult(
            assertion_type=AssertionType.BODY_CONTAINS,
            passed=passed,
            target="body",
            expected=expected,
            actual=raw_text[:200] if len(raw_text) > 200 else raw_text,
            message=msg if not passed else None,
        )

    # 6. HEADER_EQUALS / HEADER_CONTAINS
    elif assertion.assertion_type in (AssertionType.HEADER_EQUALS, AssertionType.HEADER_CONTAINS):
        h_name = (assertion.target or "").lower()
        actual_h = headers.get(h_name, "")
        if assertion.assertion_type == AssertionType.HEADER_CONTAINS:
            passed = str(expected).lower() in actual_h.lower()
            msg = f"Header '{h_name}' ({actual_h}) did not contain '{expected}'"
        else:
            passed = actual_h.lower() == str(expected).lower()
            msg = f"Header '{h_name}' was '{actual_h}', expected '{expected}'"

        return AssertionResult(
            assertion_type=assertion.assertion_type,
            passed=passed,
            target=h_name,
            expected=expected,
            actual=actual_h,
            message=msg if not passed else None,
        )

    # Fallback
    return AssertionResult(
        assertion_type=assertion.assertion_type,
        passed=True,
        target=assertion.target,
        expected=expected,
        actual="N/A",
    )

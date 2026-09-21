from __future__ import annotations

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
        actual_code = status_code
        if isinstance(expected, list):
            passed = actual_code in expected
        elif op == "eq" or op == "in":
            passed = actual_code == expected or (
                isinstance(expected, (list, tuple, set)) and actual_code in expected
            )
        elif op == "ne":
            passed = actual_code != expected
        else:
            passed = actual_code == expected

        msg = (
            assertion.message
            if assertion.message and not passed
            else (
                f"Status {actual_code} {'matched' if passed else 'did not match'} expected {expected}"
            )
        )
        return AssertionResult(
            assertion_type=AssertionType.STATUS_CODE,
            passed=passed,
            target="status_code",
            expected=expected,
            actual=actual_code,
            message=msg if not passed else None,
        )

    # 2. RESPONSE_TIME_MS
    elif assertion.assertion_type == AssertionType.RESPONSE_TIME_MS:
        actual_lat = latency_ms
        if op in ("lte", "lt"):
            passed = actual_lat <= expected
        else:
            passed = actual_lat <= expected

        msg = (
            assertion.message
            if assertion.message and not passed
            else f"Response time {actual_lat:.1f}ms exceeds threshold {expected}ms"
        )
        return AssertionResult(
            assertion_type=AssertionType.RESPONSE_TIME_MS,
            passed=passed,
            target="latency_ms",
            expected=expected,
            actual=round(actual_lat, 2),
            message=msg if not passed else None,
        )

    # 3. JSON_SCHEMA
    elif assertion.assertion_type == AssertionType.JSON_SCHEMA:
        actual_body = json_body
        if not isinstance(expected, dict):
            return AssertionResult(
                assertion_type=AssertionType.JSON_SCHEMA,
                passed=False,
                expected=expected,
                actual=actual_body,
                message=assertion.message or "Expected schema is not a valid dictionary.",
            )
        try:
            jsonschema.validate(instance=json_body, schema=expected)
            passed = True
            msg = None
        except jsonschema.ValidationError as err:
            passed = False
            msg = (
                assertion.message
                if assertion.message
                else f"JSON Schema Validation Error: {err.message} at path '{'.'.join(str(p) for p in err.path)}'"
            )
        except Exception as ex:
            passed = False
            msg = (
                assertion.message
                if assertion.message
                else f"Schema validation failed with error: {ex}"
            )

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
            default_msg = f"Expected JSON path '{target_path}' to exist, but was not found."
        elif assertion.assertion_type == AssertionType.JSON_PATH_CONTAINS:
            passed = actual_val is not None and str(expected) in str(actual_val)
            default_msg = f"Expected '{target_path}' ({actual_val}) to contain '{expected}'"
        else:
            if op == "eq":
                passed = actual_val == expected
            elif op == "ne":
                passed = actual_val != expected
            elif op == "contains":
                passed = actual_val is not None and str(expected) in str(actual_val)
            else:
                passed = actual_val == expected
            default_msg = f"Expected '{target_path}' to equal '{expected}', got '{actual_val}'"

        msg = assertion.message if assertion.message and not passed else default_msg
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
        msg = (
            assertion.message
            if assertion.message and not passed
            else f"Expected response body to contain '{expected}'"
        )
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
            default_msg = f"Header '{h_name}' ({actual_h}) did not contain '{expected}'"
        else:
            passed = actual_h.lower() == str(expected).lower()
            default_msg = f"Header '{h_name}' was '{actual_h}', expected '{expected}'"

        msg = assertion.message if assertion.message and not passed else default_msg
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

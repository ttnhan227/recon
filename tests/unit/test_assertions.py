import pytest
from recon.common.models import AssertionType, StepAssertion
from recon.execution.api.assertions import evaluate_assertion, extract_json_path


def test_extract_json_path():
    data = {
        "user": {
            "id": 42,
            "profile": {"email": "test@example.com"},
            "roles": ["admin", "editor"],
        }
    }
    assert extract_json_path(data, "user.id") == 42
    assert extract_json_path(data, "$.user.profile.email") == "test@example.com"
    assert extract_json_path(data, "user.roles.0") == "admin"
    assert extract_json_path(data, "non.existent") is None


def test_status_code_assertion():
    a = StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=200, operator="eq")
    res = evaluate_assertion(a, status_code=200, headers={}, json_body={}, raw_text="", latency_ms=10.0)
    assert res.passed is True

    res_fail = evaluate_assertion(a, status_code=500, headers={}, json_body={}, raw_text="", latency_ms=10.0)
    assert res_fail.passed is False


def test_json_schema_assertion():
    schema = {
        "type": "object",
        "required": ["id", "status"],
        "properties": {
            "id": {"type": "integer"},
            "status": {"type": "string"},
        },
    }
    a = StepAssertion(assertion_type=AssertionType.JSON_SCHEMA, expected=schema, operator="validates")

    # Valid
    res_ok = evaluate_assertion(a, 200, {}, {"id": 1, "status": "active"}, "", 10.0)
    assert res_ok.passed is True

    # Invalid (missing status)
    res_bad = evaluate_assertion(a, 200, {}, {"id": 1}, "", 10.0)
    assert res_bad.passed is False
    assert "status" in (res_bad.message or "")

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
    res = evaluate_assertion(
        a, status_code=200, headers={}, json_body={}, raw_text="", latency_ms=10.0
    )
    assert res.passed is True

    res_fail = evaluate_assertion(
        a, status_code=500, headers={}, json_body={}, raw_text="", latency_ms=10.0
    )
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
    a = StepAssertion(
        assertion_type=AssertionType.JSON_SCHEMA, expected=schema, operator="validates"
    )

    # Valid
    res_ok = evaluate_assertion(a, 200, {}, {"id": 1, "status": "active"}, "", 10.0)
    assert res_ok.passed is True

    # Invalid (missing status)
    res_bad = evaluate_assertion(a, 200, {}, {"id": 1}, "", 10.0)
    assert res_bad.passed is False
    assert "status" in (res_bad.message or "")


def test_extract_json_path_removeprefix():
    data = {"$id": 123, "meta": {"ok": True}}
    assert extract_json_path(data, "$id") == 123
    assert extract_json_path(data, "$.meta.ok") is True


def test_response_time_ms_operators():
    lt = StepAssertion(assertion_type=AssertionType.RESPONSE_TIME_MS, expected=100, operator="lt")
    assert evaluate_assertion(lt, 200, {}, {}, "", 99.0).passed is True
    assert evaluate_assertion(lt, 200, {}, {}, "", 100.0).passed is False

    gt = StepAssertion(assertion_type=AssertionType.RESPONSE_TIME_MS, expected=100, operator="gt")
    assert evaluate_assertion(gt, 200, {}, {}, "", 101.0).passed is True
    assert evaluate_assertion(gt, 200, {}, {}, "", 100.0).passed is False

    gte = StepAssertion(assertion_type=AssertionType.RESPONSE_TIME_MS, expected=100, operator="gte")
    assert evaluate_assertion(gte, 200, {}, {}, "", 100.0).passed is True
    assert evaluate_assertion(gte, 200, {}, {}, "", 99.9).passed is False

from recon.common.models import (
    AssertionType,
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStep,
    TestType,
)


def test_test_case_creation_and_serialization():
    step = TestStep(
        name="Get User Profile",
        step_type="http_request",
        endpoint="http://localhost:8000/api/users/1",
        method="GET",
        assertions=[
            StepAssertion(
                assertion_type=AssertionType.STATUS_CODE,
                expected=200,
                operator="eq",
            )
        ],
    )
    tc = TestCase(
        id="API-001",
        name="Verify user profile returns 200",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
        target="http://localhost:8000/api/users/1",
        method="GET",
        steps=[step],
        tags=["api", "users"],
    )

    data = tc.model_dump(mode="json")
    assert data["id"] == "API-001"
    assert data["category"] == "HAPPY_PATH"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["assertions"][0]["expected"] == 200

    recreated = TestCase.model_validate(data)
    assert recreated.id == tc.id
    assert recreated.category == TestCategory.HAPPY_PATH


def test_failure_evidence_model():
    trace = HTTPTrace(
        request_method="POST",
        request_url="http://localhost:8000/api/orders",
        response_status=500,
        response_body={"error": "NullReferenceException"},
        latency_ms=45.2,
    )
    evidence = FailureEvidence(
        failure_category=FailureCategory.APPLICATION_ERROR,
        message="Server crashed with 500",
        http_traces=[trace],
    )
    assert evidence.failure_category == FailureCategory.APPLICATION_ERROR
    assert len(evidence.http_traces) == 1
    assert evidence.http_traces[0].response_status == 500

import pytest
from recon.analysis.classifier import DeterministicFailureClassifier
from recon.common.models import (
    AssertionResult,
    AssertionType,
    ConsoleLog,
    FailureCategory,
    FailureEvidence,
    HTTPTrace,
    StepResult,
    TestCase,
    TestCategory,
    TestResult,
    TestStatus,
    TestType,
)


def test_classify_500_application_error():
    trace = HTTPTrace(
        request_method="POST",
        request_url="http://localhost:8000/api/orders",
        response_status=500,
        response_body={"error": "NullReferenceException: payment.currency is null"},
    )
    result = TestResult(
        test_id="API-001",
        test_name="Create Order",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
        status=TestStatus.FAILED,
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.UNKNOWN,
            message="Internal Server Error",
            http_traces=[trace],
        ),
    )
    classified = DeterministicFailureClassifier.classify(result)
    assert classified == FailureCategory.APPLICATION_ERROR


def test_classify_401_authentication_failure():
    trace = HTTPTrace(
        request_method="GET",
        request_url="http://localhost:8000/api/admin/secrets",
        response_status=401,
        response_body={"detail": "Not authenticated"},
    )
    result = TestResult(
        test_id="API-002",
        test_name="Admin Secrets",
        category=TestCategory.AUTHENTICATION,
        test_type=TestType.API,
        status=TestStatus.FAILED,
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.UNKNOWN,
            message="Status mismatch",
            http_traces=[trace],
        ),
    )
    classified = DeterministicFailureClassifier.classify(result)
    assert classified == FailureCategory.AUTHENTICATION_FAILURE


def test_classify_javascript_console_error():
    result = TestResult(
        test_id="UI-001",
        test_name="Login Click",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.BROWSER,
        status=TestStatus.FAILED,
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.UNKNOWN,
            message="Uncaught JS error",
            console_errors=[
                ConsoleLog(level="error", text="Uncaught TypeError: Cannot read properties of undefined (reading 'token')")
            ],
        ),
    )
    classified = DeterministicFailureClassifier.classify(result)
    assert classified == FailureCategory.APPLICATION_ERROR


def test_classify_timeout():
    result = TestResult(
        test_id="API-003",
        test_name="Slow Analytics",
        category=TestCategory.HAPPY_PATH,
        test_type=TestType.API,
        status=TestStatus.FAILED,
        failure_evidence=FailureEvidence(
            failure_category=FailureCategory.UNKNOWN,
            message="HTTP request timed out after 5.0s",
        ),
    )
    classified = DeterministicFailureClassifier.classify(result)
    assert classified == FailureCategory.TIMEOUT

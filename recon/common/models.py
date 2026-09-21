from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TestCategory(str, Enum):
    __test__ = False
    HAPPY_PATH = "HAPPY_PATH"
    VALIDATION = "VALIDATION"
    BOUNDARY = "BOUNDARY"
    NEGATIVE = "NEGATIVE"
    AUTHENTICATION = "AUTHENTICATION"
    AUTHORIZATION = "AUTHORIZATION"
    ERROR_HANDLING = "ERROR_HANDLING"
    REGRESSION = "REGRESSION"
    SECURITY = "SECURITY"
    EXPLORATORY = "EXPLORATORY"


class TestType(str, Enum):
    __test__ = False
    API = "API"
    BROWSER = "BROWSER"


class FailureCategory(str, Enum):
    ASSERTION_FAILURE = "ASSERTION_FAILURE"
    HTTP_ERROR = "HTTP_ERROR"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    BROWSER_ERROR = "BROWSER_ERROR"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    AUTHORIZATION_FAILURE = "AUTHORIZATION_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    APPLICATION_ERROR = "APPLICATION_ERROR"
    TEST_CONFIGURATION_ERROR = "TEST_CONFIGURATION_ERROR"
    INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
    UNKNOWN = "UNKNOWN"


class TestStatus(str, Enum):
    __test__ = False
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class AssertionType(str, Enum):
    STATUS_CODE = "STATUS_CODE"
    HEADER_EQUALS = "HEADER_EQUALS"
    HEADER_CONTAINS = "HEADER_CONTAINS"
    JSON_PATH_EQUALS = "JSON_PATH_EQUALS"
    JSON_PATH_CONTAINS = "JSON_PATH_CONTAINS"
    JSON_PATH_EXISTS = "JSON_PATH_EXISTS"
    JSON_SCHEMA = "JSON_SCHEMA"
    RESPONSE_TIME_MS = "RESPONSE_TIME_MS"
    BODY_CONTAINS = "BODY_CONTAINS"
    TEXT_VISIBLE = "TEXT_VISIBLE"
    ELEMENT_EXISTS = "ELEMENT_EXISTS"
    URL_MATCHES = "URL_MATCHES"


class StepAssertion(BaseModel):
    assertion_type: AssertionType
    target: str | None = None
    expected: Any = None
    operator: str = "eq"  # eq, ne, lt, lte, gt, gte, contains, regex, exists, not_exists
    message: str | None = None


class TestStep(BaseModel):
    __test__ = False
    name: str
    step_type: str = "http_request"  # http_request, browser_navigate, browser_click, browser_fill, browser_screenshot, browser_wait
    endpoint: str | None = None
    method: str | None = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    body: Any | None = None
    selector: str | None = None
    value: str | None = None
    timeout_seconds: float = 10.0
    assertions: list[StepAssertion] = Field(default_factory=list)


class TestCase(BaseModel):
    __test__ = False
    id: str
    name: str
    description: str | None = None
    category: TestCategory = TestCategory.HAPPY_PATH
    test_type: TestType = TestType.API
    target: str
    method: str | None = None
    steps: list[TestStep] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    timeout_seconds: float = 30.0
    retries: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class HTTPTrace(BaseModel):
    request_method: str
    request_url: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: Any | None = None
    response_status: int | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    response_body: Any | None = None
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsoleLog(BaseModel):
    level: str  # error, warning, info, log
    text: str
    location: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NetworkError(BaseModel):
    url: str
    method: str = "GET"
    error_text: str
    status_code: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScreenshotEvidence(BaseModel):
    name: str
    file_path: str
    step_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssertionResult(BaseModel):
    assertion_type: AssertionType
    passed: bool
    target: str | None = None
    expected: Any = None
    actual: Any = None
    message: str | None = None


class StepResult(BaseModel):
    step_name: str
    status: TestStatus
    duration_ms: float = 0.0
    assertion_results: list[AssertionResult] = Field(default_factory=list)
    error_message: str | None = None
    http_trace: HTTPTrace | None = None


class FailureEvidence(BaseModel):
    failure_category: FailureCategory
    message: str
    failed_step: str | None = None
    http_traces: list[HTTPTrace] = Field(default_factory=list)
    console_errors: list[ConsoleLog] = Field(default_factory=list)
    network_errors: list[NetworkError] = Field(default_factory=list)
    screenshots: list[ScreenshotEvidence] = Field(default_factory=list)
    stack_trace: str | None = None
    system_logs: list[str] = Field(default_factory=list)


class Hypothesis(BaseModel):
    hypothesis: str
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str


class FailureAnalysis(BaseModel):
    observed_facts: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    suggested_fix: str | None = None
    suggested_regression_test: TestCase | None = None
    confidence_score: float = 0.0
    raw_llm_response: str | None = None


class TestResult(BaseModel):
    __test__ = False
    test_id: str
    test_name: str
    category: TestCategory
    test_type: TestType
    status: TestStatus
    duration_ms: float = 0.0
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    step_results: list[StepResult] = Field(default_factory=list)
    failure_evidence: FailureEvidence | None = None
    failure_analysis: FailureAnalysis | None = None
    retries_attempted: int = 0


class RunSummary(BaseModel):
    run_id: str
    target_url: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    failure_breakdown: dict[str, int] = Field(default_factory=dict)
    category_breakdown: dict[str, dict[str, int]] = Field(default_factory=dict)
    exit_code: int = 0

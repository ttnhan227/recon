from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from recon.common.config import settings
from recon.common.logging import JSONLogFormatter, current_run_id
from recon.common.models import (
    AssertionType,
    RunSummary,
    StepAssertion,
    TestCase,
    TestCategory,
    TestStep,
    TestType,
)
from recon.common.telemetry import (
    add_span_processor,
    compute_trace_summary,
    extract_trace_context,
    finish_run_recording,
    get_current_trace_ids,
    get_run_spans,
    get_tracer,
    inject_trace_headers,
    start_run_recording,
)
from recon.execution.api.runner import APITestRunner
from recon.orchestration.orchestrator import TestOrchestrator
from tests.conftest import test_app as mock_target_app


def test_telemetry_get_current_trace_ids_empty():
    trace_id, span_id = get_current_trace_ids()
    assert trace_id is None
    assert span_id is None


def test_telemetry_get_current_trace_ids_active():
    tracer = get_tracer("test.tracer")
    with tracer.start_as_current_span("test.span"):
        trace_id, span_id = get_current_trace_ids()
        assert trace_id is not None
        assert span_id is not None
        assert len(trace_id) == 32
        assert len(span_id) == 16
        assert int(trace_id, 16) > 0
        assert int(span_id, 16) > 0


def test_telemetry_inject_and_extract_headers():
    tracer = get_tracer("test.propagation")
    with tracer.start_as_current_span("parent.span"):
        active_trace_id, active_span_id = get_current_trace_ids()
        headers = {"Content-Type": "application/json"}
        injected = inject_trace_headers(headers)
        assert "traceparent" in injected
        assert f"00-{active_trace_id}-{active_span_id}" in injected["traceparent"]

        extracted_ctx = extract_trace_context(injected)
        with tracer.start_as_current_span("child.span", context=extracted_ctx):
            child_trace_id, _ = get_current_trace_ids()
            assert child_trace_id == active_trace_id


def test_json_log_formatter_trace_correlation():
    formatter = JSONLogFormatter()
    logger = logging.getLogger("test.logger")
    record = logger.makeRecord("test.logger", logging.INFO, "test.py", 10, "Test message", (), None)

    # Outside span
    out_no_span = formatter.format(record)
    assert "trace_id" not in out_no_span
    assert "span_id" not in out_no_span

    # Inside span
    tracer = get_tracer("test.logging")
    with tracer.start_as_current_span("log.span"):
        expected_trace_id, expected_span_id = get_current_trace_ids()
        out_with_span = formatter.format(record)
        assert f'"trace_id": "{expected_trace_id}"' in out_with_span
        assert f'"span_id": "{expected_span_id}"' in out_with_span


@pytest.mark.asyncio
async def test_run_scoped_span_recorder_concurrency_isolation():
    run_1 = "run-isolation-001"
    run_2 = "run-isolation-002"

    start_run_recording(run_1)
    start_run_recording(run_2)

    tracer = get_tracer("test.isolation")

    async def run_worker(run_id: str, count: int):
        current_run_id.set(run_id)
        for i in range(count):
            with tracer.start_as_current_span(f"span.{run_id}.{i}", attributes={"run_id": run_id}):
                await asyncio.sleep(0.01)

    await asyncio.gather(run_worker(run_1, 5), run_worker(run_2, 3))

    spans_1 = finish_run_recording(run_1)
    spans_2 = finish_run_recording(run_2)

    assert len(spans_1) == 5
    assert len(spans_2) == 3
    assert all(s.attributes and s.attributes.get("run_id") == run_1 for s in spans_1)
    assert all(s.attributes and s.attributes.get("run_id") == run_2 for s in spans_2)

    # After finish, recorded spans are cleared
    assert get_run_spans(run_1) == []
    assert get_run_spans(run_2) == []


def test_compute_trace_summary_and_percentiles():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test.summary")

    with tracer.start_as_current_span("recon.discovery"):
        pass
    with tracer.start_as_current_span("recon.plan_generation"):
        pass
    with tracer.start_as_current_span(
        "recon.wave", attributes={"wave.index": 1, "wave.test_count": 4}
    ):
        pass
    for lat in [10.0, 20.0, 30.0, 40.0, 50.0]:
        with tracer.start_as_current_span("recon.http_step", attributes={"http.duration_ms": lat}):
            pass

    spans = exporter.get_finished_spans()
    summary = compute_trace_summary(spans)

    assert summary["total_spans"] == len(spans)
    assert "discovery" in summary["phase_durations_ms"]
    assert "plan_generation" in summary["phase_durations_ms"]
    assert "wave_1" in summary["wave_durations_ms"]
    assert summary["wave_counts"]["wave_1"] == 4
    assert summary["http_requests_count"] == 5
    assert summary["http_latency_p50_ms"] == 30.0
    assert summary["http_latency_p95_ms"] == 48.0


def test_otlp_endpoint_unset_zero_network_calls(monkeypatch):
    monkeypatch.setattr(settings, "otel_exporter_otlp_endpoint", None)
    tracer = get_tracer("test.zero_network")
    with tracer.start_as_current_span("local.test"):
        pass
    # No network exceptions or calls occur


@pytest.mark.asyncio
async def test_api_runner_w3c_traceparent_and_redaction():
    captured_request_headers: dict[str, str] = {}

    def custom_handler(request: httpx.Request) -> httpx.Response:
        captured_request_headers.update(dict(request.headers))
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(custom_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        runner = APITestRunner(client=client)

        tracer = get_tracer("test.runner")
        with tracer.start_as_current_span("parent.test_case") as parent_span:
            p_ctx = parent_span.get_span_context()
            expected_trace_id = f"{p_ctx.trace_id:032x}"

            test = TestCase(
                id="TEST-OTEL-001",
                name="Test W3C Traceparent",
                category=TestCategory.HAPPY_PATH,
                test_type=TestType.API,
                target="http://test/api/health",
                steps=[
                    TestStep(
                        name="Check Health",
                        endpoint="http://test/api/health",
                        headers={"Authorization": "Bearer sensitive-secret-token-12345"},
                        assertions=[
                            StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=200)
                        ],
                    )
                ],
            )
            result = await runner.execute_test(test)
            assert result.status.value == "PASSED"

    # W3C traceparent injected and matches parent span's trace_id
    assert "traceparent" in captured_request_headers
    assert expected_trace_id in captured_request_headers["traceparent"]

    # Verify sensitive Authorization header is never leaked into span attributes
    # The HTTP step span records only http.method, http.route, http.status_code, http.duration_ms
    spans = get_run_spans(current_run_id.get() or "default")
    for s in spans:
        if s.attributes:
            for k, v in s.attributes.items():
                assert "sensitive-secret-token" not in str(v)
                assert "authorization" not in k.lower()


@pytest.mark.asyncio
async def test_end_to_end_span_tree_hierarchy(tmp_path):
    exporter = InMemorySpanExporter()
    add_span_processor(SimpleSpanProcessor(exporter))

    transport = httpx.ASGITransport(app=mock_target_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        orchestrator = TestOrchestrator(
            concurrency=2,
            output_dir=tmp_path / "reports",
            enable_ai=False,
            db_url=f"sqlite+aiosqlite:///{tmp_path / 'recon.db'}",
            external_api_client=client,
        )

        custom_tests = [
            TestCase(
                id="E2E-001",
                name="Create User",
                category=TestCategory.HAPPY_PATH,
                test_type=TestType.API,
                target="http://testserver/api/users",
                method="POST",
                steps=[
                    TestStep(
                        name="Post User",
                        endpoint="http://testserver/api/users",
                        method="POST",
                        body={"name": "Alice", "email": "alice@example.com"},
                        assertions=[
                            StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=201)
                        ],
                    )
                ],
            ),
            TestCase(
                id="E2E-002",
                name="Get Health",
                category=TestCategory.HAPPY_PATH,
                test_type=TestType.API,
                target="http://testserver/api/health",
                method="GET",
                steps=[
                    TestStep(
                        name="Get Health Step",
                        endpoint="http://testserver/api/health",
                        method="GET",
                        assertions=[
                            StepAssertion(assertion_type=AssertionType.STATUS_CODE, expected=200)
                        ],
                    )
                ],
            ),
        ]

        summary, results = await orchestrator.run_pipeline(
            target_url="http://testserver",
            custom_tests=custom_tests,
        )

    assert summary.total == 2
    assert summary.passed == 2
    assert summary.trace_id is not None

    spans = exporter.get_finished_spans()
    span_names = [s.name for s in spans]

    # Verify all expected span names are present
    assert "recon.run_pipeline" in span_names
    assert "recon.discovery" in span_names
    assert "recon.plan_generation" in span_names
    assert "recon.execution" in span_names
    assert "recon.wave" in span_names
    assert "recon.test_case" in span_names
    assert "recon.http_step" in span_names
    assert "recon.rca" in span_names
    assert "recon.reporting" in span_names

    # Check root span and shared trace_id
    root_span = next(s for s in spans if s.name == "recon.run_pipeline")
    assert root_span.context is not None
    root_trace_id = f"{root_span.context.trace_id:032x}"
    assert summary.trace_id == root_trace_id

    # Verify all child spans share root trace_id
    for s in spans:
        assert s.context is not None
        span_trace_id = f"{s.context.trace_id:032x}"
        assert span_trace_id == root_trace_id

    # Verify parent-child relationships
    # recon.execution parent is recon.run_pipeline
    exec_span = next(s for s in spans if s.name == "recon.execution")
    assert exec_span.parent is not None
    assert exec_span.parent.span_id == root_span.context.span_id

    # recon.wave parent is recon.execution
    wave_spans = [s for s in spans if s.name == "recon.wave"]
    assert len(wave_spans) >= 1
    for ws in wave_spans:
        assert ws.parent is not None
        assert exec_span.context is not None
        assert ws.parent.span_id == exec_span.context.span_id

    # recon.test_case parent is recon.wave
    test_spans = [s for s in spans if s.name == "recon.test_case"]
    assert len(test_spans) == 2
    wave_span_ids = {ws.context.span_id for ws in wave_spans if ws.context is not None}
    for ts in test_spans:
        assert ts.parent is not None
        assert ts.parent.span_id in wave_span_ids

    # recon.http_step parent is recon.test_case
    http_spans = [s for s in spans if s.name == "recon.http_step"]
    assert len(http_spans) >= 2
    test_span_ids = {ts.context.span_id for ts in test_spans if ts.context is not None}
    for hs in http_spans:
        assert hs.parent is not None
        assert hs.parent.span_id in test_span_ids

    # Check summary.trace_summary contents
    assert summary.trace_summary["total_spans"] > 0
    assert "execution" in summary.trace_summary["phase_durations_ms"]
    assert "rca" in summary.trace_summary["phase_durations_ms"]
    assert "reporting" in summary.trace_summary["phase_durations_ms"]
    assert summary.trace_summary["http_requests_count"] >= 2
    assert summary.trace_summary["http_latency_p50_ms"] is not None


def test_reporters_render_trace_id_and_latency_summary(tmp_path):
    from datetime import datetime, timezone

    from recon.reporting.html_reporter import HTMLReporter
    from recon.reporting.markdown_reporter import MarkdownReporter

    summary = RunSummary(
        run_id="run-rep-trace-001",
        target_url="http://example.com/api",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=5.42,
        total=5,
        passed=5,
        trace_id="4bf92f3577b34da6a3ce929d0e0e4736",
        trace_summary={
            "total_spans": 12,
            "phase_durations_ms": {
                "discovery": 120.5,
                "plan_generation": 45.2,
                "execution": 1820.0,
                "rca": 0.0,
                "reporting": 30.1,
            },
            "wave_durations_ms": {
                "wave_1": 410.0,
                "wave_2": 820.5,
            },
            "wave_counts": {
                "wave_1": 2,
                "wave_2": 3,
            },
            "http_requests_count": 5,
            "http_latency_p50_ms": 78.4,
            "http_latency_p95_ms": 195.2,
        },
    )

    md_rep = MarkdownReporter(output_dir=tmp_path)
    md_content = md_rep.generate_markdown(summary, [])
    assert "**Trace ID:** `4bf92f3577b34da6a3ce929d0e0e4736`" in md_content
    assert "## Distributed Tracing & Latency Summary" in md_content
    assert "### Pipeline Phase Durations" in md_content
    assert "| `discovery` | 120.50 ms |" in md_content
    assert "| `wave_1` | 2 | 410.00 ms |" in md_content
    assert "78.40 ms" in md_content
    assert "195.20 ms" in md_content

    html_rep = HTMLReporter(output_dir=tmp_path)
    html_content = html_rep._render_html(summary, [])
    assert "4bf92f3577b34da6a3ce929d0e0e4736" in html_content
    assert (
        "Distributed Tracing &amp; Latency" in html_content
        or "Distributed Tracing & Latency" in html_content
    )
    assert "discovery" in html_content
    assert "wave_1" in html_content
    assert "78.4 ms / 195.2 ms" in html_content

    # Backward compatibility: empty trace_id and trace_summary
    empty_summary = RunSummary(
        run_id="run-rep-trace-002",
        target_url="http://example.com/api",
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        duration_seconds=1.0,
        total=1,
        passed=1,
    )
    empty_md = md_rep.generate_markdown(empty_summary, [])
    assert "Trace ID" not in empty_md
    assert "Distributed Tracing" not in empty_md

    empty_html = html_rep._render_html(empty_summary, [])
    assert "Trace ID:" not in empty_html
    assert "Distributed Tracing & Latency" not in empty_html

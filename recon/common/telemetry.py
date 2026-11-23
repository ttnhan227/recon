from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from typing import Any, Mapping, Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.trace import Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from recon.common.config import settings

logger = logging.getLogger("recon.telemetry")

_propagator = TraceContextTextMapPropagator()


class RunScopedSpanProcessor(SpanProcessor):
    """Thread-safe and async-safe in-memory span recorder keyed by run_id with strict memory bounds."""

    def __init__(self, max_runs: int = 200, max_spans_per_run: int = 10000):
        self._lock = threading.Lock()
        self._run_spans: OrderedDict[str, list[ReadableSpan]] = OrderedDict()
        self._active_runs: set[str] = set()
        self._max_runs = max_runs
        self._max_spans_per_run = max_spans_per_run

    def start_run(self, run_id: str) -> None:
        """Explicitly starts recording spans for a specific run_id."""
        with self._lock:
            self._active_runs.add(run_id)
            if run_id not in self._run_spans:
                self._run_spans[run_id] = []
            # Evict oldest inactive runs if capacity exceeded
            while len(self._run_spans) > self._max_runs:
                evicted_key, _ = self._run_spans.popitem(last=False)
                self._active_runs.discard(evicted_key)

    def get_run_spans(self, run_id: str) -> list[ReadableSpan]:
        """Returns a snapshot of recorded spans for a run_id without removing them."""
        with self._lock:
            return list(self._run_spans.get(run_id, []))

    def finish_run(self, run_id: str) -> list[ReadableSpan]:
        """Finalizes run recording, pops recorded spans to avoid memory leaks, and returns them."""
        with self._lock:
            self._active_runs.discard(run_id)
            return self._run_spans.pop(run_id, [])

    def on_start(self, span: Any, parent_context: Context | None = None) -> None:
        pass

    def on_end(self, span: ReadableSpan) -> None:
        # Determine run_id from span attributes or ambient context
        run_id: str | None = None
        if span.attributes and "run_id" in span.attributes:
            run_id = str(span.attributes["run_id"])
        if not run_id:
            try:
                from recon.common.logging import current_run_id

                run_id = current_run_id.get()
            except Exception:
                run_id = None

        if not run_id:
            return

        with self._lock:
            # If run was registered or capacity allows, record span
            if run_id in self._active_runs or len(self._run_spans) < self._max_runs:
                spans = self._run_spans.setdefault(run_id, [])
                if len(spans) < self._max_spans_per_run:
                    spans.append(span)

    def shutdown(self) -> None:
        with self._lock:
            self._run_spans.clear()
            self._active_runs.clear()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_global_lock = threading.Lock()
_tracer_provider: TracerProvider | None = None
_run_span_processor: RunScopedSpanProcessor | None = None


def init_telemetry(force_reinit: bool = False) -> TracerProvider:
    """Configures OpenTelemetry TracerProvider, OTLP exporter (if configured), and per-run recorder."""
    global _tracer_provider, _run_span_processor

    with _global_lock:
        if _tracer_provider is not None and not force_reinit:
            return _tracer_provider

        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": settings.version,
            }
        )

        provider = TracerProvider(resource=resource)
        processor = RunScopedSpanProcessor()
        provider.add_span_processor(processor)

        # Opt-in OTLP HTTP export (zero network calls if endpoint is None/empty)
        otlp_endpoint = settings.otel_exporter_otlp_endpoint
        if otlp_endpoint and otlp_endpoint.strip():
            endpoint_clean = otlp_endpoint.strip()
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                otlp_exporter = OTLPSpanExporter(endpoint=endpoint_clean)
                provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
                logger.info(f"OpenTelemetry OTLP exporter enabled: {endpoint_clean}")
            except ImportError:
                logger.warning(
                    "OTEL_EXPORTER_OTLP_ENDPOINT configured but 'opentelemetry-exporter-otlp-proto-http' is not installed. "
                    "Install with `pip install recon-qa[otel]` to enable remote OTLP export."
                )
            except Exception as ex:
                logger.warning(f"Failed to initialize OTLP exporter for {endpoint_clean}: {ex}")

        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        _run_span_processor = processor
        return provider


def get_tracer_provider() -> TracerProvider:
    """Returns the singleton TracerProvider, initializing it if necessary."""
    global _tracer_provider
    if _tracer_provider is None:
        init_telemetry()
    assert _tracer_provider is not None
    return _tracer_provider


def add_span_processor(processor: SpanProcessor) -> None:
    """Adds a custom SpanProcessor to the active TracerProvider."""
    provider = get_tracer_provider()
    provider.add_span_processor(processor)


def get_tracer(name: str = "recon") -> Tracer:
    """Returns an OpenTelemetry tracer for the requested component."""
    if _tracer_provider is None:
        init_telemetry()
    return trace.get_tracer(name, settings.version)


def get_current_trace_ids() -> tuple[str | None, str | None]:
    """Returns (trace_id_32_hex, span_id_16_hex) for the currently active valid span, or (None, None)."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        ctx = span.get_span_context()
        return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"
    return None, None


def inject_trace_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Injects W3C traceparent (and tracestate) into a copy of headers carrier."""
    carrier = dict(headers or {})
    _propagator.inject(carrier)
    return carrier


def extract_trace_context(headers: Mapping[str, str] | None = None) -> Context:
    """Extracts OpenTelemetry Context from incoming HTTP request headers (case-insensitive)."""
    carrier: dict[str, str] = {}
    if headers:
        for k, v in headers.items():
            carrier[k.lower()] = str(v)
    return _propagator.extract(carrier)


def start_run_recording(run_id: str) -> None:
    """Starts recording spans for the specified run_id."""
    if _run_span_processor is None:
        init_telemetry()
    if _run_span_processor is not None:
        _run_span_processor.start_run(run_id)


def get_run_spans(run_id: str) -> list[ReadableSpan]:
    """Returns recorded spans for the specified run_id."""
    if _run_span_processor is not None:
        return _run_span_processor.get_run_spans(run_id)
    return []


def finish_run_recording(run_id: str) -> list[ReadableSpan]:
    """Finalizes and returns recorded spans for the specified run_id, releasing in-memory references."""
    if _run_span_processor is not None:
        return _run_span_processor.finish_run(run_id)
    return []


def _calc_percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    d = k - f
    return round(s[f] + d * (s[c] - s[f]), 2)


def compute_trace_summary(spans: Sequence[ReadableSpan]) -> dict[str, Any]:
    """Computes per-phase / per-wave latencies, span counts, and HTTP p50/p95 latency metrics."""
    phase_durations_ms: dict[str, float] = {}
    wave_durations_ms: dict[str, float] = {}
    wave_counts: dict[str, int] = {}
    http_latencies: list[float] = []

    phase_names = {
        "recon.discovery",
        "recon.plan_generation",
        "recon.execution",
        "recon.rca",
        "recon.reporting",
    }

    for span in spans:
        duration_ms = 0.0
        if span.start_time and span.end_time:
            duration_ms = round((span.end_time - span.start_time) / 1_000_000.0, 2)

        name = span.name
        if name in phase_names:
            phase_durations_ms[name.removeprefix("recon.")] = duration_ms
        elif name == "recon.wave":
            attrs = span.attributes or {}
            idx = attrs.get("wave.index", 0)
            wave_key = f"wave_{idx}"
            wave_durations_ms[wave_key] = duration_ms
            count = attrs.get("wave.test_count")
            if count is not None:
                try:
                    wave_counts[wave_key] = int(str(count))
                except (ValueError, TypeError):
                    pass
        elif name == "recon.http_step":
            attrs = span.attributes or {}
            lat = attrs.get("http.duration_ms")
            if lat is not None:
                try:
                    http_latencies.append(float(str(lat)))
                except (ValueError, TypeError):
                    http_latencies.append(duration_ms)
            else:
                http_latencies.append(duration_ms)

    p50 = _calc_percentile(http_latencies, 50.0) if http_latencies else None
    p95 = _calc_percentile(http_latencies, 95.0) if http_latencies else None

    return {
        "total_spans": len(spans),
        "phase_durations_ms": phase_durations_ms,
        "wave_durations_ms": wave_durations_ms,
        "wave_counts": wave_counts,
        "http_requests_count": len(http_latencies),
        "http_latency_p50_ms": p50,
        "http_latency_p95_ms": p95,
    }

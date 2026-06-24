"""
Trace and log exporter factories, with a small registry so a project can plug in
its own exporters without modifying otelio.

Two targets ship built in: ``otlp`` (SigNoz / any OTLP-gRPC collector) and
``azure`` (App Insights). Their backend SDKs are imported lazily so a project
only needs the deps for the target it actually uses.

To add your own, pass a factory by name to :func:`otelio.init_otelio` via its
``trace_exporters`` / ``log_exporters`` params, then select it from the
environment — no otelio change needed::

    def build_loki_traces(s: Settings) -> SpanExporter:
        return MyLokiSpanExporter(endpoint=s.otlp_endpoint)

    init_otelio(
        "my-service", "1.0.0",
        trace_exporters=[{"name": "loki", "factory": build_loki_traces}],
        log_exporters=[{"name": "loki", "factory": build_loki_logs}],
    )
    # then: OTELIO_TARGET=loki

See ``docs/custom-exporter.md`` for the full guide.

(The trace exporter's OTel type is ``SpanExporter``; otelio names its own surface
after the *signal* — ``trace`` / ``log`` — to keep the pair consistent.)
"""

from collections.abc import Callable
from typing import TypedDict

from opentelemetry.sdk._logs.export import LogRecordExporter
from opentelemetry.sdk.trace.export import SpanExporter

from .config import Settings

TraceExporterFactory = Callable[[Settings], SpanExporter]
LogExporterFactory = Callable[[Settings], LogRecordExporter]


class TraceExporterEntry(TypedDict):
    """A custom trace exporter to register: ``{"name": ..., "factory": ...}``."""

    name: str
    factory: TraceExporterFactory


class LogExporterEntry(TypedDict):
    """A custom log exporter to register: ``{"name": ..., "factory": ...}``."""

    name: str
    factory: LogExporterFactory


def _otlp_trace(s: Settings) -> SpanExporter:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )

    return OTLPSpanExporter(endpoint=s.otlp_trace_endpoint)


def _azure_trace(s: Settings) -> SpanExporter:
    from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415 (optional dep)
        AzureMonitorTraceExporter,
    )

    return AzureMonitorTraceExporter(connection_string=s.azure_conn_str)


def _otlp_log(s: Settings) -> LogRecordExporter:
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (  # noqa: PLC0415
        OTLPLogExporter,
    )

    return OTLPLogExporter(endpoint=s.otlp_log_endpoint)


def _azure_log(s: Settings) -> LogRecordExporter:
    from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415 (optional dep)
        AzureMonitorLogExporter,
    )

    return AzureMonitorLogExporter(connection_string=s.azure_conn_str)


_TRACE_EXPORTERS: dict[str, TraceExporterFactory] = {"otlp": _otlp_trace, "azure": _azure_trace}
_LOG_EXPORTERS: dict[str, LogExporterFactory] = {"otlp": _otlp_log, "azure": _azure_log}


def _register_trace_exporter(name: str, factory: TraceExporterFactory) -> None:
    """Register (or override) a trace-exporter factory under ``name`` (called by init_otelio)."""
    _TRACE_EXPORTERS[name.lower()] = factory


def _register_log_exporter(name: str, factory: LogExporterFactory) -> None:
    """Register (or override) a log-exporter factory under ``name`` (called by init_otelio)."""
    _LOG_EXPORTERS[name.lower()] = factory


def build_trace_exporter(s: Settings) -> SpanExporter:
    """Return the trace (span) exporter for the configured target."""
    try:
        factory = _TRACE_EXPORTERS[s.trace_target]
    except KeyError:
        raise ValueError(
            f"No trace exporter registered for trace target {s.trace_target!r} "
            f"(OTELIO_TRACE_TARGET / OTELIO_TARGET). "
            f"Known targets: {sorted(_TRACE_EXPORTERS)}. "
            f"Register one by passing trace_exporters=[{{'name': {s.trace_target!r}, ...}}] "
            "to init_otelio."
        ) from None
    return factory(s)


def build_log_exporter(s: Settings) -> LogRecordExporter:
    """Return the log-record exporter for the configured target."""
    try:
        factory = _LOG_EXPORTERS[s.log_target]
    except KeyError:
        raise ValueError(
            f"No log exporter registered for log target {s.log_target!r} "
            f"(OTELIO_LOG_TARGET / OTELIO_TARGET). "
            f"Known targets: {sorted(_LOG_EXPORTERS)}. "
            f"Register one by passing log_exporters=[{{'name': {s.log_target!r}, ...}}] "
            "to init_otelio."
        ) from None
    return factory(s)

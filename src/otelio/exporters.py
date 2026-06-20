"""
Trace and log exporter factories, with a small registry so a project can plug in
its own exporters without modifying otelio.

Two targets ship built in: ``otlp`` (SigNoz / any OTLP-gRPC collector) and
``azure`` (App Insights). Their backend SDKs are imported lazily so a project
only needs the deps for the target it actually uses.

To add your own, register a factory by name (do this at import time, before
:func:`otelio.init_otelio`)::

    # mypkg/telemetry.py
    from otelio import Settings, register_trace_exporter, register_log_exporter

    def build_loki_traces(s: Settings) -> SpanExporter:
        return MyLokiSpanExporter(endpoint=s.otlp_endpoint)

    register_trace_exporter("loki", build_loki_traces)
    register_log_exporter("loki", build_loki_logs)

then select it from the environment — no otelio change needed::

    OTELIO_TARGET=loki

Just make sure ``mypkg.telemetry`` is imported before ``init_otelio`` runs, so
the registration has happened.

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

    return OTLPSpanExporter(endpoint=s.otlp_endpoint)


def _azure_trace(s: Settings) -> SpanExporter:
    from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415 (optional dep)
        AzureMonitorTraceExporter,
    )

    return AzureMonitorTraceExporter(connection_string=s.azure_conn_str)


def _otlp_log(s: Settings) -> LogRecordExporter:
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (  # noqa: PLC0415
        OTLPLogExporter,
    )

    return OTLPLogExporter(endpoint=s.otlp_endpoint)


def _azure_log(s: Settings) -> LogRecordExporter:
    from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415 (optional dep)
        AzureMonitorLogExporter,
    )

    return AzureMonitorLogExporter(connection_string=s.azure_conn_str)


_TRACE_EXPORTERS: dict[str, TraceExporterFactory] = {"otlp": _otlp_trace, "azure": _azure_trace}
_LOG_EXPORTERS: dict[str, LogExporterFactory] = {"otlp": _otlp_log, "azure": _azure_log}


def register_trace_exporter(name: str, factory: TraceExporterFactory) -> None:
    """
    Register (or override) a trace-exporter factory under ``name``.

    The factory receives the resolved :class:`~otelio.config.Settings` and returns
    a ``SpanExporter``. Call this before :func:`otelio.init_otelio`, then select it
    with ``OTELIO_TARGET=<name>``.
    """
    _TRACE_EXPORTERS[name.lower()] = factory


def register_log_exporter(name: str, factory: LogExporterFactory) -> None:
    """
    Register (or override) a log-record-exporter factory under ``name``.

    The factory receives the resolved :class:`~otelio.config.Settings` and returns
    a ``LogRecordExporter``. Call this before :func:`otelio.init_otelio`, then
    select it with ``OTELIO_TARGET=<name>``.
    """
    _LOG_EXPORTERS[name.lower()] = factory


def build_trace_exporter(s: Settings) -> SpanExporter:
    """Return the trace (span) exporter for the configured target."""
    try:
        factory = _TRACE_EXPORTERS[s.target]
    except KeyError:
        raise ValueError(
            f"No trace exporter registered for OTELIO_TARGET={s.target!r}. "
            f"Known targets: {sorted(_TRACE_EXPORTERS)}. "
            f"Register one with otelio.register_trace_exporter({s.target!r}, ...) "
            "before calling init_otelio."
        ) from None
    return factory(s)


def build_log_exporter(s: Settings) -> LogRecordExporter:
    """Return the log-record exporter for the configured target."""
    try:
        factory = _LOG_EXPORTERS[s.target]
    except KeyError:
        raise ValueError(
            f"No log exporter registered for OTELIO_TARGET={s.target!r}. "
            f"Known targets: {sorted(_LOG_EXPORTERS)}. "
            f"Register one with otelio.register_log_exporter({s.target!r}, ...) "
            "before calling init_otelio."
        ) from None
    return factory(s)

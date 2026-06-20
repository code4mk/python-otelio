"""One-call wiring: providers, processors, the Loguru bridge, and shutdown."""

import atexit
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from .config import Settings, load_settings
from .exporters import (
    LogExporterEntry,
    TraceExporterEntry,
    _register_log_exporter,
    _register_trace_exporter,
    build_log_exporter,
    build_trace_exporter,
)
from .logging import setup_loguru


def init_otelio(
    service_name: str,
    service_version: str,
    environment: str | None = None,
    resource_attributes: Mapping[str, Any] | None = None,
    trace_exporters: Sequence[TraceExporterEntry] | None = None,
    log_exporters: Sequence[LogExporterEntry] | None = None,
) -> Settings:
    """
    Initialise tracing + logging once at process start; returns the resolved settings.

    Pass ``resource_attributes`` to stamp extra resource-level attributes (e.g.
    ``service.namespace``, ``service.instance.id``, ``cloud.region``) onto every span
    and log this process emits. The canonical ``service.name`` / ``service.version`` /
    ``deployment.environment`` keys always win, so they cannot be clobbered here.

    Pass ``trace_exporters`` / ``log_exporters`` to register custom exporters inline,
    each a list of ``{"name": ..., "factory": ...}`` objects. The factory takes the
    resolved :class:`~otelio.config.Settings` and returns an exporter. Register a name
    here, then select it with ``OTELIO_TARGET=<name>`` — no separate registration call
    needed. See ``docs/custom-exporter.md``::

        init_otelio(
            "my-service", "1.0.0",
            trace_exporters=[{"name": "otlp-http", "factory": build_http_traces}],
            log_exporters=[{"name": "otlp-http", "factory": build_http_logs}],
        )

    Registers an :mod:`atexit` hook that flushes Loguru and shuts the providers down
    so buffered spans/logs are exported on a clean exit.
    """
    for entry in trace_exporters or ():
        _register_trace_exporter(entry["name"], entry["factory"])
    for entry in log_exporters or ():
        _register_log_exporter(entry["name"], entry["factory"])

    s = load_settings(service_name, service_version, environment)

    resource = Resource.create(
        {
            **(resource_attributes or {}),
            "service.name": s.service_name,
            "service.version": s.service_version,
            "deployment.environment": s.environment,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(build_trace_exporter(s)))
    if s.console:
        # Synchronous so spans print to stdout the moment they end, not on a batch flush.
        tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(build_log_exporter(s)))
    set_logger_provider(logger_provider)

    setup_loguru(logger_provider)

    def _shutdown() -> None:
        logger.complete()
        tracer_provider.shutdown()
        logger_provider.shutdown()

    atexit.register(_shutdown)
    return s

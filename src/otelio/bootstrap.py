"""One-call wiring: providers, processors, the Loguru bridge, and shutdown."""

import atexit
from collections.abc import Mapping
from typing import Any

from loguru import logger
from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import Settings, load_settings
from .exporters import build_log_exporter, build_span_exporter
from .logging import setup_loguru


def init_otelio(
    service_name: str,
    service_version: str,
    environment: str | None = None,
    resource_attributes: Mapping[str, Any] | None = None,
) -> Settings:
    """
    Initialise tracing + logging once at process start; returns the resolved settings.

    Pass ``resource_attributes`` to stamp extra resource-level attributes (e.g.
    ``service.namespace``, ``service.instance.id``, ``cloud.region``) onto every span
    and log this process emits. The canonical ``service.name`` / ``service.version`` /
    ``deployment.environment`` keys always win, so they cannot be clobbered here.

    Registers an :mod:`atexit` hook that flushes Loguru and shuts the providers down
    so buffered spans/logs are exported on a clean exit.
    """
    s = load_settings(service_name, service_version, environment)

    resource = Resource.create({
        **(resource_attributes or {}),
        "service.name": s.service_name,
        "service.version": s.service_version,
        "deployment.environment": s.environment,
    })

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(build_span_exporter(s)))
    trace.set_tracer_provider(tracer_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(build_log_exporter(s)))
    set_logger_provider(logger_provider)

    setup_loguru(logger_provider)

    def _shutdown() -> None:
        logger.complete()
        tracer_provider.shutdown()
        logger_provider.shutdown()

    atexit.register(_shutdown)
    return s

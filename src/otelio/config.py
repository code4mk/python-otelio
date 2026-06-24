"""Settings for otelio, resolved from environment variables with sane defaults."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Resolved telemetry configuration for one service."""

    service_name: str
    service_version: str
    environment: str
    target: str  # global default, "otlp" | "azure"
    trace_target: str  # OTELIO_TRACE_TARGET, falls back to target
    log_target: str  # OTELIO_LOG_TARGET, falls back to target
    otlp_endpoint: str  # global default OTLP endpoint
    otlp_trace_endpoint: str  # OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, falls back to otlp_endpoint
    otlp_log_endpoint: str  # OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, falls back to otlp_endpoint
    azure_conn_str: str | None
    console: bool  # also print spans to stdout for local debugging (logs already have Loguru's console sink)


def load_settings(
    service_name: str,
    service_version: str,
    environment: str | None = None,
) -> Settings:
    """Build :class:`Settings`, letting environment variables override the args."""
    target = os.getenv("OTELIO_TARGET", "otlp").lower()  # global default, local -> otlp/signoz
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    return Settings(
        service_name=os.getenv("OTEL_SERVICE_NAME", service_name),
        service_version=service_version,
        environment=environment or os.getenv("OTELIO_ENVIRONMENT", "local"),
        target=target,
        # Per-signal overrides; unset -> fall back to the global target.
        trace_target=os.getenv("OTELIO_TRACE_TARGET", target).lower(),
        log_target=os.getenv("OTELIO_LOG_TARGET", target).lower(),
        otlp_endpoint=otlp_endpoint,
        # Per-signal endpoint overrides (OTel standard names); unset -> global endpoint.
        otlp_trace_endpoint=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", otlp_endpoint),
        otlp_log_endpoint=os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", otlp_endpoint),
        azure_conn_str=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"),
        console=os.getenv("OTELIO_CONSOLE", "").lower() in ("1", "true", "yes", "on"),
    )

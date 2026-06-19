"""Settings for otelio, resolved from environment variables with sane defaults."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Resolved telemetry configuration for one service."""

    service_name: str
    service_version: str
    environment: str
    target: str  # "otlp" | "azure"
    otlp_endpoint: str
    azure_conn_str: str | None


def load_settings(
    service_name: str,
    service_version: str,
    environment: str | None = None,
) -> Settings:
    """Build :class:`Settings`, letting environment variables override the args."""
    return Settings(
        service_name=os.getenv("OTEL_SERVICE_NAME", service_name),
        service_version=service_version,
        environment=environment or os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
        target=os.getenv("OTELIO_TARGET", "otlp").lower(),  # local -> otlp/signoz
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        azure_conn_str=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"),
    )

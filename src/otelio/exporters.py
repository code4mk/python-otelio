"""
Span and log exporter factories.

The backend-specific SDKs are imported lazily so a project only needs the deps
for the target it actually uses (``otlp`` for SigNoz, ``azure`` for App Insights).
"""

from opentelemetry.sdk._logs.export import LogRecordExporter
from opentelemetry.sdk.trace.export import SpanExporter

from .config import Settings


def build_span_exporter(s: Settings) -> SpanExporter:
    """Return the span exporter for the configured target."""
    if s.target == "azure":
        from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415 (optional dep)
            AzureMonitorTraceExporter,
        )

        return AzureMonitorTraceExporter(connection_string=s.azure_conn_str)
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )

    return OTLPSpanExporter(endpoint=s.otlp_endpoint)


def build_log_exporter(s: Settings) -> LogRecordExporter:
    """Return the log-record exporter for the configured target."""
    if s.target == "azure":
        from azure.monitor.opentelemetry.exporter import (  # noqa: PLC0415 (optional dep)
            AzureMonitorLogExporter,
        )

        return AzureMonitorLogExporter(connection_string=s.azure_conn_str)
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (  # noqa: PLC0415
        OTLPLogExporter,
    )

    return OTLPLogExporter(endpoint=s.otlp_endpoint)

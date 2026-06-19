"""
Otelio — a small OpenTelemetry + Loguru toolkit for Python services.

Import surface kept intentionally small: bootstrap once with ``init_otelio``,
then use ``otel_span`` / helpers anywhere in the codebase.
"""

from .bootstrap import init_otelio
from .helpers import (
    otel_add_event,
    otel_context_from_headers,
    otel_get_all_baggage,
    otel_get_baggage,
    otel_inject_headers,
    otel_set_attributes,
    otel_set_baggage,
)
from .tracing import otel_current_span, otel_get_tracer, otel_span

__all__ = [
    "init_otelio",
    "otel_add_event",
    "otel_context_from_headers",
    "otel_current_span",
    "otel_get_all_baggage",
    "otel_get_baggage",
    "otel_get_tracer",
    "otel_inject_headers",
    "otel_set_attributes",
    "otel_set_baggage",
    "otel_span",
]

"""Span creation: a ``span()`` context manager plus low-level span access."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

_TRACER_NAME = "otelio"


def otel_get_tracer() -> Tracer:
    """Return the shared otelio tracer."""
    return trace.get_tracer(_TRACER_NAME)


def otel_current_span() -> Span:
    """Return the span active in the current context (a no-op span if none)."""
    return trace.get_current_span()


@contextmanager
def otel_span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    context: Context | None = None,
) -> Iterator[Span]:
    """
    Start ``name`` as the current span; records and re-raises any exception.

    Pass ``context`` (from :func:`otel_context_from_headers`) to continue an
    inbound distributed trace.
    """
    tracer = otel_get_tracer()
    with tracer.start_as_current_span(name, context=context, kind=kind) as s:
        if attributes:
            s.set_attributes(dict(attributes))
        try:
            yield s
        except Exception as e:
            s.record_exception(e)
            s.set_status(Status(StatusCode.ERROR, str(e)))
            raise

"""Context propagation and attribute/event helpers for working with spans."""

from collections.abc import Mapping
from typing import Any

from opentelemetry import baggage
from opentelemetry.context import Context, attach, get_current
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Span

# ---- propagation (W3C traceparent + baggage) ----


def otel_inject_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    """Inject the current trace context into ``headers`` (adds ``traceparent``)."""
    headers = headers if headers is not None else {}
    inject(headers)
    return headers


def otel_context_from_headers(headers: Mapping[str, str]) -> Context:
    """Extract a trace context from inbound ``headers``; pass to ``span(context=...)``."""
    return extract(headers)


# ---- baggage (cross-service key/values, ride the `baggage` header) ----


def otel_set_baggage(items: Mapping[str, str]) -> object:
    """
    Put key/value pairs into baggage so they propagate to every downstream hop.

    Mirrors :func:`otel_set_attributes` — pass a mapping object. Unlike span
    attributes (local to one service), baggage rides the W3C ``baggage`` header
    through APIM -> governance -> backend, so it is ideal for cross-cutting IDs
    such as ``tenant.id`` / ``request.id`` / ``user.id``.

    Baggage is sent in plaintext to every downstream service — **never put secrets
    or PII in it**, and keep entries small (it is header weight on every call).

    Baggage does not become span attributes automatically; copy what you want onto
    a span with :func:`otel_set_attributes` (e.g. via :func:`otel_get_all_baggage`).

    Attaches the updated context as current and returns a detach token. In a
    request-scoped flow (e.g. FastAPI middleware) keep the token and call
    ``opentelemetry.context.detach(token)`` when the request ends so baggage does
    not leak into the next request handled on the same context.
    """
    ctx = get_current()
    for key, value in items.items():
        ctx = baggage.set_baggage(key, value, context=ctx)
    return attach(ctx)


def otel_get_baggage(key: str) -> str | None:
    """Return a single baggage value from the current context, or ``None``."""
    value = baggage.get_baggage(key)
    return None if value is None else str(value)


def otel_get_all_baggage() -> dict[str, str]:
    """Return all baggage entries in the current context as a plain dict."""
    return {key: str(value) for key, value in baggage.get_all().items()}


# ---- attributes / events ----


def otel_set_attributes(span: Span, attributes: Mapping[str, Any]) -> None:
    """Set attributes on ``span`` when it is recording."""
    if span and span.is_recording():
        span.set_attributes(dict(attributes))


def otel_add_event(span: Span, name: str,
              attributes: Mapping[str, Any] | None = None) -> None:
    """Add a timestamped event to ``span`` when it is recording."""
    if span and span.is_recording():
        span.add_event(name, attributes=dict(attributes or {}))


def record_governance_decision(
    span: Span,
    *,
    allowed: bool,
    reason: str = "",
    code: str = "",
) -> None:
    """Record an APIM/governance allow-or-deny outcome as attributes and an event."""
    otel_set_attributes(span, {
        "governance.allowed": allowed,
        "governance.reason": reason,
        "governance.code": code,
    })
    otel_add_event(span, "governance.decision",
              {"allowed": allowed, "reason": reason, "code": code})

# otelio

> Python OpenTelemetry + Loguru toolkit

A small, batteries-included **OpenTelemetry + [Loguru](https://github.com/Delgan/loguru)**
toolkit for Python services. Call `init_otelio(...)` once at startup and you get **traces**
and **logs** that are automatically correlated by `trace_id` / `span_id`, exported over
**OTLP/gRPC** (SigNoz, Grafana, Jaeger, any OTLP collector) or to **Azure Application
Insights** — switchable with a single environment variable, no code changes.

[![PyPI](https://img.shields.io/pypi/v/otelio.svg)](https://pypi.org/project/otelio/)
[![Python](https://img.shields.io/pypi/pyversions/otelio.svg)](https://pypi.org/project/otelio/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Features

- **One call to wire everything** — `init_otelio(...)` sets up the tracer + logger
  providers, the Loguru bridge, and a clean-shutdown flush hook.
- **Logs correlate to spans automatically** — keep using Loguru; every record is stamped
  with the active `trace_id` / `span_id` and exported.
- **Backend-agnostic** — OTLP/gRPC or Azure App Insights via the `OTELIO_TARGET` env var.
  Exporter SDKs are imported lazily, so you only install what you use.
- **Cross-service tracing built in** — W3C `traceparent` + `baggage` propagation helpers so
  one request shows up as a single connected trace across service boundaries.
- **Tiny surface** — eleven well-documented functions, nothing to configure in code.

## Install

```bash
pip install otelio                # core + OTLP/gRPC exporter
pip install "otelio[azure]"       # also the Azure Application Insights exporter
```

Requires Python 3.10+.

## Quick start

```python
from otelio import init_otelio, otel_span, otel_set_attributes
from loguru import logger

# 1. Bootstrap once, at process start (before anything emits telemetry).
init_otelio(service_name="my-service", service_version="1.0.0")

# 2. Log with Loguru as usual — records are stamped with the active span.
logger.info("service started")

# 3. Wrap units of work in spans; exceptions are recorded and re-raised.
with otel_span("handle_request", attributes={"route": "/search"}):
    otel_set_attributes({"result.count": 12})
```

## Configuration

All configuration is via environment variables.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OTELIO_TARGET` | `otlp` | `otlp` (any OTLP/gRPC collector) or `azure` (App Insights). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP/gRPC collector endpoint (target `otlp`). |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | App Insights connection string (target `azure`). |
| `OTEL_SERVICE_NAME` | the `service_name` arg | Overrides the service name. |
| `DEPLOYMENT_ENVIRONMENT` | `local` | Set as the `deployment.environment` resource attribute. |

```bash
# OTLP collector (SigNoz, Grafana, Jaeger, ...)
export OTELIO_TARGET=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Azure Application Insights
export OTELIO_TARGET=azure
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=..."
export DEPLOYMENT_ENVIRONMENT=production
```

## Public API (`from otelio import ...`)

| Symbol | Purpose |
| --- | --- |
| `init_otelio(service_name, service_version, environment=None, resource_attributes=None)` | Bootstrap tracing + logging once at startup. `resource_attributes` adds extra resource-level keys to every span + log. Returns the resolved `Settings`. |
| `otel_span(name, attributes=None, kind=SpanKind.INTERNAL, context=None)` | Context manager that starts a span, records exceptions, and re-raises. |
| `otel_current_span()` | The span active in the current context. |
| `otel_get_tracer()` | The shared `otelio` tracer. |
| `otel_inject_headers(headers=None)` | Inject the current trace context + baggage into an outbound header dict. |
| `otel_context_from_headers(headers)` | Extract a trace context (+ baggage) from inbound headers; pass to `otel_span(context=...)`. |
| `otel_set_baggage(items)` | Put a mapping of key/values into baggage so they propagate downstream. Returns a detach token. |
| `otel_get_baggage(key)` | Read one baggage value from the current context (or `None`). |
| `otel_get_all_baggage()` | Read all baggage entries as a plain `dict`. |
| `otel_set_attributes(attributes, span=None)` | Set attributes on the current span, or `span` if given (guards `is_recording()`). |
| `otel_add_event(name, attributes=None, span=None)` | Add a timestamped event to the current span, or `span` if given. |

## Context propagation across services

`otelio` carries the W3C `traceparent` + `baggage` headers automatically, so one request
shows up as a single connected trace across service boundaries:

```python
import httpx
from opentelemetry.trace import SpanKind
from otelio import otel_inject_headers, otel_context_from_headers, otel_span

# Outbound — inject context into the request headers
with otel_span("call_downstream", kind=SpanKind.CLIENT):
    headers = otel_inject_headers({"Authorization": token})
    resp = httpx.post(url, headers=headers, json=payload)

# Inbound — continue the caller's trace
ctx = otel_context_from_headers(request.headers)
with otel_span("serve_request", kind=SpanKind.SERVER, context=ctx):
    ...
```

## Documentation

See the full [usage guide](https://github.com/code4mk/python-otelio/blob/main/docs/usage.md)
for bootstrapping, spans, correlated logging, context propagation, baggage, and a complete
FastAPI example.

## License

[MIT](LICENSE) © code4mk

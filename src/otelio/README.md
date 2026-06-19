# otelio

A small, batteries-included OpenTelemetry + [Loguru](https://github.com/Delgan/loguru)
toolkit. `pip install otelio`, call `init_otelio(...)` once at startup, and you get
**traces** and **logs** that are automatically correlated by `trace_id` / `span_id`.

- **Local development →** OTLP/gRPC exporter pointed at **SigNoz**.
- **Dev / Production →** **Azure Application Insights** exporter.

Switching between them is a single environment variable (`OTELIO_TARGET`) — no code
changes. The package is self-contained: nothing here imports from the host project, so the
same library works unchanged across every service.

---

## Why this exists

The system is `MCP server → APIM → governance app → backend`. APIM forwards the call
to the backend only if governance approves; otherwise it returns an error code. To debug
that flow we need a single trace that follows one request across process boundaries, with
logs attached to the right span. `otelio` standardises how every repo emits that
telemetry so the traces line up when they meet in SigNoz / App Insights.

---

## Folder structure

```
src/otelio/
├── __init__.py        # public surface — what each project imports
├── config.py          # Settings resolved from env vars
├── exporters.py       # span + log exporter factories (otlp | azure)
├── bootstrap.py       # init_otelio(): wire providers, processors, loguru, shutdown
├── tracing.py         # otel_span() context manager + low-level span access
├── helpers.py         # propagation (inject/extract) + attribute/event helpers
└── logging.py         # loguru <-> otel logs bridge (sink + trace patcher)
```

## Public API (`from otelio import ...`)

| Symbol | Purpose |
| --- | --- |
| `init_otelio(service_name, service_version, environment=None)` | Bootstrap tracing + logging once at startup. Returns the resolved `Settings`. |
| `otel_span(name, attributes=None, kind=SpanKind.INTERNAL, context=None)` | Context manager that starts a span, records exceptions, and re-raises. |
| `otel_current_span()` | The span active in the current context. |
| `otel_get_tracer()` | The shared `otelio` tracer. |
| `otel_inject_headers(headers=None)` | Inject the current trace context + baggage into an outbound header dict (`traceparent`, `baggage`). |
| `otel_context_from_headers(headers)` | Extract a trace context (+ baggage) from inbound headers; pass to `otel_span(context=...)`. |
| `otel_set_baggage(items)` | Put a mapping of key/values into baggage so they propagate to every downstream hop. Returns a detach token. |
| `otel_get_baggage(key)` | Read one baggage value from the current context (or `None`). |
| `otel_get_all_baggage()` | Read all baggage entries as a plain `dict`. |
| `otel_set_attributes(span, attributes)` | Set attributes on a span (guards `is_recording()`). |
| `otel_add_event(span, name, attributes=None)` | Add a timestamped event to a span. |
| `record_governance_decision(span, *, allowed, reason="", code="")` | Record an APIM/governance allow-or-deny outcome as attributes + an event. |

---

## Install

```bash
pip install otelio                # core + OTLP/gRPC (SigNoz) exporter
pip install "otelio[azure]"       # also Azure Application Insights exporter
```

The core install ships the OTLP/gRPC exporter (local / SigNoz). The Azure exporter is an
optional extra; both backend SDKs are imported **lazily** in `exporters.py`, so a service
that only ever targets one backend works fine without the other package installed.

---

## Configuration (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `OTELIO_TARGET` | `otlp` | `otlp` (SigNoz / local) or `azure` (App Insights). |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP/gRPC collector endpoint (used when target is `otlp`). |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | — | App Insights connection string (required when target is `azure`). |
| `OTEL_SERVICE_NAME` | the `service_name` arg | Overrides the service name. |
| `DEPLOYMENT_ENVIRONMENT` | `local` | Set as the `deployment.environment` resource attribute. |

### Local (SigNoz)

```bash
export OTELIO_TARGET=otlp
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export DEPLOYMENT_ENVIRONMENT=local
```

### Dev / Production (Azure App Insights)

```bash
export OTELIO_TARGET=azure
export APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=..."
export DEPLOYMENT_ENVIRONMENT=production
```

---

## Usage plan

### 1. Bootstrap once, at process start

Call `init_otelio` before anything emits telemetry (top of your app entrypoint —
e.g. `server.py` / `main.py`). It wires the tracer + logger providers, bridges Loguru,
and registers an `atexit` hook that flushes buffered spans/logs on shutdown.

```python
from importlib.metadata import version

from otelio import init_otelio

init_otelio(
    service_name="my-service",
    service_version=version("my-service"),
)
# from here on, just use `logger` (loguru) and `otel_span(...)` anywhere.
```

### 2. Log with Loguru as usual

No special logging API. Every Loguru record is mirrored to OpenTelemetry and stamped
with the active `trace_id` / `span_id`, so console lines and exported logs correlate to
their span automatically.

```python
from loguru import logger

logger.info("handling request", request_id=req_id)
```

### 3. Wrap units of work in spans

```python
from otelio import otel_span, otel_set_attributes

with otel_span("handle_tool_call", attributes={"tool.name": name}) as s:
    otel_set_attributes(s, {"tool.args.count": len(args)})
    result = do_work()
```

Exceptions raised inside the `with` block are recorded on the span and the status is set
to `ERROR` before re-raising — no manual try/except needed.

### 4. Propagate context across the APIM → governance → backend hops

**Outbound** (this service calling the next one) — inject the trace context into the
request headers so the downstream span joins the same trace:

```python
import httpx
from opentelemetry.trace import SpanKind

from otelio import otel_inject_headers, otel_span

with otel_span("call_apim", kind=SpanKind.CLIENT):
    headers = otel_inject_headers({"Authorization": token})
    resp = httpx.post(url, headers=headers, json=payload)
```

**Inbound** (a service receiving a request) — rebuild the parent context from the
incoming headers and pass it to `span`:

```python
from opentelemetry.trace import SpanKind

from otelio import otel_context_from_headers, otel_span

ctx = otel_context_from_headers(request.headers)
with otel_span("serve_request", kind=SpanKind.SERVER, context=ctx) as s:
    ...
```

### 5. Record the governance decision

The decision is the most important branch in the system, so make it first-class on the
span (both queryable attributes and a timeline event):

```python
from otelio import otel_current_span, record_governance_decision

allowed, code, reason = check_governance(request)
record_governance_decision(
    otel_current_span(),
    allowed=allowed,
    reason=reason,
    code=code,
)
if not allowed:
    return error_response(code)
```

---

## Reusing across services

1. `pip install otelio` (add the `[azure]` extra where you target App Insights).
2. Call `init_otelio(service_name=..., service_version=...)` at startup with that
   service's name.
3. Set the environment variables for the deployment.

Because each service sets its own `service_name` and propagates context over headers, a
single request shows up in SigNoz / App Insights as one connected trace spanning all
the services it touches.

---

> See the [usage guide](../../docs/usage.md) for spans, logging, baggage, and a full
> FastAPI example.

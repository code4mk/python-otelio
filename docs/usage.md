# otelio — Usage Guide

End-to-end guide for using `otelio` in a Python service: how to **bootstrap**, create
**spans**, write **logs** that are correlated to those spans, and use the **helpers** to
propagate context and annotate spans. Examples are shown with **FastAPI**, since that is
what our services run on, but nothing in `otelio` is FastAPI-specific.

> Public API reference and configuration live in the [README](../README.md). This doc is
> the "how do I actually use it" companion.

---

## Table of contents

1. [Mental model](#1-mental-model)
2. [Bootstrap once at startup](#2-bootstrap-once-at-startup)
3. [Logging with Loguru](#3-logging-with-loguru)
4. [Spans](#4-spans)
5. [Helpers — attributes & events](#5-helpers--attributes--events)
6. [Helpers — context propagation](#6-helpers--context-propagation)
7. [Helpers — baggage (cross-service values)](#7-helpers--baggage-cross-service-values)
8. [Full FastAPI example](#8-full-fastapi-example)
9. [The MCP → APIM → governance → backend flow](#9-the-mcp--apim--governance--backend-flow)
10. [Patterns & gotchas](#10-patterns--gotchas)

---

## 1. Mental model

`otelio` gives you three things:

| Thing | What it is | You use it via |
| --- | --- | --- |
| **Traces / spans** | A timed unit of work, possibly nested, possibly spanning services. | `otel_span(...)`, `otel_current_span()` |
| **Logs** | Normal Loguru logs, automatically stamped with the active `trace_id` / `span_id` and exported to the backend. | `loguru.logger` |
| **Helpers** | Put data on spans, carry trace context + baggage across HTTP calls. | `otel_set_attributes`, `otel_add_event`, `otel_inject_headers`, `otel_context_from_headers`, `otel_set_baggage`, `otel_get_baggage`, `otel_get_all_baggage` |

Everything flows to **SigNoz** locally or **Azure Application Insights** in dev/prod,
selected purely by the `OTELIO_TARGET` env var — your code never changes.

---

## 2. Bootstrap once at startup

Call `init_otelio(...)` **before** anything emits telemetry — ideally the very first
thing in your entrypoint. It wires the tracer + logger providers, bridges Loguru into
OpenTelemetry, and registers an `atexit` hook that flushes buffered spans/logs on a clean
shutdown.

```python
# main.py / server.py
from importlib.metadata import version

from otelio import init_otelio

init_otelio(
    service_name="my-service",
    service_version=version("my-service"),
    # environment="production",  # optional; defaults to $DEPLOYMENT_ENVIRONMENT or "local"
    # resource_attributes={      # optional; stamped on every span + log this process emits
    #     "service.namespace": "nexus-re",
    #     "service.instance.id": socket.gethostname(),
    #     "cloud.region": "westeurope",
    # },
)
```

> `resource_attributes` are **resource-level** — they describe this process and ride on
> every span and log, unlike `otel_set_attributes` (one span) or baggage (cross-service).
> The canonical `service.name` / `service.version` / `deployment.environment` keys always
> win, so you can't accidentally clobber them via this mapping.

### With FastAPI (lifespan)

Bootstrapping at import time is simplest, but if you prefer to tie it to the app
lifecycle, use a lifespan handler:

```python
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from loguru import logger

from otelio import init_otelio


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_otelio("my-service", version("my-service"))
    logger.info("telemetry initialised")
    yield
    # the atexit hook flushes providers on shutdown


app = FastAPI(lifespan=lifespan)
```

**Call it exactly once per process.** Calling it again creates duplicate providers.

---

## 3. Logging with Loguru

There is **no special logging API** — keep using Loguru's `logger`. `otelio` reconfigures
Loguru so that every record is:

- printed to the console with the active `trace_id` (the `setup_loguru` console sink), and
- exported to OpenTelemetry logs, correlated to the current span.

```python
from loguru import logger

logger.debug("cache miss", key=cache_key)
logger.info("processing request", user_id=user_id)
logger.warning("retrying upstream call", attempt=2)
logger.error("validation failed", field="email")
```

### Log levels

- **Console** shows `INFO` and above by default.
- **Export** (to SigNoz / App Insights) captures `DEBUG` and above.

(These are the `console_level` / `export_level` defaults in `setup_loguru`.)

### Structured fields

Pass keyword arguments — they become structured attributes on the exported log record,
which you can filter on in the backend:

```python
logger.bind(request_id=req_id, tenant=tenant).info("handling tool call")
```

### Exceptions

Use `logger.exception(...)` inside an `except` block; the traceback is captured and
exported with the record:

```python
try:
    risky()
except Exception:
    logger.exception("risky() failed")  # full traceback exported
    raise
```

> **Correlation is automatic.** Any log emitted while a span is active carries that span's
> `trace_id`/`span_id`. A log emitted with no active span shows `trace=-`.

---

## 4. Spans

A **span** measures one unit of work. Open one with the `otel_span(...)` context manager.

```python
from otelio import otel_span

with otel_span("load_user_profile") as s:
    profile = db.fetch_profile(user_id)
```

### Attributes at creation time

```python
with otel_span("load_user_profile", attributes={"user.id": user_id}) as s:
    ...
```

### Span kind

Set `kind` to describe the role of the span — this matters for how backends render the
trace (client/server pairing, service maps):

```python
from opentelemetry.trace import SpanKind

with otel_span("apim.request", kind=SpanKind.CLIENT):     # we are calling out
    ...

with otel_span("handle.request", kind=SpanKind.SERVER):   # we are serving a request
    ...
```

| Kind | Use when |
| --- | --- |
| `INTERNAL` (default) | In-process work — a function, a computation. |
| `CLIENT` | You are making an outbound call (HTTP, DB, queue produce). |
| `SERVER` | You are handling an inbound request. |
| `PRODUCER` / `CONSUMER` | Messaging / async work hand-off. |

### Automatic error recording

If an exception propagates out of the `with` block, `otel_span` records it on the span and
sets the span status to `ERROR`, **then re-raises**. You do not need a manual try/except
just for telemetry:

```python
with otel_span("charge_card"):
    charge()          # raises -> span marked ERROR + exception recorded, then re-raised
```

### Nesting

Spans nest automatically — a span opened inside another becomes its child:

```python
with otel_span("handle_order"):
    with otel_span("validate"):
        ...
    with otel_span("persist"):
        ...
```

### Reaching the current span

When you are deep in the call stack and just need the span that is already active (e.g. to
attach an attribute), call the helpers directly — they default to `otel_current_span()`,
so you never have to thread the span object through every function:

```python
from otelio import otel_set_attributes

def deep_helper():
    otel_set_attributes({"helper.ran": True})
```

> Outside any span, the current span is a non-recording no-op span, so the helpers below
> are safe to call unconditionally. Use `otel_current_span()` directly only when you need
> the span object itself.

---

## 5. Helpers — attributes & events

### `otel_set_attributes(attributes, span=None)`

Attach key/value data to a span. Attributes are queryable/filterable in the backend. Use
dotted, namespaced keys (`http.status_code`, `user.id`, `db.rows`). Defaults to the
current span; pass `span=` only to target a span other than the active one.

```python
from otelio import otel_set_attributes

otel_set_attributes({
    "http.method": "POST",
    "http.route": "/tools/invoke",
    "tool.name": tool_name,
})
```

### `otel_add_event(name, attributes=None, span=None)`

Record a **timestamped event** on the span's timeline — a "something happened at this
instant" marker. Good for cache hits, retries, state transitions. Defaults to the current
span; pass `span=` only to target a span other than the active one.

```python
from otelio import otel_add_event

otel_add_event("cache.miss", {"key": cache_key})
otel_add_event("retry", {"attempt": 2, "backoff_ms": 250})
```

**Attribute vs event:** an attribute describes the span as a whole ("this span had
status 200"); an event marks a point in time during the span ("at t=12ms we retried").

Both helpers guard on `span.is_recording()`, so they are no-ops when there is no real span
— safe to call anywhere.

---

## 6. Helpers — context propagation

To get a **single trace across multiple services**, the trace context must travel in the
HTTP headers between them (W3C `traceparent`).

### Outbound — `otel_inject_headers(headers=None)`

Before calling another service, inject the current context into the request headers. The
downstream service will then continue the same trace.

```python
import httpx
from opentelemetry.trace import SpanKind

from otelio import otel_inject_headers, otel_span

with otel_span("call_apim", kind=SpanKind.CLIENT):
    headers = otel_inject_headers({"Authorization": f"Bearer {token}"})
    # headers now also contains 'traceparent' (and 'tracestate')
    resp = httpx.post(apim_url, headers=headers, json=payload)
```

### Inbound — `otel_context_from_headers(headers)`

When receiving a request, rebuild the parent context from the incoming headers and pass it
to `otel_span(context=...)` so your span attaches to the caller's trace.

```python
from opentelemetry.trace import SpanKind

from otelio import otel_context_from_headers, otel_span

ctx = otel_context_from_headers(request.headers)
with otel_span("handle.request", kind=SpanKind.SERVER, context=ctx) as s:
    ...
```

If the incoming headers contain no `traceparent`, `otel_span` simply starts a brand-new
root trace — so this is safe at the edge of your system too.

---

## 7. Helpers — baggage (cross-service values)

**Baggage** is a set of key/value pairs that travels with the trace context across every
service hop (it rides the W3C `baggage` header). Use it for **cross-cutting identifiers**
every service should know — `tenant.id`, `request.id`, `user.id`.

> **Baggage vs span attributes:** a span attribute is local to one service's span.
> Baggage propagates to **all** downstream services. Set a tenant id once at the MCP edge
> and APIM / governance / backend can all read it.

Propagation is already wired: `otel_inject_headers` / `otel_context_from_headers` carry
baggage automatically (the global propagator is a composite of `tracecontext` + `baggage`).
You only need to **set** and **read** it.

### Setting baggage — `otel_set_baggage(items)`

Pass a mapping object, just like `otel_set_attributes`:

```python
from otelio import otel_set_baggage

token = otel_set_baggage({
    "tenant.id": tenant_id,
    "request.id": request_id,
})
```

`otel_set_baggage` attaches the values to the **current context** and returns a **detach
token**. From this point on, any `otel_inject_headers` call automatically includes them in
the outbound `baggage` header.

> **Manage the token in long-lived servers.** Because it mutates the current context, you
> should `detach` it when the request scope ends so values don't bleed into the next
> request handled on the same context (see the FastAPI middleware below):
>
> ```python
> from opentelemetry.context import detach
> detach(token)
> ```

### Reading baggage — `otel_get_baggage` / `otel_get_all_baggage`

In any downstream service (after `otel_context_from_headers` has restored the context),
read the values back:

```python
from otelio import otel_get_baggage, otel_get_all_baggage

tenant = otel_get_baggage("tenant.id")          # -> "acme" or None
everything = otel_get_all_baggage()             # -> {"tenant.id": "acme", "request.id": "..."}
```

### Putting baggage onto spans/logs

Baggage does **not** become span attributes automatically (this is by design — keeps it
cheap). Copy what you care about onto the span explicitly:

```python
from otelio import otel_get_all_baggage, otel_set_attributes

otel_set_attributes(otel_get_all_baggage())
```

### ⚠️ Cautions

- Baggage is sent **in plaintext** to every downstream hop (including APIM). **Never put
  secrets, tokens, or PII in it.**
- Every entry is **header weight on every outbound call** — keep keys/values small and few.

---

## 8. Full FastAPI example

A complete service that initialises telemetry, continues inbound traces via middleware,
logs with correlation, and makes a downstream call carrying the trace context.

```python
from contextlib import asynccontextmanager
from importlib.metadata import version

import httpx
from fastapi import FastAPI, Request
from loguru import logger
from opentelemetry.context import detach
from opentelemetry.trace import SpanKind

from otelio import (
    init_otelio,
    otel_add_event,
    otel_context_from_headers,
    otel_current_span,
    otel_inject_headers,
    otel_set_attributes,
    otel_set_baggage,
    otel_span,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_otelio("my-service", version("my-service"))
    yield


app = FastAPI(lifespan=lifespan)


# 1. Wrap every request in a SERVER span that continues the inbound trace,
#    and seed request-scoped baggage that all downstream hops will see.
@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    ctx = otel_context_from_headers(request.headers)
    with otel_span(
        f"{request.method} {request.url.path}",
        kind=SpanKind.SERVER,
        context=ctx,
    ):
        otel_set_attributes({
            "http.method": request.method,
            "http.route": request.url.path,
        })
        # cross-cutting IDs that should travel to APIM -> governance -> backend
        token = otel_set_baggage({
            "request.id": request.headers.get("x-request-id", "-"),
            "tenant.id": request.headers.get("x-tenant-id", "-"),
        })
        try:
            response = await call_next(request)
        finally:
            detach(token)  # don't leak baggage into the next request
        otel_set_attributes({"http.status_code": response.status_code})
        return response


# 2. A route doing real work — logs correlate automatically, child spans nest.
@app.post("/tools/{tool_name}")
async def invoke_tool(tool_name: str, request: Request):
    logger.info("tool invocation received", tool=tool_name)

    payload = await request.json()
    otel_set_attributes({"tool.name": tool_name})

    with otel_span("validate_payload"):
        otel_add_event("validation.start")
        # ... validate ...
        otel_add_event("validation.ok")

    # 3. Call APIM downstream, carrying the trace context forward.
    with otel_span("call_apim", kind=SpanKind.CLIENT):
        headers = otel_inject_headers({"Authorization": request.headers.get("authorization", "")})
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://apim.example.com/governance",
                headers=headers,
                json=payload,
            )

        otel_set_attributes({"http.status_code": resp.status_code})

    if resp.status_code >= 400:
        logger.warning("downstream returned error", tool=tool_name, code=resp.status_code)
        return {"error": "downstream_error", "code": resp.status_code}

    logger.info("tool invocation completed", tool=tool_name)
    return resp.json()
```

What you get in SigNoz / App Insights for one request:

```
SERVER  POST /tools/search                 (root span — continued from caller if traceparent present)
├─ INTERNAL validate_payload               events: validation.start, validation.ok
└─ CLIENT  call_apim                        attrs: http.status_code=200
   + logs "tool invocation received", "tool invocation completed" attached at the right span
```

---

## 9. The MCP → APIM → governance → backend flow

The whole point is one connected trace across all hops. Each service does the same two
things: **continue the inbound trace** (SERVER span from headers) and **propagate
outbound** (`otel_inject_headers` on the next call).

```python
# === MCP server: outbound to APIM ===
from opentelemetry.trace import SpanKind
from otelio import otel_span, otel_inject_headers, otel_set_attributes

with otel_span("apim.request", kind=SpanKind.CLIENT):
    headers = otel_inject_headers({"Authorization": token})
    resp = http.post(apim_url, headers=headers, json=payload)
    otel_set_attributes({"http.status_code": resp.status_code})

# === Governance / backend app: inbound (continue the trace) ===
from opentelemetry.trace import SpanKind
from otelio import otel_span, otel_context_from_headers

ctx = otel_context_from_headers(request.headers)
with otel_span("handle.request", kind=SpanKind.SERVER, context=ctx):
    ...
```

Because every service sets its own `service_name` in `init_otelio` and forwards context
via headers, a single request appears as **one trace** spanning MCP → APIM → governance →
backend.

---

## 10. Patterns & gotchas

- **Initialise exactly once.** Multiple `init_otelio` calls create duplicate providers.
- **Don't pass huge / sensitive values as attributes.** Truncate large strings; never put
  secrets or tokens on a span — they're exported to the backend.
- **Helpers are null-safe.** `otel_set_attributes` / `otel_add_event` no-op when there's
  no recording span, so you can call them without guarding. Both default to the current
  span; pass `span=` only to target a different one.
- **Logs only correlate inside a span.** A log line emitted before any span opens shows
  `trace=-`; that's expected.
- **Async is fine.** OpenTelemetry context follows `async`/`await` within a task. If you
  hand work to a thread/process pool, the context does **not** auto-propagate — capture and
  re-attach it explicitly if you need correlation there.
- **Batch export means a small delay.** Spans/logs are batched and flushed periodically (and
  on clean shutdown via the `atexit` hook). Don't expect them in the backend the instant a
  span closes.
```

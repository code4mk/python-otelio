# otelio — Custom Exporters

`otelio` ships two built-in export targets — `otlp` (SigNoz / any OTLP-gRPC collector) and
`azure` (App Insights) — selected with the `OTELIO_TARGET` env var. If you need a different
backend (Loki, an HTTP/proto OTLP exporter, a console exporter, a vendor SDK, …) you can
**register your own exporter without modifying otelio** and select it the same way:
`OTELIO_TARGET=<your-name>`.

> Public API reference and the built-in config live in the [README](../README.md). This doc
> is the "I need a backend otelio doesn't ship" companion.

---

## Table of contents

1. [Built-in targets](#1-built-in-targets)
2. [How it works](#2-how-it-works)
3. [Register your exporter](#3-register-your-exporter)
4. [Select it from the environment](#4-select-it-from-the-environment)
5. [Full example — OTLP over HTTP](#5-full-example--otlp-over-http)
6. [Overriding a built-in target](#6-overriding-a-built-in-target)
7. [Gotchas](#7-gotchas)

---

## 1. Built-in targets

otelio ships **two** export targets out of the box. You select one with `OTELIO_TARGET`;
no registration needed. Both cover **traces and logs**.

| `OTELIO_TARGET` | Backend | Transport | Reads from | Extra dependency |
| --- | --- | --- | --- | --- |
| `otlp` *(default)* | Any OTLP collector — SigNoz, Grafana, Jaeger, … | **OTLP / gRPC** | `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4317`) | bundled |
| `azure` | **Azure Application Insights** | Azure Monitor SDK | `APPLICATIONINSIGHTS_CONNECTION_STRING` | `azure-monitor-opentelemetry-exporter` |

The rest of this doc is only needed when you want a target these two don't cover (a
different transport like OTLP/HTTP, Loki, a console exporter, a vendor SDK, …).

---

## 2. How it works

Internally, otelio keeps a **registry** mapping a target *name* to an exporter *factory*.
The two built-ins above (`otlp` and `azure`) are just pre-registered entries. When
`init_otelio` runs, it looks up `OTELIO_TARGET` in that registry and calls the factory to
build the exporter.

A factory is any callable that takes the resolved [`Settings`](../README.md#configuration)
and returns an exporter:

```python
TraceExporterFactory = Callable[[Settings], SpanExporter]
LogExporterFactory   = Callable[[Settings], LogRecordExporter]
```

Receiving `Settings` means your factory can read `s.otlp_endpoint`, `s.azure_conn_str`,
`s.service_name`, `s.environment`, etc. — the same resolved config the built-ins use.

> **Naming note.** otelio names its surface after the *signal* — `trace` and `log` — so the
> pair stays consistent. The trace exporter's OTel type is still `SpanExporter` (the SDK's
> class name), which is why the factory's return annotation says `SpanExporter`.

---

## 3. Register your exporter

Pass your custom exporters straight to `init_otelio` through two optional list params,
`trace_exporters` and `log_exporters`. Each is a list of `{"name": ..., "factory": ...}`
objects. otelio registers them before resolving `OTELIO_TARGET`, so there's no separate
registration step and no import-ordering to think about.

```python
# main.py
from otelio import Settings, init_otelio

# import your backend's exporters — these are NOT otelio deps, they're yours
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter


def build_http_traces(s: Settings):
    return OTLPSpanExporter(endpoint=f"{s.otlp_endpoint}/v1/traces")


def build_http_logs(s: Settings):
    return OTLPLogExporter(endpoint=f"{s.otlp_endpoint}/v1/logs")


init_otelio(
    "my-service",
    "1.0.0",
    trace_exporters=[{"name": "otlp-http", "factory": build_http_traces}],
    log_exporters=[{"name": "otlp-http", "factory": build_http_logs}],
)
```

You picked the name `otlp-http`. It's case-insensitive (stored lowercased), and it's what
you'll set `OTELIO_TARGET` to. Each list can hold several entries if you want multiple
targets selectable by env.

> Register **both** a trace and a log factory under your name. `OTELIO_TARGET` selects the
> exporters for both signals; if only one is registered under the chosen name, otelio
> raises a clear `ValueError` listing the known targets.

The object shape is typed — import `TraceExporterEntry` / `LogExporterEntry` from `otelio`
if you want your editor to check it.

---

## 4. Select it from the environment

Nothing in your code changes per environment — only the env var:

```bash
# .env
OTELIO_TARGET=otlp-http
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
```

Local can stay on the built-in gRPC `otlp`, staging can use your `otlp-http`, and so on —
purely by flipping `OTELIO_TARGET`.

---

## 5. Full example — OTLP over HTTP

A complete, runnable shape. (`otlp` ships gRPC; this adds an HTTP/proto variant.)

```python
# main.py
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from otelio import Settings, init_otelio


def _traces(s: Settings):
    return OTLPSpanExporter(endpoint=f"{s.otlp_endpoint}/v1/traces")


def _logs(s: Settings):
    return OTLPLogExporter(endpoint=f"{s.otlp_endpoint}/v1/logs")


init_otelio(
    "my-service",
    "1.0.0",
    trace_exporters=[{"name": "otlp-http", "factory": _traces}],
    log_exporters=[{"name": "otlp-http", "factory": _logs}],
)
```

```bash
# .env
OTELIO_TARGET=otlp-http
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4318
```

`pip install opentelemetry-exporter-otlp-proto-http` (your dep, not otelio's), and you're
exporting over HTTP with zero changes to otelio.

---

## 6. Overriding a built-in target

Registering under an existing name (`otlp` or `azure`) **replaces** that built-in — useful
for tweaking exporter options (timeouts, headers, compression) the built-in factory doesn't
expose. Just reuse the name:

```python
from grpc import Compression
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from otelio import Settings, init_otelio


def _gzip_traces(s: Settings):
    return OTLPSpanExporter(endpoint=s.otlp_endpoint, compression=Compression.Gzip)


init_otelio(
    "my-service",
    "1.0.0",
    trace_exporters=[{"name": "otlp", "factory": _gzip_traces}],  # OTELIO_TARGET=otlp now uses gzip
)
```

The last factory registered for a name wins.

---

## 7. Gotchas

- **The name must be registered.** `OTELIO_TARGET=<name>` must match a built-in (`otlp` /
  `azure`) or a name you passed to `init_otelio`, or it raises
  `ValueError: No trace exporter registered for …`.
- **Register both signals.** One name needs both a trace factory and a log factory; otelio
  builds an exporter for each signal from the same `OTELIO_TARGET`.
- **The factory's deps are yours.** otelio only depends on the SDKs for `otlp` and `azure`.
  Whatever exporter you import in your factory, add it to *your* project's dependencies.
- **Build, don't wrap.** Return a bare exporter from the factory — otelio wraps it in the
  appropriate processor (`BatchSpanProcessor` / `BatchLogRecordProcessor`) itself. Don't
  return a processor.
- **Keep factories cheap and side-effect-free.** They run once during `init_otelio`. Read
  from `Settings` (or your own env vars) inside the factory; don't do network I/O there.
- **`OTELIO_CONSOLE` is independent.** It adds a console *span* exporter on top of whatever
  target you select (see the [README](../README.md#configuration)); it doesn't replace it.

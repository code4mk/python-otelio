# otelio — Custom Exporters

`otelio` ships three built-in export targets — `otlp` (SigNoz / any OTLP-gRPC collector),
`otlp-http` (any OTLP/HTTP-protobuf collector) and `azure` (App Insights) — selected with
the `OTELIO_TARGET` env var. If you need a different backend (Loki, a vendor SaaS endpoint
with custom auth, a console exporter, a vendor SDK, …) you can **register your own exporter
without modifying otelio** and select it the same way: `OTELIO_TARGET=<your-name>`.

> Public API reference and the built-in config live in the [README](../README.md). This doc
> is the "I need a backend otelio doesn't ship" companion.

---

## Table of contents

1. [Built-in targets](#1-built-in-targets)
2. [How it works](#2-how-it-works)
3. [Register your exporter](#3-register-your-exporter)
4. [Select it from the environment](#4-select-it-from-the-environment)
5. [Full example — OTLP/HTTP with custom auth headers](#5-full-example--otlphttp-with-custom-auth-headers)
6. [Overriding a built-in target](#6-overriding-a-built-in-target)
7. [Gotchas](#7-gotchas)

---

## 1. Built-in targets

otelio ships **three** export targets out of the box. You select one with `OTELIO_TARGET`;
no registration needed. All cover **traces and logs**.

| `OTELIO_TARGET` | Backend | Transport | Reads from | Extra dependency |
| --- | --- | --- | --- | --- |
| `otlp` *(default)* | Any OTLP collector — SigNoz, Grafana, Jaeger, … | **OTLP / gRPC** | `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4317`) | bundled |
| `otlp-http` | Any OTLP collector over HTTP | **OTLP / HTTP-protobuf** | `OTEL_EXPORTER_OTLP_ENDPOINT` (default `http://localhost:4318`, `/v1/traces` + `/v1/logs` appended) | bundled |
| `azure` | **Azure Application Insights** | Azure Monitor SDK | `APPLICATIONINSIGHTS_CONNECTION_STRING` | `azure-monitor-opentelemetry-exporter` |

The rest of this doc is only needed when you want a target these three don't cover (Loki, a
vendor SaaS endpoint needing custom auth headers, a console exporter, a vendor SDK, …).

---

## 2. How it works

Internally, otelio keeps a **registry** mapping a target *name* to an exporter *factory*.
The three built-ins above (`otlp`, `otlp-http` and `azure`) are just pre-registered entries. When
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
import os

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

# A vendor SaaS OTLP/HTTP endpoint that needs an API-key header — the built-in
# `otlp-http` target doesn't expose custom headers, so register a tuned variant.
_HEADERS = {"x-api-key": os.environ["VENDOR_API_KEY"]}


def build_saas_traces(s: Settings):
    return OTLPSpanExporter(endpoint=f"{s.otlp_endpoint}/v1/traces", headers=_HEADERS)


def build_saas_logs(s: Settings):
    return OTLPLogExporter(endpoint=f"{s.otlp_endpoint}/v1/logs", headers=_HEADERS)


init_otelio(
    "my-service",
    "1.0.0",
    trace_exporters=[{"name": "otlp-saas", "factory": build_saas_traces}],
    log_exporters=[{"name": "otlp-saas", "factory": build_saas_logs}],
)
```

You picked the name `otlp-saas`. It's case-insensitive (stored lowercased), and it's what
you'll set `OTELIO_TARGET` to. Each list can hold several entries if you want multiple
targets selectable by env.

> Register a trace and/or a log factory under your name. `OTELIO_TARGET` selects the
> exporters for both signals at once; if a chosen target has no factory for a given signal,
> otelio raises a clear `ValueError` listing the known targets.
>
> To send the two signals to **different** backends, set `OTELIO_TRACE_TARGET` and/or
> `OTELIO_LOG_TARGET` — each overrides `OTELIO_TARGET` for that one signal. In that case a
> name only needs a factory for the signal it's selected for (e.g. a logs-only target needs
> no trace factory).

The object shape is typed — import `TraceExporterEntry` / `LogExporterEntry` from `otelio`
if you want your editor to check it.

---

## 4. Select it from the environment

Nothing in your code changes per environment — only the env var:

```bash
# .env
OTELIO_TARGET=otlp-saas
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.vendor.example
```

Local can stay on the built-in gRPC `otlp`, staging can use your `otlp-saas`, and so on —
purely by flipping `OTELIO_TARGET`.

---

## 5. Full example — OTLP/HTTP with custom auth headers

A complete, runnable shape. Plain OTLP/HTTP is built in as `otlp-http`; this variant adds an
auth header the built-in factory doesn't expose — the common reason to register your own.

```python
# main.py
import os

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from otelio import Settings, init_otelio

_HEADERS = {"x-api-key": os.environ["VENDOR_API_KEY"]}


def _traces(s: Settings):
    return OTLPSpanExporter(endpoint=f"{s.otlp_endpoint}/v1/traces", headers=_HEADERS)


def _logs(s: Settings):
    return OTLPLogExporter(endpoint=f"{s.otlp_endpoint}/v1/logs", headers=_HEADERS)


init_otelio(
    "my-service",
    "1.0.0",
    trace_exporters=[{"name": "otlp-saas", "factory": _traces}],
    log_exporters=[{"name": "otlp-saas", "factory": _logs}],
)
```

```bash
# .env
OTELIO_TARGET=otlp-saas
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.vendor.example
```

The OTLP/HTTP exporter is already an otelio dependency, so there's nothing extra to install —
and you're exporting with custom auth and zero changes to otelio.

---

## 6. Overriding a built-in target

Registering under an existing name (`otlp`, `otlp-http` or `azure`) **replaces** that built-in — useful
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
  `otlp-http` / `azure`) or a name you passed to `init_otelio`, or it raises
  `ValueError: No trace exporter registered for …`.
- **Register both signals.** One name needs both a trace factory and a log factory; otelio
  builds an exporter for each signal from the same `OTELIO_TARGET`.
- **The factory's deps are yours.** otelio bundles the SDKs for `otlp` and `otlp-http`, and pulls in `azure` via the `[azure]` extra.
  Whatever exporter you import in your factory, add it to *your* project's dependencies.
- **Build, don't wrap.** Return a bare exporter from the factory — otelio wraps it in the
  appropriate processor (`BatchSpanProcessor` / `BatchLogRecordProcessor`) itself. Don't
  return a processor.
- **Keep factories cheap and side-effect-free.** They run once during `init_otelio`. Read
  from `Settings` (or your own env vars) inside the factory; don't do network I/O there.
- **`OTELIO_CONSOLE` is independent.** It adds a console *span* exporter on top of whatever
  target you select (see the [README](../README.md#configuration)); it doesn't replace it.

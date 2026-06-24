# Changelog

All notable changes to **otelio** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.3] - 2026-06-24

### Added

- Per-signal exporter selection. `OTELIO_TARGET` stays the global default; new
  `OTELIO_TRACE_TARGET` / `OTELIO_LOG_TARGET` override the target for traces / logs
  individually, so the two signals can go to different backends. Each falls back to
  `OTELIO_TARGET` when unset.
- Per-signal OTLP endpoints (OTel standard names). `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
  / `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` override `OTEL_EXPORTER_OTLP_ENDPOINT` for traces /
  logs individually, allowing two separate OTLP collectors. Each falls back to the global
  endpoint when unset.

### Changed

- `build_trace_exporter` / `build_log_exporter` now resolve from the per-signal target,
  and OTLP exporters use the per-signal endpoint. Exporter `ValueError` messages name the
  offending per-signal target and the env vars that set it.
- Documented the global-vs-per-signal model in the README configuration table and the
  usage guide.

[0.0.3]: https://github.com/code4mk/python-otelio/releases/tag/v0.0.3

## [0.0.2] - 2026-06-20

### Added

- `otel_set_span_status(status, message=None, span=None)` — set a span's `StatusCode`
  (`UNSET` / `OK` / `ERROR`) with an optional description. `StatusCode` is now re-exported
  from the `otelio` package.
- Pluggable exporter registry: `init_otelio` accepts `trace_exporters` / `log_exporters`
  to register custom exporters inline (lists of `{"name", "factory"}`), selectable via
  `OTELIO_TARGET`. Built-in `otlp` (gRPC) and `azure` targets are now pre-registered
  entries. Exports `Settings`, `TraceExporterEntry`, and `LogExporterEntry`.
- `OTELIO_CONSOLE` — when truthy, attach a `SimpleSpanProcessor` + `ConsoleSpanExporter`
  alongside the batch exporter so spans print to stdout for local debugging.
- Custom resource attributes via `init_otelio`.
- `docs/custom-exporter.md` documenting built-in targets, `OTELIO_CONSOLE`, and custom
  exporters.

### Changed

- Renamed the `DEPLOYMENT_ENVIRONMENT` env var to `OTELIO_ENVIRONMENT` for consistency
  with the `OTELIO_*` prefix. The `deployment.environment` resource attribute key is
  unchanged.
- Pinned OpenTelemetry to 1.40 for Azure exporter compatibility.

### Fixed

- Forward Loguru `extra` fields as OTel log attributes.

[0.0.2]: https://github.com/code4mk/python-otelio/releases/tag/v0.0.2

## [0.0.1] - 2026-06-20

### Added

- `init_otelio(...)` — one-call bootstrap of the tracer + logger providers, the Loguru
  bridge, and an `atexit` flush hook.
- Span helpers: `otel_span`, `otel_current_span`, `otel_get_tracer`.
- Attribute / event helpers: `otel_set_attributes`, `otel_add_event`.
- Context propagation helpers: `otel_inject_headers`, `otel_context_from_headers`.
- Baggage helpers: `otel_set_baggage`, `otel_get_baggage`, `otel_get_all_baggage`.
- OTLP/gRPC exporter (core install) and optional Azure Application Insights exporter
  (`otelio[azure]`), selected at runtime via the `OTELIO_TARGET` environment variable.
- Automatic correlation of Loguru log records to the active `trace_id` / `span_id`.

[0.0.1]: https://github.com/code4mk/python-otelio/releases/tag/v0.0.1

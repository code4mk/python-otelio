# Changelog

All notable changes to **otelio** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

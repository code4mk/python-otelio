"""
Bridge Loguru into the OpenTelemetry logs pipeline.

Loguru stays the single logging API for the app; every record is mirrored to an
OTel ``LoggingHandler`` (so logs are exported and correlated to the active span)
while a patcher stamps ``trace_id`` / ``span_id`` onto the console line.
"""

import logging
import sys
from typing import TYPE_CHECKING

from loguru import logger
from opentelemetry import trace
from opentelemetry.context import attach, detach
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.trace import (
    NonRecordingSpan,
    SpanContext,
    TraceFlags,
    set_span_in_context,
)

if TYPE_CHECKING:
    from loguru import Message

_LOGURU_TO_STD = {
    "TRACE": 5,
    "DEBUG": 10,
    "INFO": 20,
    "SUCCESS": 25,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


def _trace_patcher(record: dict) -> None:
    ctx = trace.get_current_span().get_span_context()
    if ctx and ctx.trace_id:
        record["extra"]["trace_id"] = format(ctx.trace_id, "032x")
        record["extra"]["span_id"] = format(ctx.span_id, "016x")
    else:
        record["extra"]["trace_id"] = "-"
        record["extra"]["span_id"] = "-"


def setup_loguru(
    logger_provider: LoggerProvider,
    console_level: str = "INFO",
    export_level: str = "DEBUG",
) -> None:
    """Reconfigure Loguru with a console sink and an OTel-export sink."""
    otel_handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)

    def _otel_sink(message: "Message") -> None:
        r = message.record
        std = logging.LogRecord(
            name=r["name"] or "otelio",
            level=_LOGURU_TO_STD.get(r["level"].name, 20),
            pathname=r["file"].path,
            lineno=r["line"],
            msg=r["message"],
            args=(),
            exc_info=r["exception"],  # loguru's (type, value, tb) namedtuple
            func=r["function"],
        )
        # Forward Loguru's structured fields (logger.info(msg, k=v) / logger.bind)
        # onto the std record so OTel's LoggingHandler emits them as log
        # attributes. trace_id/span_id are skipped: they're correlated via the
        # span context attached below, not as duplicate attributes.
        for key, value in r["extra"].items():
            if key not in ("trace_id", "span_id"):
                setattr(std, key, value)
        # enqueue=True runs this on Loguru's writer thread, where the OTel
        # contextvar is empty — so re-attach the span context the patcher
        # captured (on the originating thread) before emitting, otherwise the
        # exported record loses its trace_id/span_id.
        tid = r["extra"].get("trace_id")
        sid = r["extra"].get("span_id")
        token = None
        if tid and tid != "-":
            span_ctx = SpanContext(
                trace_id=int(tid, 16),
                span_id=int(sid, 16),
                is_remote=False,
                trace_flags=TraceFlags(TraceFlags.SAMPLED),
            )
            token = attach(set_span_in_context(NonRecordingSpan(span_ctx)))
        try:
            otel_handler.emit(std)  # backend; span context attached here
        finally:
            if token is not None:
                detach(token)

    logger.remove()  # drop loguru's default stderr sink
    logger.configure(patcher=_trace_patcher)
    logger.add(
        sys.stderr,
        level=console_level,
        format="<green>{time:HH:mm:ss.SSS}</green> | {level: <8} | "
        "trace={extra[trace_id]} | {name}:{line} - {message}",
    )
    logger.add(_otel_sink, level=export_level, enqueue=True)

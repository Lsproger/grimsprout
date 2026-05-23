"""Logging setup (loguru) + stdlib intercept (aiogram, apscheduler, motor)."""

from __future__ import annotations

import logging
import sys

from loguru import logger


class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        # Prepend the stdlib logger name so intercepted library messages are
        # identifiable (e.g. "[httpx] HTTP Request: ..." instead of the generic
        # "logging:callHandlers" source that loguru would otherwise show).
        msg = f"[{record.name}] {record.getMessage()}"
        logger.opt(depth=depth, exception=record.exc_info).log(level, msg)


# Libraries whose DEBUG output is too noisy (low-level I/O, heartbeats, etc.).
# They are silenced to WARNING regardless of the app log level.
_NOISY_LOGGERS = (
    "pymongo",
    "pymongo.topology",
    "pymongo.connection",
    "pymongo.serverSelection",
    "asyncio",
    "aiohttp",
    "aiohttp.access",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
)


def setup_logging(level: str = "INFO", as_json: bool = False) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        serialize=as_json,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    # Route stdlib logging (aiogram, apscheduler, motor, httpx) into loguru.
    logging.basicConfig(handlers=[_InterceptHandler()], level=level, force=True)
    for name in ("aiogram", "aiogram.event", "aiogram.dispatcher", "apscheduler", "httpx", "motor"):
        lg = logging.getLogger(name)
        lg.handlers = [_InterceptHandler()]
        lg.propagate = False
        lg.setLevel(level)
    # Suppress chatty library loggers — keep only WARNING and above.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

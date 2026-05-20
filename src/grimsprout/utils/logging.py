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
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


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
    # route stdlib logging (aiogram, apscheduler, motor, httpx) into loguru
    logging.basicConfig(handlers=[_InterceptHandler()], level=level, force=True)
    for name in ("aiogram", "aiogram.event", "aiogram.dispatcher", "apscheduler", "httpx", "motor"):
        lg = logging.getLogger(name)
        lg.handlers = [_InterceptHandler()]
        lg.propagate = False
        lg.setLevel(level)

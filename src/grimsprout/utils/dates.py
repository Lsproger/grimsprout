"""Date helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime


def today_iso() -> str:
    return date.today().isoformat()


def utcnow() -> datetime:
    return datetime.now(tz=UTC)

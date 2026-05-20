"""Pydantic models for Mongo documents."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["admin", "editor", "publisher", "viewer"]
ScheduleKind = Literal["water", "fertilize", "repot"]


class User(BaseModel):
    tg_id: int
    role: Role
    display_name: str = ""
    added_by: int | None = None
    added_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class Session(BaseModel):
    tg_id: int
    current_plant_id: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class Schedule(BaseModel):
    plant_id: str
    kind: ScheduleKind
    interval_days: int
    next_run_at: datetime
    owner_tg_id: int
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class AuditEntry(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    tg_id: int
    action: str
    payload: dict = Field(default_factory=dict)
    file: str | None = None
    commit_sha: str | None = None

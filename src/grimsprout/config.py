"""Configuration loader: YAML + .env via pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramConfig(BaseModel):
    token_env: str = "BOT_TOKEN"
    bootstrap_admin_tg_id: int
    parse_mode: str = "HTML"


class RepositoryConfig(BaseModel):
    """Repository config.

    ``path`` may be either a local filesystem path or a git URL
    (SSH or HTTPS). When a URL is given, the repo is cloned into
    ``clone_dir/<repo-name>`` on bootstrap and all bot operations target
    the dedicated ``work_branch`` (never ``git_branch`` directly).

    ``local_path`` is populated at runtime by
    :func:`grimsprout.services.repo_bootstrap.ensure_workdir` and exposes
    the resolved on-disk working tree.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    path: str
    images_dir: str = "images"
    template_file: str = "_template.md"
    git_remote: str = "origin"
    git_branch: str = "master"
    work_branch: str = "grimsprout/auto"
    clone_dir: Path = Path("var/repo")
    https_token_env: str = "GIT_HTTPS_TOKEN"
    github_token_env: str = "GITHUB_TOKEN"

    # Populated at runtime by repo_bootstrap.ensure_workdir.
    local_path: Path | None = None

    def require_local_path(self) -> Path:
        if self.local_path is None:
            raise RuntimeError("repository.local_path is not set; call repo_bootstrap.ensure_workdir() first")
        return self.local_path


class MongoConfig(BaseModel):
    uri_env: str = "MONGO_URI"
    database: str = "grimsprout"


class LLMConfig(BaseModel):
    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://openwebui.lab.kekpuk.top:11434"
    model: str = "gemma3:4b"
    temperature: float = 0.1
    timeout_sec: int = 30
    system_prompt_file: Path
    intent_schema_file: Path


class SchedulingConfig(BaseModel):
    timezone: str = "Europe/Warsaw"
    default_snooze_days: int = 1


class LoggingConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    level: str = "INFO"
    json_format: bool = Field(default=False, alias="json")


class AppConfig(BaseModel):
    telegram: TelegramConfig
    repository: RepositoryConfig
    mongo: MongoConfig
    llm: LLMConfig
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class _EnvSettings(BaseSettings):
    """Loads BOT_TOKEN / MONGO_URI / MONGO_TEST_URI from environment or .env."""

    BOT_TOKEN: str = ""
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_TEST_URI: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def _config_path() -> Path:
    env = os.environ.get("GRIMSPROUT_CONFIG")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parents[2] / "config" / "config.yaml").resolve()


def _resolve_env(raw: dict) -> dict:
    """Merge the active environment profile into each config section.

    The active env name is resolved (highest priority first) from:
    1. ``GRIMSPROUT_ENV`` OS environment variable
    2. Top-level ``env`` key in the YAML

    For each section: if the section dict contains a key matching the active
    env name whose value is a dict, that sub-dict is merged over the shared
    flat fields (non-dict values in the section).  Sections that do not
    contain the active env key pass through unchanged.

    If no env name is found the raw dict is returned as-is for full backwards
    compatibility with flat config files.
    """
    env_name: str | None = os.environ.get("GRIMSPROUT_ENV") or raw.get("env")
    if not env_name:
        return raw

    result: dict = {}
    for key, value in raw.items():
        if key == "env":
            continue
        if isinstance(value, dict) and isinstance(value.get(env_name), dict):
            flat = {k: v for k, v in value.items() if not isinstance(v, dict)}
            result[key] = {**flat, **value[env_name]}
        else:
            result[key] = value
    return result


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    path = _config_path()
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return AppConfig.model_validate(_resolve_env(raw))


@lru_cache(maxsize=1)
def load_env() -> _EnvSettings:
    return _EnvSettings()

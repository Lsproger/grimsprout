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
    path: Path
    images_dir: str = "images"
    template_file: str = "_template.md"
    git_remote: str = "origin"
    git_branch: str = "master"


class MongoConfig(BaseModel):
    uri_env: str = "MONGO_URI"
    database: str = "grimsprout"


class LLMConfig(BaseModel):
    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "llama3"
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
    """Loads BOT_TOKEN / MONGO_URI from environment or .env."""

    BOT_TOKEN: str = ""
    MONGO_URI: str = "mongodb://localhost:27017"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def _config_path() -> Path:
    env = os.environ.get("GRIMSPROUT_CONFIG")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parents[2] / "config" / "config.yaml").resolve()


@lru_cache(maxsize=1)
def load_config() -> AppConfig:
    path = _config_path()
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return AppConfig.model_validate(raw)


@lru_cache(maxsize=1)
def load_env() -> _EnvSettings:
    return _EnvSettings()

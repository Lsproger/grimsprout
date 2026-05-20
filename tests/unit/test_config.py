"""Tests for grimsprout.config."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from grimsprout import config as cfg_module

VALID_YAML = textwrap.dedent(
    """\
    telegram:
      token_env: BOT_TOKEN
      bootstrap_admin_tg_id: 42
      parse_mode: HTML

    repository:
      path: /tmp/trava

    mongo:
      uri_env: MONGO_URI
      database: grimsprout

    llm:
      provider: ollama
      base_url: http://localhost:11434
      model: llama3
      temperature: 0.1
      timeout_sec: 30
      system_prompt_file: prompts/system.md
      intent_schema_file: prompts/schema.json

    scheduling:
      timezone: Europe/Warsaw
      default_snooze_days: 1

    logging:
      level: INFO
      json: true
    """
)


def _write_config(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_config_via_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = _write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()

    assert cfg.telegram.bootstrap_admin_tg_id == 42
    assert cfg.repository.path == "/tmp/trava"
    assert cfg.repository.work_branch == "grimsprout/auto"  # default
    assert cfg.mongo.database == "grimsprout"
    assert cfg.scheduling.timezone == "Europe/Warsaw"


def test_logging_alias_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = _write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()
    assert cfg.logging.json_format is True


def test_load_config_missing_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = textwrap.dedent(
        """\
        telegram:
          token_env: BOT_TOKEN
        """
    )
    cfg_path = _write_config(tmp_path, bad)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        cfg_module.load_config()


def test_repository_require_local_path() -> None:
    repo = cfg_module.RepositoryConfig(path="/tmp/x")
    with pytest.raises(RuntimeError):
        repo.require_local_path()

    repo.local_path = Path("/tmp/x")
    assert repo.require_local_path() == Path("/tmp/x")


def test_load_env_reads_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Avoid picking up the real .env from cwd.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_TOKEN", "secret-token")
    monkeypatch.setenv("MONGO_URI", "mongodb://test:27017")

    env = cfg_module.load_env()
    assert env.BOT_TOKEN == "secret-token"
    assert env.MONGO_URI == "mongodb://test:27017"

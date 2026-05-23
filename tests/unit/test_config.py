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


# ---------------------------------------------------------------------------
# Env-profile branching tests
# ---------------------------------------------------------------------------

VALID_YAML_ENV = textwrap.dedent(
    """\
    env: local

    telegram:
      bootstrap_admin_tg_id: 42
      parse_mode: HTML
      local:
        token_env: BOT_TOKEN_DEV
      prod:
        token_env: BOT_TOKEN

    repository:
      images_dir: images
      template_file: _template.md
      git_remote: origin
      git_branch: master
      work_branch: grimsprout/auto
      clone_dir: var/repo
      local:
        path: /tmp/trava
      prod:
        path: https://github.com/example/trava.git

    mongo:
      local:
        uri_env: MONGO_URI
        database: grimsprout_dev
      prod:
        uri_env: MONGO_URI
        database: grimsprout

    llm:
      provider: ollama
      temperature: 0.1
      timeout_sec: 30
      system_prompt_file: prompts/system.md
      intent_schema_file: prompts/schema.json
      local:
        base_url: http://localhost:11434
        model: llama3
      prod:
        base_url: http://ollama.prod:11434
        model: llama3

    scheduling:
      timezone: Europe/Warsaw
      default_snooze_days: 1

    logging:
      local:
        level: DEBUG
        json: false
      prod:
        level: INFO
        json: false
    """
)


def test_env_profile_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = _write_config(tmp_path, VALID_YAML_ENV)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()

    assert cfg.telegram.token_env == "BOT_TOKEN_DEV"  # local profile
    assert cfg.mongo.database == "grimsprout_dev"  # local profile
    assert cfg.logging.level == "DEBUG"  # local profile
    assert cfg.repository.path == "/tmp/trava"  # local profile


def test_env_profile_override_via_envvar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = _write_config(tmp_path, VALID_YAML_ENV)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))
    monkeypatch.setenv("GRIMSPROUT_ENV", "prod")  # override local → prod

    cfg = cfg_module.load_config()

    assert cfg.telegram.token_env == "BOT_TOKEN"  # prod profile
    assert cfg.mongo.database == "grimsprout"  # prod profile
    assert cfg.logging.level == "INFO"  # prod profile


def test_env_section_without_profile_passes_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Flat sections without an env sub-key are passed through unchanged."""
    cfg_path = _write_config(tmp_path, VALID_YAML_ENV)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()

    # scheduling has no env sub-keys → flat values pass through
    assert cfg.scheduling.timezone == "Europe/Warsaw"
    # flat fields in a section with env sub-keys are preserved as defaults
    assert cfg.repository.work_branch == "grimsprout/auto"


def test_env_key_absent_backwards_compat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Old flat config without an 'env' key loads unchanged."""
    cfg_path = _write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()

    assert cfg.telegram.token_env == "BOT_TOKEN"
    assert cfg.mongo.database == "grimsprout"


def test_llm_config_threshold_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig carries sensible threshold defaults when not specified in YAML."""
    cfg_path = _write_config(tmp_path, VALID_YAML)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()

    assert cfg.llm.confidence_threshold == 0.5
    assert cfg.llm.mutate_confidence_threshold == 0.75


def test_llm_config_threshold_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMConfig threshold fields can be overridden in YAML."""
    custom = VALID_YAML.replace(
        "  timeout_sec: 30",
        "  timeout_sec: 30\n  confidence_threshold: 0.6\n  mutate_confidence_threshold: 0.9",
    )
    cfg_path = _write_config(tmp_path, custom)
    monkeypatch.setenv("GRIMSPROUT_CONFIG", str(cfg_path))

    cfg = cfg_module.load_config()

    assert cfg.llm.confidence_threshold == 0.6
    assert cfg.llm.mutate_confidence_threshold == 0.9

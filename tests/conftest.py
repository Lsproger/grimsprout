"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import git
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_trava(tmp_path: Path) -> Path:
    """Copy the fixture plant catalog into a fresh tmp dir."""
    dst = tmp_path / "trava"
    shutil.copytree(FIXTURES_DIR / "plants", dst)
    return dst


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Initialize an empty git repo with one initial commit on `master`."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = git.Repo.init(repo_path, initial_branch="master")
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    readme = repo_path / "README.md"
    readme.write_text("# test\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("init")
    return repo_path


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    """Create a bare git repo to act as `origin`."""
    remote_path = tmp_path / "remote.git"
    git.Repo.init(remote_path, bare=True, initial_branch="master")
    return remote_path


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Iterator[None]:
    """Ensure config loaders don't bleed state between tests."""
    from grimsprout import config as cfg_module

    cfg_module.load_config.cache_clear()
    cfg_module.load_env.cache_clear()
    yield
    cfg_module.load_config.cache_clear()
    cfg_module.load_env.cache_clear()


# ---- Mongo integration fixtures ----------------------------------------------------


def _mongo_uri() -> str | None:
    uri = os.environ.get("MONGO_TEST_URI")
    if not uri:
        # Fall back to .env via the same pydantic-settings loader the app uses.
        from grimsprout.config import load_env

        uri = load_env().MONGO_TEST_URI or None
    return uri


@pytest.fixture
async def mongo_db() -> AsyncIterator:
    """Yield a fresh, unique AsyncIOMotorDatabase. Skips if MONGO_TEST_URI is not set."""
    uri = _mongo_uri()
    if not uri:
        pytest.skip("MONGO_TEST_URI not set; skipping mongo integration test")

    from motor.motor_asyncio import AsyncIOMotorClient

    client: AsyncIOMotorClient = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
    try:
        # ping to fail fast if the service is unreachable
        await client.admin.command("ping")
    except Exception as exc:  # pragma: no cover - depends on env
        client.close()
        pytest.skip(f"MongoDB at {uri} is not reachable: {exc}")

    db_name = f"grimsprout_test_{uuid.uuid4().hex[:12]}"
    db = client[db_name]
    try:
        yield db
    finally:
        if not os.environ.get("KEEP_TEST_DB"):
            await client.drop_database(db_name)
        else:
            print(f"keeping test db: {db_name}")
        client.close()

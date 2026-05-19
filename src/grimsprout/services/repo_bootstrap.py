"""Repository bootstrap: resolve ``repository.path`` to an on-disk working tree.

Behaviour:
- If ``path`` is a local filesystem path, validate it is an existing git repo.
- If ``path`` is a git URL (SSH or HTTPS), clone it into
  ``<project_root>/<clone_dir>/<repo-name>`` (only when missing). Existing
  clones are opened as-is — we never run ``fetch``/``pull``/``reset`` here
  (see docs/spec/05-git-flow.md §5.5).

After the working tree is open, ensure the configured ``work_branch`` exists
and is checked out. The branch is created from ``origin/<git_branch>`` (or
local ``git_branch`` as fallback) the first time. We never write to
``git_branch`` directly — see ADR 0006.

Auth:
- SSH URLs: pass through unmodified; relies on the host's ``ssh-agent`` /
  ``~/.ssh/config`` (``GIT_SSH_COMMAND`` is also honoured by GitPython).
- HTTPS URLs: if the ``https_token_env`` env var is set, the token is
  injected into the clone URL once and the remote's ``origin`` URL is then
  rewritten to the original (token-free) value so the secret is never
  persisted to ``.git/config``. ``GIT_TERMINAL_PROMPT=0`` is exported to
  prevent interactive prompts on later push.
"""
from __future__ import annotations

import os
from pathlib import Path

import git
from loguru import logger

from grimsprout.config import AppConfig
from grimsprout.utils.errors import GrimSproutError
from grimsprout.utils.git_url import GitUrl, parse_git_url


class RepoBootstrapError(GrimSproutError):
    pass


def project_root() -> Path:
    """Return the grimsprout project root (the directory containing ``src/``)."""
    return Path(__file__).resolve().parents[3]


def _resolve_clone_target(cfg: AppConfig, url: GitUrl) -> Path:
    clone_dir = cfg.repository.clone_dir
    if not clone_dir.is_absolute():
        clone_dir = project_root() / clone_dir
    return clone_dir / url.repo_dir_name


def _build_https_clone_url(url: GitUrl, token: str) -> str:
    # x-access-token works for GitHub fine-grained and classic PATs; for other
    # hosts it is still a valid Basic-auth user that gets ignored when the
    # password (token) is what authenticates.
    return f"https://x-access-token:{token}@{url.host}/{url.owner}/{url.name}.git"


def _clone(cfg: AppConfig, url: GitUrl, target: Path) -> git.Repo:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Suppress interactive credential prompts on any future operation.
    os.environ.setdefault("GIT_TERMINAL_PROMPT", "0")

    if url.scheme == "ssh":
        logger.info("cloning {} via SSH → {}", url.raw, target)
        try:
            return git.Repo.clone_from(url.raw, target)
        except git.GitCommandError as exc:
            raise RepoBootstrapError(
                f"SSH clone failed for {url.raw}: {exc.stderr or exc}. "
                "Ensure your ssh-agent has a key authorised for the host."
            ) from exc

    # https
    token = os.environ.get(cfg.repository.https_token_env, "").strip()
    if not token:
        # Try a plain clone first (works for public repos / cached creds).
        logger.info("cloning {} via HTTPS (no token) → {}", url.raw, target)
        try:
            return git.Repo.clone_from(url.raw, target)
        except git.GitCommandError as exc:
            raise RepoBootstrapError(
                f"HTTPS clone failed for {url.raw} and "
                f"${cfg.repository.https_token_env} is not set: {exc.stderr or exc}"
            ) from exc

    logger.info("cloning {} via HTTPS (token) → {}", url.raw, target)
    auth_url = _build_https_clone_url(url, token)
    try:
        repo = git.Repo.clone_from(auth_url, target)
    except git.GitCommandError as exc:
        raise RepoBootstrapError(
            f"HTTPS clone failed for {url.raw}: {exc.stderr or exc}"
        ) from exc
    # Rewrite remote so the token is not persisted in .git/config.
    try:
        repo.remote("origin").set_url(url.raw)
    except git.GitCommandError as exc:  # pragma: no cover - defensive
        raise RepoBootstrapError(f"failed to scrub token from origin URL: {exc}") from exc
    return repo


def _validate_local(path: Path) -> git.Repo:
    if not path.exists():
        raise RepoBootstrapError(f"repository.path does not exist: {path}")
    if not path.is_dir():
        raise RepoBootstrapError(f"repository.path is not a directory: {path}")
    try:
        return git.Repo(path)
    except git.InvalidGitRepositoryError as exc:
        raise RepoBootstrapError(f"not a git repository: {path}") from exc
    except git.NoSuchPathError as exc:
        raise RepoBootstrapError(f"path not found: {path}") from exc


def _ensure_work_branch(repo: git.Repo, base_branch: str, work_branch: str) -> None:
    if repo.head.is_detached:
        raise RepoBootstrapError(
            f"HEAD is detached at {repo.head.commit.hexsha[:10]}; "
            "switch to a branch manually before starting the bot."
        )

    existing = {h.name for h in repo.heads}
    if work_branch in existing:
        if repo.active_branch.name != work_branch:
            logger.info("checking out existing work branch '{}'", work_branch)
            repo.git.checkout(work_branch)
        return

    # Create work_branch from origin/<base> if available, else local <base>.
    start_point: str | None = None
    try:
        remote_ref = f"origin/{base_branch}"
        repo.commit(remote_ref)
        start_point = remote_ref
    except (git.BadName, ValueError):
        if base_branch in existing:
            start_point = base_branch

    if start_point is None:
        # Empty repo or unknown base — just create from current HEAD if any.
        try:
            repo.head.commit  # noqa: B018
            start_point = "HEAD"
        except (ValueError, git.BadName) as exc:
            raise RepoBootstrapError(
                f"cannot create work branch '{work_branch}': "
                f"base branch '{base_branch}' not found and repo has no commits"
            ) from exc

    logger.info("creating work branch '{}' from {}", work_branch, start_point)
    repo.git.checkout("-b", work_branch, start_point)


def ensure_workdir(cfg: AppConfig) -> Path:
    """Resolve ``cfg.repository.path`` to a ready-to-use working tree.

    Side effects:
    - Clones the repo if ``path`` is a URL and the local clone is missing.
    - Creates/checks out ``cfg.repository.work_branch``.
    - Sets ``cfg.repository.local_path`` to the resolved on-disk path.
    """
    url = parse_git_url(cfg.repository.path)

    if url is None:
        local = Path(cfg.repository.path).expanduser().resolve()
        repo = _validate_local(local)
    else:
        target = _resolve_clone_target(cfg, url)
        if target.exists():
            logger.info("opening existing clone at {}", target)
            repo = _validate_local(target)
        else:
            repo = _clone(cfg, url, target)
        local = Path(repo.working_tree_dir or target).resolve()

    _ensure_work_branch(
        repo, base_branch=cfg.repository.git_branch, work_branch=cfg.repository.work_branch
    )

    cfg.repository.local_path = local
    logger.info(
        "repo ready: path={} branch={} (base={})",
        local,
        cfg.repository.work_branch,
        cfg.repository.git_branch,
    )
    return local

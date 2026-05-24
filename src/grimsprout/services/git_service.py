"""Git operations via GitPython.

Design notes:
- We never run `git add .`. Only explicit paths are staged.
- Before staging we verify that the repo has no unrelated staged or unmerged changes.
  Untracked files are allowed (user may be working on a new card).
- `.git/index.lock` is waited for up to 2 seconds.
"""

from __future__ import annotations

import time
from pathlib import Path

import git

from grimsprout.utils.errors import DirtyRepoError, GrimSproutError


class GitError(GrimSproutError):
    pass


def _wait_lock(repo_path: Path, timeout: float = 2.0) -> None:
    lock = repo_path / ".git" / "index.lock"
    deadline = time.monotonic() + timeout
    while lock.exists():
        if time.monotonic() > deadline:
            raise GitError(f".git/index.lock held > {timeout}s")
        time.sleep(0.1)


def _open(repo_path: Path) -> git.Repo:
    try:
        return git.Repo(repo_path)
    except Exception as exc:
        raise GitError(f"cannot open git repo at {repo_path}: {exc}") from exc


def _assert_clean_outside(repo: git.Repo, allowed: set[str]) -> None:
    """Ensure no unrelated staged or modified-tracked files exist."""
    # Staged changes (index vs HEAD) outside `allowed`
    try:
        diff_index = repo.index.diff("HEAD")
    except git.BadName:
        # Empty repo (no HEAD yet) - allow
        diff_index = []
    for d in diff_index:
        p = d.a_path or d.b_path
        if p and p not in allowed:
            raise DirtyRepoError(f"unrelated staged change: {p}")
    # Unstaged changes to tracked files outside `allowed`
    for d in repo.index.diff(None):
        p = d.a_path or d.b_path
        if p and p not in allowed:
            raise DirtyRepoError(f"unrelated modified tracked file: {p}")
    # Unmerged blobs => conflict
    if repo.index.unmerged_blobs():
        raise DirtyRepoError("repository has merge conflicts")


def add(repo_path: Path, paths: list[Path]) -> None:
    if not paths:
        return
    _wait_lock(repo_path)
    repo = _open(repo_path)
    rels: list[str] = []
    for p in paths:
        try:
            rels.append(str(p.resolve().relative_to(repo_path.resolve())))
        except ValueError as exc:
            raise GitError(f"path {p} is outside repo {repo_path}") from exc
    _assert_clean_outside(repo, allowed=set(rels))
    repo.index.add(rels)


def commit(repo_path: Path, message: str) -> str:
    _wait_lock(repo_path)
    repo = _open(repo_path)
    if not repo.index.diff("HEAD") and not _has_initial_commit_pending(repo):
        raise GitError("nothing staged to commit")
    return repo.index.commit(message).hexsha


def _has_initial_commit_pending(repo: git.Repo) -> bool:
    try:
        repo.head.commit  # noqa: B018
        return False
    except (ValueError, git.BadName):
        return True


def push(repo_path: Path, remote: str, branch: str, token: str = "") -> None:
    """Push ``branch`` to ``remote`` with upstream tracking.

    Only the bot's ``work_branch`` should ever be passed here — never the
    base branch. Caller is responsible for that policy.

    If ``token`` is provided and the remote URL is HTTPS, it is temporarily
    injected into the URL for the duration of the push, then removed.
    """
    _wait_lock(repo_path)
    repo = _open(repo_path)
    try:
        remote_obj = repo.remote(remote)
    except ValueError as exc:
        raise GitError(f"remote '{remote}' not configured") from exc

    original_url = remote_obj.url
    auth_url: str | None = None
    if token and original_url.startswith("https://"):
        # Strip any existing credentials from the URL before injecting token.
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(original_url)
        auth_url = urlunparse(
            parsed._replace(
                netloc=f"x-access-token:{token}@{parsed.hostname}{f':{parsed.port}' if parsed.port else ''}"
            )
        )
        remote_obj.set_url(auth_url)

    try:
        results = remote_obj.push(refspec=f"{branch}:{branch}", set_upstream=True)
    except git.GitCommandError as exc:
        raise GitError(f"git push failed: {exc.stderr or exc}") from exc
    finally:
        if auth_url is not None:
            remote_obj.set_url(original_url)

    for r in results:
        if r.flags & r.ERROR:
            raise GitError(f"push rejected for {r.local_ref}: {r.summary}")

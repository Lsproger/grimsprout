"""Git operations via GitPython.

Design notes:
- We never run `git add .`. Only explicit paths are staged.
- Before staging we verify that the repo has no unrelated staged or unmerged changes.
  Untracked files are allowed (user may be working on a new card).
- `.git/index.lock` is waited for up to 2 seconds.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import git

from grimsprout.utils.errors import DirtyRepoError, GrimSproutError


class GitError(GrimSproutError):
    pass


BOT_COMMIT_MARKER = "GrimSprout: tg_id="


def _to_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


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


def find_commit_by_short_sha(
    repo_path: Path,
    short_sha: str,
    branch: str,
    *,
    max_count: int | None = None,
    marker: str | None = None,
) -> git.Commit:
    """Find a unique commit in ``branch`` by SHA prefix.

    If ``marker`` is set, only commits containing that marker in the message
    are considered.
    """
    query = short_sha.strip().lower()
    if not query:
        raise GitError("empty short sha")
    if not re.fullmatch(r"[0-9a-f]+", query):
        raise GitError(f"invalid short sha: {short_sha}")

    _wait_lock(repo_path)
    repo = _open(repo_path)
    try:
        commits = list(repo.iter_commits(branch, max_count=max_count))
    except git.GitCommandError as exc:
        raise GitError(f"cannot read branch '{branch}': {exc.stderr or exc}") from exc

    matches: list[git.Commit] = []
    for commit in commits:
        commit_message = _to_text(commit.message)
        if marker and marker not in commit_message:
            continue
        if commit.hexsha.startswith(query):
            matches.append(commit)

    if not matches:
        raise GitError(f"commit not found for short sha: {short_sha}")
    if len(matches) > 1:
        choices = ", ".join(c.hexsha[:10] for c in matches[:5])
        raise GitError(f"ambiguous short sha '{short_sha}', matches: {choices}")
    return matches[0]


def revert_commit(repo_path: Path, commit_sha: str) -> str:
    """Revert a commit and return the new revert commit SHA."""
    _wait_lock(repo_path)
    repo = _open(repo_path)
    _assert_clean_outside(repo, allowed=set())

    try:
        commit = repo.commit(commit_sha)
    except Exception as exc:
        raise GitError(f"cannot resolve commit: {commit_sha}") from exc

    if len(commit.parents) > 1:
        raise GitError("revert for merge commits is not supported")

    try:
        repo.git.revert(commit.hexsha, no_edit=True)
    except git.GitCommandError as exc:
        # Best effort cleanup when revert stops on conflicts.
        try:
            repo.git.revert("--abort")
        except Exception:
            pass
        raise GitError(f"git revert failed: {exc.stderr or exc}") from exc

    return repo.head.commit.hexsha

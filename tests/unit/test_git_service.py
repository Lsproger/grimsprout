"""Tests for grimsprout.services.git_service."""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from grimsprout.services import git_service
from grimsprout.services.git_service import GitError
from grimsprout.utils.errors import DirtyRepoError


def _append_commit(repo_path: Path, rel_path: str, content: str, message: str) -> str:
    repo = git.Repo(repo_path)
    path = repo_path / rel_path
    path.write_text(content, encoding="utf-8")
    repo.index.add([rel_path])
    return repo.index.commit(message).hexsha


def _to_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).decode("utf-8", errors="replace")
    return str(value)


# ---- add ----------------------------------------------------------------------------


def test_add_stages_named_path(tmp_git_repo: Path) -> None:
    target = tmp_git_repo / "plant.md"
    target.write_text("# x\n", encoding="utf-8")

    git_service.add(tmp_git_repo, [target])

    repo = git.Repo(tmp_git_repo)
    staged = {d.a_path or d.b_path for d in repo.index.diff("HEAD")}
    assert "plant.md" in staged


def test_add_path_outside_repo_raises(tmp_git_repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")

    with pytest.raises(GitError):
        git_service.add(tmp_git_repo, [outside])


def test_add_empty_paths_is_noop(tmp_git_repo: Path) -> None:
    # Must not raise and must not touch the index.
    git_service.add(tmp_git_repo, [])


# ---- _assert_clean_outside (via add) ------------------------------------------------


def test_add_rejects_unrelated_staged_file(tmp_git_repo: Path) -> None:
    repo = git.Repo(tmp_git_repo)
    # Create + stage an unrelated file.
    unrelated = tmp_git_repo / "unrelated.md"
    unrelated.write_text("u", encoding="utf-8")
    repo.index.add(["unrelated.md"])

    target = tmp_git_repo / "plant.md"
    target.write_text("# x\n", encoding="utf-8")

    with pytest.raises(DirtyRepoError):
        git_service.add(tmp_git_repo, [target])


def test_add_rejects_unrelated_modified_tracked_file(tmp_git_repo: Path) -> None:
    # README.md is already tracked by the fixture. Modify it without staging.
    (tmp_git_repo / "README.md").write_text("# modified\n", encoding="utf-8")

    target = tmp_git_repo / "plant.md"
    target.write_text("# x\n", encoding="utf-8")

    with pytest.raises(DirtyRepoError):
        git_service.add(tmp_git_repo, [target])


def test_add_allows_unrelated_untracked_file(tmp_git_repo: Path) -> None:
    # New cards may already sit untracked next to ours — that's fine.
    (tmp_git_repo / "draft.md").write_text("draft", encoding="utf-8")

    target = tmp_git_repo / "plant.md"
    target.write_text("# x\n", encoding="utf-8")

    git_service.add(tmp_git_repo, [target])  # must not raise


# ---- commit -------------------------------------------------------------------------


def test_commit_with_staged_paths_returns_sha(tmp_git_repo: Path) -> None:
    target = tmp_git_repo / "plant.md"
    target.write_text("# x\n", encoding="utf-8")
    git_service.add(tmp_git_repo, [target])

    sha = git_service.commit(tmp_git_repo, "chore(auto): water x")

    assert isinstance(sha, str) and len(sha) == 40
    repo = git.Repo(tmp_git_repo)
    assert repo.head.commit.hexsha == sha
    assert _to_text(repo.head.commit.message).startswith("chore(auto): water x")


def test_commit_empty_index_raises(tmp_git_repo: Path) -> None:
    with pytest.raises(GitError):
        git_service.commit(tmp_git_repo, "noop")


# ---- _wait_lock ---------------------------------------------------------------------


def test_index_lock_held_raises(tmp_git_repo: Path) -> None:
    lock = tmp_git_repo / ".git" / "index.lock"
    lock.write_text("", encoding="utf-8")
    try:
        with pytest.raises(GitError):
            git_service.add(tmp_git_repo, [tmp_git_repo / "README.md"])
    finally:
        lock.unlink(missing_ok=True)


# ---- push -----------------------------------------------------------------------


def test_push_to_bare_remote(tmp_git_repo: Path, bare_remote: Path) -> None:
    repo = git.Repo(tmp_git_repo)
    repo.create_remote("origin", str(bare_remote))

    # Make a commit on a work branch and push it.
    work_branch = "grimsprout/auto"
    repo.git.checkout("-b", work_branch)
    plant = tmp_git_repo / "plant.md"
    plant.write_text("# new\n", encoding="utf-8")
    git_service.add(tmp_git_repo, [plant])
    sha = git_service.commit(tmp_git_repo, "chore(auto): test")

    git_service.push(tmp_git_repo, "origin", work_branch)

    # Use ls-remote from the non-bare repo to avoid safe.bareRepository restriction
    output = repo.git.ls_remote("origin", work_branch)
    pushed_sha = output.split()[0]
    assert pushed_sha == sha


def test_push_unknown_remote_raises(tmp_git_repo: Path) -> None:
    with pytest.raises(GitError):
        git_service.push(tmp_git_repo, "origin", "master")


def test_find_commit_by_short_sha_returns_unique_commit(tmp_git_repo: Path) -> None:
    sha = _append_commit(
        tmp_git_repo,
        "plant.md",
        "a",
        "chore(auto): photo x\n\nФото\nGrimSprout: tg_id=1",
    )

    commit = git_service.find_commit_by_short_sha(
        tmp_git_repo,
        sha[:10],
        "master",
        marker=git_service.BOT_COMMIT_MARKER,
    )

    assert commit.hexsha == sha


def test_find_commit_by_short_sha_not_found_raises(tmp_git_repo: Path) -> None:
    with pytest.raises(GitError):
        git_service.find_commit_by_short_sha(tmp_git_repo, "abcdef1", "master")


def test_find_commit_by_short_sha_ambiguous_raises(tmp_git_repo: Path) -> None:
    # Generate enough commits so at least two share the first hex char.
    commits: list[str] = []
    for i in range(20):
        commits.append(
            _append_commit(
                tmp_git_repo,
                f"file_{i}.md",
                f"{i}",
                f"chore(auto): note p{i}\n\ntext\nGrimSprout: tg_id=1",
            )
        )

    buckets: dict[str, int] = {}
    duplicate_prefix = ""
    for sha in commits:
        prefix = sha[:1]
        buckets[prefix] = buckets.get(prefix, 0) + 1
        if buckets[prefix] > 1:
            duplicate_prefix = prefix
            break
    assert duplicate_prefix

    with pytest.raises(GitError):
        git_service.find_commit_by_short_sha(tmp_git_repo, duplicate_prefix, "master")


def test_find_commit_by_short_sha_respects_marker(tmp_git_repo: Path) -> None:
    _append_commit(tmp_git_repo, "a.md", "a", "chore(auto): note a")
    bot_sha = _append_commit(
        tmp_git_repo,
        "b.md",
        "b",
        "chore(auto): note b\n\ntext\nGrimSprout: tg_id=77",
    )

    commit = git_service.find_commit_by_short_sha(
        tmp_git_repo,
        bot_sha[:10],
        "master",
        marker=git_service.BOT_COMMIT_MARKER,
    )

    assert commit.hexsha == bot_sha


def test_revert_commit_returns_new_sha_and_reverts_content(tmp_git_repo: Path) -> None:
    first_sha = _append_commit(
        tmp_git_repo,
        "plant.md",
        "one",
        "chore(auto): note x\n\ntext\nGrimSprout: tg_id=1",
    )
    _append_commit(
        tmp_git_repo,
        "plant.md",
        "two",
        "chore(auto): note x\n\ntext2\nGrimSprout: tg_id=1",
    )

    new_sha = git_service.revert_commit(tmp_git_repo, "HEAD")

    repo = git.Repo(tmp_git_repo)
    assert repo.head.commit.hexsha == new_sha
    assert (tmp_git_repo / "plant.md").read_text(encoding="utf-8") == "one"
    assert new_sha != first_sha


def test_revert_commit_rejects_dirty_repo(tmp_git_repo: Path) -> None:
    _append_commit(
        tmp_git_repo,
        "plant.md",
        "one",
        "chore(auto): note x\n\ntext\nGrimSprout: tg_id=1",
    )
    (tmp_git_repo / "README.md").write_text("# changed\n", encoding="utf-8")

    with pytest.raises(DirtyRepoError):
        git_service.revert_commit(tmp_git_repo, "HEAD")

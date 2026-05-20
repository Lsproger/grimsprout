"""Tests for grimsprout.utils.git_url."""

from __future__ import annotations

import pytest

from grimsprout.utils import git_url


def test_ssh_shorthand_with_git_suffix() -> None:
    parsed = git_url.parse_git_url("git@github.com:Lsproger/trava.git")
    assert parsed is not None
    assert parsed.scheme == "ssh"
    assert parsed.host == "github.com"
    assert parsed.owner == "Lsproger"
    assert parsed.name == "trava"
    assert parsed.repo_dir_name == "trava"


def test_ssh_shorthand_without_git_suffix() -> None:
    parsed = git_url.parse_git_url("git@github.com:Lsproger/trava")
    assert parsed is not None
    assert parsed.name == "trava"


def test_ssh_explicit_scheme() -> None:
    parsed = git_url.parse_git_url("ssh://git@github.com/Lsproger/trava.git")
    assert parsed is not None
    assert parsed.scheme == "ssh"
    assert parsed.owner == "Lsproger"
    assert parsed.name == "trava"


def test_https_url() -> None:
    parsed = git_url.parse_git_url("https://github.com/Lsproger/trava.git")
    assert parsed is not None
    assert parsed.scheme == "https"
    assert parsed.host == "github.com"
    assert parsed.owner == "Lsproger"
    assert parsed.name == "trava"


def test_https_with_nested_owner_path() -> None:
    """Self-hosted GitLab style: group/subgroup/repo. Last segment is name."""
    parsed = git_url.parse_git_url("https://gitlab.example.com/org/team/trava.git")
    assert parsed is not None
    assert parsed.owner == "org/team"
    assert parsed.name == "trava"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "/opt/data/trava",
        "./trava",
        "../trava",
        "trava",
        "https://github.com/onlyowner",  # too few path segments
    ],
)
def test_non_url_returns_none(value: str) -> None:
    assert git_url.parse_git_url(value) is None
    assert git_url.is_git_url(value) is False


def test_is_git_url_positive() -> None:
    assert git_url.is_git_url("git@github.com:owner/repo.git")
    assert git_url.is_git_url("https://github.com/owner/repo")

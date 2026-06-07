"""Unit tests for /revert command helpers."""

from __future__ import annotations

from grimsprout.bot.handlers.revert import _parse_revert_args


def test_parse_revert_args_basic() -> None:
    sha, hard = _parse_revert_args("abc1234")
    assert sha == "abc1234"
    assert hard is False


def test_parse_revert_args_hard_mode_flag() -> None:
    sha, hard = _parse_revert_args("abc1234 --hard")
    assert sha == "abc1234"
    assert hard is True


def test_parse_revert_args_hard_mode_short_flag() -> None:
    sha, hard = _parse_revert_args("-H abc1234")
    assert sha == "abc1234"
    assert hard is True


def test_parse_revert_args_rejects_extra_sha_like_token() -> None:
    sha, hard = _parse_revert_args("abc1234 deadbeef")
    assert sha is None
    assert hard is False

"""Git URL detection and parsing.

Supported schemes:
- SSH shorthand: ``git@github.com:owner/repo(.git)?``
- SSH explicit:  ``ssh://git@github.com[:port]/owner/repo(.git)?``
- HTTPS:         ``https://github.com/owner/repo(.git)?``

Anything else (including absolute/relative filesystem paths) is treated as
a local path by :func:`is_git_url`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse


Scheme = Literal["ssh", "https"]


@dataclass(frozen=True)
class GitUrl:
    raw: str
    scheme: Scheme
    host: str
    owner: str
    name: str  # without trailing ".git"

    @property
    def repo_dir_name(self) -> str:
        return self.name


_SSH_SHORTHAND_RE = re.compile(
    r"^(?P<user>[A-Za-z0-9_.-]+)@(?P<host>[A-Za-z0-9_.-]+):"
    r"(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$"
)


def parse_git_url(value: str) -> GitUrl | None:
    """Return a :class:`GitUrl` if ``value`` looks like a git URL, else ``None``."""
    s = value.strip()
    if not s:
        return None

    m = _SSH_SHORTHAND_RE.match(s)
    if m:
        return GitUrl(
            raw=s,
            scheme="ssh",
            host=m.group("host"),
            owner=m.group("owner"),
            name=m.group("name"),
        )

    if s.startswith(("ssh://", "https://", "http://")):
        parsed = urlparse(s)
        if not parsed.hostname:
            return None
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[: -len(".git")]
        segments = [seg for seg in path.split("/") if seg]
        if len(segments) < 2:
            return None
        owner = "/".join(segments[:-1])
        name = segments[-1]
        scheme: Scheme = "ssh" if parsed.scheme == "ssh" else "https"
        return GitUrl(raw=s, scheme=scheme, host=parsed.hostname, owner=owner, name=name)

    return None


def is_git_url(value: str) -> bool:
    return parse_git_url(value) is not None

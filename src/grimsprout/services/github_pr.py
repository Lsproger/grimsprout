"""GitHub PR creation via the REST API.

Only the minimal subset needed by the bot is implemented:
- Resolve owner/repo from a configured git URL or from the clone's
  ``origin`` remote.
- Create a pull request from ``head`` into ``base``.
- Idempotent: if an open PR with the same head→base already exists,
  return its URL instead of erroring.

Auth uses a Bearer token taken from the env var configured by
``repository.github_trava_token_env`` (default ``GIT_TRAVA_TOKEN``).
"""

from __future__ import annotations

from pathlib import Path

import git
import httpx
from loguru import logger

from grimsprout.utils.errors import GrimSproutError
from grimsprout.utils.git_url import GitUrl, parse_git_url


class PRError(GrimSproutError):
    pass


def _resolve_owner_repo(configured_path: str, repo_path: Path) -> GitUrl:
    """Prefer the configured URL; fall back to the clone's origin remote."""
    url = parse_git_url(configured_path)
    if url is not None:
        return url
    try:
        remote_url = git.Repo(repo_path).remote("origin").url
    except (ValueError, git.InvalidGitRepositoryError) as exc:
        raise PRError("cannot determine origin remote") from exc
    parsed = parse_git_url(remote_url)
    if parsed is None:
        raise PRError(f"origin URL is not a recognised git URL: {remote_url}")
    return parsed


def open_pr(
    *,
    configured_path: str,
    repo_path: Path,
    token: str,
    title: str,
    body: str,
    head: str,
    base: str,
) -> str:
    """Create (or find) a PR and return its HTML URL.

    Raises :class:`PRError` on transport / API failures or when the host is
    not GitHub.
    """
    if not token:
        raise PRError("GitHub token is empty; set the configured github_trava_token_env")

    url = _resolve_owner_repo(configured_path, repo_path)
    if url.host not in ("github.com", "api.github.com"):
        raise PRError(f"PR creation supports GitHub only, got host {url.host!r}")

    api = f"https://api.github.com/repos/{url.owner}/{url.name}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with httpx.Client(timeout=15.0, headers=headers) as client:
        # Idempotency: look for an existing open PR head→base first.
        existing = client.get(api, params={"state": "open", "head": f"{url.owner}:{head}", "base": base})
        if existing.status_code == 200 and existing.json():
            pr = existing.json()[0]
            logger.info("reusing existing PR #{n}: {url}", n=pr["number"], url=pr["html_url"])
            return pr["html_url"]

        resp = client.post(api, json={"title": title, "body": body, "head": head, "base": base})
        if resp.status_code == 201:
            pr = resp.json()
            logger.info("opened PR #{n}: {url}", n=pr["number"], url=pr["html_url"])
            return pr["html_url"]

        # 422 with "A pull request already exists" — search again without
        # state filter to catch edge cases.
        if resp.status_code == 422:
            again = client.get(api, params={"head": f"{url.owner}:{head}", "base": base})
            if again.status_code == 200 and again.json():
                pr = again.json()[0]
                return pr["html_url"]

        raise PRError(f"GitHub API error {resp.status_code}: {resp.text}")

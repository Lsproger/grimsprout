# ADR 0006 — Bot writes only to a dedicated work branch

## Context
GrimSprout commits to the `trava` repository on the user's behalf. Originally
the bot was pointed at a local clone via `repository.path` and committed
directly to `repository.git_branch` (e.g. `master`). We are extending the
config so that `repository.path` can also be a git URL (SSH or HTTPS), in
which case the bot clones the repo into `var/repo/<name>` on startup.

Once the bot can clone arbitrary remotes — and once `push` is implemented —
allowing it to write to the base branch becomes risky:
- A bug or a misinterpreted intent could land bad changes on `master`.
- Concurrent user edits on `master` would race with bot commits.
- Recovery requires force-pushes that the bot must not perform.

## Decision
- The bot **always** writes to `repository.work_branch` (default
  `grimsprout/auto`). The base branch `repository.git_branch` is treated as
  read-only by the bot.
- On startup, `repo_bootstrap.ensure_workdir` creates the work branch from
  `origin/<base>` (or local `<base>`) if it doesn't exist and checks it out.
- `git push` only ever pushes the work branch with upstream tracking.
- Merging into the base branch is **manual**: a human, CI, or a Pull
  Request opened via `/pr` and merged in GitHub.
- The bot never runs `fetch` / `pull` / `reset` / `checkout <base>` on
  existing clones, in line with spec §5.5.

## Consequences
- A single long-lived `grimsprout/auto` branch accumulates auto-commits.
  Operators are expected to merge it periodically.
- If the base branch advances on the remote, the work branch falls behind
  — that's intentional. Rebasing/merging is a human action.
- HTTPS credentials, if provided via `GIT_HTTPS_TOKEN`, are used for the
  initial clone only; the token is scrubbed from `.git/config` afterwards
  so a later inspection of the working tree does not leak it.

## Alternatives considered
- **Per-session branches** (`grimsprout/auto-YYYYMMDD-HHMM`): rejected as
  unnecessarily noisy for the current scale; PRs would multiply.
- **Direct commits to base**: rejected (see Context).
- **Tag-based audit instead of branch**: doesn't compose with PRs.

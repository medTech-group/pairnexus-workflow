"""Which kind of session this is: ticket, conductor or attended.

`WORKFLOW_ROLE` (set by the ticket sessions' own cloud environment, or by the
conductor for itself) wins; a value that isn't one of the three is treated as
ticket, the strictest, so a typo never loosens the guard. Otherwise a branch
matching the profile's `run.ticket_branch` means a ticket session. Otherwise
attended. A file in the repo is never used: the session itself could edit it.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path

ROLES = {"ticket", "conductor", "attended"}


def current_branch(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    b = out.stdout.strip()
    return b if out.returncode == 0 and b and b != "HEAD" else None


def env_role() -> str | None:
    """The role `WORKFLOW_ROLE` sets: None when unset or empty, "ticket" when
    it holds something that isn't a role (see `unrecognised`)."""
    env = (os.environ.get("WORKFLOW_ROLE") or "").strip().lower()
    if not env:
        return None
    return env if env in ROLES else "ticket"


def unrecognised() -> str | None:
    """`WORKFLOW_ROLE`'s value when it is set but isn't a role, else None."""
    raw = (os.environ.get("WORKFLOW_ROLE") or "").strip()
    return raw if raw and raw.lower() not in ROLES else None


def role(cwd: Path, ticket_branch: str = "claude/build-*") -> str:
    """The session's role. Only `WORKFLOW_ROLE` is a firm signal; the branch
    fallback is a convenience the session itself can change."""
    env = env_role()
    if env:
        return env
    b = current_branch(cwd)
    if b and fnmatch.fnmatchcase(b, ticket_branch):
        return "ticket"
    return "attended"

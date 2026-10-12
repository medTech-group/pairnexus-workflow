"""Which kind of session this is: ticket, conductor or attended.

`WORKFLOW_ROLE` (set by the ticket sessions' own cloud environment, or by the
conductor for itself) wins. Otherwise a branch matching the profile's
`run.ticket_branch` means a ticket session. Otherwise attended. A file in the
repo is never used: the session itself could edit it.
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


def role(cwd: Path, ticket_branch: str = "claude/build-*") -> str:
    env = (os.environ.get("WORKFLOW_ROLE") or "").strip().lower()
    if env in ROLES:
        return env
    b = current_branch(cwd)
    if b and fnmatch.fnmatchcase(b, ticket_branch):
        return "ticket"
    return "attended"

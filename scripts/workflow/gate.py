"""The checklist gate: a Stop hook for ticket sessions.

A ticket session ends each turn with a status line:

    WORKFLOW-STATUS: done | waiting | needs-human | stopped

`done` also needs the flow's checklist (at least three `- [x]` / `- [ ]` lines).
`waiting` (CI running, a check-in scheduled), `needs-human` and `stopped` end
the turn as they are. Without a valid status the gate asks the session to add
one, at most twice a session, and never while a stop hook is already making it
continue, so it can't trap a session in a loop.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

STATUS = re.compile(r"^\s*\**WORKFLOW-STATUS\**\s*:\s*\**\s*(done|waiting|needs-human|stopped)\b", re.I | re.M)
CHECK_LINE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s+\S", re.M)
MAX_BLOCKS = 2


def _counter(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")[:80]
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"workflow-gate-{safe}"


def verdict(message: str) -> str | None:
    """None when the message may end the turn, else what's missing."""
    m = STATUS.search(message or "")
    if not m:
        return (
            "End the turn with a status line, `WORKFLOW-STATUS: done | waiting | needs-human | stopped`. "
            "`done` also needs the flow's Building checklist, every line marked done or saying why not. "
            "Waiting on CI with a check-in scheduled is `waiting`."
        )
    if m.group(1).lower() == "done" and len(CHECK_LINE.findall(message)) < 3:
        return "`WORKFLOW-STATUS: done` needs the flow's Building checklist (each line `- [x] …` or `- [ ] … because …`)."
    return None


def decide(event: dict) -> str | None:
    """The reason to block, or None to let the turn end."""
    if event.get("stop_hook_active"):
        return None
    missing = verdict(event.get("last_assistant_message") or "")
    if missing is None:
        return None
    c = _counter(event.get("session_id") or "")
    try:
        n = int(c.read_text()) if c.exists() else 0
    except (OSError, ValueError):
        n = 0
    if n >= MAX_BLOCKS:
        return None
    try:
        c.write_text(str(n + 1))
    except OSError:
        pass
    return missing

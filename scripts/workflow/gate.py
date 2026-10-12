"""The checklist gate: a Stop hook for ticket sessions.

A ticket session ends each turn with a status line:

    WORKFLOW-STATUS: done | waiting | needs-human | stopped

`done` also needs the flow's checklist (at least three `- [x]` / `- [ ]` lines),
and every unchecked line must say why: `because`, `why`, ` — `, ` - `, `n/a`
or `not ` ("not needed"). A bare link or a colon isn't a reason.
Text inside ``` fences is ignored when looking for both, so a quoted status line
or checklist doesn't count.
`waiting` (CI running, a check-in scheduled), `needs-human` and `stopped` end
the turn as they are. Without a valid status the gate asks the session to add
one, once per turn: never while a stop hook is already making it continue
(`stop_hook_active`), so it can't trap a session in a loop. A cap of
`MAX_BLOCKS` a session a day (UTC) is a last safety net, so a long ticket
session keeps the gate the next day.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATUS = re.compile(r"^\s*\**WORKFLOW-STATUS\**\s*:\s*\**\s*(done|waiting|needs-human|stopped)\b", re.I | re.M)
CHECK_LINE = re.compile(r"^\s*[-*]\s*\[[ xX]\]\s+\S", re.M)
UNCHECKED = re.compile(r"^\s*[-*]\s*\[ \]\s+(\S.*)$", re.M)
WHY = re.compile(r"because|why| — | - |n/a|not ", re.I)
FENCED = re.compile(r"^[ \t]*```.*?^[ \t]*```[^\n]*$", re.M | re.S)
MAX_BLOCKS = 40
NEEDS_REASON = "an unchecked checklist line needs its reason"


def _unfenced(message: str) -> str:
    """The message without its ``` fenced blocks."""
    return FENCED.sub("", message or "")


def _counter(session_id: str, now: datetime | None = None) -> Path:
    """The session's block count for the day (UTC)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")[:80]
    day = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"workflow-gate-{safe}-{day}"


def verdict(message: str) -> str | None:
    """None when the message may end the turn, else what's missing."""
    message = _unfenced(message)
    m = STATUS.search(message)
    if not m:
        return (
            "End the turn with a status line, `WORKFLOW-STATUS: done | waiting | needs-human | stopped`. "
            "`done` also needs the flow's Building checklist, every line marked done or saying why not. "
            "Waiting on CI with a check-in scheduled is `waiting`."
        )
    if m.group(1).lower() == "done" and len(CHECK_LINE.findall(message)) < 3:
        return "`WORKFLOW-STATUS: done` needs the flow's Building checklist (each line `- [x] …` or `- [ ] … because …`)."
    if m.group(1).lower() == "done":
        bare = [x.strip() for x in UNCHECKED.findall(message) if not WHY.search(x)]
        if bare:
            return (
                f"`WORKFLOW-STATUS: done`: {NEEDS_REASON} (`- [ ] … because …`): "
                + "; ".join(f"`{b[:80]}`" for b in bare[:3])
                + ". Do it, or say why it isn't done."
            )
    return None


def _last_message(event: dict) -> str:
    msg = event.get("last_assistant_message")
    if isinstance(msg, str):
        return msg
    path = event.get("transcript_path")
    if not path:
        return ""
    try:
        import json

        last = ""
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                m = e.get("message") or {}
                if e.get("type") == "assistant" and isinstance(m, dict):
                    parts = m.get("content")
                    if isinstance(parts, list):
                        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
                        if text:
                            last = text
                    elif isinstance(parts, str):
                        last = parts
        return last
    except OSError:
        return ""


def decide(event: dict, now: datetime | None = None) -> str | None:
    """The reason to block, or None to let the turn end."""
    if event.get("stop_hook_active"):
        return None
    missing = verdict(_last_message(event))
    if missing is None:
        return None
    c = _counter(event.get("session_id") or "", now)
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

"""Flow context: a UserPromptSubmit hook.

When a prompt is about the flow (`/next`, or a flow verb next to an issue
reference), add the kit's flow to the context: the whole file the first time in
a session, a one-line reminder after that.

The first prompt of an attended session that isn't about the flow already, and
isn't a command, brings the guided start instead (`skills/start`): Claude asks
what we're working on, with choices. Anything else passes untouched.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_NEXT = re.compile(r"(^|\s)/(?:[\w-]+:)?next\b")
# The commands that plan or build under the flow bring it in on their own:
# the kit adds rules to what they publish (flow.md sections 2 and 3).
_COMMAND = re.compile(
    r"(^|\s)/(?:[\w-]+:)?(?:to-spec|to-tickets|wayfinder|grill-with-docs|triage|implement(?:-spec)?)(?![\w-])"
)
_VERB = re.compile(
    r"\b(implement\w*|build\w*|work(?:ing)?|fix\w*|spec\w*|tickets?|maps?|wayfinder|grill\w*|to-spec|to-tickets|frontier|conductor|unattended)\b",
    re.I,
)
_MAP = re.compile(r"\bwork(?:ing)?\s+(?:on\s+)?the\s+[\w -]{1,40}\bmap\b|\b(?:start|run|resume|stop)\s+(?:an?\s+|the\s+)?(?:unattended\s+)?run\b|\bconductor\b", re.I)
_REF = re.compile(r"(?<![\w/])#\d+\b|/issues/\d+")


def wants_flow(prompt: str) -> bool:
    if _NEXT.search(prompt or "") or _COMMAND.search(prompt or "") or _MAP.search(prompt or ""):
        return True
    return bool(_VERB.search(prompt or "") and _REF.search(prompt or ""))


# A prompt that starts with a slash command: the person chose what to run.
_SLASH = re.compile(r"^\s*/[\w:-]+")

START = (
    "This is the first message of the session. Follow the kit's guided start, the `start` skill "
    "(`.claude/skills/start/SKILL.md`, or `pairnexus-workflow:start` as a plugin): if this message already asks for "
    "something clear, just do it; if it describes work to plan, split it into items with a path for each; otherwise "
    "ask \"What are we working on?\" with choices. If the conversation was already under way before this message "
    "(a resumed session), ignore this."
)


def _marker(kind: str, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")[:80]
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"workflow-{kind}-{safe}"


def start_for(prompt: str, session_id: str) -> str | None:
    """The guided start's nudge, at the session's first prompt only, unless the
    prompt is a command or already about the flow."""
    marker = _marker("start", session_id)
    if marker.exists():
        return None
    try:
        marker.touch()
    except OSError:
        pass
    if _SLASH.match(prompt or "") or wants_flow(prompt):
        return None
    return START


def flow_files(project: Path, kit_root: Path, addendum: str = "") -> list[Path]:
    out = []
    for cand in (project / ".claude/workflow/flow.md", kit_root / "docs/flow.md"):
        if cand.exists():
            out.append(cand)
            break
    if addendum and (project / addendum).exists():
        out.append(project / addendum)
    return out


def context_for(prompt: str, session_id: str, files: list[Path]) -> str | None:
    if not files or not wants_flow(prompt):
        return None
    marker = _marker("flow", session_id)
    names = ", ".join(str(f) for f in files)
    if marker.exists():
        return f"Follow the workflow's flow ({names}) for this request, step by step, and end with its checklist. If it is no longer in your context, read it again first."
    try:
        marker.touch()
    except OSError:
        pass
    body = "\n\n".join(f.read_text(encoding="utf-8") for f in files)
    return f"This request is part of the project's workflow. Follow the flow below step by step: skip nothing, and end with its checklist.\n\n{body}"

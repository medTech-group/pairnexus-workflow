"""Flow context: a UserPromptSubmit hook.

When a prompt is about the flow (`/next`, or a flow verb next to an issue
reference), add the kit's flow to the context: the whole file the first time in
a session, a one-line reminder after that.

The first prompt of an attended session that isn't about the flow already, and
isn't a command, brings the guided start instead (`skills/start`): Claude asks
what we're working on, with choices. Anything else passes untouched.

Beside either, the first prompt of an attended session for someone new to
building brings the kit's glossary and the rule to explain its words once.
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
# Only a command name: "/home/user/app.py crashes" is a path, not a command.
_SLASH = re.compile(r"^\s*/[\w:-]+(?=\s|$)")

START = (
    "This is the first message of the session. Follow the kit's guided start, the `start` skill "
    "(`.claude/skills/start/SKILL.md`, or `pairnexus-workflow:start` as a plugin): first, when `workflow status` finds "
    "no experience level, ask it as the skill says; then, if this message already asks for "
    "one clear thing, just do it; if it describes work to plan, or more than one thing, don't start on any of it: "
    "split it into items with a path for each and agree the plan first; otherwise "
    "ask \"What are we working on?\" with choices. If the conversation was already under way before this message "
    "(a resumed session), ignore this."
)


def _marker(kind: str, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")[:80]
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"workflow-{kind}-{safe}"


def first_prompt(session_id: str) -> bool:
    """Whether this is the session's first prompt, marking it seen either way,
    so a first message that was a command or a flow request still counts."""
    marker = _marker("start", session_id)
    if marker.exists():
        return False
    try:
        marker.touch()
    except OSError:
        pass
    return True


def start_for(prompt: str, session_id: str) -> str | None:
    """The guided start's nudge, at the session's first prompt only, unless the
    prompt is a command or already about the flow."""
    if not first_prompt(session_id):
        return None
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


FLOW_HEAD = "This request is part of the project's workflow. Follow the flow below step by step: skip nothing, and end with its checklist."


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
    return f"{FLOW_HEAD}\n\n{body}"


# The glossary, for someone new to building (#74): at the first prompt of an
# attended session, beside whatever else the prompt brings.

LIMIT = 10_000  # Claude Code saves a hook's longer string to a file, showing 2,000 characters of it
GLOSSARY_RULE = (
    "Treat the person in this session as new to building: the words in the kit's glossary ({where}) are new to them: "
    "explain each one in the glossary's wording, in one or two sentences, the first time you use it in this session, "
    "and never again in this session. Never explain them in what you write on GitHub (pull request descriptions, "
    "comments, reports)."
)


def glossary_file(project: Path, kit_root: Path) -> Path | None:
    """The vendored glossary, else the kit's own (plugin mode), as the flow is found."""
    for cand in (project / ".claude/workflow/docs/glossary.md", kit_root / "docs/glossary.md"):
        if cand.is_file():
            return cand
    return None


def first_glossary_prompt(session_id: str) -> bool:
    """Whether the glossary hasn't been considered yet this session, marking it
    either way: its own marker, so the guided start's doesn't decide it."""
    marker = _marker("glossary", session_id)
    if marker.exists():
        return False
    try:
        marker.touch()
    except OSError:
        pass
    return True


def glossary_for(path: Path | None, beside: str = "", whole_flow: bool = False) -> str | None:
    """The glossary and its rule, to add beside `beside`. With the whole flow,
    or when the text wouldn't fit under Claude Code's limit, only the rule and
    the glossary's path with "read it now"."""
    if path is None:
        return None
    rule = GLOSSARY_RULE.format(where=path)
    by_path = f"{rule} It isn't included here: read it now."
    if whole_flow:
        return by_path
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return by_path
    whole = f"{rule}\n\n{text}"
    used = len(beside) + 2 if beside else 0
    return whole if used + len(whole) < LIMIT else by_path

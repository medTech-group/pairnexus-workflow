"""Flow context: a UserPromptSubmit hook.

When a prompt is about the flow (`/next`, or a flow verb next to an issue
reference), add the kit's flow to the context: the first time in a session, an
instruction to read it now, all of it, with the sections that fit under Claude
Code's limit; a one-line reminder after that.

The first prompt of an attended session that isn't about the flow already, and
isn't a command, brings the guided start instead (`skills/start`): Claude asks
what we're working on, with choices. Each later prompt like it brings a
one-line reminder to plan new work before starting on it. Anything else passes
untouched.

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

REMINDER = (
    "Workflow: if this message asks for new work that isn't part of the plan or ticket already agreed in this "
    "session, don't start on it: split it into items with a path for each and agree the plan first (the `start` "
    "skill, step 2). A question, a named issue or one small change with an obvious place may go ahead (on its own "
    "branch, with a pull request). Replies to your own questions carry on."
)

START = (
    "This is the first message of the session. Follow the kit's guided start, the `start` skill "
    "(`.claude/skills/start/SKILL.md`, or `pairnexus-workflow:start` as a plugin): first, when `workflow status` finds "
    "no experience level, ask it as the skill says. Act on this message straight away only when it is a question, "
    "names an issue, or asks for one small change with an obvious place (on its own branch, with a pull request). "
    "If it asks for any other work (a feature, a change, a fix whose cause isn't known, or more than one thing), "
    "don't start on it: split it into items with a path for each and agree the plan first. Otherwise "
    "ask \"What are we working on?\" with choices. If the conversation was already under way (a resumed session), "
    "follow the reminder below instead."
    "\n\n" + REMINDER
)


def _marker(kind: str, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")[:80]
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"workflow-{kind}-{safe}"


def _first_time(kind: str, session_id: str) -> bool:
    """Whether `kind`'s marker is unset for this session, setting it either way."""
    marker = _marker(kind, session_id)
    if marker.exists():
        return False
    try:
        marker.touch()
    except OSError:
        pass
    return True


def first_prompt(session_id: str) -> bool:
    """Whether this is the session's first prompt, marking it seen either way,
    so a first message that was a command or a flow request still counts."""
    return _first_time("start", session_id)


def start_for(prompt: str, session_id: str) -> str | None:
    """The guided start's nudge, at the session's first prompt only, unless the
    prompt is a command or already about the flow."""
    if not first_prompt(session_id):
        return None
    if _SLASH.match(prompt or "") or wants_flow(prompt):
        return None
    return START


def reminder_for(prompt: str) -> str | None:
    """The reminder, for a prompt after the first: on the same terms as the
    guided start's nudge, and with no marker of its own, so every later prompt
    gets it."""
    if _SLASH.match(prompt or "") or wants_flow(prompt):
        return None
    return REMINDER


def flow_files(project: Path, kit_root: Path, addendum: str = "") -> list[Path]:
    out = []
    for cand in (project / ".claude/workflow/flow.md", kit_root / "docs/flow.md"):
        if cand.is_file():
            out.append(cand)
            break
    if addendum and (project / addendum).is_file():
        out.append(project / addendum)
    return out


FLOW_HEAD = "This request is part of the project's workflow. Follow its flow step by step: skip nothing, and end with its checklist."
# What the first flow context may take of Claude Code's limit (CONTEXT_LIMIT,
# below): the rest is room for the glossary's rule and path put in front of it.
FLOW_BUDGET = 8_500
_READ = " Read it now, all of it, before acting: "
_WHOLE = " All of it is below (from "
_STOPS = " Only its start fits below. It stops before "


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def _sections(text: str) -> list[str]:
    """`text` cut before each `## ` heading outside a code block: the opening
    (before the first heading), then one piece per section. A block closes
    only on a fence of its own kind, at least as long, with nothing after it."""
    out, cur, fence = [], [], ""
    for line in text.splitlines(keepends=True):
        m = _FENCE.match(line.rstrip("\r\n"))
        if m and not fence and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence = m.group(1)
        elif m and fence and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
            fence = ""
        elif line.startswith("## ") and not fence and cur:
            out.append("".join(cur))
            cur = []
        cur.append(line)
    if cur:
        out.append("".join(cur))
    return [p.strip() for p in out if p.strip()]


def _name(section: str, file: Path) -> str:
    first = section.splitlines()[0].lstrip("#").strip()
    if len(first) > 80:
        first = first[:79].rstrip() + "…"
    return f'"{first}" ({file.name})'


def first_flow(files: list[Path]) -> str:
    """The first flow context: a short, fixed instruction with the flow's paths,
    then the flow's sections from its start, each whole, as far as they fit
    under FLOW_BUDGET. Claude Code saves a string over its limit to a file and
    shows Claude its first 2,000 characters, so the instruction comes first,
    the whole stays under it, and the instruction names where the text below
    stops. A file that can't be read leaves only the instruction."""
    names = ", ".join(str(f) for f in files)
    head = f"{FLOW_HEAD}{_READ}{names}."
    try:
        pieces = [(f, s) for f in files for s in _sections(f.read_text(encoding="utf-8-sig"))]
    except (OSError, UnicodeDecodeError):
        return head
    whole = f"{FLOW_HEAD}{_WHOLE}{names})."
    if len(whole) + sum(len(p) + 2 for _, p in pieces) <= FLOW_BUDGET:
        return "\n\n".join([whole, *(p for _, p in pieces)])
    body = 0  # the length of the first k sections, joined
    for k, (f, s) in enumerate(pieces):
        nxt = pieces[k + 1] if k + 1 < len(pieces) else None
        grown = body + len(s) + 2
        # what the text would be with this section too, stopping before the next
        if nxt is None or len(head) + len(_stop(*nxt)) + grown > FLOW_BUDGET:
            if k == 0:
                return head  # not even the opening fits: nothing below
            return "\n\n".join([head + _stop(f, s), *(p for _, p in pieces[:k])])
        body = grown
    return head


def _stop(f: Path, s: str) -> str:
    return f"{_STOPS}{_name(s, f)}: read that section and everything after it there."


def flow_instruction(ctx: str) -> str:
    """The first flow context cut to its instruction: follow the flow and read
    it now, all of it, at its paths, with nothing said about text below."""
    first = ctx.split("\n\n", 1)[0].split(_STOPS.split(" It stops")[0], 1)[0]
    lead = f"{FLOW_HEAD}{_WHOLE}"
    if first.startswith(lead) and first.endswith(")."):
        first = f"{FLOW_HEAD}{_READ}{first[len(lead):-2]}."
    return first


def context_for(prompt: str, session_id: str, files: list[Path]) -> str | None:
    if not files or not wants_flow(prompt):
        return None
    marker = _marker("flow", session_id)
    names = ", ".join(str(f) for f in files)
    if marker.exists():
        return f"Follow the workflow's flow ({names}) for this request, step by step, and end with its checklist. Unless all of it is still in your context, read it again first."
    ctx = first_flow(files)  # read before the marker is set
    try:
        marker.touch()
    except OSError:
        pass
    return ctx


def is_first_flow(ctx: str | None) -> bool:
    """Whether `context_for` gave the first flow context, not the one-line reminder."""
    return bool(ctx and ctx.startswith(FLOW_HEAD))


# The glossary, for someone new to building (#74): at the first prompt of an
# attended session, beside whatever else the prompt brings.

CONTEXT_LIMIT = 10_000  # Claude Code's cap on a hook's added context, per string: a longer one is saved to a file, 2,000 characters shown
GLOSSARY_RULE = (
    "Treat the person in this session as new to building, unless they tell you they are a developer. "
    "The words in the kit's glossary ({where}) are new to them. Explain each one in the glossary's wording, "
    "in one or two sentences, the first time you use it in this session, and never again in this session. "
    "Never explain them in what you write on GitHub (pull request descriptions, comments, reports). "
    "If the conversation was already under way before this message (a resumed session), only the rule applies from here."
)


def glossary_file(project: Path, kit_root: Path) -> Path | None:
    """The vendored glossary, else the kit's own (plugin mode), in the order the flow is found."""
    for cand in (project / ".claude/workflow/docs/glossary.md", kit_root / "docs/glossary.md"):
        if cand.is_file():
            return cand
    return None


def first_glossary_prompt(session_id: str) -> bool:
    """Whether the glossary hasn't been considered yet this session, marking it
    either way: its own marker, so the guided start's doesn't decide it."""
    return _first_time("glossary", session_id)


def with_glossary(ctx: str | None, path: Path | None) -> str | None:
    """`ctx` with the glossary and its rule beside it. The glossary goes in
    whole when it all stays under Claude Code's limit; beside the first flow
    context, or when it wouldn't fit, only the rule and its path with "read it now",
    put first so it stays within the 2,000 characters Claude sees of a longer
    string. An empty or unreadable glossary adds nothing."""
    if path is None:
        return ctx
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ctx  # Claude couldn't read it either
    if not text:
        return ctx
    rule = GLOSSARY_RULE.format(where=path)
    if not is_first_flow(ctx):
        whole = f"{ctx}\n\n{rule}\n\n{text}" if ctx else f"{rule}\n\n{text}"
        if len(whole) < CONTEXT_LIMIT:
            return whole
    by_path = f"{rule} It isn't included here: read it now."
    if ctx and len(by_path) + 2 + len(ctx) >= CONTEXT_LIMIT and is_first_flow(ctx):
        ctx = flow_instruction(ctx)  # long paths: keep the flow's instruction, which names them
    return f"{by_path}\n\n{ctx}" if ctx else by_path

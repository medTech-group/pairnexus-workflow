"""Render a ticket session's briefing from a template.

Placeholders are `{{name}}` or `{{group.name}}`. Values come from the ticket,
the profile, the charter and the conductor's slots. Rendering refuses when the
template has a placeholder with no value or a malformed one, a required slot is
empty, or a slot still says SEE_BELOW/TODO_FILL, so a session can never be sent
a briefing with a hole in it. Values are inserted as they are: a value holding
braces ("Fix {{x}} binding") renders.

`seal` ends a rendered briefing with `Briefing <hash>`, the first 12 hex
characters of the SHA-256 of the text above it. The session echoes that line in
its first comment, so the conductor sees the briefing arrived intact.
"""

from __future__ import annotations

import hashlib
import re

from .profile import Profile

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
# Filled by the conductor for each ticket. "none" is a valid answer; empty isn't.
# `wake_trigger` is the id of the routine that wakes the conductor when a ticket ends.
REQUIRED_SLOTS = ("alongside", "read_first", "owner_decisions", "briefing", "wake_trigger")
_SEAL = re.compile(r"[ \t]*Briefing ([0-9a-f]{12})")


def _plain(text: str) -> str:
    """The text as the hash reads it: Windows line endings made plain, and the
    whitespace at the end of each line and of the whole left out, so a copy
    that differs only there still matches."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(l.rstrip() for l in lines).rstrip()


def briefing_hash(text: str) -> str:
    return hashlib.sha256(_plain(text).encode("utf-8")).hexdigest()[:12]


def seal(text: str) -> str:
    """The briefing with its last line `Briefing <hash>`."""
    body = text.rstrip("\n")
    return f"{body}\n\nBriefing {briefing_hash(body)}\n"


def seal_of(text: str) -> tuple[str | None, str | None]:
    """(the hash the last line states, the hash of the text above it), or
    (None, None) when the text doesn't end with a `Briefing <hash>` line.
    Trailing whitespace and blank lines are ignored."""
    plain = _plain(text)
    cut = plain.rfind("\n") + 1  # the last line starts here (0 when it is the only one)
    m = _SEAL.fullmatch(plain, cut)
    if not m:
        return None, None
    return m.group(1), briefing_hash(plain[:cut])


def sealed_intact(text: str) -> bool:
    """The text ends with a `Briefing <hash>` line that matches what is above it."""
    stated, got = seal_of(text)
    return stated is not None and stated == got


MARKER = re.compile(r"\b(SEE_BELOW|TODO_FILL)\b|<fill[^>]*>")
LEFTOVER = re.compile(r"\{\{.*?\}\}|\{\{|\}\}")


class RenderError(ValueError):
    pass


def _code(cmd: str) -> str:
    return f"`{cmd}`" if cmd else "none"


def _suite_line(s) -> str:
    where = f", run in `{s.cwd}`" if s.cwd else ""
    if "{files}" in s.run and s.files:
        given = f", each given relative to `{s.cwd}`" if s.cwd else ""
        files = (
            f", where {{files}} is the test files to run, space-separated (those matching `{s.files}`, "
            f"relative to the project root{given}); give it all of them for the whole suite"
        )
    elif "{files}" in s.run:
        files = ", with {files} left empty"
    else:
        files = ""
    return f"{s.name}: `{s.run}`{where}{files}"


def _test_file(cmd: str) -> str:
    return f"`{cmd}` (replace {{file}} with the test file's path)" if "{file}" in cmd else _code(cmd)


def _per_package(profile: Profile, attr: str, show) -> str:
    """The top-level command, then each package's with the files it covers:
    "`mypy .`; for `web/**` (package web, run in `web`): `npx tsc`"."""
    parts = []
    top = getattr(profile, attr)
    packages = [pk for pk in profile.packages if getattr(pk, attr)]
    if top:
        parts.append(show(top) + (" for everything else" if packages else ""))
    for pk in packages:
        where = f", run in `{pk.cwd}`" if pk.cwd else ""
        parts.append(f"for `{pk.path}` (package {pk.name}{where}): {show(getattr(pk, attr))}")
    return "; ".join(parts) if parts else "none"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- none"


def values(profile: Profile, ticket: dict, charter: dict, slots: dict, tracking: int, by_hand: int | None) -> dict:
    merge = charter.get("merge") or {}
    waived = merge.get("waived_checks") or []
    v = {
        "ticket.number": str(ticket["number"]),
        "ticket.title": ticket.get("title") or "",
        "ticket.branch": profile.ticket_branch.replace("*", str(ticket["number"])),
        "project.name": profile.name,
        "project.repo": profile.repo,
        "project.base_branch": profile.base_branch,
        "project.owner": f"@{profile.owner}" if profile.owner else "not named in the profile",
        "project.rules": _bullets(profile.rules),
        "tracking.issue": str(tracking),
        "by_hand.issue": f"#{by_hand}" if by_hand else "none yet: add by-hand checks to the tracking issue",
        "merge.mode": merge.get("mode", "auto-merge"),
        "merge.waived": ", ".join(waived) if waived else "none: every required check must be green",
        "run.review_rounds": str(profile.review_rounds),
        "run.check_in_minutes": str((charter.get("limits") or {}).get("check_in_minutes", profile.check_in_minutes)),
        "open_decisions": "take the choice most consistent with the spec, ADRs and the project's rules, and record it in the PR body"
        if charter.get("open_decisions", "decide-and-record") == "decide-and-record"
        else "label the ticket needs-human, say exactly what needs deciding, and stop",
        "commands.typecheck": _per_package(profile, "typecheck", _code),
        "commands.test_file": _per_package(profile, "test_file", _test_file),
        "commands.suites": _bullets([_suite_line(s) for s in profile.suites]),
        "ui.explorer": profile.explorer,
    }
    for k in REQUIRED_SLOTS:
        v[k] = slots.get(k, "")
    for k, val in slots.items():
        v.setdefault(k, val)
    return v


def render(template: str, vals: dict) -> str:
    used = [m.group(1) for m in PLACEHOLDER.finditer(template)]
    missing_slots = [k for k in REQUIRED_SLOTS if k in used and not str(vals.get(k, "")).strip()]
    if missing_slots:
        raise RenderError(
            "required slots are empty: " + ", ".join(missing_slots) + ' (write "none" when there is nothing to say)'
        )
    unknown = sorted({k for k in used if k not in vals})
    if unknown:
        raise RenderError("no value for: " + ", ".join(unknown))
    # The template, its known placeholders removed: anything brace-like or a
    # marker left is a hole in the template itself.
    bare = PLACEHOLDER.sub("", template)
    left = sorted(set(LEFTOVER.findall(bare)) | {m.group(0) for m in MARKER.finditer(bare)})
    if left:
        raise RenderError("the template has a malformed or unfilled placeholder: " + ", ".join(left))
    # A slot (or other value) still holding a marker is a hole the conductor left.
    holes = sorted({k for k in used if MARKER.search(str(vals[k]))})
    if holes:
        raise RenderError(
            "these still say SEE_BELOW/TODO_FILL/<fill …>: " + ", ".join(holes) + "; write what the session needs, or \"none\""
        )
    return PLACEHOLDER.sub(lambda m: str(vals[m.group(1)]), template)

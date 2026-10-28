"""Render a ticket session's briefing from a template.

Placeholders are `{{name}}` or `{{group.name}}`. Values come from the ticket,
the profile, the charter and the conductor's slots. Rendering refuses when the
template has a placeholder with no value or a malformed one, a required slot is
empty, or a slot still says SEE_BELOW/TODO_FILL, so a session can never be sent
a briefing with a hole in it. Values are inserted as they are: a value holding
braces ("Fix {{x}} binding") renders.

A ticket's "Starts from:" line (a quick ticket for another pull request's fix,
#348) names the branch its session starts from, in place of the base branch;
the briefing's "Starts from:" line gives it, or the base branch without one.

`seal` ends a rendered briefing with `Briefing <hash>`, the first 12 hex
characters of the SHA-256 of the text above it. The session echoes that line in
its first comment, so the conductor sees the briefing arrived intact.
"""

from __future__ import annotations

import hashlib
import re

from . import presets as presets_mod
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


# The label on a line of its own: after any quote marker, an indent of at most 3
# columns, then any list, checkbox or heading marker, bold or italic, the colon
# inside or outside them, in any case.
_STARTS_FROM = re.compile(
    r"^(?:> ?)* {0,3}(?:(?:[-*+]|\d+[.)])[ \t]+(?:\[[ xX]\][ \t]+)?|#{1,6}[ \t]+)*"
    r"[*_]{0,3}starts[ \t]+from[*_]{0,3}[ \t]*[:：][*_]{0,3}[ \t]*(.*)$",
    re.I,
)
# A branch name or `pull/<n>/head`: no option, no `..`, nothing a shell reads.
_REF = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/-]{0,199}")
_REF_WORDS = "one branch name of letters, digits and `._/-` (at most 200), or `pull/<n>/head`"
_PLACEHOLDERS = {"none", "n/a", "na", "tbd", "todo", "head", "same", "base"}


def _prose_lines(body: str):
    """The body's lines outside fenced code and HTML comments that start a line.
    A fence opens with three or more backticks (none in its info string) or
    tildes, indented at most 3 columns, and closes on a fence of the same kind at
    least as long, or at the end."""
    fence, comment = None, False
    for line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = line.expandtabs(4)
        bare = re.sub(r"^(?:> ?)*", "", line)  # a fence or comment in a quote counts too
        if comment:
            comment = "-->" not in line
            continue
        if fence:
            m = re.match(r" {0,3}(`{3,}|~{3,})[ \t]*$", bare)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        m = re.match(r" {0,3}(`{3,}(?=[^`]*$)|~{3,})", bare)
        if m:
            fence = m.group(1)
            continue
        if re.match(r" {0,3}<!--", bare):
            comment = "-->" not in bare.split("<!--", 1)[1]
            continue
        yield line


def _ref_of(value: str) -> str | None:
    """The one branch a "Starts from:" line's value names, or None: a word, or a
    word in backticks, then nothing but a full stop or a remark in brackets."""
    value = value.strip("*_ \t")
    m = re.fullmatch(r"(?:`([^`\s]+)`|([^`\s]+?))\.?(?:[ \t]+\(.*\))?", value)
    if not m:
        return None
    ref = m.group(1) or m.group(2)
    if ref.startswith("refs/heads/"):
        ref = ref[len("refs/heads/"):]
    if (
        not _REF.fullmatch(ref)
        or ref.lower() in _PLACEHOLDERS
        or ".." in ref
        or ref.endswith(".")
        or any(not c or c.startswith(".") or c.endswith(".lock") for c in ref.split("/"))
    ):
        return None
    return ref


def _starts_from(ticket: dict) -> str | None:
    """The branch a ticket's "Starts from:" lines name, outside code, or None
    without one. A line naming no branch, or two naming different ones, is a
    RenderError."""
    body = ticket.get("body")
    refs = []
    for line in _prose_lines(body if isinstance(body, str) else ""):
        m = _STARTS_FROM.match(line)
        if not m:
            continue
        value = m.group(1).strip()
        ref = _ref_of(value)
        if ref is None:
            raise RenderError(
                f'#{ticket.get("number")}\'s "Starts from:" line names no branch: {value[:80]!r}; '
                f"give {_REF_WORDS}, in backticks"
            )
        refs.append(ref)
    if len(set(refs)) > 1:
        raise RenderError(f'#{ticket.get("number")}\'s "Starts from:" lines name different branches: ' + ", ".join(sorted(set(refs))))
    return refs[0] if refs else None


def _starts_from_words(ticket: dict, profile: Profile, branch: str) -> str:
    ref = _starts_from(ticket)
    if ref is None or ref == profile.base_branch:
        return f"`{profile.base_branch}`, the base branch."
    if ref == branch:
        return f"`{branch}`, your own branch, as the ticket's \"Starts from:\" line names it: carry on from it and its pull request."
    return (
        f'`{ref}`, as the ticket\'s "Starts from:" line names it. If `{branch}` is already on GitHub '
        f"(`git ls-remote --exit-code origin refs/heads/{branch}`: an earlier attempt's), carry on from it and its "
        f"pull request instead. Otherwise fetch it (`git fetch origin {ref}`) and create `{branch}` from what it "
        f"fetched (`git switch -c {branch} FETCH_HEAD`). Open your own pull request (closing the old one's ticket "
        "too, if it has one), and close the old pull request with a comment linking yours, unless that is done already."
    )


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


def _rounds(n: int) -> str:
    """The review's rounds; 1 is the light review (`review-panel` §6)."""
    return "1 (the light review)" if n == 1 else str(n)


def _small(review: dict, profile: Profile) -> str:
    """The small review's line: on or off, with the threshold to measure against."""
    if not review["small"]:
        return "off: build a ticket marked `Review: small` with the review above, as any other"
    past = presets_mod.past_small(review) + (", as for an unmarked ticket" if review["rounds"] == 1 else "")
    return (
        "on: a ticket marked `Review: small` gets the small review (`review-panel`: one round, Correctness, "
        f"{presets_mod.small_reviewers(review, profile)}) while its diff stays within "
        f"{presets_mod.threshold_words(review)} outside tests (added plus removed). Measure it before reviewing: "
        "`python3 .claude/workflow/bin/workflow.py review-record --measure --commit <sha> "
        f"--small-max-lines {review['small_max_lines']} --small-max-files {review['small_max_files']}`; "
        f"past the threshold, {past}"
    )


def values(profile: Profile, ticket: dict, charter: dict, slots: dict, tracking: int, by_hand: int | None) -> dict:
    merge = charter.get("merge") or {}
    review = presets_mod.review_of(charter, profile)
    waived = merge.get("waived_checks") or []
    branch = profile.ticket_branch.replace("*", str(ticket["number"]))
    v = {
        "ticket.number": str(ticket["number"]),
        "ticket.title": ticket.get("title") or "",
        "ticket.branch": branch,
        "ticket.starts_from": _starts_from_words(ticket, profile, branch),
        "project.name": profile.name,
        "project.repo": profile.repo,
        "project.base_branch": profile.base_branch,
        "project.owner": f"@{profile.owner}" if profile.owner else "not named in the profile",
        "project.rules": _bullets(profile.rules),
        "tracking.issue": str(tracking),
        "by_hand.issue": f"#{by_hand}" if by_hand else "none yet: add by-hand checks to the tracking issue",
        "merge.mode": merge.get("mode", "auto-merge"),
        "merge.waived": ", ".join(waived) if waived else "none: every required check must be green",
        "run.review_rounds": _rounds(review["rounds"]),
        "review.rounds": str(review["rounds"]),  # the bare number, for merge-check's --review-rounds
        "review.small": _small(review, profile),
        "review.passes_words": presets_mod.passes_words(review),
        # The bare numbers, for merge-check's --review-passes, --small-max-lines and --small-max-files.
        "review.passes": str(review["passes"]),
        "review.small_max_lines": str(review["small_max_lines"]),
        "review.small_max_files": str(review["small_max_files"]),
        "run.check_in_minutes": str((charter.get("limits") or {}).get("check_in_minutes", profile.check_in_minutes)),
        "open_decisions": "take the choice most consistent with the spec, ADRs and the project's rules, and record it in the PR body"
        if charter.get("open_decisions", "decide-and-record") == "decide-and-record"
        else "label the ticket needs-human, say exactly what needs deciding, and stop",
        "commands.typecheck": _per_package(profile, "typecheck", _code),
        "commands.test_file": _per_package(profile, "test_file", _test_file),
        "commands.suites": _bullets([_suite_line(s) for s in profile.suites]),
        "ui.explorer": profile.explorer if presets_mod.runs_explorer(review) else "none",
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

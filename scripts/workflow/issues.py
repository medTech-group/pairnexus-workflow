"""Reading tickets: blockers, areas, readiness. Pure functions over issue JSON.

An issue is a dict as GitHub's REST API returns it (number, title, body, state,
state_reason, labels, assignees, pull_request, sub_issues_summary,
issue_dependencies_summary). Labels may be dicts with a "name" or plain
strings; assignees dicts with a "login" or plain strings. Labels are compared
case-insensitively.

A blocker is an issue number in this repository, or the text "owner/repo#n"
for one in another repository, which readiness can't resolve and so blocks.
Blockers are read as `#n`, `owner/repo#n` or an issue URL
(`https://github.com/owner/repo/issues/n`), on plain lines or lines quoted
with `>`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Union

READY_LABEL = "ready-for-agent"
CLAIM_LABEL = "workflow:in-progress"
INFRA_LABEL = "workflow:infra"
HUMAN_LABELS = {"needs-human", "owner-task", "ready-for-human"}
NOT_BUILD_LABELS = {"wayfinder:map", "spec"}

Blocker = Union[int, str]

# "#12" or "owner/repo#12", not "foo#12" or part of a longer word.
_REF = re.compile(r"(?<![\w#/.-])((?:[\w.-]+/[\w.-]+)?)#(\d+)\b")
_CLOSES = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*"
    r"(?:(?P<repo>[\w.-]+/[\w.-]+)#|https?://(?:www\.)?github\.com/(?P<urepo>[\w.-]+/[\w.-]+)/issues/|#)"
    r"(?P<n>\d+)\b",
    re.I,
)
_HEADING = re.compile(r"^\s*#{1,6}\s")
_BLOCKED_LINE = re.compile(r"^\s*(?:[-*+]\s+)?\**blocked by\**(?:\s*:\**|(?=\s)|$)(.*)$", re.I)
_BLOCKED_HEADING = re.compile(r"^\s*#{1,6}\s*blocked by\s*:?\s*$", re.I)
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_QUOTE = re.compile(r"^\s*(?:>\s?)+")
_URL = re.compile(r"https?://(?:www\.)?github\.com/([\w.-]+/[\w.-]+)/issues/(\d+)\b[^\s)\]>]*", re.I)


def labels_of(issue: dict) -> set[str]:
    """The issue's labels, casefolded."""
    out = set()
    for l in issue.get("labels") or []:
        name = (l.get("name") or "") if isinstance(l, dict) else str(l)
        if name:
            out.add(name.casefold())
    return out


def assignees_of(issue: dict) -> list[str]:
    return [a["login"] if isinstance(a, dict) else str(a) for a in issue.get("assignees") or []]


def parse_numbers(text: str | None) -> set[int]:
    """Ticket numbers from "13, #143": commas between, `#` and spaces ignored.

    Raises ValueError naming the first part that isn't a number.
    """
    out: set[int] = set()
    for part in (text or "").split(","):
        p = part.strip().lstrip("#").strip()
        if not p:
            continue
        if not p.isdigit():
            raise ValueError(f"not a ticket number: {part.strip()!r}")
        out.add(int(p))
    return out


def _same_repo(ref_repo: str, repo: str | None) -> bool:
    return bool(repo) and ref_repo.casefold() == (repo or "").casefold()


def _refs(text: str, repo: str | None) -> list[Blocker]:
    """The refs in a line, in order: `#n`, `owner/repo#n` and issue URLs."""
    found: list[tuple[int, Blocker]] = []

    def add(pos: int, ref_repo: str, n: int) -> None:
        found.append((pos, n if not ref_repo or _same_repo(ref_repo, repo) else f"{ref_repo}#{n}"))

    for m in _URL.finditer(text):
        add(m.start(), m.group(1), int(m.group(2)))
    rest = _URL.sub(lambda m: " " * len(m.group(0)), text)
    for m in _REF.finditer(rest):
        add(m.start(), m.group(1), int(m.group(2)))
    return [b for _, b in sorted(found, key=lambda x: x[0])]


def _is_none(line: str) -> bool:
    return _BULLET.sub("", line).strip().strip("*_`").casefold().startswith("none")


def blockers_of(body: str | None, repo: str | None = None) -> list[Blocker]:
    """Blockers, in the conventions the flow uses.

    - a line `Blocked by: #a, #b` (the colon optional, anywhere, usually first);
    - `Blocked by:` with the refs listed on the following lines, until a blank
      line or a heading;
    - a `## Blocked by` heading whose section lists refs.

    A list or section whose first non-empty line starts with "None" has none.
    `owner/repo#n` is this repo's #n only when owner/repo is `repo` (any case);
    otherwise it is kept as the text "owner/repo#n".
    """
    if not body:
        return []
    found: list[Blocker] = []
    lines = [_QUOTE.sub("", l) for l in body.splitlines()]
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if _BLOCKED_HEADING.match(line):
            first = True
            while i < len(lines) and not _HEADING.match(lines[i]):
                cur = lines[i]
                i += 1
                if not cur.strip():
                    continue
                if first and _is_none(cur):
                    while i < len(lines) and not _HEADING.match(lines[i]):
                        i += 1
                    break
                first = False
                found += _refs(cur, repo)
            continue
        m = _BLOCKED_LINE.match(line)
        if not m:
            continue
        rest = m.group(1)
        if _is_none(rest):
            continue
        if rest.strip(" \t*_"):
            found += _refs(rest, repo)
            continue
        # The refs follow as a list, until a blank line or a heading.
        first = True
        while i < len(lines) and lines[i].strip() and not _HEADING.match(lines[i]):
            cur = lines[i]
            i += 1
            if first and _is_none(cur):
                while i < len(lines) and lines[i].strip() and not _HEADING.match(lines[i]):
                    i += 1
                break
            first = False
            found += _refs(cur, repo)
    seen: set = set()
    out: list[Blocker] = []
    for b in found:
        key = b.casefold() if isinstance(b, str) else b
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out


_AREA_LINE = re.compile(r"^\s*(?:[-*+]\s+)?\**area\**\s*:\s*(.*)$", re.I)
_AREA_HEADING = re.compile(r"^\s*#{1,6}\s*area\s*(?::\s*(.*))?$", re.I)
_AREA_WORD = re.compile(r"[\w.-]+")


def _slug(text: str) -> str:
    return re.sub(r"[^\w]+", "-", text.casefold()).strip("-_")


def _area_value(text: str) -> str:
    """The value as written, without a bullet, emphasis, backticks, quotes or a
    trailing (parenthetical)."""
    v = _BULLET.sub("", text).strip()
    v = re.sub(r"\([^)]*\)", " ", v)
    return v.replace("`", " ").replace("*", " ").replace('"', " ").replace("'", " ").strip()


def read_area(body: str | None, areas: Iterable[str] | None = None) -> tuple[str | None, str | None]:
    """The ticket's area and a note about it, if any.

    The value after `Area:` (bold, bulleted or in backticks too), or the first
    non-empty line under an `## Area` heading, lowercased. An area is one word.
    With several words (`Area: the clock module`), the first word is taken only
    when it is one of the profile's `areas`; otherwise the whole value is
    slugified (`the-clock-module`), with a note. A one-word area that isn't one
    of the profile's areas is kept as its own area, with a note.
    """
    raw = _raw_area(body)
    if raw is None:
        return None, None
    known = sorted({a.casefold() for a in areas}) if areas else []
    words = [w.strip(".-_").casefold() for w in _AREA_WORD.findall(raw)]
    words = [w for w in words if w]
    if not words:
        return None, None
    listed = f"[{', '.join(known)}]" if known else "the profile's [areas]"
    if len(words) == 1:
        area = words[0]
        if known and area not in known:
            return area, f"area {area} isn't one of the profile's areas ({', '.join(known)}); treated as its own area"
        return area, None
    if words[0] in known:
        return words[0], None
    area = _slug(raw)
    return area, f"Area should be one word from {listed}; {raw!r} treated as its own area, {area}"


def _raw_area(body: str | None) -> str | None:
    if not body:
        return None
    lines = body.splitlines()
    for i, line in enumerate(lines):
        h = _AREA_HEADING.match(line)
        if h:
            if (h.group(1) or "").strip():
                v = _area_value(h.group(1))
                if v:
                    return v
                continue
            for nxt in lines[i + 1 :]:
                if not nxt.strip():
                    continue
                if _HEADING.match(nxt):
                    break
                return _area_value(nxt) or None
            continue
        m = _AREA_LINE.match(line)
        if m:
            v = _area_value(m.group(1))
            if v:
                return v
    return None


def area_of(body: str | None, areas: Iterable[str] | None = None) -> str | None:
    """The ticket's area (see `read_area`)."""
    return read_area(body, areas)[0]


def closed_by_open_prs(prs: list[dict], repo: str | None = None) -> dict[int, int]:
    """Issue number -> the open PR whose body closes it (drafts included).

    `Closes #8`, `closes:#8`, `Fixes owner/repo#3` and
    `Resolves https://github.com/owner/repo/issues/12`; the last two only
    when owner/repo is `repo` (any case).
    """
    out: dict[int, int] = {}
    for pr in prs:
        if (pr.get("state") or "open").lower() != "open":
            continue
        for m in _CLOSES.finditer(pr.get("body") or ""):
            ref_repo = m.group("repo") or m.group("urepo")
            if ref_repo and not _same_repo(ref_repo, repo):
                continue
            out.setdefault(int(m.group("n")), pr["number"])
    return out


def is_build_ticket(issue: dict) -> bool:
    """Not a map, not a spec (label or a "Spec:" title), not a parent of sub-issues."""
    if labels_of(issue) & NOT_BUILD_LABELS:
        return False
    if (issue.get("title") or "").strip().casefold().startswith("spec:"):
        return False
    subs = issue.get("sub_issues_summary") or {}
    if isinstance(subs, dict) and (subs.get("total") or 0) > 0:
        return False
    return True


@dataclass
class Verdict:
    number: int
    title: str
    ready: bool
    area: str | None = None
    reasons: list[str] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


def readiness(
    issues: list[dict],
    prs: list[dict],
    exclude: set[int] | frozenset = frozenset(),
    claimed_ok: set[int] | frozenset = frozenset(),
    repo: str | None = None,
    areas: Iterable[str] | None = None,
) -> list[Verdict]:
    """Every open `ready-for-agent` build ticket with whether it is ready and why not.

    Ready means: open; labelled ready-for-agent; a build ticket (not a map, a
    spec or a parent of sub-issues); not needs-human, owner-task or
    ready-for-human; not claimed (the claim label) unless in `claimed_ok`; no
    open PR closes it; not excluded; no open GitHub issue dependency blocks it;
    and every blocker closed *as completed*. A blocker closed as not planned,
    one missing from `issues`, or one in another repository still blocks.

    `repo` is the profile's owner/repo. `areas` are the profile's areas: when
    given, a ticket whose area isn't one of them gets a note, never a block.
    """
    by_num = {i["number"]: i for i in issues if "pull_request" not in i}
    pr_for = closed_by_open_prs(prs, repo)
    known_areas = sorted({a.casefold() for a in areas}) if areas else []
    out: list[Verdict] = []
    for num in sorted(by_num):
        issue = by_num[num]
        if (issue.get("state") or "").lower() != "open":
            continue
        labels = labels_of(issue)
        if READY_LABEL not in labels or not is_build_ticket(issue):
            continue
        area, note = read_area(issue.get("body"), known_areas)
        v = Verdict(
            number=num,
            title=issue.get("title") or "",
            ready=True,
            area=area,
            labels=sorted(labels),
        )
        v.blockers = blockers_of(issue.get("body"), repo)
        if note:
            v.notes.append(note)
        if num in exclude:
            v.reasons.append("excluded")
        for lab in sorted(labels & HUMAN_LABELS):
            v.reasons.append(f"labelled {lab}")
        if CLAIM_LABEL in labels and num not in claimed_ok:
            v.reasons.append("claimed (workflow:in-progress)")
        if num in pr_for:
            v.reasons.append(f"open PR #{pr_for[num]} closes it")
        deps = issue.get("issue_dependencies_summary") or {}
        if isinstance(deps, dict) and (deps.get("blocked_by") or 0) > 0:
            v.reasons.append("blocked by a GitHub issue dependency")
        for b in v.blockers:
            if isinstance(b, str):
                v.reasons.append(f"blocker {b} is in another repository")
                continue
            bi = by_num.get(b)
            if bi is None:
                v.reasons.append(f"blocker #{b} unknown (not in the issue list)")
            elif (bi.get("state") or "").lower() != "closed":
                v.reasons.append(f"blocked by open #{b}")
            elif (bi.get("state_reason") or "completed") != "completed":
                v.reasons.append(f"blocker #{b} closed as {bi.get('state_reason')}, not completed")
        v.ready = not v.reasons
        out.append(v)
    return out


def startable(
    verdicts: list[Verdict],
    running_areas: list[str | None],
    slots: int,
    overrides: set[int] | frozenset = frozenset(),
) -> list[Verdict]:
    """Ready tickets to start now, at most `slots`, one per area.

    Tickets labelled workflow:infra come first, then lowest number first. A
    ticket with no area may run beside anything. `overrides` are tickets the
    run state allows to share an area. Areas are compared case-insensitively.
    """
    taken = {a.casefold() for a in running_areas if a}
    order = sorted(
        (v for v in verdicts if v.ready),
        key=lambda v: (INFRA_LABEL not in {l.casefold() for l in v.labels}, v.number),
    )
    out: list[Verdict] = []
    for v in order:
        if len(out) >= slots:
            break
        area = v.area.casefold() if v.area else None
        if area and area in taken and v.number not in overrides:
            continue
        out.append(v)
        if area:
            taken.add(area)
    return out

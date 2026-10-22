"""Reading tickets: blockers, areas, readiness. Pure functions over issue JSON.

An issue is a dict as GitHub's REST API returns it (number, title, body, state,
state_reason, labels, assignees, pull_request, sub_issues_summary,
issue_dependencies_summary). Labels may be dicts with a "name" or plain
strings; assignees dicts with a "login" or plain strings. Labels are compared
case-insensitively.

A blocker is an issue number in this repository, or the text "owner/repo#n"
for one in another repository, which readiness can't resolve and so blocks.
Blockers are read as `#n`, `owner/repo#n` or an issue or pull request URL
(`https://github.com/owner/repo/issues/n`, `…/pull/n`), on plain lines or lines
quoted with `>`, and after "blocked by" in the middle of a sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timezone
from typing import Callable, Iterable, Union

READY_LABEL = "ready-for-agent"
CLAIM_LABEL = "workflow:in-progress"
INFRA_LABEL = "workflow:infra"
HUMAN_LABELS = {"needs-human", "owner-task", "ready-for-human"}
SPEC_LABEL = "spec"
NOT_BUILD_LABELS = {"wayfinder:map", SPEC_LABEL}
# Specs created before this date are never noted as unreviewed (#234), so
# updating the kit adds no notes to old specs: the date of the release that
# brings the note in, which that release sets.
SPEC_REVIEW_SINCE = date(2026, 10, 22)

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
_URL = re.compile(r"https?://(?:www\.)?github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/(\d+)\b[^\s)\]>]*", re.I)
# "… is blocked by #8 and #9 …" in the middle of a sentence: the refs right after it.
_ONE_REF = r"(?:https?://(?:www\.)?github\.com/[\w.-]+/[\w.-]+/(?:issues|pull)/\d+\S*|(?:[\w.-]+/[\w.-]+)?#\d+\b)"
_MID_BLOCKED = re.compile(rf"\bblocked\s+by\s*:?\s*\**\s*({_ONE_REF}(?:\s*(?:,|\band\b|&|\+)\s*{_ONE_REF})*)", re.I)
_NEGATED = re.compile(r"(?:\bnot|\bno\s+longer|n['’]t|\bnever)\s+(?:\w+\s+)?$", re.I)


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
            for mm in _MID_BLOCKED.finditer(line):
                if not _NEGATED.search(line[: mm.start()]):
                    found += _refs(mm.group(1), repo)
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
    when it is one of the profile's `areas` (with a note when other words are
    areas too, `Area: messages, sharing`); otherwise the whole value is
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
        others = [w for w in dict.fromkeys(words[1:]) if w in known and w != words[0]]
        if others:
            return words[0], f"Area names several areas ({', '.join([words[0], *others])}); took the first, {words[0]}"
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


_BACKTICKED = re.compile(r"`([^`\n]+)`")
_URLISH = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_DOTFILE = re.compile(r"^\.[A-Za-z_][\w.-]*$")
_SPLIT = re.compile(r"[\s()\[\]<>\"',;|]+")
_WORD = re.compile(r"[^\s()\[\]<>\"',;|]+")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
# A GitHub blob or tree URL: the repository, then the path after the branch.
_REPO_URL = re.compile(
    r"https?://(?:www\.)?github\.com/([\w.-]+/[\w.-]+)/(?:blob|tree|edit|raw)/[^/\s?#]+/([^\s?#)\]>\"'`]+)[^\s)\]>\"'`]*",
    re.I,
)
# "Don't touch `.github/workflows/ci.yml`": the line says not to change it.
_DONT = re.compile(r"\b(?:don['’]t|do\s+not|never(?!\s+mind\b))\b", re.I)
# Where a clause ends: a sentence's end, a semicolon, a colon or a dash. Only
# the clause a path is in decides whether it is read or left alone.
_CLAUSE = re.compile(r"[.;:!?](?=\s|$)|\s[—–-]\s|,\s*(?=(?:just|but|then|instead|so|and)\b)", re.I)
# A fenced block whose paths count: the prose just before it asks for a change
# *to* or *in* what follows ("Add a job to:").
# Matched against the line with its trailing colon and spaces taken off, so it stays linear.
_INTO = re.compile(r"\b(?:to|in|into)$", re.I)
# "Read the key from .env at startup": the code reads it, and nothing before
# the path on its line says to change anything.
_READS = re.compile(r"\b(?:read|reads|reading|load|loads|loading|parse|parses|parsing)\b|\bfrom\s*$", re.I)
_CHANGES = re.compile(
    r"\b(?:edit|change|update|add|remove|delete|rotate|write|modify|fix|replace|rename|move|create|set|cache|bump|touch"
    r"|make|tweak|adjust|configure|enable|disable|pin|raise|lower|split|merge|extend|drop|append|insert|include)(?:s|es|d|ed|ing)?\b",
    re.I,
)


def _path_token(tok: str) -> str | None:
    """`tok` cleaned as a path (`./`, a leading `/`, a `#L20` anchor and
    trailing punctuation gone), or None when it isn't one: a URL, an issue ref
    (`acme/demo#3`), an @mention, empty."""
    t = tok.strip().strip("*_:!?")
    if "#" in t:
        t, anchor = t.split("#", 1)
        if not t or anchor.isdigit():
            return None
    while t.endswith(".") and t not in (".", ".."):
        t = t[:-1]
    if not t or _URLISH.match(t) or "@" in t:
        return None
    while t.startswith("./"):
        t = t[2:]
    t = t.lstrip("/")
    return t or None


def _blank(m: re.Match) -> str:
    return " " * len(m.group(0))


def _mentions(body: str | None, repo: str | None = None) -> list[tuple[str, bool]]:
    """(path, exact) for each path a ticket's body names, in order: every word
    of a `backticked` span, bare words holding a `/` or a dot-file name
    (`.env`), and the path of a GitHub blob or tree URL into `repo` (into any
    repository when `repo` isn't given). `exact` is True for a bare dot-file
    name: it counts only when it is itself protected (`.env`), not when it
    merely holds a protected path ("the .github directory").

    Left out: fenced code blocks, unless the prose just before one asks for a
    change to what follows ("Add a job to:"); a mention after "don't", "do not"
    or "never" in its clause; and one its clause only reads ("Read the key from
    .env"), with no word of change before it. A clause ends at a sentence's
    end, a semicolon, a colon or a dash, so "Don't break the build: edit
    `ci.yml`" names it. When in doubt it names it: a note costs a question."""
    if not body:
        return []
    found: list[tuple[str, bool]] = []
    fence: str | None = None
    fence_counts = False
    prose = ""
    for line in body.splitlines():
        f = _FENCE.match(line)
        if f:
            if fence is None:
                fence = f.group(1)[0]
                last = _CLAUSE.split(prose.rstrip().rstrip(":"))[-1] if prose.strip() else ""
                fence_counts = bool(_CHANGES.search(last) and _INTO.search(prose.rstrip().rstrip(":").rstrip()))
            elif f.group(1)[0] == fence:
                fence = None
                prose = ""
            continue
        if fence is not None and not fence_counts:
            continue
        if fence is None and line.strip():
            prose = line
        here: list[tuple[int, str, bool]] = []
        for m in _REPO_URL.finditer(line):
            p = _path_token(m.group(2))
            if p and (repo is None or m.group(1).casefold() == repo.casefold()):
                here.append((m.start(), p, False))
        rest = _REPO_URL.sub(_blank, line)
        for m in _BACKTICKED.finditer(rest):
            here += [(m.start(), p, False) for p in map(_path_token, _SPLIT.split(m.group(1))) if p]
        rest = _BACKTICKED.sub(_blank, rest)
        for m in _WORD.finditer(rest):
            p = _path_token(m.group(0))
            if p and ("/" in p or _DOTFILE.match(p)):
                here.append((m.start(), p, "/" not in p))
        for pos, p, exact in sorted(here, key=lambda x: x[0]):
            before = "" if fence is not None else _CLAUSE.split(line[:pos])[-1]
            if _DONT.search(before) or (_READS.search(before) and not _CHANGES.search(before)):
                continue
            found.append((p, exact))
    return found


def named_paths(body: str | None, repo: str | None = None) -> list[str]:
    """Path-like tokens a ticket's body names, in order and once each (see
    `_mentions`). Other URLs and issue refs are left out."""
    return list(dict.fromkeys(p for p, _ in _mentions(body, repo)))


def protected_named(body: str | None, patterns: Iterable[str] | None, repo: str | None = None) -> list[tuple[str, str]]:
    """(path, pattern) for each path the body names that is, or holds, one of
    the protected `patterns`, matched as the guard matches them (a bare
    dot-file name only when it is one)."""
    pats = [p for p in patterns or [] if p]
    if not pats:
        return []
    from .guard import contains_protected, matches

    out: dict[str, str] = {}
    for p, exact in _mentions(body, repo):
        hit = (matches if exact else contains_protected)(p.rstrip("/"), pats)
        if hit and p not in out:
            out[p] = hit
    return list(out.items())


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
    protected: Iterable[str] | None = None,
) -> list[Verdict]:
    """Every open `ready-for-agent` build ticket with whether it is ready and why not.

    Ready means: open; labelled ready-for-agent; a build ticket (not a map, a
    spec or a parent of sub-issues); not needs-human, owner-task or
    ready-for-human; not claimed (the claim label) unless in `claimed_ok`; no
    open PR closes it; not excluded; no open GitHub issue dependency blocks it;
    every blocker closed *as completed*. A blocker closed as not planned, one
    missing from `issues`, or one in another repository still blocks.

    `repo` is the profile's owner/repo. `areas` are the profile's areas: when
    given, a ticket whose area isn't one of them gets a note, never a block.
    `protected` are the profile's protected paths: a ticket whose body names
    one (`protected_named`) gets a note, never a block, since a ticket session
    can't change one and the words alone can't tell a change from a mention;
    the conductor lists such tickets at kick-off for the owner to keep or exclude.
    """
    protected = list(protected or [])
    by_num = {i["number"]: i for i in issues if "pull_request" not in i}
    # Pull requests as the issues API lists them (`pull_request.merged_at`), for PR blockers.
    pr_items = {i["number"]: i for i in issues if "pull_request" in i}
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
            if bi is None and b in pr_items:
                pi = pr_items[b]
                if (pi.get("state") or "").lower() != "closed":
                    v.reasons.append(f"blocked by open PR #{b}")
                elif not (pi.get("pull_request") or {}).get("merged_at"):
                    v.reasons.append(f"blocker PR #{b} closed without merging")
                continue
            if bi is None:
                v.reasons.append(f"blocker #{b} unknown (not in the issue list; for a PR, list it with the issues API's pull requests)")
            elif (bi.get("state") or "").lower() != "closed":
                v.reasons.append(
                    f"blocked by owner task #{b}" if labels_of(bi) & {"owner-task", "ready-for-human"} else f"blocked by open #{b}"
                )
            elif (bi.get("state_reason") or "completed") != "completed":
                v.reasons.append(f"blocker #{b} closed as {bi.get('state_reason')}, not completed")
        for path, pat in protected_named(issue.get("body"), protected, repo):
            v.notes.append(f"names protected path {path} ({pat}): check it isn't an owner task")
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


# ---------- a spec with no clean review (#234) ----------

_PARENT_HEADING = re.compile(r"^\s*#{1,6}\s*parent\s*:?\s*$", re.I)
_ISSUE_API_URL = re.compile(r"/repos/([\w.-]+/[\w.-]+)/issues/(\d+)/?$", re.I)


class SpecReviewsUnread(Exception):
    """A spec's comments, or their authors' permissions, couldn't be read:
    the message says why."""


def parent_of(issue: dict, repo: str | None = None) -> int | None:
    """The ticket's parent issue in this repository: GitHub's sub-issue link
    (`parent`, as the MCP tools give it, or `parent_issue_url`, as the REST API
    does), else the first ref on the first line under a `## Parent` heading.
    None when it has none, or its parent is in another repository."""
    p = issue.get("parent")
    if isinstance(p, dict) and isinstance(p.get("number"), int) and not isinstance(p["number"], bool):
        where = p.get("repository")
        where = where.get("full_name") or where.get("nameWithOwner") if isinstance(where, dict) else where
        return p["number"] if not isinstance(where, str) or not where or _same_repo(where, repo or where) else None
    url = issue.get("parent_issue_url")
    if isinstance(url, str) and url:
        m = _ISSUE_API_URL.search(url)
        return int(m.group(2)) if m and _same_repo(m.group(1), repo or m.group(1)) else None
    lines = [_QUOTE.sub("", l) for l in (issue.get("body") or "").splitlines()]
    for i, line in enumerate(lines):
        if not _PARENT_HEADING.match(line):
            continue
        for cur in lines[i + 1 :]:
            if _HEADING.match(cur):
                return None
            if cur.strip():
                refs = _refs(cur, repo)  # the first ref, which may be another repository's
                return refs[0] if refs and isinstance(refs[0], int) else None
    return None


def _created_on(issue: dict) -> date | None:
    """The day an issue was created, in UTC, or None when it can't be read."""
    from .merge import _time

    t = _time(issue.get("created_at") or issue.get("createdAt"))
    try:
        return t.astimezone(timezone.utc).date() if t else None
    except OverflowError:  # a date at the edge of the calendar, which GitHub never gives
        return None


def parent_spec(issue: dict, by_num: dict[int, dict], repo: str | None = None, since: date = SPEC_REVIEW_SINCE) -> dict | None:
    """The ticket's parent spec when its review counts: labelled `spec` and
    created on or after `since` (one whose creation date can't be read counts:
    a note costs a question). None otherwise."""
    n = parent_of(issue, repo)
    spec = by_num.get(n) if n is not None else None
    if spec is None or SPEC_LABEL not in labels_of(spec):
        return None
    created = _created_on(spec)
    return spec if created is None or created >= since else None


def _spec_note(
    spec: dict,
    fetch_comments: Callable[[int], object],
    permissions: Callable[[list[str]], object],
    known: dict[str, str],
) -> str | None:
    """The note for one spec, or None when it has a clean review. `known` holds
    the permissions already read (login casefolded -> permission), shared by
    every spec of one `ready`, so each login is looked up once."""
    from .merge import Unreadable, _in_time_order, _may_review, _permissions, _time
    from .posts import CommentsError, _number, comments_from
    from .reviews import body_hash, read, spec_reviewed

    n = spec["number"]
    body = spec.get("body") if isinstance(spec.get("body"), str) else ""

    def unread_note(why: str) -> str:
        return f"spec #{n}: couldn't read its reviews ({why})"

    try:
        carried = spec.get("comments")
        if isinstance(carried, int) and not isinstance(carried, bool) and carried == 0:
            comments = []
        elif isinstance(carried, (list, dict)):  # the MCP route's file carries them
            comments = comments_from(carried)
        else:
            comments = comments_from(fetch_comments(n))
    except SpecReviewsUnread as e:
        return unread_note(str(e))
    except CommentsError as e:
        return unread_note(f"its comments: {e}")
    ordered = _in_time_order(comments, lambda c: _time(c.get("created_at") or c.get("createdAt")), _number)
    records = read(ordered)
    digest = body_hash(body)
    authors = sorted({r.author for r in records if r.kind == "spec" and r.body == digest and r.author}, key=str.casefold)
    new = [a for a in authors if a.casefold() not in known]
    if new:
        try:
            got = _permissions(permissions(new))
        except SpecReviewsUnread as e:
            return unread_note(str(e))
        except Unreadable as e:
            return unread_note(f"the reviewers' permissions: {e.why}")
        known.update(got)
        known.update({a.casefold(): "none" for a in new if a.casefold() not in got})  # left out: no write access
    if spec_reviewed([r for r in records if _may_review(r.author, known)], body):
        return None
    return f"spec #{n} has no clean review: check it before building"


def note_unreviewed_specs(
    verdicts: list[Verdict],
    issues: list[dict],
    repo: str | None,
    fetch_comments: Callable[[int], object],
    permissions: Callable[[list[str]], object],
    since: date = SPEC_REVIEW_SINCE,
) -> None:
    """Add a note to each ready verdict whose parent spec (`parent_spec`) has
    no clean spec record for its current body from an account with write
    access: "spec #<n> has no clean review: check it before building". It
    never changes whether a ticket is ready.

    A spec's comments come from its issue JSON when it carries them (a list,
    as the MCP route's file gives them; a count of 0 is none), else from
    `fetch_comments(number)`, called only for the parent specs of ready
    tickets, once each. `permissions(logins)` gives the permissions of the
    authors of a spec's records for its current body, in any shape
    merge-check's `--permissions` takes, each login asked once; a login it
    leaves out has no write access. Either
    raises SpecReviewsUnread, which gives the note "spec #<n>: couldn't read
    its reviews (<why>)" instead of silence."""
    by_num = {i["number"]: i for i in issues if "pull_request" not in i}
    note_of: dict[int, str | None] = {}  # spec number -> its note, read once
    known: dict[str, str] = {}  # login (casefolded) -> permission, looked up once
    for v in verdicts:
        issue = by_num.get(v.number)
        spec = parent_spec(issue, by_num, repo, since) if v.ready and issue else None
        if spec is None:
            continue
        if spec["number"] not in note_of:
            note_of[spec["number"]] = _spec_note(spec, fetch_comments, permissions, known)
        if note_of[spec["number"]]:
            v.notes.append(note_of[spec["number"]])

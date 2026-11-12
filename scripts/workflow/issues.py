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
# Handed on by an earlier session with its review not yet clean (#380, #376).
CARRY_ON_LABEL = "workflow:carry-on"
INFRA_LABEL = "workflow:infra"
HUMAN_LABELS = {"needs-human", "owner-task", "ready-for-human"}
# An owner task: what only the owner can do. A blocker carrying one holds what it blocks.
OWNER_TASK_LABELS = {"owner-task", "ready-for-human"}
# Tracks a research note: a study's, a fact note's, or one a session filed about a note
# (the `study` skill's section 5). The kit reads every issue carrying it as research.
RESEARCH_LABEL = "research"
SPEC_LABEL = "spec"
NOT_BUILD_LABELS = {"wayfinder:map", SPEC_LABEL}
# Specs created before this date are never noted as unreviewed (#234), so
# updating the kit adds no notes to old specs: the date of the release that
# brings the note in, which that release sets.
SPEC_REVIEW_SINCE = date(2026, 10, 23)

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


def is_whole(v) -> bool:
    """Whether a value read from JSON or TOML is a whole number: an `int`,
    never a `bool` (which Python counts as one). A float such as `3.0`, a
    text such as `"3"` and None aren't. Every whole-number check in the kit
    calls it (#773); a caller adds its own range."""
    return isinstance(v, int) and not isinstance(v, bool)


_SURROGATE = re.compile("[\ud800-\udfff]")


def escape_surrogates(text: str) -> str:
    """The text with each lone surrogate (half a pair, as JSON's `\\ud800`
    gives it) written as JSON escapes it, `\\ud800`: UTF-8 can't encode one,
    so printing it ends in a traceback. Everything else is left as it is
    (#774)."""
    return _SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text)


# Control characters (C0, DEL, C1), the line and paragraph separators, and the
# bidirectional embeddings, overrides and isolates: each could start a line, or
# be acted on by a terminal, if printed as it is (#776).
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
_NAMED = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def escape_controls(text: str) -> str:
    """Untrusted text (an issue's title, a branch) as a terminal may show it:
    each control character, line or paragraph separator and bidirectional
    override written as JSON escapes it (`\\n`, `\\u001b`), so it can't
    add a line or send an escape code; everything else, text outside ASCII
    and a lone surrogate among it, is left as it is (#776)."""
    return _CONTROL.sub(lambda m: _NAMED.get(m.group()) or f"\\u{ord(m.group()):04x}", text)


def labels_of(issue: dict) -> set[str]:
    """The issue's labels, casefolded, as GitHub matches them: names, or
    objects with a text `name`. A label of any other type is read past, the
    others kept, and a `labels` field that isn't a list reads as none (#772)."""
    labels = issue.get("labels")
    names = [l.get("name") if isinstance(l, dict) else l for l in labels] if isinstance(labels, list) else []
    return {n.casefold() for n in names if isinstance(n, str) and n}


def assignees_of(issue: dict) -> list[str]:
    return [a["login"] if isinstance(a, dict) else str(a) for a in issue.get("assignees") or []]


def parse_number_list(text: str | None) -> list[int]:
    """Ticket numbers from "13, #143", in the order given, each once: commas
    between, `#` and spaces ignored.

    Raises ValueError naming the first part that isn't a number.
    """
    out: dict[int, None] = {}
    for part in (text or "").split(","):
        p = part.strip().lstrip("#").strip()
        if not p:
            continue
        digits = p.lstrip("0")
        # "٣" or "²" is no ticket number, nor one past 18 digits (Python's own
        # limit on int() is a setting, and counts leading zeros)
        if not (p.isascii() and p.isdigit()) or len(digits) > 18:
            shown = part.strip()
            shown = shown[:20] + "\u2026" if len(shown) > 20 else shown
            raise ValueError(f"not a ticket number: {shown!r}")
        out.setdefault(int(digits or "0"))
    return list(out)


def parse_numbers(text: str | None) -> set[int]:
    """`parse_number_list`, as a set."""
    return set(parse_number_list(text))


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


def can_be_area(name: str) -> bool:
    """A ticket's `Area:` could give `name`: one word, as `read_area` reads it."""
    return bool(_AREA_WORD.fullmatch(name)) and name.strip(".-_") == name


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


def is_spec(issue: dict) -> bool:
    """The `spec` label, or a "Spec:" title."""
    return SPEC_LABEL in labels_of(issue) or (issue.get("title") or "").strip().casefold().startswith("spec:")


def is_build_ticket(issue: dict) -> bool:
    """Not a map, not a spec (`is_spec`), not a parent of sub-issues."""
    if labels_of(issue) & NOT_BUILD_LABELS or is_spec(issue):
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


# The bar (#428, spec #412): a `## Bar` heading of the ticket's own, as GitHub
# shows it. When in doubt it isn't one, so the ticket is noted (fail closed):
# `has_bar` stops reading at anything whose rendering it can't be sure of.
# Each pattern runs on a line with its trailing spaces taken off, and no two
# of its space runs sit side by side, so a long line can't make it slow.
_BAR_WORD = r"(?:bar:?|\*\*bar:?\*\*|__bar:?__|\*bar:?\*|_bar:?_)"  # bold or italic too
_BAR_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+" + _BAR_WORD + r"(?:[ \t]*:)?(?:[ \t]+#+)?$", re.I)
_BAR_SETEXT = re.compile(_BAR_WORD + r"(?:[ \t]*:)?$", re.I)  # "Bar" at column 0, underlined
_SETEXT_RULE = re.compile(r"(?:=+|-+)$")  # at column 0: not a list item's
_TOP_FENCE = re.compile(r"(`{3,}|~{3,})(.*)$")  # a fence at column 0: top level
# What comes before a line's content: indentation, quote and list markers.
# A fence after any of it, or HTML after a quote or list marker, is where
# GitHub may pair or end things differently.
_CONTAINER = re.compile(r"(?:[ \t>]|(?:[-*+]|\d{1,9}[.)])(?=[ \t]))*")
_FENCE_MARK = re.compile(r"`{3,}|~{3,}")
_HTML_MARK = re.compile(r"<[!?/A-Za-z]")
# HTML blocks, as cmark-gfm starts and ends them: a comment, <?, <!X (a
# capital letter) and <![CDATA[ end at their terminator, a raw-text tag at
# the first line holding any raw-text closing tag, any other tag at a blank
# line. Tag names are ASCII.
_HTML_ENDS = (
    (re.compile(r" {0,3}<!--"), "-->"),
    (re.compile(r" {0,3}<\?"), "?>"),
    (re.compile(r" {0,3}<!\[CDATA\["), "]]>"),
    (re.compile(r" {0,3}<![A-Z]"), ">"),
)
_HTML_RAW = re.compile(r" {0,3}<(?:pre|script|style|textarea)(?=[ \t\v\f>]|$)", re.I | re.A)
_RAW_END = re.compile(r"</(?:pre|script|style|textarea)>", re.I | re.A)
# <!x: a paragraph under cmark-gfm's rule (a declaration needs a capital
# letter), a declaration under newer CommonMark's: either may hide what follows.
_LOWER_DECLARATION = re.compile(r" {0,3}<![a-z]")
_HTML_TAG = re.compile(r" {0,3}</?[A-Za-z]")
# In a stretch has_bar skips as HTML: something GitHub may read as opening
# code or a comment there instead (the first line may be inline HTML, not a
# block, or a list item's block may end early), so has_bar stops reading.
_OPENS_MORE = re.compile(r"`{3,}|~{3,}|<!|<\?|<(?:pre|script|style|textarea)(?=[ \t\v\f>]|$)", re.I | re.A)
_LINE_END = re.compile(r"\r\n|\r|\n")  # Markdown's line ends, not str.splitlines()'s


def _past(lines: list[str], i: int, ends) -> int | None:
    """The index after the first line from `i` on that `ends`, or None when
    none does (the construct is never closed)."""
    while i < len(lines):
        if ends(lines[i]):
            return i + 1
        i += 1
    return None


# What `_html_closed` understands; anything else after a `<` is treated as
# left open. Tags as CommonMark and HTML5 both read them: a quote opens a
# value only after `=`.
_SP = r"[ \t\n\r\f]"
_TAG = re.compile(
    rf"</?[A-Za-z][A-Za-z0-9-]*(?:{_SP}+[A-Za-z_:][-A-Za-z0-9_:.]*"
    rf"(?:{_SP}*={_SP}*(?:\"[^\"]*\"|'[^']*'|[^ \t\n\r\f\"'=<>`]+))?)*{_SP}*/?>",
    re.A,
)
_PLAIN_BOGUS = re.compile(r"<![A-Z][^>]*>")  # <!DOCTYPE …>: HTML5 ends it at the first >
# Constructs whose reading differs between cmark-gfm, newer CommonMark,
# GitHub's tag filter and HTML5, inline or in a block: has_bar stops reading
# at any line (outside fenced code) that holds one. <? and <![ (a processing
# instruction or CDATA cmark ends later than HTML5), comments HTML5 ends
# early, a vertical tab, and tags the tag filter turns into text or whose
# content a browser hides.
_RISKY = re.compile(
    r"<\?|<!\[|--!>|<!--->|<!-->|\v"  # \v: cmark parts a tag's attributes at it, HTML5 doesn't
    r"|</?(?:title|textarea|style|xmp|iframe|noembed|noframes|script|plaintext|select|template|noscript|rp|svg|math)(?![A-Za-z0-9-])",
    re.I | re.A,
)


def _html_closed(text: str) -> bool:
    """`text`, passed through as raw HTML, is made only of plain text, closed
    comments, well-formed tags and `<!X …>`, with nothing `_RISKY`, so it
    ends outside any tag, value or comment and a browser shows what follows
    it. Anything else counts as left open: has_bar stops reading."""
    if _RISKY.search(text):
        return False
    i, n = 0, len(text)
    while i < n:
        i = text.find("<", i)
        if i < 0:
            return True
        if text.startswith("<!--", i):
            j = text.find("-->", i + 4)  # <!-->, <!---> and --!> are _RISKY
            if j < 0:
                return False
            i = j + 3
        elif m := (_TAG.match(text, i) or _PLAIN_BOGUS.match(text, i)):
            i = m.end()
        elif i + 1 < n and (text[i + 1] in "/!?" or text[i + 1].isascii() and text[i + 1].isalpha()):
            return False  # a construct it doesn't understand
        else:
            i += 1  # a literal <
    return True


def _odd_container(line: str) -> bool:
    """A fence indented, quoted or in a list item, or HTML in a quote, a list
    item or indented 4 columns or more (code at the top level, but a list
    item's continuation may hold it): where has_bar stops reading."""
    p = _CONTAINER.match(line).end()
    if not p:
        return False
    rest, before = line[p:], line[:p]
    deep = before.strip(" \t") or "\t" in before or len(before) >= 4
    return bool(_FENCE_MARK.match(rest) or (deep and _HTML_MARK.match(rest)))


def has_bar(body: str | None) -> bool:
    """The body has a `## Bar` heading of its own: at any level, or "Bar"
    underlined at column 0 after a blank line, bold or italic, a trailing
    colon allowed. One GitHub hides or shows as code or text doesn't count:
    in fenced or indented code, an HTML block or comment, or a quote. Reading
    stops (no bar from there on) at a fence that isn't at column 0 or a
    construct never closed, where GitHub could read the rest differently."""
    lines = _LINE_END.split((body or "").removeprefix("\ufeff"))  # GitHub skips a leading BOM
    i, n = 0, len(lines)
    while i < n:
        line = lines[i].rstrip(" \t")
        nxt: int | None = None
        f = _TOP_FENCE.match(line)
        if f and not (f.group(1)[0] == "`" and "`" in f.group(2)):
            close = re.compile(r" {0,3}" + re.escape(f.group(1)[0]) + "{" + str(len(f.group(1))) + ",}$")
            nxt = _past(lines, i + 1, lambda l: close.match(l.rstrip(" \t")))
        elif _odd_container(line) or _LOWER_DECLARATION.match(line) or _RISKY.search(line):
            return False
        elif _HTML_RAW.match(line):
            nxt = _past(lines, i, _RAW_END.search)
        elif end := next((e for start, e in _HTML_ENDS if start.match(line)), None):
            nxt = _past(lines, i, lambda l: end in l)
        elif _HTML_TAG.match(line):
            nxt = _past(lines, i, lambda l: not l.strip(" \t"))
            if nxt is None:
                return False  # to the end: the rest is HTML
        elif _BAR_HEADING.match(line):
            return True
        else:
            after_blank = i == 0 or not lines[i - 1].strip(" \t")
            if after_blank and _BAR_SETEXT.match(line) and i + 1 < n and _SETEXT_RULE.match(lines[i + 1].rstrip(" \t")):
                return True
            i += 1
            continue
        if nxt is None:
            return False  # never closed: the rest is code or HTML
        if not f and nxt > i + 1 and (line[:1] in " \t" or any(_OPENS_MORE.search(l) for l in lines[i + 1 : nxt])):
            # Skipped as HTML, but GitHub may end it sooner (indented, it may be
            # a list item's) or open code or a comment inside it.
            return False
        if not f and not _html_closed("\n".join(lines[i:nxt])):
            return False  # it leaves a tag, a quoted value or a comment open
        i = nxt
    return False


BAR_NOTE = (
    "area {area} is in run.bar_areas, but the ticket has no ## Bar heading: add one saying what the change "
    "must handle, what it does when it can't be sure (fail closed), and the limits it accepts"
)


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
    bar_areas: Iterable[str] | None = None,
) -> list[Verdict]:
    """Every open `ready-for-agent` build ticket with whether it is ready and why not.

    Ready means: open; labelled ready-for-agent; a build ticket (not a map, a
    spec or a parent of sub-issues); not needs-human, owner-task or
    ready-for-human; not research (#572); not claimed (the claim label) unless in `claimed_ok`; no
    open PR closes it; not excluded; no open GitHub issue dependency blocks it;
    every blocker closed *as completed*. A blocker closed as not planned, one
    missing from `issues`, or one in another repository still blocks.

    `repo` is the profile's owner/repo. `areas` are the profile's areas: when
    given, a ticket whose area isn't one of them gets a note, never a block.
    `protected` are the profile's protected paths: a ticket whose body names
    one (`protected_named`) gets a note, never a block, since a ticket session
    can't change one and the words alone can't tell a change from a mention;
    the conductor lists such tickets at kick-off for the owner to keep or exclude.
    `bar_areas` are the profile's `run.bar_areas` (#428): a ticket in one
    whose body has no `## Bar` (`has_bar`) gets a note, never a block.
    """
    protected = list(protected or [])
    need_bar = {a.casefold() for a in bar_areas or [] if a}
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
        if RESEARCH_LABEL in labels:
            # Research, not a build ticket, whatever its other labels (#572), as `status` reads it (#514).
            v.reasons.append(f"labelled `{RESEARCH_LABEL}`: a research issue, not a build ticket (the `study` skill's section 5)")
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
                    f"blocked by owner task #{b}" if labels_of(bi) & OWNER_TASK_LABELS else f"blocked by open #{b}"
                )
            elif (bi.get("state_reason") or "completed") != "completed":
                v.reasons.append(f"blocker #{b} closed as {bi.get('state_reason')}, not completed")
        for path, pat in protected_named(issue.get("body"), protected, repo):
            v.notes.append(f"names protected path {path} ({pat}): check it isn't an owner task")
        if area and area in need_bar and not has_bar(issue.get("body")):
            v.notes.append(BAR_NOTE.format(area=area))
        v.ready = not v.reasons
        out.append(v)
    return out


def startable(
    verdicts: list[Verdict],
    running_areas: list[str | None],
    slots: int,
    overrides: set[int] | frozenset = frozenset(),
    first: list[int] | tuple = (),
) -> list[Verdict]:
    """Ready tickets to start now, at most `slots`, one per area.

    Tickets labelled workflow:infra come first (lowest number first), then the
    tickets in `first`, in the order given (`ready --first`, #372: a run's
    tickets to fix old bugs or late findings, and split tickets), then the
    rest, lowest number first. A ticket in `first` that isn't ready is left
    out like any other; one that is infra stays among the infra tickets. A
    ticket with no area may run beside anything. `overrides` are tickets the
    run state allows to share an area. Areas are compared case-insensitively.
    """
    taken = {a.casefold() for a in running_areas if a}
    rank = {n: i for i, n in enumerate(dict.fromkeys(first))}  # a caller's list may repeat a number

    def key(v: Verdict):
        if INFRA_LABEL in {l.casefold() for l in v.labels}:
            return (0, 0, v.number)  # infra: by number, whatever `first` says
        return (1, rank.get(v.number, len(rank)), v.number)

    order = sorted((v for v in verdicts if v.ready), key=key)
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
    if isinstance(p, dict) and is_whole(p.get("number")):
        where = p.get("repository")
        if isinstance(where, dict):
            where = where.get("full_name") or where.get("nameWithOwner")
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


def _unread_note(n: int, why: str) -> str:
    return f"spec #{n}: couldn't read its reviews ({why})"


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
        return _unread_note(n, why)

    try:
        carried = spec.get("comments")
        if is_whole(carried) and carried == 0:
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
    new: dict[str, str] = {}  # casefolded -> the login as first written, once each whatever its case
    for r in records:  # in the order posted, so the same login is asked each time
        if r.kind == "spec" and r.body == digest and r.author and r.author.casefold() not in known:
            new.setdefault(r.author.casefold(), r.author)
    if new:
        try:
            got = _permissions(permissions(list(new.values())))
        except SpecReviewsUnread as e:
            return unread_note(str(e))
        except Unreadable as e:
            return unread_note(f"the reviewers' permissions: {e.why}")
        known.update(got)
        known.update({k: "none" for k in new if k not in got})  # left out: no write access
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
    pull_numbers: Iterable[int] = (),
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
    leaves out has no write access. Either raises SpecReviewsUnread, which
    gives the note "spec #<n>: couldn't read its reviews (<why>)" instead of
    silence. A parent missing from `issues` gets that note too, unless it is
    a pull request (listed in `issues`, or in `pull_numbers`)."""
    by_num = {i["number"]: i for i in issues if "pull_request" not in i}
    pulls = {i["number"] for i in issues if "pull_request" in i} | set(pull_numbers)
    note_of: dict[int, str | None] = {}  # spec number -> its note, read once
    known: dict[str, str] = {}  # login (casefolded) -> permission, looked up once
    for v in verdicts:
        issue = by_num.get(v.number)
        if not v.ready or issue is None:
            continue
        parent = parent_of(issue, repo)
        if parent is not None and parent not in by_num and parent not in pulls:
            # Not in the list (an issues file of open issues only, or one page):
            # whether it is a spec, and reviewed, can't be told.
            v.notes.append(_unread_note(parent, f"#{parent} isn't in the issue list"))
            continue
        spec = parent_spec(issue, by_num, repo, since)
        if spec is None:
            continue
        if spec["number"] not in note_of:
            note_of[spec["number"]] = _spec_note(spec, fetch_comments, permissions, known)
        if note_of[spec["number"]]:
            v.notes.append(note_of[spec["number"]])

"""The stakes and token records (#510, spec #505): `workflow research stakes`
and `workflow research estimate`.

Each record is one issue comment, in the one fixed shape the `study` skill's
text shows (its sections 2 and 3, which the tests' fixtures are copied from):

    Stakes: touches payments. Recommended: study. Owner chose: skip, because …

    <!-- workflow:stakes -->
    <!-- workflow:agent -->

    Tokens: 1,180,000 across 11 agents, … The main session's own share isn't counted.

    <!-- workflow:tokens study=full agents=11 total=1180000 -->
    <!-- workflow:agent -->

A comment is read as a record only as the skill writes it: exactly one marker
line of its kind (and none of the other kind), on a line of its own, no code
fence before it, and for a stakes record exactly one line starting `Stakes: `
with something after it. Only comments carrying the agents' marker, posted by
an account with write access, count, as hand-off comments do (`read`); the
others are left out and counted, so the command can say how many. The
records are read in the order given (as GitHub gives them, oldest first).

`estimate` averages the past full studies' token records, one per issue (the
last one given), never a second study's. Before there are any, it counts the panel at
its largest at the per-agent figure, `PER_AGENT_TOKENS`, which the skill's
text quotes (a test ties the two). Nothing here calls a model or writes a file.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from fractions import Fraction

from .merge import WRITE
from .posts import AGENT_MARKER, _login, comments_from

# The per-agent figure, approximate: a trial run of the panel's 9 agents in the
# `study` skill's ticket (#512) reported 714,627 tokens, about 79,403 each
# (spec #505; answer 35), until the sandbox study's per-agent average replaces
# it (#519). The skill's text quotes it.
PER_AGENT_TOKENS = 80_000
# The panel at its largest: one evidence gatherer, one question writer, 8
# personas (5 to 8), a synthesizer and a validator. The skill's text quotes it.
PANEL_AGENTS = 12
MAX_AGENTS = 999
LINE_LIMIT = 1000  # characters of a stakes line or a title shown

STAKES_MARKER = "<!-- workflow:stakes -->"
STAKES_PREFIX = "Stakes: "
STUDIES = ("full", "second")
_TOKENS = re.compile(r"<!-- workflow:tokens study=(full|second) agents=([1-9][0-9]{0,2}) total=([1-9][0-9]{0,11}) -->")
_ANY_STAKES = re.compile(r"<!--\s*workflow:stakes\b", re.I)
_ANY_TOKENS = re.compile(r"<!--\s*workflow:tokens\b", re.I)
_FENCE = ("```", "~~~")
_LINE_END = re.compile(r"\r\n|\r|\n")
_ISSUE_API = re.compile(r"/issues/([0-9]{1,9})/?$")
_ISSUE_PAGE = re.compile(r"/(?:issues|pull)/([0-9]{1,9})(?:[#?/]|$)")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class RecordsError(ValueError):
    """An input the records can't be read from, said in plain words."""


@dataclass(frozen=True)
class Tokens:
    study: str
    agents: int
    total: int


def _lines(text) -> list[str]:
    return [line.rstrip() for line in _LINE_END.split(text)] if isinstance(text, str) else []


def _marked(lines: list[str], marker) -> int | None:
    """The index of the one line that is the marker, with none like it and no
    code fence before it; else None. `marker` is the exact line, or a pattern
    the whole line must match."""
    like = _ANY_STAKES if marker == STAKES_MARKER else _ANY_TOKENS
    other = _ANY_TOKENS if marker == STAKES_MARKER else _ANY_STAKES
    if sum(1 for line in lines if like.search(line)) != 1 or any(other.search(line) for line in lines):
        return None
    for i, line in enumerate(lines):
        if any(f in line for f in _FENCE):
            return None
        if like.search(line):
            exact = line == marker if isinstance(marker, str) else marker.fullmatch(line) is not None
            return i if exact else None
    return None


def stakes_line(text, agents_only: bool = True) -> str | None:
    """The stakes line of one comment written as the skill shows, or None.
    With `agents_only` false, a comment without the agents' marker reads too."""
    if agents_only and AGENT_MARKER not in (text or ""):
        return None
    lines = _lines(text)
    at = _marked(lines, STAKES_MARKER)
    if at is None:
        return None
    said = [line for line in lines[:at] if line.startswith(STAKES_PREFIX)]
    if len(said) != 1 or any(line.startswith(STAKES_PREFIX) for line in lines[at:]) or not said[0][len(STAKES_PREFIX):].strip():
        return None
    return said[0]


def token_record(text, agents_only: bool = True) -> Tokens | None:
    """The token record of one comment written as the skill shows, or None."""
    if agents_only and AGENT_MARKER not in (text or ""):
        return None
    lines = _lines(text)
    at = _marked(lines, _TOKENS)
    if at is None:
        return None
    m = _TOKENS.fullmatch(lines[at])
    return Tokens(study=m.group(1), agents=int(m.group(2)), total=int(m.group(3)))


def shown(text, patterns: list[str]) -> str:
    """Text for one line of output: other control and format characters and
    lone surrogates dropped, whitespace made one space, the profile's sensitive
    patterns left out, and at most LINE_LIMIT characters."""
    from .research import leave_out

    text = "".join(c for c in str(text or "") if c.isspace() or unicodedata.category(c) not in ("Cc", "Cf", "Cs"))
    text = re.sub(r"\s+", " ", text).strip()
    text = leave_out(text, patterns)[0]
    return text if len(text) <= LINE_LIMIT else text[: LINE_LIMIT - 1] + "…"


def _issue_of(c: dict) -> int | None:
    m = _ISSUE_API.search(str(c.get("issue_url") or ""))
    if m:
        return int(m.group(1))
    for key in ("html_url", "url"):
        m = _ISSUE_PAGE.search(str(c.get(key) or ""))
        if m:
            return int(m.group(1))
    return None


def _when(c: dict) -> str:
    at = c.get("created_at") or c.get("createdAt")
    return at if isinstance(at, str) else ""


def titles(issues) -> dict[int, str]:
    """Issue number -> title, from a list of issues (pages flattened).
    Raises RecordsError for anything that isn't an issue."""
    out: dict[int, str] = {}

    def walk(v) -> None:
        if isinstance(v, list):
            for x in v:
                walk(x)
            return
        if isinstance(v, dict) and any(isinstance(v.get(k), list) for k in ("issues", "items")):
            for k in ("issues", "items"):
                if isinstance(v.get(k), list):
                    walk(v[k])
            return
        n = v.get("number") if isinstance(v, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or not isinstance(v.get("title"), str):
            said = f": {str(v['message'])[:200]}" if isinstance(v, dict) and "message" in v else ""
            raise RecordsError(f"it holds something that isn't an issue with a number and a title{said}")
        out[n] = v["title"]

    try:
        walk(issues)
    except RecursionError:
        raise RecordsError("the JSON is nested too deeply to read") from None
    return out


def candidates(comments) -> list[dict]:
    """The comments that hold a stakes or token record, agents' marker or not,
    in the order given (as GitHub gives them, oldest first). `comments` is any
    shape `posts.comments_from` reads."""
    return [c for c in comments_from(comments) if stakes_line(c.get("body"), False) or token_record(c.get("body"), False)]


@dataclass
class Read:
    stakes: list[dict]  # {issue, title, date, line, url}, in the order given
    tokens: dict[int, tuple[Tokens, str]]  # issue -> the last token record given and the comment's link
    left_out_stakes: int = 0
    left_out_tokens: int = 0


def read(comments, perms: dict[str, str], issue_titles: dict[int, str], patterns: list[str]) -> Read:
    """Every counted record in the comments: carrying the agents' marker,
    posted by an account with write access (`perms`: login, casefolded ->
    permission). Raises RecordsError for a counted comment naming no issue."""
    got = Read(stakes=[], tokens={})
    for c in candidates(comments):
        body, who = c.get("body"), _login(c)
        trusted = AGENT_MARKER in (body or "") and bool(who) and perms.get(who.casefold()) in WRITE
        line, tokens = stakes_line(body, False), token_record(body, False)
        if not trusted:
            if line:
                got.left_out_stakes += 1
            else:
                got.left_out_tokens += 1
            continue
        issue = _issue_of(c)
        if issue is None:
            raise RecordsError(f"a comment with a {'stakes' if line else 'token'} record names no issue: its comments need their issue_url or html_url")
        url = c.get("html_url") or c.get("url")
        url = url if isinstance(url, str) else None
        if line:
            when = _when(c)[:10]
            title = issue_titles.get(issue)
            got.stakes.append({
                "issue": issue,
                "title": shown(title, patterns) if title is not None else None,
                "date": when if _DATE.fullmatch(when) else None,
                "line": shown(line, patterns),
                "url": url,
            })
        else:
            got.tokens[issue] = (tokens, url)  # the last one given
    return got


def rough(n: int) -> str:
    """A token count, rounded as a person says it: 950, 104k, 1.2M."""
    if n < 1000:
        return str(n)
    if n < 999_500:
        return f"{round(n / 1000)}k"
    return f"{n / 1_000_000:.1f}".removesuffix(".0") + "M"


def estimate(tokens: dict[int, tuple[Tokens, str]], agents: int | None = None) -> dict:
    """The agent count and token estimate: from the past full studies' records
    (one per issue), else from the per-agent figure, saying it isn't learned."""
    full = sorted((issue, t) for issue, (t, _) in tokens.items() if t.study == "full")
    studies = [{"issue": issue, "agents": t.agents, "total": t.total} for issue, t in full]
    if not full:
        n = agents or PANEL_AGENTS
        return {"agents": n, "tokens": n * PER_AGENT_TOKENS, "learned": False, "per_agent": PER_AGENT_TOKENS, "studies": []}
    per_agent = Fraction(sum(t.total for _, t in full), sum(t.agents for _, t in full))
    if agents is None:
        n = int(Fraction(sum(t.agents for _, t in full), len(full)) + Fraction(1, 2))
        total = int(Fraction(sum(t.total for _, t in full), len(full)) + Fraction(1, 2))  # the average total
    else:
        n, total = agents, int(per_agent * agents + Fraction(1, 2))
    return {"agents": n, "tokens": total, "learned": True, "per_agent": int(per_agent + Fraction(1, 2)), "studies": studies}


def estimate_line(e: dict) -> str:
    size = f"About {e['agents']} agent{'s' if e['agents'] != 1 else ''}, roughly {rough(e['tokens'])} tokens"
    if not e["learned"]:
        return (f"{size}: not learned yet, since no past full study has a token record; "
                f"from the per-agent figure, {e['per_agent']:,} tokens per agent.")
    n = len(e["studies"])
    which = ", ".join(f"#{s['issue']}" for s in e["studies"])
    whose = "study's" if n == 1 else "studies'"
    return (f"{size}: averaged from {n} past full {whose} token record{'s' if n != 1 else ''} ({which}). "
            "The main session's own share isn't counted.")


def stakes_lines(stakes: list[dict]) -> list[str]:
    out = []
    for s in stakes:
        title = s["title"].replace("\\", "\\\\").replace('"', '\\"') if s["title"] is not None else None
        head = f"#{s['issue']}" + (f" {s['date']}" if s["date"] else "") + (f' "{title}"' if title is not None else "")
        out.append(f"{head}: {s['line']}")
    return out

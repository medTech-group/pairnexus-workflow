"""Review records: what each review round, or later Correctness pass, leaves on a pull request.

One writer (`record`, behind `workflow review-record`) and one reader
(`records_in` for one comment's text, `read` for a pull request's comments), so
the two can't drift. A record is a comment written for people, with one
machine-readable line and the agents' marker:

    Review round 2 on `3f2a9c0`: clean. Reviewers: Standards, Spec, Correctness.
    <!-- workflow:review kind=round round=2 commit=<full sha> reviewers=standards,spec,correctness result=clean -->
    <!-- workflow:agent -->

- `kind`: `round` for a review round, `pass` for the short Correctness pass on
  commits made after the last round;
- `round`: the round's number; for a `pass`, the round it follows;
- `commit`: the full SHA the round or pass covered (the branch's head when it ran);
- `reviewers`: those that ran, in `REVIEWERS`' order; a `pass` is `correctness`;
- `result`: `clean` (nothing left to fix) or `not-clean`.

Both apply the same rules (`_checked`). The reader never raises on a comment:
a malformed record line is skipped, and only a line of its own counts. It
doesn't judge who posted a record; `read` keeps each record's author, so a
caller can count only records from accounts with write access.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .posts import AGENT_MARKER, _login, _number, comments_from

KINDS = ("round", "pass")
REVIEWERS = ("standards", "spec", "correctness", "security", "explorer")
RESULTS = ("clean", "not-clean")

_FIELDS = ("kind", "round", "commit", "reviewers", "result")
# A record line is a line of its own (at most three spaces in, as Markdown
# allows outside a code block), so one quoted in a sentence, in backticks or in
# a code block isn't read as a record.
_LINE = re.compile(r" {0,3}<!-- workflow:review (\S[^\n]*?\S) -->[ \t]*\r?")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")
_SHA = re.compile(r"[0-9a-f]{40}")
# A round's number, at most six digits (int() refuses past Python's digit limit).
_ROUND = re.compile(r"[1-9][0-9]{0,5}")


class RecordError(ValueError):
    """A record the writer refuses, said in plain words."""


@dataclass(frozen=True)
class Record:
    kind: str
    round: int
    commit: str
    reviewers: tuple[str, ...]
    result: str
    # Filled by `read` from the comment that carried the record.
    author: str | None = None
    comment_id: int | None = None
    created_at: str | None = None

    @property
    def clean(self) -> bool:
        return self.result == "clean"

    def line(self) -> str:
        """The machine-readable line."""
        return (
            f"<!-- workflow:review kind={self.kind} round={self.round} commit={self.commit} "
            f"reviewers={','.join(self.reviewers)} result={self.result} -->"
        )


def _shown(value, n: int) -> str:
    """A value as the refusal quotes it: cut to `n` characters, control
    characters escaped."""
    text = str(value)
    cut = "".join(c if c.isprintable() else repr(c)[1:-1] for c in text[:n])
    return cut + ("…" if len(text) > n else "")


def _checked(kind, round, commit, reviewers, result) -> Record:
    """The one set of rules the writer and the reader share: a Record, or
    RecordError saying which flag to fix. Names are read in any case;
    `reviewers` is a comma-separated string or a list, put in the panel's order."""
    given, kind = kind, str(kind or "").strip().lower()
    if not kind:
        raise RecordError("give --kind: `round` for a review round, `pass` for a later Correctness pass")
    if kind not in KINDS:
        raise RecordError(f"--kind is `round` or `pass`, not `{_shown(given, 20)}`")
    rnd = "" if round is None else str(round).strip()
    if not rnd:
        raise RecordError("give --round: the round's number (for a pass, the round it follows)")
    if not _ROUND.fullmatch(rnd):
        raise RecordError(f"--round is a whole number from 1 to 999999, not `{_shown(rnd, 20)}`")
    if commit is None or not str(commit).strip():
        raise RecordError("give --commit: the full SHA the round covered (`git rev-parse HEAD`)")
    sha = str(commit).strip().lower()
    if not _SHA.fullmatch(sha):
        raise RecordError(f"--commit is the full 40-character SHA (`git rev-parse HEAD`), not `{_shown(commit, 50)}`")
    if reviewers is not None and not isinstance(reviewers, (str, list, tuple)):
        raise RecordError("give --reviewers as names, comma-separated")
    parts = [reviewers] if isinstance(reviewers, str) else list(reviewers or [])
    names = [n.strip().lower() for part in parts for n in str(part).split(",")]
    if not any(names):
        raise RecordError("give --reviewers: those that ran, from " + ", ".join(REVIEWERS))
    if "" in names:
        raise RecordError("--reviewers has an empty name: give them comma-separated, with nothing between two commas")
    for n in names:
        if n not in REVIEWERS:
            raise RecordError(f"unknown reviewer `{_shown(n, 30)}`: the reviewers are " + ", ".join(REVIEWERS))
    who = tuple(r for r in REVIEWERS if r in names)
    if kind == "pass" and who != ("correctness",):
        raise RecordError("a pass is reviewed by correctness alone: give --reviewers correctness")
    if result not in RESULTS:
        raise RecordError("give --clean or --not-clean: whether the round left anything to fix")
    return Record(kind=kind, round=int(rnd), commit=sha, reviewers=who, result=result)


def record(*, kind, round, commit, reviewers, clean) -> str:
    """The comment's body for one round or pass, ending with a newline.

    `round` is a number (or its digits), `reviewers` a list of names or one
    comma-separated string, `clean` True or False (None: not given). Raises
    RecordError, saying which flag to fix, for a missing or malformed field."""
    if clean is True:
        result = "clean"
    elif clean is False:
        result = "not-clean"
    else:
        result = None
    r = _checked(kind, round, commit, reviewers, result)
    what = f"Review round {r.round}" if r.kind == "round" else f"Correctness pass after round {r.round}"
    names = ", ".join(n.capitalize() for n in r.reviewers)
    return f"{what} on `{r.commit[:7]}`: {r.result.replace('-', ' ')}. Reviewers: {names}.\n{r.line()}\n{AGENT_MARKER}\n"


def _parse(fields: str) -> Record | None:
    got = dict(p.partition("=")[::2] for p in fields.split(" "))
    if set(got) != set(_FIELDS):
        return None
    try:
        r = _checked(*(got[k] for k in _FIELDS))
    except RecordError:
        return None
    # Only exactly what the writer writes: the fields in order, single spaces,
    # lowercase, the panel's order, no repeats.
    return r if r.line() == f"<!-- workflow:review {fields} -->" else None


def records_in(text) -> list[Record]:
    """Every well-formed record line in one comment's text, in order, outside
    code blocks. A malformed one, or text that isn't a string, yields nothing;
    never raises."""
    if not isinstance(text, str):
        return []
    out, fence = [], ""
    for line in text.split("\n"):
        f = _FENCE.match(line)
        if fence:
            # A fence closes on a line of the same character, at least as long.
            if f and f.group(1)[0] == fence[0] and len(f.group(1)) >= len(fence) and not line[f.end():].strip():
                fence = ""
            continue
        if f:
            fence = f.group(1)
            continue
        m = _LINE.fullmatch(line)
        r = _parse(m.group(1)) if m else None
        if r is not None:
            out.append(r)
    return out


def read(comments) -> list[Record]:
    """Every record in a pull request's comments, in the order given (GitHub's:
    oldest first), each with its comment's `author`, `comment_id` and
    `created_at`. `comments` is any shape `workflow comments` reads (see
    `posts.comments_from`), which raises `posts.CommentsError` for any other."""
    out = []
    for c in comments_from(comments):
        for r in records_in(c.get("body")):
            out.append(replace(r, author=_login(c) or None, comment_id=_number(c), created_at=c.get("created_at") or c.get("createdAt")))
    return out

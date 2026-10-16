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

The reader never raises on a comment: a malformed record line is skipped. It
doesn't judge who posted a record; `read` keeps the author for the caller
(merge-check counts only records from accounts with write access).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .posts import AGENT_MARKER, _login, _number, comments_from

KINDS = ("round", "pass")
REVIEWERS = ("standards", "spec", "correctness", "security", "explorer")
RESULTS = ("clean", "not-clean")

_FIELDS = ("kind", "round", "commit", "reviewers", "result")
_LINE = re.compile(r"<!-- workflow:review ([^\n]*?) -->")
_SHA = re.compile(r"[0-9a-f]{40}")
_ROUND = re.compile(r"[1-9][0-9]*")


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


def _reviewers(given) -> tuple[str, ...]:
    """The reviewers in the panel's order, any case; raises RecordError."""
    names = [given] if isinstance(given, str) else list(given or [])
    names = [n.strip().lower() for part in names for n in str(part).split(",")]
    if not any(names):
        raise RecordError("give --reviewers: those that ran, from " + ", ".join(REVIEWERS))
    for n in names:
        if n not in REVIEWERS:
            raise RecordError(f"unknown reviewer `{n}`: the reviewers are " + ", ".join(REVIEWERS))
    return tuple(r for r in REVIEWERS if r in names)


def record(*, kind, round, commit, reviewers, clean) -> str:
    """The comment's body for one round or pass, ending with a newline.

    `round` is a number (or its digits), `reviewers` a list of names or one
    comma-separated string, `clean` True or False. Raises RecordError, saying
    which flag to fix, for a missing or malformed field."""
    if not kind:
        raise RecordError("give --kind: `round` for a review round, `pass` for a later Correctness pass")
    if kind not in KINDS:
        raise RecordError(f"--kind is `round` or `pass`, not `{kind}`")
    if round is None or str(round).strip() == "":
        raise RecordError("give --round: the round's number (for a pass, the round it follows)")
    if not _ROUND.fullmatch(str(round).strip()):
        raise RecordError(f"--round is a whole number from 1, not `{round}`")
    n = int(str(round).strip())
    if commit is None:
        raise RecordError("give --commit: the full SHA the round covered (`git rev-parse HEAD`)")
    sha = str(commit).strip().lower()
    if not _SHA.fullmatch(sha):
        raise RecordError(f"--commit is the full 40-character SHA (`git rev-parse HEAD`), not `{commit}`")
    who = _reviewers(reviewers)
    if kind == "pass" and who != ("correctness",):
        raise RecordError("a pass is reviewed by correctness alone: give --reviewers correctness")
    if clean is None:
        raise RecordError("give --clean or --not-clean: whether the round left anything to fix")
    result = "clean" if clean else "not-clean"
    what = f"Review round {n}" if kind == "round" else f"Correctness pass after round {n}"
    names = ", ".join(r.capitalize() for r in who)
    return (
        f"{what} on `{sha[:7]}`: {result.replace('-', ' ')}. Reviewers: {names}.\n"
        f"<!-- workflow:review kind={kind} round={n} commit={sha} reviewers={','.join(who)} result={result} -->\n"
        f"{AGENT_MARKER}\n"
    )


def _parse(fields: str) -> Record | None:
    pairs = [p.partition("=") for p in fields.split()]
    if any(not eq for _, eq, _ in pairs):
        return None
    got = {k: v for k, _, v in pairs}
    if len(got) != len(pairs) or set(got) != set(_FIELDS):
        return None
    kind, rnd, sha, who, result = (got[k] for k in _FIELDS)
    if kind not in KINDS or result not in RESULTS or not _ROUND.fullmatch(rnd) or not _SHA.fullmatch(sha):
        return None
    names = who.split(",")
    if not who or any(n not in REVIEWERS for n in names):
        return None
    reviewers = tuple(r for r in REVIEWERS if r in names)
    if kind == "pass" and reviewers != ("correctness",):
        return None
    return Record(kind=kind, round=int(rnd), commit=sha, reviewers=reviewers, result=result)


def records_in(text: str | None) -> list[Record]:
    """Every well-formed record line in one comment's text, in order. A
    malformed one is skipped; never raises."""
    out = []
    for m in _LINE.finditer(text or ""):
        r = _parse(m.group(1))
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
            out.append(
                Record(
                    **{k: getattr(r, k) for k in _FIELDS},
                    author=_login(c) or None,
                    comment_id=_number(c),
                    created_at=c.get("created_at") or c.get("createdAt"),
                )
            )
    return out

"""The hand-off comment (#371, spec #412; from #362's session hand-off).

A session that hands its ticket on to a fresh one posts it on the pull
request: a session restarted or stopped, a run's end time (the conductor posts
it), and attended work's stop after 10 reviews that weren't clean. Never after
3 reviews. One writer (`comment`, behind `workflow hand-off`) and one reader
(`in_text` for one comment's text, `read` for a pull request's comments), so
the two can't drift:

    ## Carry on in a fresh session

    This session stops here. A fresh session carries the review on from `3f2a9c0`, the head this covers.

    Open blocking findings:
    - the part `the requeue order`.
    - a security problem the change adds, in `sign-in`.

    Tickets filed: #415, #416.

    Reviews so far: 3 review rounds and 2 Correctness passes.

    <!-- workflow:hand-off head=<full sha> round=3 passes=2 -->
    <!-- workflow:agent -->

- `head`: the full SHA of the branch's head the hand-off covers;
- `round`: the review rounds so far (0: no review yet);
- `passes`: the Correctness passes so far, after any round (0 without a round).

The open blocking findings are the findings file's (`findings`, the last
review's) marked blocks, each by its part's name, a security finding by its
area only, and never a reproducer, so no security detail crosses sessions. The
tickets filed are those given, the findings' tickets to fix them and the parts
split out, each once, in number order.

The reader takes a comment only as the writer writes it: exactly one hand-off
line, on a line of its own before any code fence, in a comment holding the
agents' marker and no review record (`reviews`); otherwise none. It never
raises, and doesn't judge who posted it: `read` keeps each comment's author
and position, so `merge-check` reports the latest one from an account with
write access, for a commit of the pull request, until a counted review record
follows it (its `hand_off`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import findings as findings_mod
from . import reviews as reviews_mod
from .posts import AGENT_MARKER, _login, _number, comments_from

HEADING = "## Carry on in a fresh session"
# A count, as `reviews` writes a round's number: at most six digits, 0 allowed.
_COUNT = re.compile(r"0|[1-9][0-9]{0,5}")
_SHA = re.compile(r"[0-9a-f]{40}")
_ISSUE = re.compile(r"#?([1-9][0-9]{0,6})")
_LINE = re.compile(r"<!-- workflow:hand-off (\S[^\n]*?\S) -->[ \t]*")
# A hand-off or review line however spelt: the reader leaves out a comment
# holding one it can't account for.
_ANY_HAND_OFF = re.compile(r"\s*<!--\s*workflow:hand-off\b", re.IGNORECASE)
_ANY_REVIEW = re.compile(r"\s*<!--\s*workflow:(review|finding|outcome)\b", re.IGNORECASE)
_FENCE = ("```", "~~~")
_LINE_END = re.compile(r"\r\n|\r|\n")


class HandOffError(ValueError):
    """A hand-off the writer refuses, said in plain words."""


@dataclass(frozen=True)
class HandOff:
    head: str
    round: int
    passes: int
    # Filled by `read` from the comment that carried it.
    author: str | None = None
    comment_id: int | None = None
    created_at: str | None = None
    url: str | None = None
    position: int | None = None  # the comment's place among the pull request's, oldest first

    def line(self) -> str:
        return f"<!-- workflow:hand-off head={self.head} round={self.round} passes={self.passes} -->"


def _count(value, flag: str, what: str) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        raise HandOffError(f"give {flag}: {what}")
    if not _COUNT.fullmatch(text):
        raise HandOffError(f"{flag} is a whole number from 0 to 999999: {what}")
    return int(text)


def checked(head, round, passes) -> HandOff:
    """The rules the writer and the reader share. Raises HandOffError."""
    sha = "" if head is None else str(head).strip()
    if not sha:
        raise HandOffError("give --commit: the full SHA of the head this hand-off covers (`git rev-parse HEAD`)")
    if not _SHA.fullmatch(sha.lower()):
        raise HandOffError("--commit is the full 40-character SHA (`git rev-parse HEAD`)")
    rounds = _count(round, "--round", "the review rounds so far (0 for none)")
    passes = _count(passes, "--passes", "the Correctness passes so far (0 for none)")
    if passes and not rounds:
        raise HandOffError("--passes is more than 0 with no round: a pass follows a round")
    return HandOff(head=sha.lower(), round=rounds, passes=passes)


def tickets_from(text) -> tuple[int, ...]:
    """`--tickets`: issue numbers, comma-separated, each as 415 or #415."""
    out = []
    for part in str(text or "").split(","):
        m = _ISSUE.fullmatch(part.strip())
        if not m:
            raise HandOffError("--tickets is the tickets filed, comma-separated, each as 415 or #415")
        out.append(int(m.group(1)))
    return tuple(out)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def comment(*, head, round, passes, found: findings_mod.Findings | None = None, tickets=()) -> str:
    """The comment's body, ending with a newline. `found` is the last review's
    findings (`findings.from_file`); `tickets` the tickets filed so far.
    Raises HandOffError for a malformed field."""
    h = checked(head, round, passes)
    found = found or findings_mod.Findings()
    blocking = [f for f in found.findings if f.mark == "blocks"]
    if blocking:
        # `Finding.text` names the part, or a security finding's area only; drop its "Blocks: ".
        listed = "\n".join(["Open blocking findings:", *("- " + f.text().removeprefix("- ").split(": ", 1)[1] for f in blocking)])
    else:
        listed = "Open blocking findings: none."
    filed = sorted({*tickets, *(f.issue for f in found.findings if f.mark == "ticket" and f.issue),
                    *(o.issue for o in found.outcomes if o.kind == "split")})
    tickets_line = "Tickets filed: " + (", ".join(f"#{n}" for n in filed) if filed else "none") + "."
    if h.round:
        so_far = _plural(h.round, "review round", "review rounds") + " and " + _plural(h.passes, "Correctness pass", "Correctness passes")
    else:
        so_far = "no review yet"
    paragraphs = [
        HEADING,
        f"This session stops here. A fresh session carries the review on from `{h.head[:7]}`, the head this covers.",
        listed,
        tickets_line,
        f"Reviews so far: {so_far}.",
        f"{h.line()}\n{AGENT_MARKER}",
    ]
    return "\n\n".join(paragraphs) + "\n"


def _parse(fields: str) -> HandOff | None:
    got = dict(p.partition("=")[::2] for p in fields.split(" "))
    if set(got) != {"head", "round", "passes"}:
        return None
    try:
        h = checked(got["head"], got["round"], got["passes"])
    except HandOffError:
        return None
    # Only exactly what the writer writes.
    return h if h.line() == f"<!-- workflow:hand-off {fields} -->" else None


def in_text(text) -> HandOff | None:
    """The hand-off in one comment's text, or None: exactly one hand-off line,
    a line of its own before any code fence, as the writer writes it, in a
    comment with the agents' marker and no review record line. Never raises."""
    if not isinstance(text, str) or AGENT_MARKER not in text:
        return None
    lines = _LINE_END.split(text)
    if sum(1 for line in lines if _ANY_HAND_OFF.match(line)) != 1 or any(_ANY_REVIEW.match(line) for line in lines):
        return None
    for line in lines:
        if any(f in line for f in _FENCE):
            return None
        m = _LINE.fullmatch(line)
        if m:
            return _parse(m.group(1))
    return None


def read(comments) -> list[HandOff]:
    """Every hand-off in a pull request's comments, in the order given
    (GitHub's: oldest first), each with its comment's author, id, time, link
    and position. `comments` is any shape `posts.comments_from` reads, which
    raises `posts.CommentsError` for any other."""
    out = []
    for i, c in enumerate(comments_from(comments)):
        h = in_text(c.get("body"))
        if h is not None:
            url = c.get("html_url") or c.get("url")
            out.append(HandOff(h.head, h.round, h.passes, author=_login(c) or None, comment_id=_number(c),
                               created_at=c.get("created_at") or c.get("createdAt"), url=url if isinstance(url, str) else None, position=i))
    return out


def records_after(comments, position: int) -> list[reviews_mod.Record]:
    """The review records in the comments after the one at `position`, each
    with its author (`reviews.read`)."""
    return reviews_mod.read(comments_from(comments)[position + 1:])

"""Review records: what each review round, or later Correctness pass, leaves on a
pull request, and what a spec's review leaves on the spec's issue.

One writer (`record`, behind `workflow review-record`) and one reader
(`records_in` for one comment's text, `read` for a pull request's comments), so
the two can't drift. A record is a comment written for people, with one
machine-readable line and the agents' marker:

    Review round 2 on `3f2a9c0`: clean. Reviewers: Standards, Spec, Correctness.
    <!-- workflow:review kind=round round=2 commit=<full sha> reviewers=standards,spec,correctness diff=<64 hex> lines=<64 hex> result=clean -->
    <!-- workflow:agent -->

- `kind`: `round` for a review round, `pass` for the short Correctness pass on
  commits made after the last round;
- `round`: the round's number; for a `pass`, the round it follows;
- `commit`: the full SHA the round or pass covered (the branch's head when it ran);
- `reviewers`: those that ran, in `REVIEWERS`' order; a `pass` is `correctness`;
- `diff` and `lines` (#258): the hashes of the pull request's own changes at
  `commit`, with their context lines and of the changed lines alone
  (`own_changes`), each `unknown` where they couldn't be computed. The command
  computes them, not this writer: without them it writes the line as before
  #258, and the reader takes records with or without them;
- `result`: `clean` (nothing left to fix) or `not-clean`.

A spec has no commit to name (#233): its record names the SHA-256 of the spec's
body in a field of its own, `body`, in place of `commit`, so an edit after the
review makes the spec read as unreviewed again:

    Spec review round 1 on body `9c1e4b2`: clean. Reviewers: Spec, Correctness.
    <!-- workflow:review kind=spec round=1 body=<64 hex> reviewers=spec,correctness result=clean -->
    <!-- workflow:agent -->

- `kind`: `spec`;
- `body`: the SHA-256 of the body (`body_hash`): line endings made `\n`, so
  GitHub's `\r\n` doesn't break the match, and a byte order mark at its start,
  the whitespace at its very end and a Claude Code cloud session's footer at
  its very end (`_CLOUD_FOOTER`), once or repeated, left out;
- `reviewers`: `spec`, `correctness` or both.

A build review written from a findings file (#370, spec #412 "Records and
clean"; `findings`) carries `rule=2`: its result is worked out from the
findings' marks (not clean when any is marked blocks), and the line names how
many findings and outcomes follow, and whether the ticket was made by a split:

    Review round 2 on `3f2a9c0`: not clean. Reviewers: Standards, Spec, Correctness.

    Findings:
    - Blocks: the part `the requeue order`.

    <!-- workflow:review kind=round round=2 commit=<full sha> reviewers=standards,spec,correctness diff=<64 hex> lines=<64 hex> rule=2 findings=1 outcomes=0 split=no result=not-clean -->
    <!-- workflow:finding n=1 mark=blocks mechanism=the%20requeue%20order covered=no contested=no security=no issue=none -->
    <!-- workflow:agent -->

Its finding and outcome lines follow the review line directly, in order; the
reader takes such a record only whole, every line there and keeping the rules,
and skips it otherwise. A record without `rule=2` reads exactly as before:
`rule` None, no findings.

`spec_reviewed` says whether a list of records holds a clean spec record for a
body: the latest spec record for that body's hash is clean.

Both apply the same rules (`_checked`). The reader never raises on a comment:
a malformed record line is skipped, and only a line of its own counts. It
doesn't judge who posted a record; `read` keeps each record's author, so a
caller can count only records from accounts with write access.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

from . import findings as findings_mod
from .own_changes import UNKNOWN
from .posts import AGENT_MARKER, _login, _number, comments_from

KINDS = ("round", "pass", "spec")
REVIEWERS = ("standards", "spec", "correctness", "security", "explorer")
# Those a spec's review allows, in the panel's order.
SPEC_REVIEWERS = ("spec", "correctness")
RESULTS = ("clean", "not-clean")

_FIELDS = ("kind", "round", "commit", "reviewers", "result")
_HASHED_FIELDS = ("kind", "round", "commit", "reviewers", "diff", "lines", "result")
_SPEC_FIELDS = ("kind", "round", "body", "reviewers", "result")
# A `rule=2` record's own fields, between its reviewers (or hashes) and its result.
_RULE_FIELDS = ("rule", "findings", "outcomes", "split")
# The rule a record written from a findings file names (#370, spec #412).
RULE = 2
# A record line is a line of its own, at the start of the line as the writer
# writes it, before any code fence: one quoted in a sentence, in backticks, in
# a list or quote, or in a code block isn't read as a record. When in doubt the
# reader leaves a line out: a record missed is posted again, a quoted one
# counted could pass a review that never happened. Telling where a code block
# ends takes Markdown's whole grammar, so nothing after the first fence-like
# line counts; the writer's comment has none.
_LINE = re.compile(r"<!-- workflow:review (\S[^\n]*?\S) -->[ \t]*")
_FENCE = ("```", "~~~")
# A finding or outcome line however spelt: a comment's other lines like it
# leave its `rule=2` records unread.
_OWN_LINE = re.compile(r"\s*<!--\s*workflow:(finding|outcome)\b", re.IGNORECASE)
_LINE_END = re.compile(r"\r\n|\r|\n")
_SHA = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# What a Claude Code cloud session's GitHub tools append to every body they
# write, `gh api` included, however the body ends: editing it back appends it
# again. A spec's hash leaves it out at the very end, exactly as written here
# (a blank line, the rule, the line), as often as it repeats there, so a spec
# published from a cloud session reads as the `spec.md` its review covered.
# Any other difference still counts.
_CLOUD_FOOTER = "\n\n---\n_Generated by [Claude Code](https://claude.ai/code)_"
# A round's number, at most six digits (int() refuses past Python's digit limit).
_ROUND = re.compile(r"[1-9][0-9]{0,5}")


class RecordError(ValueError):
    """A record the writer refuses, said in plain words."""


@dataclass(frozen=True)
class Record:
    kind: str
    round: int
    commit: str | None  # None for a spec record
    reviewers: tuple[str, ...]
    result: str
    # A spec record's body hash (`body_hash`); None for a round or pass.
    body: str | None = None
    # A round's or pass's hashes of its own changes (64 hex, or `unknown`);
    # None on a record without them (before #258) and on a spec record.
    diff: str | None = None
    lines: str | None = None
    # A `rule=2` record's (#370): its findings and the last review's outcomes,
    # and whether the ticket was made by a split; None, (), () and False on a
    # record without it.
    rule: int | None = None
    findings: tuple[findings_mod.Finding, ...] = ()
    outcomes: tuple[findings_mod.Outcome, ...] = ()
    from_split: bool = False
    # Filled by `read` from the comment that carried the record.
    author: str | None = None
    comment_id: int | None = None
    created_at: str | None = None

    @property
    def clean(self) -> bool:
        return self.result == "clean"

    def line(self) -> str:
        """The machine-readable line."""
        if self.kind == "spec":
            return (
                f"<!-- workflow:review kind=spec round={self.round} body={self.body} "
                f"reviewers={','.join(self.reviewers)} result={self.result} -->"
            )
        hashes = "" if self.diff is None else f"diff={self.diff} lines={self.lines} "
        rule = "" if self.rule is None else self.found.fields() + " "
        return (
            f"<!-- workflow:review kind={self.kind} round={self.round} commit={self.commit} "
            f"reviewers={','.join(self.reviewers)} {hashes}{rule}result={self.result} -->"
        )

    @property
    def found(self) -> findings_mod.Findings:
        """A `rule=2` record's findings, outcomes and split flag together."""
        return findings_mod.Findings(self.findings, self.outcomes, self.from_split)

    def with_found(self, found: findings_mod.Findings) -> "Record":
        """This record as a `rule=2` one, carrying `found`."""
        return replace(self, rule=RULE, findings=found.findings, outcomes=found.outcomes, from_split=found.from_split)

    def machine_lines(self) -> list[str]:
        """The machine-readable lines: the review line, then a `rule=2`
        record's finding and outcome lines."""
        return [self.line(), *(self.found.lines() if self.rule is not None else [])]


def _shown(value, n: int) -> str:
    """A value as the refusal quotes it: cut to `n` characters, control
    characters and backticks escaped."""
    text = str(value)
    cut = "".join("\\" + c if c in "`\\" else c if c.isprintable() else repr(c)[1:-1] for c in text[:n])
    return cut + ("…" if len(text) > n else "")


def plain_body(text: str) -> str:
    """A spec's body as its hash reads it: line endings made `\n` (GitHub gives
    a body back with `\r\n`), and a byte order mark at the start (an editor's),
    the whitespace at the very end and a trailing `_CLOUD_FOOTER` left out, so
    the file a session publishes and the body GitHub returns read alike. Empty
    when the body is."""
    plain = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").rstrip()
    while plain.endswith(_CLOUD_FOOTER):
        plain = plain.removesuffix(_CLOUD_FOOTER).rstrip()
    return plain


def body_hash(text: str) -> str:
    """The SHA-256 of a spec's body (`plain_body`), as a spec record names it."""
    return hashlib.sha256(plain_body(text).encode("utf-8")).hexdigest()


def _given(value) -> bool:
    return value is not None and bool(str(value).strip())


def _kind(kind) -> str:
    return str(kind or "").strip().lower()


BOTH_KEYS = "give --commit or --body, not both: --commit for a round or a pass, --body for a spec's review"
EMPTY_BODY = "is empty (nothing but whitespace or a byte order mark, or only a cloud session's footer): give the spec's body as you publish it"
_BY_SPEC = "a spec's review is by " + " and ".join(SPEC_REVIEWERS)


def _kind_refused(given) -> RecordError:
    return RecordError(f"--kind is `round` or `pass` (or `spec` for a spec's review), not `{_shown(given, 20)}`")


def check_key(kind, commit, body_given: bool) -> None:
    """What a record is keyed to, checked before a spec's body is read: a
    commit for a round or a pass, a body for a spec. Raises RecordError."""
    if commit is not None and body_given:  # even an empty --commit: one key or the other
        raise RecordError(BOTH_KEYS)
    k = _kind(kind)
    if body_given and k not in ("", "spec"):
        if k in KINDS:
            raise RecordError("a round or a pass names a commit: give --commit; --body is for a spec record (--kind spec)")
        raise _kind_refused(kind)


def _checked(kind, round, commit, reviewers, result, body=None, diff=None, lines=None) -> Record:
    """The one set of rules the writer and the reader share: a Record, or
    RecordError saying which flag to fix. Names are read in any case;
    `reviewers` is a comma-separated string or a list, put in the panel's order.
    `body` is a spec record's body hash, given in place of `commit`. `diff` and
    `lines` are a round's or pass's hashes of its own changes, both or neither."""
    check_key(kind, commit, body is not None)
    given, kind = kind, _kind(kind)
    if not kind:
        raise RecordError("give --kind: `round` for a review round, `pass` for a later Correctness pass, `spec` for a spec's review")
    if kind not in KINDS:
        raise _kind_refused(given)
    rnd = "" if round is None else str(round).strip()
    if not rnd:
        raise RecordError("give --round: the round's number (for a pass, the round it follows)")
    if not _ROUND.fullmatch(rnd):
        raise RecordError(f"--round is a whole number from 1 to 999999, not `{_shown(rnd, 20)}`")
    sha = digest = None
    if kind == "spec":
        if body is None:
            names = "a spec record names its body, not a commit: " if _given(commit) else ""
            raise RecordError(names + "give --body: the file holding the spec's body, exactly as you publish it")
        digest = str(body)
        if not _SHA256.fullmatch(digest):
            raise RecordError(f"a spec record's body hash is 64 hex characters, not `{_shown(body, 70)}`")
    else:
        if not _given(commit):
            raise RecordError("give --commit: the full SHA the round covered (`git rev-parse HEAD`)")
        sha = str(commit).strip().lower()
        if not _SHA.fullmatch(sha):
            raise RecordError(f"--commit is the full 40-character SHA (`git rev-parse HEAD`), not `{_shown(commit, 50)}`")
    if reviewers is not None and not isinstance(reviewers, (str, list, tuple)):
        raise RecordError("give --reviewers as names, comma-separated")
    parts = [reviewers] if isinstance(reviewers, str) else list(reviewers or [])
    typed = [n.strip() for part in parts for n in str(part).split(",")]
    names = [n.lower() for n in typed]
    allowed = SPEC_REVIEWERS if kind == "spec" else REVIEWERS
    if not any(names):
        raise RecordError("give --reviewers: those that ran, from " + ", ".join(allowed))
    if "" in names:
        raise RecordError("--reviewers has an empty name: give them comma-separated, with nothing between two commas")
    for n, t in zip(names, typed):
        if n not in REVIEWERS:
            known = _BY_SPEC if kind == "spec" else "the reviewers are " + ", ".join(REVIEWERS)
            raise RecordError(f"unknown reviewer `{_shown(t, 30)}`: {known}")
    who = tuple(r for r in REVIEWERS if r in names)
    if kind == "pass" and who != ("correctness",):
        raise RecordError("a pass is reviewed by correctness alone: give --reviewers correctness")
    if kind == "spec" and not set(who) <= set(SPEC_REVIEWERS):
        raise RecordError(f"{_BY_SPEC}: give --reviewers {','.join(SPEC_REVIEWERS)} (or the one that ran)")
    if result not in RESULTS:
        raise RecordError("give --clean or --not-clean: whether the round left anything to fix")
    if (diff is None) != (lines is None):
        raise RecordError("a record names both hashes of its own changes, diff and lines, or neither")
    if diff is not None:
        if kind == "spec":
            raise RecordError("a spec record names no hashes of a pull request's changes")
        for name, value in (("diff", diff), ("lines", lines)):
            if value != UNKNOWN and not (isinstance(value, str) and _SHA256.fullmatch(value)):
                raise RecordError(f"the {name} hash is 64 hex characters or `{UNKNOWN}`, not `{_shown(value, 70)}`")
    return Record(kind=kind, round=int(rnd), commit=sha, reviewers=who, result=result, body=digest, diff=diff, lines=lines)


FINDINGS_WITH_RESULT = "--findings works the result out from the findings' marks: leave out --clean and --not-clean"
FINDINGS_WITH_SPEC = "--findings is for a build review's round or pass, not a spec's review: leave it out"
# GitHub's limit on a comment's body, in characters. A `rule=2` record keeps
# within it once a cloud session's footer is added (`_CLOUD_FOOTER`), counted
# in UTF-16 units, never fewer than its characters.
COMMENT_LIMIT = 65_536
RECORD_LIMIT = COMMENT_LIMIT - len(_CLOUD_FOOTER)
# What the hashes of a round's own changes add to its line, when the size is
# checked before they are computed.
_HASHES_ROOM = len(" diff= lines=") + 2 * 64


def record(*, kind, round, commit=None, reviewers, clean, body=None, diff=None, lines=None, findings=None) -> str:
    """The comment's body for one round or pass, or for a spec's review round,
    ending with a newline.

    `round` is a number (or its digits), `reviewers` a list of names or one
    comma-separated string, `clean` True or False (None: not given). A round or
    a pass gives `commit`; a spec's review gives `body`, the spec's text as it
    is published, and the record names its `body_hash`. `diff` and `lines`
    are a round's or pass's hashes of its own changes (`own_changes`), which
    `workflow review-record` computes; without them the line is written as
    before #258. `findings` (a `findings.Findings`, #370) writes a `rule=2`
    record whose result is worked out from its marks, so `clean` is None with
    it, and a spec's review takes none. Raises RecordError, saying which flag
    to fix, for a missing or malformed field."""
    if findings is not None:
        if body is not None or _kind(kind) == "spec":
            raise RecordError(FINDINGS_WITH_SPEC)
        if clean is not None:
            raise RecordError(FINDINGS_WITH_RESULT)
        if not isinstance(findings, findings_mod.Findings):
            raise RecordError("give the findings as read from a findings file")
        clean = findings.clean
    if clean is True:
        result = "clean"
    elif clean is False:
        result = "not-clean"
    else:
        result = None
    digest = None
    if body is not None:
        check_key(kind, commit, body_given=True)
        if not isinstance(body, str):
            raise RecordError("give --body as the spec's text")
        if not plain_body(body):
            raise RecordError(f"the spec's body {EMPTY_BODY}")
        digest = body_hash(body)
    r = _checked(kind, round, commit, reviewers, result, digest, diff, lines)
    if findings is not None:
        try:
            found = findings_mod.checked(findings.findings, findings.outcomes, findings.from_split)
        except findings_mod.FindingsError as e:
            raise RecordError(str(e)) from None
        r = r.with_found(found)
    names = ", ".join(n.capitalize() for n in r.reviewers)
    if r.kind == "spec":
        what, on = f"Spec review round {r.round}", f"body `{r.body[:7]}`"
    else:
        what = f"Review round {r.round}" if r.kind == "round" else f"Correctness pass after round {r.round}"
        on = f"`{r.commit[:7]}`"
    head = f"{what} on {on}: {r.result.replace('-', ' ')}. Reviewers: {names}."
    if r.rule is None:
        return f"{head}\n{r.line()}\n{AGENT_MARKER}\n"
    # Paragraphs apart, so Markdown never runs a list into the next line.
    machine = "\n".join([*r.machine_lines(), AGENT_MARKER])
    text = "\n\n".join([head, *r.found.paragraphs(), machine]) + "\n"
    # Checked as if hashed already, so a record refused for its size is never hashed.
    size = len(text.encode("utf-16-le")) // 2 + (_HASHES_ROOM if r.diff is None else 0)
    if size > RECORD_LIMIT:
        raise RecordError(
            f"the record would be {size} characters, past the {RECORD_LIMIT} a comment holds with a cloud session's footer "
            f"(GitHub takes {COMMENT_LIMIT}): file the lesser findings as one ticket and give its issue, or shorten the parts' names"
        )
    return text


def _parse(fields: str, below=()) -> Record | None:
    """A review line's record, or None. `below` is the lines under it, where a
    `rule=2` record's finding and outcome lines are."""
    got = dict(p.partition("=")[::2] for p in fields.split(" "))
    found = None
    if "rule" in got:
        rule = {k: got.pop(k, None) for k in _RULE_FIELDS}
        if rule["rule"] != str(RULE) or None in rule.values():
            return None
        found = findings_mod.read_lines(below, rule["findings"], rule["outcomes"], rule["split"])
        if found is None:
            return None
    try:
        if set(got) == set(_FIELDS):
            r = _checked(*(got[k] for k in _FIELDS))
        elif set(got) == set(_HASHED_FIELDS):
            r = _checked(*(got[k] for k in _FIELDS), diff=got["diff"], lines=got["lines"])
        elif set(got) == set(_SPEC_FIELDS):
            r = _checked(got["kind"], got["round"], None, got["reviewers"], got["result"], got["body"])
        else:
            return None
    except RecordError:
        return None
    if found is not None:
        if r.kind == "spec" or r.clean != found.clean:
            return None
        r = r.with_found(found)
    # Only exactly what the writer writes: the fields in order, single spaces,
    # lowercase, the panel's order, no repeats.
    return r if r.line() == f"<!-- workflow:review {fields} -->" else None


def records_in(text) -> list[Record]:
    """Every well-formed record line in one comment's text, in order, up to its
    first code fence. A malformed one, or text that isn't a string, yields
    nothing; never raises. A `rule=2` record counts only when every finding
    or outcome line in the comment, anywhere and in any spelling, is one of
    the lines its records were read from: so one can't be read beside lines
    it doesn't account for."""
    if not isinstance(text, str):
        return []
    out, own = [], set()
    lines = _LINE_END.split(text)
    for i, line in enumerate(lines):
        if any(f in line for f in _FENCE):
            break
        m = _LINE.fullmatch(line)
        # A `rule=2` record's own lines below it, up to the next fence.
        r = _parse(m.group(1), _below(lines, i + 1)) if m else None
        if r is not None:
            out.append(r)
            own.update(range(i + 1, i + 1 + len(r.findings) + len(r.outcomes)))
    if any(_OWN_LINE.match(line) and i not in own for i, line in enumerate(lines)):
        out = [r for r in out if r.rule is None]
    return out


def _below(lines, start: int, most: int = 2 * findings_mod.MAX_ITEMS) -> list[str]:
    out = []
    for line in lines[start:start + most]:
        if any(f in line for f in _FENCE):
            break
        out.append(line.rstrip(" \t"))
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


def spec_reviewed(records, body) -> bool:
    """Whether `records` (in the order posted, oldest first) hold a clean
    review of this spec body: the latest spec record for its `body_hash` is
    clean. Records of other bodies, and round and pass records, don't count.
    It doesn't judge who posted them: a caller that counts only accounts with
    write access leaves the others out first."""
    if not isinstance(body, str) or not plain_body(body):
        return False
    digest = body_hash(body)
    mine = [r for r in records if r.kind == "spec" and r.body == digest]
    return bool(mine) and mine[-1].clean

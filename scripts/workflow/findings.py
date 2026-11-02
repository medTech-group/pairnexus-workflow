"""The findings file a build review's record is written from, and the lines
that carry its findings in a `rule=2` record (#370, spec #412 "Records and
clean").

`workflow review-record --findings F` reads a JSON file: a list of findings, or
an object with that list under `findings` and, optionally, `outcomes` and
`split`:

    {
      "findings": [
        {"mark": "blocks", "mechanism": "the requeue order",
         "reproducer": "a dropped PR requeued twice: queued once", "covered": true},
        {"mark": "ticket", "mechanism": "label sync", "issue": 415},
        {"mark": "note", "mechanism": "wording"},
        {"mark": "blocks", "mechanism": "…", "reproducer": "…",
         "security": "change", "area": "sign-in"}
      ],
      "outcomes": [
        {"outcome": "contested", "finding": 2, "ruling": "kept"},
        {"outcome": "fail-closed", "mechanism": "the merge gate"},
        {"outcome": "split", "mechanism": "the preview reader", "issue": 416}
      ],
      "split": false
    }

A finding, one for each this review reported:
- `mark`: `blocks`, `ticket` (a ticket to fix it) or `note`;
- `mechanism`: the reviewer's short name for the part of the change it is
  about ("the part", in what a person reads), at most 80 characters, with no
  backtick or control character;
- `reproducer`: the concrete failing case; a finding marked `blocks` needs
  one. It stays in the file: the record never carries it;
- `covered` (default false): the bar's fail-closed form covers it;
- `contested` (default false): a finding the last review reported, contested
  and kept by this one, re-entered here; it is marked `blocks`;
- `security` (absent by default): `change`, a security problem the change
  adds, or `main`, a security or safety problem in code already on the base
  branch, with its `area`. The record shows such a finding's area in place of
  its mechanism, and never its reproducer;
- `issue`: the issue of a ticket to fix it, as `415` or `"#415"`.

The outcomes of the last review's findings, which happen after its record was
posted:
- `{"outcome": "contested", "finding": N, "ruling": "kept"|"overturned"}`:
  that review's finding N was contested, and this review ruled on it. Each
  contest kept has its finding re-entered above, flagged `contested`;
- `{"outcome": "fail-closed", "mechanism": M}`: the part took the bar's
  fail-closed form (the safe fallback);
- `{"outcome": "split", "mechanism": M, "issue": N}`: the part was split out
  to that ticket.

`split` (default false): the ticket was itself made by a split, copied from
its `<!-- workflow:fix-ticket … kind=split -->` line.

An empty list is a clean review; the result is worked out: not clean when any
finding is marked `blocks`.

In the record, under its `rule=2` review line and with nothing between, one
line for each finding and then one for each outcome, in order:

    <!-- workflow:finding n=1 mark=blocks mechanism=the%20requeue%20order covered=yes contested=no security=no issue=none -->
    <!-- workflow:outcome n=1 kind=split mechanism=the%20preview%20reader issue=416 -->

A mechanism is percent-encoded (every byte but letters, digits and `-._~`),
so it is written exactly and never ends the comment. The writer and the
reader share one set of rules (`checked`); the reader never raises.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

MARKS = ("blocks", "ticket", "note")
SECURITY = ("change", "main")
OUTCOMES = ("contested", "fail-closed", "split")
RULINGS = ("kept", "overturned")
MAX_NAME = 80
# At most this many findings, or outcomes, in one record.
MAX_ITEMS = 999

_ISSUE = re.compile(r"#?([1-9][0-9]{0,6})")
_COUNT = re.compile(r"0|[1-9][0-9]{0,2}")
_FINDING_KEYS = ("mark", "mechanism", "reproducer", "covered", "contested", "security", "area", "issue")
_OUTCOME_KEYS = {
    "contested": ("outcome", "finding", "ruling"),
    "fail-closed": ("outcome", "mechanism"),
    "split": ("outcome", "mechanism", "issue"),
}
_TOP_KEYS = ("findings", "outcomes", "split")
_FINDING_LINE = re.compile(
    r"<!-- workflow:finding n=([0-9]+) mark=(\S+) mechanism=(\S+) covered=(yes|no) "
    r"contested=(yes|no) security=(\S+) issue=(\S+) -->[ \t]*"
)
_OUTCOME_LINE = re.compile(r"<!-- workflow:outcome n=([0-9]+) kind=(\S+) (\S[^\n]*?) -->[ \t]*")


class FindingsError(ValueError):
    """A findings file, or a finding, refused in plain words."""


@dataclass(frozen=True)
class Finding:
    mark: str
    # As the record shows it: a security finding's area.
    mechanism: str
    covered: bool = False
    contested: bool = False
    security: str | None = None
    issue: int | None = None

    def line(self, n: int) -> str:
        return (
            f"<!-- workflow:finding n={n} mark={self.mark} mechanism={_enc(self.mechanism)} "
            f"covered={_yn(self.covered)} contested={_yn(self.contested)} "
            f"security={self.security or 'no'} issue={self.issue or 'none'} -->"
        )

    def text(self) -> str:
        what = {"blocks": "Blocks", "ticket": "A ticket to fix it", "note": "Note"}[self.mark]
        if self.contested:
            what += ", kept after a contest"
        if self.security == "change":
            part = f"a security problem the change adds, in `{self.mechanism}`"
        elif self.security == "main":
            part = f"a security or safety problem in code on the base branch, in `{self.mechanism}`"
        else:
            part = f"the part `{self.mechanism}`"
        if self.covered:
            part += ", which the safe fallback covers"
        if self.issue:
            part += f", #{self.issue}"
        return f"- {what}: {part}."


@dataclass(frozen=True)
class Outcome:
    kind: str
    # contested: the last review's finding, by its number there, and the ruling.
    finding: int | None = None
    ruling: str | None = None
    # fail-closed and split: the part; split: the ticket it went to.
    mechanism: str | None = None
    issue: int | None = None

    def line(self, n: int) -> str:
        if self.kind == "contested":
            rest = f"finding={self.finding} ruling={self.ruling}"
        elif self.kind == "fail-closed":
            rest = f"mechanism={_enc(self.mechanism)}"
        else:
            rest = f"mechanism={_enc(self.mechanism)} issue={self.issue}"
        return f"<!-- workflow:outcome n={n} kind={self.kind} {rest} -->"

    def text(self) -> str:
        if self.kind == "contested":
            return f"- Finding {self.finding}'s contest: {self.ruling}."
        if self.kind == "fail-closed":
            return f"- The part `{self.mechanism}` took the safe fallback."
        return f"- The part `{self.mechanism}` was split out to #{self.issue}."


@dataclass(frozen=True)
class Findings:
    findings: tuple[Finding, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    # The ticket was itself made by a split.
    from_split: bool = False

    @property
    def clean(self) -> bool:
        """No finding marked blocks."""
        return not any(f.mark == "blocks" for f in self.findings)

    def fields(self) -> str:
        """The review line's own fields, before its `result`."""
        return f"rule=2 findings={len(self.findings)} outcomes={len(self.outcomes)} split={_yn(self.from_split)}"

    def lines(self) -> list[str]:
        """The lines under the review line, in order."""
        return [f.line(i) for i, f in enumerate(self.findings, 1)] + [o.line(i) for i, o in enumerate(self.outcomes, 1)]

    def text(self) -> list[str]:
        """What a person reads, as paragraphs."""
        out = []
        if self.findings:
            out.append("\n".join(["Findings:", *(f.text() for f in self.findings)]))
        if self.outcomes:
            out.append("\n".join(["From the last review:", *(o.text() for o in self.outcomes)]))
        if self.from_split:
            out.append("This ticket was made by a split.")
        return out


def _yn(v: bool) -> str:
    return "yes" if v else "no"


def _enc(name: str) -> str:
    return quote(name, safe="")


def _shown(value, n: int = 30) -> str:
    text = str(value)
    cut = "".join("\\" + c if c in "`\\" else c if c.isprintable() else repr(c)[1:-1] for c in text[:n])
    return cut + ("…" if len(text) > n else "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


# The shared rules -------------------------------------------------------------


def _name(value, where: str, key: str) -> str:
    """A mechanism or an area: text, at most MAX_NAME characters once trimmed,
    with no backtick or control character."""
    if not isinstance(value, str):
        raise FindingsError(f"{where}: `{key}` is text")
    name = value.strip()
    if not name:
        raise FindingsError(f"{where}: `{key}` is empty: give the part's short name")
    if len(name) > MAX_NAME:
        raise FindingsError(f"{where}: `{key}` is longer than {MAX_NAME} characters: give a short name")
    if "`" in name:
        raise FindingsError(f"{where}: `{key}` has a backtick: leave it out")
    if not all(c.isprintable() for c in name):
        raise FindingsError(f"{where}: `{key}` has a control character (a line break, a tab): keep it to one line of plain text")
    return name


def _issue(value, where: str, key: str = "issue") -> int:
    """An issue's number: 415, or "#415"."""
    text = value if isinstance(value, str) else str(value) if type(value) is int else ""
    m = _ISSUE.fullmatch(text.strip())
    if not m:
        raise FindingsError(f"{where}: `{key}` is an issue's number, as 415 or \"#415\", not `{_shown(value)}`")
    return int(m.group(1))


def _flag(value, where: str, key: str) -> bool:
    if not isinstance(value, bool):
        raise FindingsError(f"{where}: `{key}` is true or false, not `{_shown(value)}`")
    return value


def _number(value, where: str, key: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_ITEMS:
        raise FindingsError(f"{where}: `{key}` is the number of the last review's finding, from 1 to {MAX_ITEMS}, not `{_shown(value)}`")
    return value


def checked(findings, outcomes, from_split) -> Findings:
    """The rules a record's findings and outcomes keep, for the writer and the
    reader alike: a Findings, or FindingsError naming what is wrong."""
    findings, outcomes = tuple(findings), tuple(outcomes)
    if len(findings) > MAX_ITEMS or len(outcomes) > MAX_ITEMS:
        raise FindingsError(f"at most {MAX_ITEMS} findings and {MAX_ITEMS} outcomes in one review")
    for i, f in enumerate(findings, 1):
        where = f"finding {i}"
        if f.mark not in MARKS:
            raise FindingsError(f"{where}: `mark` is `blocks`, `ticket` (a ticket to fix it) or `note`, not `{_shown(f.mark)}`")
        if _name(f.mechanism, where, "area" if f.security else "mechanism") != f.mechanism:
            raise FindingsError(f"{where}: `mechanism` has space at its ends")
        if f.security is not None and f.security not in SECURITY:
            raise FindingsError(f"{where}: `security` is `change` (a security problem the change adds) or `main` (a security or safety problem in code on the base branch), not `{_shown(f.security)}`")
        if f.contested and f.mark != "blocks":
            raise FindingsError(f"{where} is contested (kept after a contest), so it is marked blocks: a kept finding is re-entered as blocking")
        if f.issue is not None and not (type(f.issue) is int and 1 <= f.issue <= 9_999_999):
            raise FindingsError(f"{where}: `issue` is an issue's number")
    ruled, acted = set(), set()
    for i, o in enumerate(outcomes, 1):
        where = f"outcome {i}"
        if o.kind not in OUTCOMES:
            raise FindingsError(f"{where}: `outcome` is `contested`, `fail-closed` or `split`, not `{_shown(o.kind)}`")
        if o.kind == "contested":
            _number(o.finding, where, "finding")
            if o.ruling not in RULINGS:
                raise FindingsError(f"{where}: `ruling` is `kept` or `overturned`, not `{_shown(o.ruling)}`")
            if o.mechanism is not None or o.issue is not None:
                raise FindingsError(f"{where}: a contest names the finding and its ruling only")
            if o.finding in ruled:
                raise FindingsError(f"{where}: finding {o.finding}'s contest is already ruled")
            ruled.add(o.finding)
        else:
            if o.finding is not None or o.ruling is not None:
                raise FindingsError(f"{where}: a {o.kind} outcome names the part, not a finding")
            if _name(o.mechanism, where, "mechanism") != o.mechanism:
                raise FindingsError(f"{where}: `mechanism` has space at its ends")
            if (o.kind == "split") != (o.issue is not None):
                raise FindingsError(f"{where}: " + ("give `issue`: the ticket it was split out to" if o.kind == "split" else "only a split names an issue"))
            if o.issue is not None and not (type(o.issue) is int and 1 <= o.issue <= 9_999_999):
                raise FindingsError(f"{where}: `issue` is an issue's number")
            if (o.kind, o.mechanism) in acted:
                verb = "split" if o.kind == "split" else "in its safe fallback"
                raise FindingsError(f"{where}: the part `{_shown(o.mechanism, MAX_NAME)}` is already {verb}")
            acted.add((o.kind, o.mechanism))
    kept = sum(1 for o in outcomes if o.ruling == "kept")
    flagged = sum(1 for f in findings if f.contested)
    if kept != flagged:
        raise FindingsError(
            f"{_plural(kept, 'contest')} kept but {_plural(flagged, 'finding')} flagged contested: "
            "re-enter each finding whose contest was kept, marked blocks, with `contested: true`"
        )
    if not isinstance(from_split, bool):
        raise FindingsError(f"`split` is true or false, not `{_shown(from_split)}`")
    return Findings(findings, outcomes, from_split)


# The file ---------------------------------------------------------------------


def _no_repeats(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise FindingsError(f"the file gives `{_shown(k)}` twice in one object: give it once")
        seen[k] = v
    return seen


def _known(obj: dict, keys, where: str) -> None:
    for k in obj:
        if k not in keys:
            raise FindingsError(f"{where}: unknown key `{_shown(k)}`: the keys are {', '.join(f'`{x}`' for x in keys)}")


def _finding(raw, i: int) -> Finding:
    where = f"finding {i}"
    if not isinstance(raw, dict):
        raise FindingsError(f"{where} is an object, as {{\"mark\": \"note\", \"mechanism\": \"…\"}}")
    _known(raw, _FINDING_KEYS, where)
    for key in ("mark", "mechanism"):
        if key not in raw:
            raise FindingsError(f"{where}: give `{key}`")
    mark = raw["mark"]
    if mark not in MARKS:
        raise FindingsError(f"{where}: `mark` is `blocks`, `ticket` (a ticket to fix it) or `note`, not `{_shown(mark)}`")
    mechanism = _name(raw["mechanism"], where, "mechanism")
    reproducer = raw.get("reproducer")
    if reproducer is not None and not isinstance(reproducer, str):
        raise FindingsError(f"{where}: `reproducer` is text")
    if mark == "blocks" and not (reproducer or "").strip():
        raise FindingsError(f"{where} is marked blocks but has no `reproducer`: give the concrete failing case, or mark it `note`")
    covered = _flag(raw.get("covered", False), where, "covered")
    contested = _flag(raw.get("contested", False), where, "contested")
    security = raw.get("security")
    if security is not None and security not in SECURITY:
        raise FindingsError(f"{where}: `security` is `change` (a security problem the change adds) or `main` (a security or safety problem in code on the base branch), not `{_shown(security)}`")
    if security is None and "area" in raw:
        raise FindingsError(f"{where}: `area` goes only with `security`")
    if security is not None:
        if "area" not in raw:
            raise FindingsError(f"{where} is a security finding: give its `area`, the only part of it the record shows")
        mechanism = _name(raw["area"], where, "area")
    issue = None if raw.get("issue") is None else _issue(raw["issue"], where)
    return Finding(mark=mark, mechanism=mechanism, covered=covered, contested=contested, security=security, issue=issue)


def _outcome(raw, i: int) -> Outcome:
    where = f"outcome {i}"
    if not isinstance(raw, dict):
        raise FindingsError(f"{where} is an object, as {{\"outcome\": \"split\", \"mechanism\": \"…\", \"issue\": 416}}")
    if "outcome" not in raw:
        raise FindingsError(f"{where}: give `outcome`: `contested`, `fail-closed` or `split`")
    kind = raw["outcome"]
    if kind not in OUTCOMES:
        raise FindingsError(f"{where}: `outcome` is `contested`, `fail-closed` or `split`, not `{_shown(kind)}`")
    keys = _OUTCOME_KEYS[kind]
    _known(raw, keys, where)
    for key in keys:
        if key not in raw:
            raise FindingsError(f"{where}: give `{key}`")
    if kind == "contested":
        finding = _number(raw["finding"], where, "finding")
        if raw["ruling"] not in RULINGS:
            raise FindingsError(f"{where}: `ruling` is `kept` or `overturned`, not `{_shown(raw['ruling'])}`")
        return Outcome(kind=kind, finding=finding, ruling=raw["ruling"])
    mechanism = _name(raw["mechanism"], where, "mechanism")
    issue = _issue(raw["issue"], where) if kind == "split" else None
    return Outcome(kind=kind, mechanism=mechanism, issue=issue)


def load(text: str) -> Findings:
    """A findings file's text, read and checked. Raises FindingsError."""
    if not text.strip():
        raise FindingsError("is empty: give `[]` for a review with no findings")
    try:
        data = json.loads(text, object_pairs_hook=_no_repeats)
    except FindingsError:
        raise
    except (ValueError, RecursionError) as e:
        where = f" (line {e.lineno}, column {e.colno})" if isinstance(e, json.JSONDecodeError) else ""
        raise FindingsError(f"isn't JSON{where}: give a list of findings, or an object with `findings`") from None
    if isinstance(data, list):
        data = {"findings": data}
    if not isinstance(data, dict):
        raise FindingsError("holds a list of findings, or an object with `findings`, `outcomes` and `split`")
    _known(data, _TOP_KEYS, "the file")
    if "findings" not in data:
        raise FindingsError("give `findings`: the list of this review's findings (`[]` for none)")
    if not isinstance(data["findings"], list):
        raise FindingsError("`findings` is a list")
    outcomes = data.get("outcomes", [])
    if not isinstance(outcomes, list):
        raise FindingsError("`outcomes` is a list")
    split = data.get("split", False)
    if not isinstance(split, bool):
        raise FindingsError(f"`split` is true or false, not `{_shown(split)}`")
    return checked(
        (_finding(raw, i) for i, raw in enumerate(data["findings"], 1)),
        (_outcome(raw, i) for i, raw in enumerate(outcomes, 1)),
        split,
    )


def from_file(path) -> Findings:
    """A findings file read from disk, refused in words for a file that is
    missing, can't be read, isn't UTF-8 text or is malformed."""
    if not path:
        raise FindingsError("give --findings a file: this review's findings, `[]` for none")
    shown = _shown(path, 80) if len(path) <= 80 else "…" + _shown(path[-79:], 79)
    p = Path(path)
    try:
        if not p.exists():
            raise FindingsError(f"--findings names no file: `{shown}`")
        if not p.is_file():
            raise FindingsError(f"--findings `{shown}` isn't a file: give the file holding this review's findings")
        text = p.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise FindingsError(f"--findings `{shown}` isn't UTF-8 text") from None
    except OSError as e:
        raise FindingsError(f"--findings `{shown}` can't be read: {e.strerror or e}") from None
    try:
        return load(text.removeprefix("﻿"))
    except FindingsError as e:
        raise FindingsError(f"--findings `{shown}` {e}" if str(e).startswith(("is ", "isn't ", "holds ")) else f"--findings `{shown}`: {e}") from None


# The reader -------------------------------------------------------------------


def _dec(text: str) -> str | None:
    """A mechanism as written, or None when it isn't exactly as the writer
    encodes it."""
    try:
        name = unquote(text, errors="strict")
    except UnicodeDecodeError:
        return None
    return name if _enc(name) == text else None


def _count(text: str) -> int | None:
    return int(text) if _COUNT.fullmatch(text) else None


def parse_finding(line: str, n: int) -> Finding | None:
    m = _FINDING_LINE.fullmatch(line)
    if not m or m.group(1) != str(n):
        return None
    _, mark, mech, covered, contested, security, issue = m.groups()
    name = _dec(mech)
    if name is None or (issue != "none" and not re.fullmatch(r"[1-9][0-9]{0,6}", issue)) or security not in ("no", *SECURITY):
        return None
    return Finding(
        mark=mark, mechanism=name, covered=covered == "yes", contested=contested == "yes",
        security=None if security == "no" else security, issue=None if issue == "none" else int(issue),
    )


def parse_outcome(line: str, n: int) -> Outcome | None:
    m = _OUTCOME_LINE.fullmatch(line)
    if not m or m.group(1) != str(n):
        return None
    kind, rest = m.group(2), dict(p.partition("=")[::2] for p in m.group(3).split(" "))
    if kind == "contested" and list(rest) == ["finding", "ruling"]:
        finding = _count(rest["finding"])
        return None if not finding else Outcome(kind=kind, finding=finding, ruling=rest["ruling"])
    if kind in ("fail-closed", "split") and list(rest) == list(_OUTCOME_KEYS[kind][1:]):
        name = _dec(rest["mechanism"])
        if name is None:
            return None
        if kind == "fail-closed":
            return Outcome(kind=kind, mechanism=name)
        if not re.fullmatch(r"[1-9][0-9]{0,6}", rest["issue"]):
            return None
        return Outcome(kind=kind, mechanism=name, issue=int(rest["issue"]))
    return None


def read_lines(lines, findings: str, outcomes: str, split: str) -> Findings | None:
    """The findings and outcomes from the lines right under a `rule=2` review
    line (`lines` holds at least as many as its counts say, or fewer when the
    comment ends first), or None unless they are all there, in order, and keep
    the rules. Never raises."""
    nf, no = _count(findings), _count(outcomes)
    if nf is None or no is None or split not in ("yes", "no") or len(lines) < nf + no:
        return None
    fs = [parse_finding(lines[i], i + 1) for i in range(nf)]
    os_ = [parse_outcome(lines[nf + i], i + 1) for i in range(no)]
    if any(x is None for x in fs) or any(x is None for x in os_):
        return None
    try:
        got = checked(fs, os_, split == "yes")
    except FindingsError:
        return None
    # Only exactly what the writer writes.
    return got if got.lines() == list(lines[: nf + no]) else None

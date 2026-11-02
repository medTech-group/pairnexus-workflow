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
  backtick, `~~~` or control character;
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
finding is marked `blocks`. A refusal names the finding or outcome and the key,
and never quotes a finding's values, which may describe a security problem.

In the record, under its `rule=2` review line and with nothing between, one
line for each finding and then one for each outcome, in order:

    <!-- workflow:finding n=1 mark=blocks mechanism=the%20requeue%20order covered=yes contested=no security=no issue=none -->
    <!-- workflow:outcome n=1 kind=split mechanism=the%20preview%20reader issue=416 -->

A mechanism is percent-encoded (every byte but letters, digits and `-._`),
so it is written exactly and never ends the comment or reads as a code fence. The writer and the
reader share one set of rules (`checked`); the reader never raises.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote

# The rule a record written from a findings file names (spec #412).
RULE = 2
MARKS = ("blocks", "ticket", "note")
SECURITY = ("change", "main")
OUTCOMES = ("contested", "fail-closed", "split")
RULINGS = ("kept", "overturned")
MAX_NAME = 80
# At most this many findings, or outcomes, in one record.
MAX_ITEMS = 999

# An issue's number, at most seven digits, as a record line writes it.
_ISSUE_DIGITS = r"[1-9][0-9]{0,6}"
_ISSUE = re.compile(rf"#?({_ISSUE_DIGITS})")
# What `_encoded` writes: letters, digits, `%._-`.
_ENCODED = re.compile(r"[A-Za-z0-9%._-]+")
_COUNT = re.compile(r"0|[1-9][0-9]{0,2}")
_FINDING_KEYS = ("mark", "mechanism", "reproducer", "covered", "contested", "security", "area", "issue")
_OUTCOME_KEYS = {
    "contested": ("outcome", "finding", "ruling"),
    "fail-closed": ("outcome", "mechanism"),
    "split": ("outcome", "mechanism", "issue"),
}
_TOP_KEYS = ("findings", "outcomes", "split")
# The rules' words, shared by the file's refusals and `checked`.
_MARK_RULE = "`mark` is `blocks`, `ticket` (a ticket to fix it) or `note`"
_SECURITY_RULE = "`security` is `change` (a security problem the change adds) or `main` (a security or safety problem in code on the base branch)"
_OUTCOME_RULE = "`outcome` is `contested`, `fail-closed` or `split`"
_RULING_RULE = "`ruling` is `kept` or `overturned`"
_ISSUE_RULE = "`issue` is an issue's number, as 415 or \"#415\""

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
            f"<!-- workflow:finding n={n} mark={self.mark} mechanism={_encoded(self.mechanism)} "
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
            rest = f"mechanism={_encoded(self.mechanism)}"
        else:
            rest = f"mechanism={_encoded(self.mechanism)} issue={self.issue}"
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
        return f"rule={RULE} findings={len(self.findings)} outcomes={len(self.outcomes)} split={_yn(self.from_split)}"

    def lines(self) -> list[str]:
        """The lines under the review line, in order."""
        return [f.line(i) for i, f in enumerate(self.findings, 1)] + [o.line(i) for i, o in enumerate(self.outcomes, 1)]

    def paragraphs(self) -> list[str]:
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


def _encoded(name: str) -> str:
    """Every byte but letters, digits and `-._` percent-encoded: `~` too, so a
    name never holds `~~~`, which a reader takes for a code fence."""
    return quote(name, safe="").replace("~", "%7E")


def _plain(text: str, n: int) -> str:
    """Text as a refusal shows it: cut to `n` characters, a backtick and
    anything that isn't printable escaped."""
    cut = "".join("\\`" if c == "`" else c if c.isprintable() else repr(c)[1:-1] for c in text[:n])
    return cut + ("…" if len(text) > n else "")


def _json(value, n: int = 30) -> str:
    """A value as the person wrote it, in JSON, in backticks (a list or an
    object only named): for refusals of an outcome or the file's own keys,
    never of a finding's."""
    if isinstance(value, list):
        return "a list"
    if isinstance(value, dict):
        return "an object"
    try:
        text = json.dumps(value, ensure_ascii=False)
    except (ValueError, OverflowError):
        text = str(value)
    return f"`{_plain(text, n)}`"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


# The shared rules -------------------------------------------------------------


def _name(value, where: str, key: str) -> str:
    """A mechanism or an area: text, at most MAX_NAME characters once trimmed,
    with no backtick, `~~~` or control character. Never quotes it."""
    if not isinstance(value, str):
        raise FindingsError(f"{where}: `{key}` is text")
    name = value.strip()
    if not name:
        raise FindingsError(f"{where}: `{key}` is empty: give the part's short name")
    if len(name) > MAX_NAME:
        raise FindingsError(f"{where}: `{key}` is longer than {MAX_NAME} characters: give a short name")
    if "`" in name:
        raise FindingsError(f"{where}: `{key}` has a backtick: leave it out")
    if "~~~" in name:
        raise FindingsError(f"{where}: `{key}` has `~~~`, which reads as a code fence: leave it out")
    if not all(c.isprintable() for c in name):
        raise FindingsError(f"{where}: `{key}` has a control or invisible character (a line break, a tab): keep it to one line of plain text")
    return name


def _issue_read(text: str) -> int | None:
    """An issue's number as a record line writes it, or None."""
    return int(text) if re.fullmatch(_ISSUE_DIGITS, text) else None


def _issue_ok(value) -> bool:
    return type(value) is int and _issue_read(str(value)) == value


def _issue(value, where: str, quoted: bool) -> int:
    """An issue's number from the file: 415, or "#415"."""
    text = value if isinstance(value, str) else str(value) if type(value) is int else ""
    m = _ISSUE.fullmatch(text.strip())
    if not m:
        raise FindingsError(f"{where}: {_ISSUE_RULE}" + (f", not {_json(value)}" if quoted else ""))
    return int(m.group(1))


def _flag(value, where: str, key: str) -> bool:
    """true or false; a finding's own flags, so the value isn't quoted."""
    if not isinstance(value, bool):
        raise FindingsError(f"{where}: `{key}` is true or false (in JSON, without quotes)")
    return value


def _finding_number(value, where: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_ITEMS:
        raise FindingsError(f"{where}: `finding` is the number of the last review's finding, from 1 to {MAX_ITEMS}, not {_json(value)}")
    return value


def checked(findings, outcomes, from_split) -> Findings:
    """The rules a record's findings and outcomes keep, for the writer and the
    reader alike: a Findings, or FindingsError naming what is wrong, never
    quoting a finding's values."""
    findings, outcomes = tuple(findings), tuple(outcomes)
    if len(findings) > MAX_ITEMS or len(outcomes) > MAX_ITEMS:
        raise FindingsError(f"at most {MAX_ITEMS} findings and {MAX_ITEMS} outcomes in one review")
    for i, f in enumerate(findings, 1):
        where = f"finding {i}"
        if f.mark not in MARKS:
            raise FindingsError(f"{where}: {_MARK_RULE}")
        if f.security is not None and f.security not in SECURITY:
            raise FindingsError(f"{where}: {_SECURITY_RULE}")
        if _name(f.mechanism, where, "area" if f.security else "mechanism") != f.mechanism:
            raise FindingsError(f"{where}: `mechanism` has space at its ends")
        if f.contested and f.mark != "blocks":
            raise FindingsError(f"{where} is contested (kept after a contest), so it is marked blocks: a kept finding is re-entered as blocking")
        if f.issue is not None and not _issue_ok(f.issue):
            raise FindingsError(f"{where}: {_ISSUE_RULE}")
    ruled, acted = set(), set()
    for i, o in enumerate(outcomes, 1):
        where = f"outcome {i}"
        if o.kind not in OUTCOMES:
            raise FindingsError(f"{where}: {_OUTCOME_RULE}")
        if o.kind == "contested":
            _finding_number(o.finding, where)
            if o.ruling not in RULINGS:
                raise FindingsError(f"{where}: {_RULING_RULE}, not {_json(o.ruling)}")
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
            if o.issue is not None and not _issue_ok(o.issue):
                raise FindingsError(f"{where}: {_ISSUE_RULE}")
            if (o.kind, o.mechanism) in acted:
                verb = "split" if o.kind == "split" else "in its safe fallback"
                raise FindingsError(f"{where}: the part `{o.mechanism}` is already {verb}")
            acted.add((o.kind, o.mechanism))
    kept = sum(1 for o in outcomes if o.ruling == "kept")
    flagged = sum(1 for f in findings if f.contested)
    if kept != flagged:
        raise FindingsError(
            f"{_plural(kept, 'contest')} kept but {_plural(flagged, 'finding')} flagged contested: "
            "re-enter each finding whose contest was kept, marked blocks, with `contested: true`"
        )
    if not isinstance(from_split, bool):
        raise FindingsError(f"`split` is true or false (in JSON, without quotes), not {_json(from_split)}")
    return Findings(findings, outcomes, from_split)


# The file ---------------------------------------------------------------------


def _no_repeats(pairs):
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise FindingsError(f"the file gives {_json(k)} twice in one object: give it once")
        seen[k] = v
    return seen


def _known(obj: dict, keys, where: str) -> None:
    for k in obj:
        if k not in keys:
            raise FindingsError(f"{where}: unknown key {_json(k)}: the keys are {', '.join(f'`{x}`' for x in keys)}")


def _finding(raw, i: int) -> Finding:
    """One finding from the file. What only the file has (its keys and their
    JSON types, the reproducer, the area) is checked here, and the mark and
    names too, so refusals come in the file's order; `checked` then applies
    the rules the reader shares."""
    where = f"finding {i}"
    if not isinstance(raw, dict):
        raise FindingsError(f"{where} is an object, as {{\"mark\": \"note\", \"mechanism\": \"…\"}}")
    _known(raw, _FINDING_KEYS, where)
    for key in ("mark", "mechanism"):
        if key not in raw:
            raise FindingsError(f"{where}: give `{key}`")
    if raw["mark"] not in MARKS:
        raise FindingsError(f"{where}: {_MARK_RULE}")
    mechanism = _name(raw["mechanism"], where, "mechanism")
    reproducer = raw.get("reproducer")
    if reproducer is not None and not isinstance(reproducer, str):
        raise FindingsError(f"{where}: `reproducer` is text")
    if raw["mark"] == "blocks" and not (reproducer or "").strip():
        raise FindingsError(f"{where} is marked blocks but has no `reproducer`: give the concrete failing case, or mark it `note`")
    security = raw.get("security")
    if security is not None and security not in SECURITY:
        raise FindingsError(f"{where}: {_SECURITY_RULE}")
    if security is None and "area" in raw:
        raise FindingsError(f"{where}: `area` goes only with `security`")
    if security is not None:
        if "area" not in raw:
            raise FindingsError(f"{where} is a security finding: give its `area`, the only part of it the record shows")
        mechanism = _name(raw["area"], where, "area")
    return Finding(
        mark=raw["mark"],
        mechanism=mechanism,
        covered=_flag(raw.get("covered", False), where, "covered"),
        contested=_flag(raw.get("contested", False), where, "contested"),
        security=security,
        issue=None if raw.get("issue") is None else _issue(raw["issue"], where, quoted=False),
    )


def _outcome(raw, i: int) -> Outcome:
    """One outcome from the file: its keys and their JSON types here, the rest
    by `checked`."""
    where = f"outcome {i}"
    if not isinstance(raw, dict):
        raise FindingsError(f"{where} is an object, as {{\"outcome\": \"split\", \"mechanism\": \"…\", \"issue\": 416}}")
    if "outcome" not in raw:
        raise FindingsError(f"{where}: give `outcome`: `contested`, `fail-closed` or `split`")
    kind = raw["outcome"]
    if kind not in OUTCOMES:
        raise FindingsError(f"{where}: {_OUTCOME_RULE}, not {_json(kind)}")
    keys = _OUTCOME_KEYS[kind]
    _known(raw, keys, where)
    for key in keys:
        if key not in raw:
            raise FindingsError(f"{where}: give `{key}`" + (": the ticket it was split out to" if key == "issue" else ""))
    if kind == "contested":
        return Outcome(kind=kind, finding=_finding_number(raw["finding"], where), ruling=raw["ruling"])
    mechanism = _name(raw["mechanism"], where, "mechanism")
    issue = _issue(raw["issue"], where, quoted=True) if kind == "split" else None
    return Outcome(kind=kind, mechanism=mechanism, issue=issue)


def _no_constant(name: str):
    raise FindingsError(f"isn't JSON: `{name}` is no JSON value")


def _finite(text: str) -> float:
    """A number with a fraction or exponent, refused when too large to hold,
    so a refusal never quotes it as `Infinity`."""
    value = float(text)
    if value in (float("inf"), float("-inf")):
        raise FindingsError(f"isn't JSON this command reads: `{_plain(text, 30)}` is too large a number")
    return value


def load(text: str) -> Findings:
    """A findings file's text, read and checked. Raises FindingsError."""
    if not text.strip():
        raise FindingsError("is empty: give `[]` for a review with no findings")
    try:
        data = json.loads(text, object_pairs_hook=_no_repeats, parse_constant=_no_constant, parse_float=_finite)
    except FindingsError:
        raise
    except (ValueError, RecursionError) as e:
        where = f" (line {e.lineno}, column {e.colno})" if isinstance(e, json.JSONDecodeError) else ""
        raise FindingsError(f"isn't JSON this command reads{where}: give a list of findings, or an object with `findings`") from None
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
    return checked(
        [_finding(raw, i) for i, raw in enumerate(data["findings"], 1)],
        [_outcome(raw, i) for i, raw in enumerate(outcomes, 1)],
        data.get("split", False),
    )


def from_file(path) -> Findings:
    """A findings file read from disk, refused in words for a file that is
    missing, can't be read, isn't UTF-8 text or is malformed."""
    if not path:
        raise FindingsError("give --findings a file: this review's findings, `[]` for none")
    # The end of a long path, where the file's name is.
    shown = _plain(path, 80) if len(path) <= 80 else "…" + _plain(path[-79:], 79)
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
        return load(text.removeprefix("\ufeff"))
    except FindingsError as e:
        raise FindingsError(f"--findings `{shown}` {e}" if str(e).startswith(("is ", "isn't ", "holds ")) else f"--findings `{shown}`: {e}") from None


# The reader -------------------------------------------------------------------


def _decoded(text: str) -> str | None:
    """A mechanism as written, or None when it isn't exactly as the writer
    encodes it."""
    if not _ENCODED.fullmatch(text):
        return None
    try:
        name = unquote(text, errors="strict")
    except UnicodeDecodeError:
        return None
    return name if _encoded(name) == text else None


def _count(text: str) -> int | None:
    return int(text) if _COUNT.fullmatch(text) else None


def _parse_finding(line: str, n: int) -> Finding | None:
    m = _FINDING_LINE.fullmatch(line)
    if not m or m.group(1) != str(n):
        return None
    _, mark, mech, covered, contested, security, issue = m.groups()
    name = _decoded(mech)
    number = None if issue == "none" else _issue_read(issue)
    if name is None or (issue != "none" and number is None) or security not in ("no", *SECURITY):
        return None
    return Finding(
        mark=mark, mechanism=name, covered=covered == "yes", contested=contested == "yes",
        security=None if security == "no" else security, issue=number,
    )


def _parse_outcome(line: str, n: int) -> Outcome | None:
    m = _OUTCOME_LINE.fullmatch(line)
    if not m or m.group(1) != str(n):
        return None
    kind, rest = m.group(2), dict(p.partition("=")[::2] for p in m.group(3).split(" "))
    if kind not in _OUTCOME_KEYS or list(rest) != list(_OUTCOME_KEYS[kind][1:]):
        return None
    if kind == "contested":
        finding = _count(rest["finding"])
        return Outcome(kind=kind, finding=finding, ruling=rest["ruling"]) if finding else None
    name = _decoded(rest["mechanism"])
    if name is None:
        return None
    if kind == "fail-closed":
        return Outcome(kind=kind, mechanism=name)
    issue = _issue_read(rest["issue"])
    return Outcome(kind=kind, mechanism=name, issue=issue) if issue else None


def read_lines(lines, n_findings: str, n_outcomes: str, split: str) -> Findings | None:
    """The findings and outcomes from the lines right under a `rule=2` review
    line, given its counts and split flag as written, or None unless that many
    are there, in order, keeping the rules. Never raises. (`reviews.records_in`
    refuses the record when the comment holds any other finding or outcome
    line.)"""
    findings_count, outcomes_count = _count(n_findings), _count(n_outcomes)
    if findings_count is None or outcomes_count is None or split not in ("yes", "no") or len(lines) < findings_count + outcomes_count:
        return None
    found = [_parse_finding(lines[i], i + 1) for i in range(findings_count)]
    outs = [_parse_outcome(lines[findings_count + i], i + 1) for i in range(outcomes_count)]
    if None in found or None in outs:
        return None
    try:
        got = checked(found, outs, split == "yes")
    except FindingsError:
        return None
    # Only exactly what the writer writes.
    return got if got.lines() == list(lines[: findings_count + outcomes_count]) else None

"""`workflow graph cites`: what rests on a decision (spec #682, the project graph).

Built fresh each run from git and the issues' text, with no model and no
stored graph. For each id asked (`#n` or `ADR:NNNN`) it lists, counts
first:

- every passage citing it in the base branch's tracked text files, read at
  `origin/<base>` after fetching it, as `file:line` and its sentence, grouped
  by file;
- every open issue and open pull request whose body cites it, with the
  sentence, its `kind` and whether it is `claimed`.

The citation forms are built in: `#n` (and `owner/repo#n`, for this
repository); "ADR 0001", "ADR-0001" and paths under `adr/`, compared by
number. Left out: the vendored kit
(`lock.json`'s `files`, `orphaned` and the `<file>.new` its `conflicts` name),
research notes' saved copies and fingerprint files (third-party text), a
style file's colour (`#` and 3, 6 or 8 hex digits), and an issue's citations
inside its own `## Replaces`. A sentence matching one of the profile's
`[sensitive].patterns` is given as "[left out: sensitive]", keeping its place.

Answer ids, `built_by`, `changed_by` and the record come with later tickets
(#745 to #747); their fields are here, empty, so `--json`'s form is the
spec's from the start. A research note's path as an id comes later too
(#762): it is refused, as an answer id is. It writes nothing but the fetch of the base branch.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import doctor as doctor_mod
from . import estimate as estimate_mod
from . import evidence as evidence_mod
from . import issues as issues_mod
from . import presets as presets_mod
from . import research as research_mod
from . import small as small_mod
from . import state as state_mod
from . import status as status_mod
from . import vendor as vendor_mod

SENSITIVE = "[left out: sensitive]"
RESEARCH_DIR = "docs/research/"
LOCK = vendor_mod.LOCK.as_posix()
STYLE_SUFFIXES = (".css", ".scss")
RUN_LABEL = estimate_mod.RUN_LABEL
CLAIM_LABEL = issues_mod.CLAIM_LABEL
NOT_TICKET_LABELS = issues_mod.OWNER_TASK_LABELS | {issues_mod.RESEARCH_LABEL}
GREP_CHUNK = 400  # paths given to one `git grep`, well inside any command line's limit


class GraphError(Exception):
    """The command can't run: the message says why, in plain words."""


class BadId(ValueError):
    """An id that isn't one the command reads."""


# ---------- ids ----------


@dataclass(frozen=True)
class Id:
    """A decision asked about: `kind` is "issue" or "adr", with its `number`."""

    kind: str
    number: int = 0

    @property
    def shown(self) -> str:
        return f"#{self.number}" if self.kind == "issue" else f"ADR:{self.number:04d}"


_ISSUE_ID = re.compile(r"#([1-9]\d*)")
_ANSWER_ID = re.compile(r"#\d+:answer:\d+", re.I)
_ADR_ID = re.compile(r"ADR:(\d+)", re.I)


def parse_id(text: str) -> Id:
    """`#n` or `ADR:NNNN` (backticks dropped). An answer id and a research
    note's path (under `docs/research/`, any leading `./` dropped) are ids not
    read yet: refused, saying so. Anything else, other paths too, isn't an id."""
    t = (text or "").strip().strip("`").strip()
    if _ANSWER_ID.fullmatch(t):
        raise BadId(f"`{t}`: answer ids (`#n:answer:N`) aren't read yet")
    m = _ISSUE_ID.fullmatch(t)
    if m:
        return Id("issue", number=int(m.group(1)))
    m = _ADR_ID.fullmatch(t)
    if m:
        return Id("adr", number=int(m.group(1)))
    if re.sub(r"\A(?:\./)+", "", t).startswith(RESEARCH_DIR):
        raise BadId(f"`{t}`: a path (a research note's) isn't read as an id yet: that form comes later")
    raise BadId(f"`{text}` isn't an id: give `#n` or `ADR:NNNN`")


# ---------- citation forms ----------


def citation_pattern(id_: Id, repo: str | None) -> re.Pattern:
    """Where the id is cited in a line of text."""
    if id_.kind == "issue":
        return re.compile(rf"(?<![\w#/.&-])(?:(?P<repo>[\w.-]+/[\w.-]+))?#{id_.number}(?!\d)\b", re.I)
    return re.compile(r"(?<![\w])ADR[ -]0*(?P<n>\d+)(?!\d)|(?<![\w.-])adr/0*(?P<p>\d+)(?!\d)", re.I)


def _cites(m: re.Match, id_: Id, repo: str | None) -> bool:
    if id_.kind == "issue":
        other = m.groupdict().get("repo")
        return not other or issues_mod._same_repo(other, repo)
    return int(m.group("n") or m.group("p")) == id_.number


_COLOUR = re.compile(r"[0-9a-f]{3}(?:[0-9a-f]{3}(?:[0-9a-f]{2})?)?(?![\w])", re.I)


def _is_colour(line: str, m: re.Match) -> bool:
    """A style file's `#` followed by 3, 6 or 8 hex digits."""
    hash_at = line.find("#", m.start())
    return hash_at >= 0 and bool(_COLOUR.match(line, hash_at + 1))


def _grep_pattern(id_: Id) -> str:
    """A loose extended regex (case-insensitive) that every file citing the id
    matches, to find the files worth reading."""
    return rf"#{id_.number}" if id_.kind == "issue" else r"adr"


# ---------- sentences ----------


_QUOTE = re.compile(r"[ \t]*(?:>[ \t]?)+")
_HEADING = re.compile(r"[ \t]{0,3}#{1,6}(?:[ \t]+|$)")
_TABLE = re.compile(r"[ \t]*\|")
_ITEM = re.compile(r"[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+")
_END = re.compile(r"[.!?][\"'”’)\]`*_]*(?=\s|$)")
_NOT_AN_END = re.compile(r"(?:\bans|\be\.g|\bi\.e)\Z", re.I)
_WS = re.compile(r"\s+")


@dataclass
class Sentence:
    lines: list[tuple[int, str]] = field(default_factory=list)  # (line index, text) pieces

    @property
    def text(self) -> str:
        return _WS.sub(" ", " ".join(t for _, t in self.lines)).strip()


def _ends(text: str, start: int) -> list[int]:
    """Where sentences end in `text` after `start`: just past each end mark."""
    out = []
    for m in _END.finditer(text, start):
        # Only the three characters before the mark: `\b` still sees the one before them.
        if text[m.start()] == "." and _NOT_AN_END.search(text, max(0, m.start() - 3), m.start()):
            continue
        out.append(m.end())
    return out


def sentences(lines: list[str]) -> tuple[list[Sentence], dict[int, list[tuple[int, int]]]]:
    """The text's sentences, and for each line its pieces as (start column,
    sentence index), in order. A sentence ends at an end mark, a blank line,
    and the end of a heading, a list item or a table row; a list item starts
    one. Quote marks and a heading's or list item's marker aren't its text."""
    out: list[Sentence] = []
    where: dict[int, list[tuple[int, int]]] = {}
    cur: Sentence | None = None

    def close() -> None:
        nonlocal cur
        if cur is not None and cur.text:
            out.append(cur)
        cur = None

    for i, line in enumerate(lines):
        q = _QUOTE.match(line)
        start = q.end() if q else 0
        if not line[start:].strip():
            close()
            continue
        own = False
        for marker in (_HEADING, _ITEM):
            m = marker.match(line, start)
            if m:
                close()
                start, own = m.end(), marker is _HEADING
                break
        else:
            if _TABLE.match(line, start):
                close()
                own = True
        pos = start
        for end, closes in [*((e, True) for e in _ends(line, start)), (len(line), own)]:
            if end <= pos:
                continue
            if cur is None:
                cur = Sentence()
            where.setdefault(i, []).append((pos, len(out)))
            cur.lines.append((i, line[pos:end]))
            if closes:
                close()
            pos = end
        if own:
            close()
    close()
    # A piece whose sentence was empty (only spaces) points past the list: drop it.
    return out, {i: [(c, s) for c, s in pieces if s < len(out)] for i, pieces in where.items()}


def _sentence_at(where: dict[int, list[tuple[int, int]]], line: int, col: int) -> int | None:
    found = None
    for start, s in where.get(line, []):
        if start <= col:
            found = s
    return found


# ---------- `## Replaces` ----------


_ANY_HEADING = re.compile(r"[ \t]{0,3}#{1,6}(?:[ \t]|$)")
_REPLACES = re.compile(r"[ \t]{0,3}#{1,6}[ \t]+Replaces[ \t]*:?[ \t]*#*[ \t]*$", re.I)


def replaces_lines(lines: list[str]) -> set[int]:
    """The lines of a body's own `## Replaces` section: from its heading to the
    next heading, leaving out a fenced block and a `>` quote, where neither a
    heading nor the section's own lines are read."""
    fence: str | None = None
    inside, out = False, set()
    for i, line in enumerate(lines):
        m = issues_mod._FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not line[m.end():].strip():
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        if line.lstrip().startswith(">"):
            continue
        if _ANY_HEADING.match(line):
            inside = bool(_REPLACES.match(line))
            if inside:
                out.add(i)
            continue
        if inside:
            out.add(i)
    return out


# ---------- finding citations in a text ----------


def _split(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def cited(text: str, id_: Id, pattern: re.Pattern, repo: str | None, *, style: bool = False, skip: set[int] | None = None) -> list[tuple[int, str]]:
    """(1-based line, sentence) for each sentence of `text` citing the id, once
    each, at its first citation's line."""
    lines = _split(text)
    hits: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if skip and i in skip:
            continue
        for m in pattern.finditer(line):
            if not _cites(m, id_, repo):
                continue
            if style and id_.kind == "issue" and m.group(0).startswith("#") and _is_colour(line, m):
                continue
            hits.append((i, m.start()))
    if not hits:
        return []
    found, where = sentences(lines)
    seen: dict[int, int] = {}
    for i, col in hits:
        s = _sentence_at(where, i, col)
        if s is not None and s not in seen:
            seen[s] = i
    return [(seen[s] + 1, found[s].text) for s in sorted(seen, key=lambda s: (seen[s], s))]


# ---------- what is read ----------


def _git(root: Path, *args: str, timeout: int = 120):
    return small_mod._git(root, *args, timeout=timeout, binary=True)


def vendored(root: Path, ref: str, note) -> set[str]:
    """The vendored kit's paths at `ref`, from its lock: `files`, `orphaned`
    and the `<file>.new` its `conflicts` name. None without a lock."""
    got = _git(root, "cat-file", "-e", f"{ref}:{LOCK}")
    if got.returncode != 0:
        return set()
    got = _git(root, "show", f"{ref}:{LOCK}")
    try:
        lock = json.loads(got.stdout.decode("utf-8")) if got.returncode == 0 else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        lock = None
    if not isinstance(lock, dict):
        note(f"{LOCK} at {ref} can't be read, so the vendored kit isn't left out")
        return set()

    def keys(name: str) -> list[str]:
        v = lock.get(name)
        return [k for k in v if isinstance(k, str)] if isinstance(v, dict) else []

    return {*keys("files"), *keys("orphaned"), *(f"{k}.new" for k in keys("conflicts"))}


def _third_party(path: str, text: str) -> bool:
    """A research note's saved copy or fingerprint file, in its topic's folder."""
    if not path.startswith(RESEARCH_DIR) or path.count("/") < 3 or PurePosixPath(path).name == research_mod.NOTE_FILE:
        return False
    if research_mod.is_fingerprint_start(path, text):
        return True
    try:
        research_mod.read_saved_copy(text, path)
    except research_mod.LayoutError:
        return False
    return True


def _decode_path(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def files_citing(root: Path, ref: str, ids: list[Id], left_out: set[str]) -> dict[str, str]:
    """{path: text} of the tracked text files at `ref` that may cite one of the
    ids (found with `git grep`, binary files left out), less `left_out` and
    research notes' third-party files."""
    if not ids:
        return {}
    args = ["grep", "-l", "-z", "-I", "-i", "-E", "--full-name"]
    for id_ in ids:
        args += ["-e", _grep_pattern(id_)]
    got = _git(root, *args, ref, "--")
    if got.returncode not in (0, 1):
        raise GraphError(f"git grep at {ref} failed: {got.stderr.decode('utf-8', 'replace').strip()[:300]}")
    prefix = f"{ref}:"
    paths = [p[len(prefix):] if p.startswith(prefix) else p for p in (_decode_path(x) for x in got.stdout.split(b"\0") if x)]
    paths = [p for p in paths if p not in left_out]
    texts: dict[str, list[str]] = {}
    for at in range(0, len(paths), GREP_CHUNK):
        chunk = paths[at : at + GREP_CHUNK]
        got = _git(root, "grep", "-z", "-n", "-I", "--full-name", "--no-color", "-e", "", ref, "--", *(f":(literal){p}" for p in chunk))
        if got.returncode not in (0, 1):
            raise GraphError(f"git grep at {ref} failed: {got.stderr.decode('utf-8', 'replace').strip()[:300]}")
        _read_lines(got.stdout, prefix, texts)
    return {p: "\n".join(ls) for p, ls in texts.items() if not _third_party(p, "\n".join(ls))}


def _read_lines(out: bytes, prefix: str, texts: dict[str, list[str]]) -> None:
    """`git grep -z -n -e ''`'s output, `<ref>:<path>\\0<n>\\0<line>\\n`, into
    each file's lines (every line matches the empty pattern, in order)."""
    pos = 0
    while pos < len(out):
        a = out.index(b"\0", pos)
        b = out.index(b"\0", a + 1)
        c = out.find(b"\n", b + 1)
        c = len(out) if c < 0 else c
        name = _decode_path(out[pos:a])
        name = name[len(prefix):] if name.startswith(prefix) else name
        texts.setdefault(name, []).append(out[b + 1 : c].decode("utf-8", "replace").rstrip("\r"))
        pos = c + 1


# ---------- issues ----------


@dataclass
class Runs:
    by_hand: set[int] = field(default_factory=set)
    unread: list[str] = field(default_factory=list)  # a line for each run whose state can't be read


def runs(issues: list[dict]) -> Runs:
    """The by-hand issues the `workflow:run` issues' states name, open and
    closed, and a line for each run whose state can't be read."""
    got = Runs()
    for item in issues:
        n = doctor_mod._number(item)
        if n is None or RUN_LABEL not in issues_mod.labels_of(item):
            continue
        try:
            st = state_mod.get(item.get("body") or "")
        except state_mod.StateError as e:
            got.unread.append(f"run #{n}: its state can't be read ({e}), so its by-hand issue isn't told apart")
            continue
        if st is None:
            got.unread.append(f"run #{n}: its state isn't written yet, so its by-hand issue isn't told apart")
            continue
        if not isinstance(st, dict):
            got.unread.append(f"run #{n}: its state can't be read (it isn't a JSON object), so its by-hand issue isn't told apart")
            continue
        h = st.get("by_hand_issue")
        if isinstance(h, int) and not isinstance(h, bool):
            got.by_hand.add(h)
        elif h is not None:
            got.unread.append(f"run #{n}: its state names no by-hand issue it can read ({h!r}), so its by-hand issue isn't told apart")
    return got


def kind_of(item: dict, is_pr: bool, by_hand: set[int]) -> str:
    """`pull_request`, `spec`, `decision`, `run`, `ticket` or `other`, in this order."""
    if is_pr:
        return "pull_request"
    labels = issues_mod.labels_of(item)
    if issues_mod.is_spec(item):
        return "spec"
    if any(l.startswith("wayfinder:") and l != "wayfinder:map" for l in labels):
        return "decision"
    if RUN_LABEL in labels or doctor_mod._number(item) in by_hand:
        return "run"
    if issues_mod.is_build_ticket(item) and not labels & NOT_TICKET_LABELS and not status_mod.ITEM.search(item.get("body") or ""):
        return "ticket"
    return "other"


def claimed(item: dict, kind: str, closed_by: dict[int, int]) -> bool:
    """`workflow:in-progress`; a decision ticket's assignee; an open issue an
    open pull request closes (never a pull request by that clause)."""
    if CLAIM_LABEL in issues_mod.labels_of(item):
        return True
    if kind == "decision" and issues_mod.assignees_of(item):
        return True
    return kind != "pull_request" and doctor_mod._number(item) in closed_by


@dataclass
class Body:
    number: int
    kind: str
    claimed: bool
    text: str
    skip: set[int]


def open_bodies(issues: list[dict], prs: list[dict], repo: str | None, by_hand: set[int]) -> list[Body]:
    """Every open issue's and open pull request's body, by number, with its
    kind, whether it is claimed, and its own `## Replaces` lines."""
    closed_by = issues_mod.closed_by_open_prs([p for p in prs if doctor_mod._number(p) is not None], repo)
    out: dict[int, Body] = {}
    for item, is_pr in [*((p, True) for p in prs), *((i, False) for i in issues)]:
        n = doctor_mod._number(item)
        if n is None or not status_mod._open(item) or n in out or not is_pr and "pull_request" in item:
            continue
        k = kind_of(item, is_pr, by_hand)
        text = item.get("body") or ""
        out[n] = Body(n, k, claimed(item, k, closed_by), text, replaces_lines(_split(text)))
    return [out[n] for n in sorted(out)]


# ---------- the run ----------


@dataclass
class Result:
    id: Id
    passages: list[dict]
    issues: list[dict]

    def as_dict(self) -> dict:
        return {
            "decision": self.id.shown,
            "counts": {
                "passages": len(self.passages),
                "files": len({p["file"] for p in self.passages}),
                "issues": len({i["number"] for i in self.issues}),
                "built_by": 0,
                "spec_unsure": 0,
            },
            "passages": self.passages,
            "issues": self.issues,
            "built_by": [],
            "changed_by": [],
        }


def _shown(sentence: str, sensitive: list[str]) -> str:
    return SENSITIVE if any(re.search(p, sentence) for p in sensitive) else sentence


def cites(root: Path, base: str, ids: list[Id], issues: list[dict], prs: list[dict], *, repo: str | None, sensitive: list[str], note) -> tuple[list[Result], list[str]]:
    """Each id's passages and open issues, from the issues and pull requests
    as objects (their pages flattened), and the lines naming runs whose state
    can't be read. `note(text)` gets a fetch that failed (the `origin/<base>`
    already here is read instead). Raises GraphError."""
    try:
        ref = small_mod.base_ref(root, base, note, "the profile's project.base_branch")
        texts = files_citing(root, ref, ids, vendored(root, ref, note))
    except small_mod.CantMeasure as e:  # git couldn't run, or didn't finish
        raise GraphError(str(e)) from None
    got_runs = runs(issues)
    bodies = open_bodies(issues, prs, repo, got_runs.by_hand)
    results = []
    for id_ in ids:
        pattern = citation_pattern(id_, repo)
        passages = []
        for path in sorted(texts):
            style = path.casefold().endswith(STYLE_SUFFIXES)
            # A name that isn't UTF-8 (or holds a control character) is shown as git quotes it, so any output can print it.
            shown = path if path.isprintable() else evidence_mod._git_quoted(path)
            for line, sentence in cited(texts[path], id_, pattern, repo, style=style):
                passages.append({"file": shown, "line": line, "sentence": _shown(sentence, sensitive), "spec_unsure": False})
        listed = []
        for b in bodies:
            for _, sentence in cited(b.text, id_, pattern, repo, skip=b.skip):
                listed.append({"number": b.number, "kind": b.kind, "claimed": b.claimed, "sentence": _shown(sentence, sensitive), "spec_unsure": False})
        results.append(Result(id_, passages, listed))
    return results, got_runs.unread


def text(results: list[Result], notes: list[str]) -> str:
    """Counts first, then the passages grouped by file, then the open issues.
    Each sentence is shown printable, for terminal output (`doctor._printable`)."""
    blocks = []
    for r in results:
        d = r.as_dict()
        c = d["counts"]
        lines = [f"{d['decision']}: {presets_mod.plural(c['passages'], 'passage', 'passages')} in {presets_mod.plural(c['files'], 'file', 'files')}, "
                 f"{presets_mod.plural(c['issues'], 'open issue', 'open issues')}"]
        last = None
        for p in d["passages"]:
            if p["file"] != last:
                lines.append(f"  {p['file']}")
                last = p["file"]
            lines.append(f"    {p['line']}: {doctor_mod._printable(p['sentence'])}")
        if d["issues"]:
            lines.append("  open issues:")
            for i in d["issues"]:
                lines.append(f"    #{i['number']} ({i['kind']}{', claimed' if i['claimed'] else ''}): {doctor_mod._printable(i['sentence'])}")
        blocks.append("\n".join(lines))
    if notes:
        blocks.append("\n".join(notes))
    return "\n\n".join(blocks)

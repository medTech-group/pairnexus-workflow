"""A pull request of research notes (#509, spec #505): which pull requests are
one, the mark, and what changed in its own changes since a research record.

**Research notes** are the files under `docs/research/` (`FOLDER`). A pull
request whose files are all research notes, a rename's old path included, is
judged on its latest counted research record (`merge.py`'s `_research`), not
on the review panel's rounds.

**The mark** is ` **(unconfirmed)**` (`MARK`), with its leading space, at the
end of the line that holds a claim the look at a fix still found wrong. The
`study` skill writes it down ("The mark"); `tests/test_research_merge_check.py`
ties the two.

**What changed since** (`since`) compares the pull request's own changes at
the record's commit with its own changes at the head, both as GitHub's per-file
data gives them (`small.Change`: path, old path, status, blob SHA, patch).
Comparing own changes, not the files, means a merge of the base brings in
nothing of its own, and a change taken out again is no change. The answer is
`none` (the files read the same), `marks` (they differ only by marks added)
or `more` (anything else).

A mark adds no line, so a file changed only by marks has the same lines, in
the same places, as at the record's commit. For each file, both patches give
the lines they show, by their numbers: the file at the record's commit and at
the head (its new side, context lines included), and the file it was changed
from (its old side). A line that one patch shows and the other doesn't is, in
the other, a line the pull request left as it was: the old side's line in its
place, which one of the two patches shows. Every line either patch shows is
compared at its number: the same, or the record's line with the mark added
at its end. The two must add and remove the same number of lines, and where
both show a line of the file they were changed from, it must be the same
line. A file one side changes and the other doesn't (other than by marks, on
the head's side), a status or old path that differs, a mark taken off, a
patch that can't be read, a line it can't place, or a file with no patch
whose blob differs, is `more`. When in doubt it says `more`: a change it
can't tell from marks stops the merge, never passes it. So does a merge of
the base that moved lines in the pull request's own files, which leaves its
lines in other places.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .own_changes import _patch_lines
from .small import Change

FOLDER = "docs/research/"
MARK = " **(unconfirmed)**"
_HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def is_research(paths) -> bool:
    """Every path is a research note, a file under `docs/research/`, and
    there is at least one. A path with an empty, `.` or `..` part isn't one."""
    paths = list(paths)
    if not paths:
        return False
    for p in paths:
        if not isinstance(p, str) or not p.startswith(FOLDER):
            return False
        if any(part in ("", ".", "..") for part in p[len(FOLDER):].split("/")):
            return False
    return True


@dataclass(frozen=True)
class Since:
    kind: str  # none, marks or more
    marks: int = 0  # the marks added, for `marks`
    files: tuple[str, ...] = ()  # for `more`: the files that changed by more than marks


def _unmark(text: str) -> tuple[str, bool]:
    """The line without the mark at its end (before a `\\r`, if it has one),
    and whether it had it."""
    for end in ("", "\r"):
        if text.endswith(MARK + end):
            return text[: len(text) - len(MARK + end)] + end, True
    return text, False


class _Unreadable(Exception):
    pass


@dataclass
class _Sides:
    old: dict  # line number -> (text, ends with a newline), on the side it was changed from
    new: dict  # the same, on the side it was changed to
    hunks: list  # (first new line, last new line, lines added minus removed), in order

    def offset(self, n: int) -> int:
        """Lines added minus removed by the hunks above new line `n`."""
        return sum(d for _, last, d in self.hunks if last < n)


def _sides(patch: str | None) -> _Sides:
    """The lines a patch shows, on each side, by number. Raises _Unreadable."""
    sides = _Sides({}, {}, [])
    if not patch:
        return sides
    lines = _patch_lines(patch)
    if not lines or not lines[0].startswith("@@"):
        raise _Unreadable
    o = n = 0
    first = 0
    left = None  # the lines still due in the hunk: (old, new)
    last: list = []  # where the line before went, for "\ No newline at end of file"

    def close() -> None:
        if left is not None:
            if left != (0, 0):
                raise _Unreadable  # the header's counts and its lines don't agree
            sides.hunks.append((first, n - 1, n - first - (o - old_first)))

    old_first = 0
    for line in lines:
        if line.startswith("@@"):
            close()
            m = _HUNK.match(line)
            if not m:
                raise _Unreadable
            o_len = 1 if m.group(2) is None else int(m.group(2))
            n_len = 1 if m.group(4) is None else int(m.group(4))
            o = int(m.group(1)) + (o_len == 0)  # `-0,0`, or `-4,0` (lines added after line 4)
            n = int(m.group(3)) + (n_len == 0)
            old_first, first, left = o, n, (o_len, n_len)
            continue
        sign, text = line[:1], (line[1:], True)
        if sign == "\\":
            for side, k in last:
                side[k] = (side[k][0], False)
            continue
        if left is None:
            raise _Unreadable
        if sign in (" ", ""):
            sides.old[o], sides.new[n] = text, text
            last = [(sides.old, o), (sides.new, n)]
            o, n, left = o + 1, n + 1, (left[0] - 1, left[1] - 1)
        elif sign == "-":
            sides.old[o] = text
            last = [(sides.old, o)]
            o, left = o + 1, (left[0] - 1, left[1])
        elif sign == "+":
            sides.new[n] = text
            last = [(sides.new, n)]
            n, left = n + 1, (left[0], left[1] - 1)
        else:
            raise _Unreadable
        if min(left) < 0:
            raise _Unreadable
    close()
    return sides


def _file(before: Change | None, after: Change | None) -> int | None:
    """The marks added to one file since, or None when it changed by more."""
    if after is None:
        return None  # the pull request no longer changes it: more than marks
    if before is None and (after.status != "modified" or after.previous):
        return None  # only a file it didn't change before can be one it marks now
    if before is not None and (before.status, before.previous) != (after.status, after.previous):
        return None
    if before is not None and not before.patch and not after.patch:
        same = after.status == "removed" or (before.sha is not None and before.sha == after.sha)
        return 0 if same else None
    if (before is not None and not before.patch) or not after.patch:
        return None
    try:
        was, now = _sides(before.patch if before is not None else None), _sides(after.patch)
    except _Unreadable:
        return None
    if sum(d for *_, d in was.hunks) != sum(d for *_, d in now.hunks):
        return None
    if any(was.old[k] != now.old[k] for k in was.old.keys() & now.old.keys()):
        return None  # the file they were changed from differs where both show it
    base = {**was.old, **now.old}

    def line(sides: _Sides, k: int):
        if k in sides.new:
            return sides.new[k]
        return base.get(k - sides.offset(k))  # a line left as it was: the old side's

    marks = 0
    for k in sorted(was.new.keys() | now.new.keys()):
        w, h = line(was, k), line(now, k)
        if w is None or h is None:
            return None
        if w == h:
            continue
        bare, marked = _unmark(h[0])
        if not (marked and (bare, h[1]) == w and not _unmark(w[0])[1]):
            return None
        marks += 1
    return marks


def since(before: list[Change], after: list[Change]) -> Since:
    """What changed in the pull request's own changes from `before` (at the
    record's commit) to `after` (at the head)."""
    was = {c.path: c for c in before}
    now = {c.path: c for c in after}
    marks, more = 0, []
    for path in sorted(set(was) | set(now)):
        got = _file(was.get(path), now.get(path))
        if got is None:
            more.append(path)
        else:
            marks += got
    if more:
        return Since("more", files=tuple(more))
    return Since("marks", marks) if marks else Since("none")

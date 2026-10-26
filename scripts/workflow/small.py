"""The small review's threshold (#257, from #255): how much of a change counts,
and whether it is within `run.small_max_lines` and `run.small_max_files`.

One counting, for `workflow merge-check` (GitHub's list of the pull request's
files) and `workflow review-record --measure` (git's diff of a commit against
the merge base of `origin/<base>`), so the two can't disagree:
- only files outside tests count. A test file is a path matching one of the
  profile's suites' `files` globs, matched as path patterns: `*` and `?` stay
  within a folder, `**` crosses folders. That is stricter than the evidence's
  matching, where `*` crosses folders, so the threshold never gets looser. A
  rename is a test only when both its paths match. With no suite globs, every
  file counts;
- lines are each counted file's additions plus deletions (a binary file's are 0);
- a rename is one file.

"Within the threshold" means at most both numbers.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_LINES = 60  # the profile's run.small_max_lines
DEFAULT_MAX_FILES = 4  # the profile's run.small_max_files
MAX_LINES = range(1, 1001)  # what run.small_max_lines and --small-max-lines accept
MAX_FILES = range(1, 51)  # what run.small_max_files and --small-max-files accept


@dataclass(frozen=True)
class Change:
    """One changed file, as GitHub lists a pull request's files or git diffs them."""

    path: str
    previous: str | None = None  # a rename's old path
    status: str | None = None  # GitHub's: added, removed, modified, renamed, ...
    additions: int | None = None  # None where not given
    deletions: int | None = None
    sha: str | None = None  # the blob at the commit (GitHub's per-file `sha`)
    patch: str | None = None  # its hunks, as GitHub's per-file `patch` gives them


@dataclass(frozen=True)
class Measure:
    """A change's counted lines and files, and the threshold they're held to."""

    lines: int
    files: int
    max_lines: int
    max_files: int

    @property
    def within(self) -> bool:
        """At most both numbers."""
        return self.lines <= self.max_lines and self.files <= self.max_files

    def as_dict(self) -> dict:
        """As `merge-check --json` gives it, under `small`."""
        return {"lines": self.lines, "files": self.files, "max_lines": self.max_lines, "max_files": self.max_files, "within": self.within}

    def text(self) -> str:
        """The measurement in one line, as `review-record --measure` prints it."""
        where = "within" if self.within else "past"
        return (
            f"{_plural(self.lines, 'line')} in {_plural(self.files, 'file')} outside tests: {where} the small threshold "
            f"(at most {_plural(self.max_lines, 'line')} in at most {_plural(self.max_files, 'file')})"
        )


class NoCounts(ValueError):
    """A counted file without its additions and deletions."""


def _plural(n: int, one: str) -> str:
    return f"{n} {one if n == 1 else one + 's'}"


def suite_globs(profile) -> list[str]:
    """The profile's suites' `files` globs, each comma-separated list split."""
    if profile is None:
        return []
    return [g.strip() for s in profile.suites for g in (s.files or "").split(",") if g.strip()]


def _regex(glob: str) -> re.Pattern:
    """A glob as a path pattern: `*` and `?` within a folder, `**` across folders
    (`**/` also matches no folder at all), `[...]` a character other than `/`."""
    g = glob.strip().removeprefix("./")
    out, i, n = [], 0, len(g)
    while i < n:
        c = g[i]
        if g.startswith("**", i):
            j = i + 2
            while j < n and g[j] == "*":
                j += 1
            if j < n and g[j] == "/" and (i == 0 or g[i - 1] == "/"):
                out.append("(?:[^/]*/)*")
                j += 1
            else:
                out.append(".*")
            i = j
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        elif c == "[":
            start = i + 1 + (g[i + 1:i + 2] in ("!", "^"))
            end = g.find("]", start + 1)
            if end == -1:
                out.append(re.escape(c))
                i += 1
                continue
            body = g[start:end].replace("\\", "\\\\")
            out.append(f"(?!/)[{'^' if start > i + 1 else ''}{body}]")
            i = end + 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out))


def is_test(path: str, globs: list[str]) -> bool:
    """The path matches one of the globs, as path patterns (`_regex`)."""
    return any(_regex(g).fullmatch(path) for g in globs)


def counted(changes: list[Change], globs: list[str]) -> list[Change]:
    """The changes that count: those outside tests. A rename is a test only
    when both its paths are, so one whose old path isn't given (gh's and
    GraphQL's lists name only the new one) counts."""

    def test(c: Change) -> bool:
        if c.previous is None:
            return c.status not in ("renamed", "copied") and is_test(c.path, globs)
        return is_test(c.path, globs) and is_test(c.previous, globs)

    return [c for c in changes if not test(c)]


def measure(changes: list[Change], globs: list[str], max_lines: int, max_files: int) -> Measure:
    """The counted lines and files against the threshold. Raises NoCounts
    naming the first counted file without its additions and deletions."""
    mine = counted(changes, globs)
    for c in mine:
        if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (c.additions, c.deletions)):
            raise NoCounts(f"`{c.path}` has no additions and deletions as whole numbers")
    return Measure(sum(c.additions + c.deletions for c in mine), len(mine), max_lines, max_files)


# ---------- the local side: `review-record --measure` ----------


class CantMeasure(Exception):
    """The measurement can't be made, said in plain words."""


def _git(root: Path, *args: str, timeout: int = 60, binary: bool = False, env: dict | None = None) -> subprocess.CompletedProcess:
    """git in `root`; CantMeasure when it can't run or doesn't finish. A path
    that isn't UTF-8 is kept (surrogate escapes), never an error. With
    `binary`, the output is bytes, so a `\\r\\n` stays as it is. git never asks
    for credentials itself (a fetch fails instead; ssh's own prompt isn't
    stopped), and the environment's diff options and external diff are left
    out; `env` adds to it."""
    text = {} if binary else {"text": True, "encoding": "utf-8", "errors": "surrogateescape"}
    env = {**{k: v for k, v in os.environ.items() if k not in ("GIT_DIFF_OPTS", "GIT_EXTERNAL_DIFF")}, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, stdin=subprocess.DEVNULL, env=env,
                              timeout=timeout, **text)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CantMeasure(f"git {args[0]} failed: {e}") from None


def base_ref(root: Path, base: str, note, source: str = "--base") -> str:
    """`origin/<base>`, fetched first (as `review-panel` §1 does). If the fetch
    fails, the existing one, with a note (`note(text)`); with none, CantMeasure.
    `source` names where `base` came from, for a name git refuses."""
    ref = f"refs/remotes/origin/{base}"
    if base.startswith("-") or any(c in base for c in "*?[") or _git(root, "check-ref-format", f"refs/heads/{base}").returncode != 0:
        raise CantMeasure(f"`{base}` isn't a branch's name ({source})")
    try:
        got = _git(root, "fetch", "--quiet", "origin", f"+refs/heads/{base}:{ref}", timeout=120)
        lines = got.stderr.strip().splitlines()
        why = None if got.returncode == 0 else next((ln for ln in lines if ln.startswith("fatal:")), lines[-1] if lines else "git fetch failed")
    except CantMeasure as e:
        why = str(e)
    have = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode == 0
    if why is not None:
        if not have:
            raise CantMeasure(f"couldn't fetch origin/{base} ({why}), and there is no origin/{base} here to measure against")
        note(f"couldn't fetch origin/{base} ({why}): using the origin/{base} already here")
    return ref


def _numstat(text: str) -> list[Change]:
    """`git diff --numstat -z -M`'s output: `<added>\\t<deleted>\\t<path>\\0`, or
    for a rename `<added>\\t<deleted>\\t\\0<old>\\0<new>\\0`; a binary file's
    counts are `-`, read as 0."""
    tokens = text.split("\0")
    out, i = [], 0
    while i < len(tokens) and tokens[i]:
        added, deleted, path = tokens[i].split("\t", 2)
        lines = [0 if x == "-" else int(x) for x in (added, deleted)]
        if path:
            out.append(Change(path, None, None, *lines))
            i += 1
        else:
            out.append(Change(tokens[i + 2], tokens[i + 1], "renamed", *lines))
            i += 3
    return out


# `git diff` pinned to what GitHub shows, whatever the configuration or the
# environment says (`own_changes` names each pin). Both the counts here and the
# hashes (`own_changes.local_files`) diff with it, so they count the same diff.
DIFF = (
    "-c", "core.quotePath=false", "-c", "diff.suppressBlankEmpty=false", "-c", "core.bigFileThreshold=512m",
    "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--no-relative", "--diff-algorithm=myers",
    "--indent-heuristic", "-U3", "--inter-hunk-context=0", "-M", "-l1000", "--submodule=short",
    "--ignore-submodules=none", "--src-prefix=a/", "--dst-prefix=b/",
)


def pinned_diff(root: Path, base: str, commit: str, *args: str, binary: bool = False) -> subprocess.CompletedProcess:
    """`git diff <args> <base> <commit>` with `DIFF`'s pins, the attributes
    read from `commit`'s own `.gitattributes` (git 2.40 and later), never a
    global or the system's file, and the objects as committed, never their
    replacements (`git replace`), which GitHub doesn't read."""
    return _git(root, "-c", f"core.attributesFile={os.devnull}", *DIFF, *args, base, commit, binary=binary,
                env={"GIT_ATTR_SOURCE": commit, "GIT_ATTR_NOSYSTEM": "1", "GIT_NO_REPLACE_OBJECTS": "1"})


def local_changes(root: Path, commit: str, ref: str) -> list[Change]:
    """The changes from the merge base of `ref` to `commit`, by the same pinned
    diff as the hashes (`pinned_diff`), as GitHub counts."""
    if _git(root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        raise CantMeasure(f"{commit[:7]} isn't a commit in this repository")
    mb = _git(root, "merge-base", ref, commit)
    if mb.returncode != 0:
        raise CantMeasure(f"the commit {commit[:7]} has no merge base with {ref.removeprefix('refs/remotes/')}")
    diff = pinned_diff(root, mb.stdout.strip(), commit, "--numstat", "-z")
    if diff.returncode != 0:
        raise CantMeasure(f"git diff failed: {diff.stderr.strip()}")
    return _numstat(diff.stdout)

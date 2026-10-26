"""The hashes of a pull request's own changes (#258, from #255): `diff`, with
their context lines, and `lines`, of the changed lines alone. Each round and
pass record names both for the commit it reviewed, so `merge-check` (#261) can
tell a merge of the base that left the pull request's own changes as they were.

One definition (`of_files`), taking each file's path(s), status, blob SHA and
patch as GitHub's REST list of a pull request's files gives them, so
`workflow review-record` (from git, `local`) and `workflow merge-check` (from
GitHub's per-file data) hash alike. Each hash is the SHA-256 of the files, in
path order, each written as:

- `file\\0<path>\\0<old path, for a rename, else empty>\\0<status>\\0`, the
  status as GitHub names it (`added`, `removed`, `modified`, `renamed`, or
  `changed` for a type change or a change of mode alone);
- for `diff`, each hunk as a line `@@` (the separator: its `@@` line, numbers
  and function name, left out), then its lines, each ended by `\\n`: context,
  added and removed lines with their mark, and `\\ No newline at end of file`.
  A `\\r` at a line's end is kept;
- for `lines`, the added and removed lines alone, each with its mark and ended
  by `\\n`: no context, no separators;
- a file with no hunks (binary, empty, a rename or a mode change alone): the
  same for both, `blob\\0<blob SHA at the commit>\\0`, nothing for a removed file.

A file with additions or deletions but no patch (too large for GitHub to show),
or with no status, makes both hashes `unknown` (`CantHash`).

Locally, `git diff` is pinned to what GitHub shows, whatever the configuration
or the environment says: no external diff or textconv, the Myers algorithm with
git's default indent heuristic, 3 lines of context, no hunks joined across
unchanged lines, renames found (copies never) within git's default limit,
UTF-8 paths, empty context lines with their space, a submodule as its
`Subproject commit` lines and never left out, git's default size past which a
file is binary, and the attributes of the commit itself (git 2.40 and later;
older git reads the working tree's). Two things still count: a diff driver's
`binary` setting in the configuration, and `.git/info/attributes`. A type
change, which git shows as a removal and an addition of the same path, is one
`changed` file with both hunks.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from .small import CantMeasure, Change, _git, base_ref

UNKNOWN = "unknown"


@dataclass(frozen=True)
class Hashes:
    diff: str
    lines: str


UNKNOWN_HASHES = Hashes(UNKNOWN, UNKNOWN)


class CantHash(ValueError):
    """The hashes can't be computed, said in plain words."""


def _b(text: str) -> bytes:
    return text.encode("utf-8", "surrogateescape")


def _patch_lines(patch: str) -> list[str]:
    """The patch's lines, split at `\\n` alone, so a `\\r` stays; a final
    newline (git's, not GitHub's) ends the last line rather than adding one."""
    lines = patch.split("\n")
    return lines[:-1] if patch.endswith("\n") else lines


def _file(c: Change) -> tuple[bytes, bytes]:
    """One file's part of the `diff` and `lines` hashes. Raises CantHash."""
    if not c.status:
        raise CantHash(f"`{c.path}` has no status")
    head = b"".join(_b(x) + b"\0" for x in ("file", c.path, c.previous or "", c.status))
    if not c.patch:
        if c.additions or c.deletions:
            raise CantHash(f"`{c.path}` has changed lines but no patch")
        if c.status == "removed":
            return head, head
        if not c.sha:
            raise CantHash(f"`{c.path}` has no hunks and no blob SHA")
        blob = b"blob\0" + _b(c.sha) + b"\0"
        return head + blob, head + blob
    lines = _patch_lines(c.patch)
    if not lines[0].startswith("@@"):
        raise CantHash(f"`{c.path}`'s patch doesn't start with a hunk")
    diff, changed = [head], [head]
    for line in lines:
        if line.startswith("@@"):
            diff.append(b"@@\n")
            continue
        diff.append(_b(line) + b"\n")
        if line[:1] in ("+", "-"):
            changed.append(_b(line) + b"\n")
    return b"".join(diff), b"".join(changed)


def of_files(files: list[Change]) -> Hashes:
    """The two hashes of a change's files. Raises CantHash."""
    diff, lines = hashlib.sha256(), hashlib.sha256()
    for c in sorted(files, key=lambda c: (c.path, c.previous or "")):
        d, ln = _file(c)
        diff.update(d)
        lines.update(ln)
    return Hashes(diff.hexdigest(), lines.hexdigest())


# ---------- the local side: `review-record` ----------

_DIFF = (
    "-c", "core.quotePath=false", "-c", "diff.suppressBlankEmpty=false", "-c", "core.bigFileThreshold=512m",
    "diff", "--no-ext-diff", "--no-textconv", "--no-color", "--no-relative", "--diff-algorithm=myers",
    "--indent-heuristic", "-U3", "--inter-hunk-context=0", "-M", "-l1000", "--submodule=short",
    "--ignore-submodules=none", "--src-prefix=a/", "--dst-prefix=b/",
)
_STATUS = {"A": "added", "D": "removed", "M": "modified", "R": "renamed", "T": "changed"}
_SECTION = re.compile(rb"^diff --git ", re.M)


def _raw(out: bytes) -> list[tuple[Change, int]]:
    """`git diff --raw -z --no-abbrev`'s files, without their patches: path,
    old path for a rename, status, and blob SHA at the commit (none when
    removed), each with how many sections `git diff -p` shows it in: two for a
    type change, as a removal and an addition. A modification with the same
    blob on both sides is a change of mode alone: `changed`."""
    tokens = out.split(b"\0")
    files, i = [], 0
    while i < len(tokens) and tokens[i]:
        _old_mode, _new_mode, old_sha, new_sha, letter = tokens[i].decode("ascii").lstrip(":").split(" ")
        status = _STATUS.get(letter[:1])
        if status is None:
            raise CantHash(f"git reported a change of kind `{letter}`, which has no GitHub name")
        if status == "modified" and old_sha == new_sha:
            status = "changed"
        paths = [t.decode("utf-8", "surrogateescape") for t in tokens[i + 1:i + (3 if status == "renamed" else 2)]]
        i += 1 + len(paths)
        previous, path = paths if status == "renamed" else (None, paths[0])
        files.append((Change(path, previous, status, sha=None if status == "removed" else new_sha), 2 if letter == "T" else 1))
    return files


def _with_patches(patch: bytes, files: list[tuple[Change, int]]) -> list[Change]:
    """Each file with its hunks from `git diff -p`'s output, in `--raw`'s order,
    as GitHub's `patch` gives them: from the first `@@` line, header lines left
    out; None with no hunks. A type change's two sections have their hunks
    joined. A section whose `diff --git` line doesn't name its file's paths
    (a line where git quotes either path isn't compared), or counts that don't match, raise
    CantHash rather than pair hunks with the wrong file."""
    sections = _SECTION.split(patch)[1:]
    if len(sections) != sum(n for _, n in files):
        raise CantHash("git diff's list of files and its patch don't match")
    out = []
    for c, n in files:
        mine, sections = sections[:n], sections[n:]
        hunks = []
        for section in mine:
            names = section.split(b"\n", 1)[0].decode("utf-8", "surrogateescape")
            if '"' not in names and names != f"a/{c.previous or c.path} b/{c.path}":
                raise CantHash(f"git diff's patch doesn't match its list of files at `{c.path}`")
            at = section.find(b"\n@@ ")
            if at != -1:
                hunks.append(section[at + 1:].decode("utf-8", "surrogateescape"))
        out.append(replace(c, patch="".join(hunks) or None))
    return out


def local_files(root: Path, commit: str, ref: str) -> list[Change]:
    """The files changed from the merge base of `ref` to `commit`, each with its
    status, blob SHA and patch, as GitHub's REST list gives them. The
    attributes (a `-diff` or `binary` file) are read from `commit`'s own
    `.gitattributes`, never the working tree's or a global file. Raises
    CantMeasure or CantHash."""
    mb = _git(root, "merge-base", ref, commit)
    if mb.returncode != 0:
        shallow = _git(root, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
        raise CantMeasure(f"the commit {commit[:7]} has no merge base with {ref.removeprefix('refs/remotes/')}"
                          + (" in this shallow clone's history" if shallow else ""))
    base, attrs = mb.stdout.strip(), {"GIT_ATTR_SOURCE": commit}
    pinned = ("-c", f"core.attributesFile={os.devnull}", *_DIFF)
    raw = _git(root, *pinned, "--raw", "-z", "--no-abbrev", base, commit, binary=True, env=attrs)
    patch = _git(root, *pinned, "-p", base, commit, binary=True, env=attrs)
    for got in (raw, patch):
        if got.returncode != 0:
            raise CantMeasure(f"git diff failed: {got.stderr.decode('utf-8', 'replace').strip()}")
    return _with_patches(patch.stdout, _raw(raw.stdout))


def local(root: Path, commit: str, base: str, note, source: str) -> Hashes:
    """The hashes of `commit`'s own changes: from the merge base of
    `origin/<base>`, fetched first (`small.base_ref`, which notes a failed
    fetch), to `commit`. A commit not in the repository is found before the
    fetch. Raises CantMeasure or CantHash."""
    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        raise CantMeasure("there is no git repository here")
    if _git(root, "cat-file", "-e", f"{commit}^{{commit}}").returncode != 0:
        raise CantMeasure(f"{commit[:7]} isn't a commit in this repository")
    return of_files(local_files(root, commit, base_ref(root, base, note, source)))

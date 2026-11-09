"""The architecture documents in `docs/architecture/` (spec #611): the
overview (`README.md`), the pages beside it, and which pages a change reads.

A page is a Markdown file directly in `docs/architecture/` other than
`README.md`; files in subfolders and files that aren't `.md` are neither
pages nor noted. Its form, as the overview's `## Writing a page` section
gives it:

    Covers: <glob>              one or more, at the top, one glob on each
    Interface: <one line>
    ## Helpers                  list items written - `name`: what it's for
    ## Rules

`Covers:` globs match a path as `guard.protected_paths` does (the guard's
`matches`: case-insensitive, `*` crossing `/`). A page with no `Covers:` line
"covers nothing yet": `reads` gives it to every change until it has globs.

Reading changes nothing. `workflow index` (cli.py) prints what this returns.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .guard import matches

DIR = "docs/architecture"
OVERVIEW = f"{DIR}/README.md"

_COVERS = re.compile(r"Covers:(.*)")
_INTERFACE = re.compile(r"Interface:(.*)")
_HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"\s{0,3}(`{3,}|~{3,})")
_HELPER = re.compile(r"[-*+]\s+`([^`]+)`\s*:?\s*(.*)")
_ITEM = re.compile(r"[-*+]\s+(.*)")


class ReadError(Exception):
    """`reads` can't tell which files changed: its message says why."""


@dataclass
class Page:
    file: str  # relative to the project's root, e.g. docs/architecture/orders.md
    covers: list[str] = field(default_factory=list)
    interface: str | None = None
    helpers: list[tuple[str, str]] = field(default_factory=list)
    unreadable: str = ""  # why the file couldn't be read, when it couldn't


def parse(file: str, text: str) -> Page:
    """A page's `Covers:` globs, `Interface:` line and helpers, from its text."""
    page = Page(file)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿").split("\n")
    i = 0
    while i < len(lines):  # the Covers: lines at the top, blank lines between them allowed
        s = lines[i].strip()
        m = _COVERS.fullmatch(s)
        if s and not m:
            break
        if m and m.group(1).strip():
            page.covers.append(m.group(1).strip())
        i += 1
    fence = ""
    in_helpers = False
    for line in lines[i:]:
        f = _FENCE.match(line)
        if f:
            mark = f.group(1)
            if not fence:
                fence = mark
                continue
            if mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip()[len(mark):].strip():
                fence = ""
            continue
        if fence:
            continue
        h = _HEADING.match(line)
        if h:
            if len(h.group(1)) <= 2:
                in_helpers = len(h.group(1)) == 2 and h.group(2).casefold() == "helpers"
            continue
        if page.interface is None:
            m = _INTERFACE.fullmatch(line.strip())
            if m and m.group(1).strip() and not line[:1].isspace():
                page.interface = m.group(1).strip()
                continue
        if in_helpers and line[:1] not in (" ", "\t"):
            m = _HELPER.fullmatch(line.rstrip())
            if m:
                page.helpers.append((m.group(1).strip(), m.group(2).strip()))
                continue
            m = _ITEM.fullmatch(line.rstrip())
            if m and m.group(1).strip():
                page.helpers.append((m.group(1).strip(), ""))
    return page


def pages(root: Path) -> list[Page]:
    """Every page in the project's `docs/architecture/`, sorted by path. No
    folder: none. A page that can't be read is listed with no globs, so `reads`
    still gives it out, and `unreadable` says why."""
    d = root / DIR
    if not d.is_dir():
        return []
    out: list[Page] = []
    for p in d.iterdir():
        if p.suffix != ".md" or p.name == "README.md" or not p.is_file():
            continue
        rel = f"{DIR}/{p.name}"
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            out.append(Page(rel, unreadable=e.strerror or str(e)))
            continue
        out.append(parse(rel, text))
    return sorted(out, key=lambda pg: pg.file)


def overview(root: Path) -> str | None:
    """The overview's path when it exists."""
    return OVERVIEW if (root / OVERVIEW).is_file() else None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def changed_files(root: Path, base: str) -> list[str]:
    """The files changed since the branch's merge base with `base`, a moved
    file at its old path and its new one (`--no-renames`)."""
    p = _git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}")
    if p.returncode or not p.stdout.strip():
        raise ReadError(f"--base {base}: not a commit here; fetch it first (git fetch origin <branch>), or name another")
    p = _git(root, "merge-base", p.stdout.strip(), "HEAD")
    if p.returncode or not p.stdout.strip():
        why = p.stderr.strip()[:200]
        raise ReadError(
            f"no merge base between HEAD and {base}"
            + (f" ({why})" if why else "")
            + ": in a shallow clone, fetch more history (git fetch --unshallow)"
        )
    mb = p.stdout.strip()
    p = _git(root, "-c", "core.quotePath=false", "diff", "--no-renames", "--name-only", "-z", mb, "HEAD")
    if p.returncode:
        raise ReadError(f"git diff against the merge base with {base} failed: {p.stderr.strip()[:200]}")
    return [f for f in p.stdout.split("\0") if f]


def normal_path(root: Path, path: str) -> str:
    """A `--paths` entry as a path from the project's root: `./` and
    doubled slashes dropped, an absolute path inside the project made relative."""
    p = path
    q = Path(p)
    if q.is_absolute():
        try:
            p = q.resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            return p
    p = posixpath.normpath(p)
    return "" if p == "." else p


@dataclass
class Reads:
    documents: list[str]
    pages: list[tuple[str, list[str]]]  # (file, the globs that matched it; none for a page that covers nothing yet)
    unreadable: list[Page] = field(default_factory=list)  # pages that couldn't be read, given out as covering nothing yet


def reads(root: Path, base: str, paths: list[str]) -> Reads:
    """What a change reads: the overview when it exists, then, in one sorted
    list, every page whose `Covers:` matches a changed file or one of
    `paths`, and every page that covers nothing yet. No folder: nothing, and
    git isn't asked."""
    if not (root / DIR).is_dir():
        return Reads([], [])
    files = changed_files(root, base)
    files += [n for n in (normal_path(root, p) for p in paths) if n]
    files = sorted(set(files))
    got: list[tuple[str, list[str]]] = []
    every = pages(root)
    for pg in every:
        if not pg.covers:
            got.append((pg.file, []))
            continue
        hit = [g for g in pg.covers if any(matches(f, [g]) for f in files)]
        if hit:
            got.append((pg.file, hit))
    ov = overview(root)
    return Reads(([ov] if ov else []) + [f for f, _ in got], got, [pg for pg in every if pg.unreadable])

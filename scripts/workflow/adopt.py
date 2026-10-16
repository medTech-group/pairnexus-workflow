"""`workflow adopt`: make a copy of the starter the person's own project.

It rewrites only the template's names (#106, #40's user stories 7 and 8):
- the profile's `project.owner`, `project.name` and `project.repo`;
- CODEOWNERS: the profile's old owner becomes the new one, on every line;
- `wrangler.toml`'s top-level `name` and `package.json`'s `name`, both the
  project's name in lower case with dashes;
- the README's title, its first `# ` line.

Every file is edited line by line, never re-serialized, so comments, order,
formatting and line endings stay as they are. A missing file is skipped with a
note, never created. Every edit is worked out, and the results read back,
before anything is written, so a refusal leaves the working tree unchanged.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .profile import OWNER, PROFILE_PATH, ProfileError, parse

# Where GitHub looks for CODEOWNERS, in its order: it reads the first it finds.
CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
WRANGLER = "wrangler.toml"
PACKAGE = "package.json"
README = "README.md"
PROFILE = PROFILE_PATH.as_posix()
WORKER_NAME_MAX = 63  # a Worker's name is a DNS label; the package's is cut the same, so the two match

# GitHub's rules: a login of letters, digits and single inner hyphens; a
# repository name of letters, digits, `.`, `_` and `-`, but not `.` or `..`.
_LOGIN = r"[A-Za-z0-9](?:-?[A-Za-z0-9])*"
REPO = re.compile(rf"^{_LOGIN}/(?!\.\.?$)[A-Za-z0-9._-]+$")
_TABLE = re.compile(r"^\s*\[")
_PROJECT_TABLE = re.compile(r"^\s*\[\s*project\s*\]\s*(#.*)?$")
# `key = "value"` or `key = 'value'`, then anything (a comment) after it.
_TOML_KEY = r"^(?P<lead>\s*{key}\s*=\s*)(?P<value>\"(?:[^\"\\\n]|\\.)*\"|'[^'\n]*')(?P<rest>.*)$"
_FENCE = re.compile(r"^\s*(```|~~~)")
BOM = "\ufeff"


class AdoptError(ValueError):
    pass


@dataclass
class Result:
    changed: list[tuple[str, str]] = field(default_factory=list)  # (path, what changed)
    notes: list[str] = field(default_factory=list)
    writes: dict[str, bytes] = field(default_factory=dict)
    boms: set[str] = field(default_factory=set)  # files that start with a BOM, kept on write

    def read(self, root: Path, rel: str) -> str | None:
        """The file's text without any BOM, or None when it isn't there."""
        path = root / rel
        if not path.is_file():
            return None
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            raise AdoptError(f"{rel} isn't UTF-8 text") from e
        if text.startswith(BOM):
            self.boms.add(rel)
            text = text[1:]
        return text

    def record(self, rel: str, old: str, new: str, what: str) -> None:
        if new != old:
            self.changed.append((rel, what))
            self.writes[rel] = ((BOM if rel in self.boms else "") + new).encode("utf-8")

    def text(self) -> str:
        lines = [f"Changed {path}: {what}" for path, what in self.changed]
        lines += self.notes
        if not self.changed:
            lines.append("Already yours: nothing to change.")
        return "\n".join(lines)


def dashed(name: str) -> str:
    """The project's name in lower case with dashes: a Worker's and a package's name."""
    out = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return out[:WORKER_NAME_MAX].rstrip("-")


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _lines(text: str) -> list[tuple[str, str]]:
    """(the line, its ending), so an edit keeps the file's own line endings."""
    out = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        out.append((body, line[len(body):]))
    return out


def _join(lines: list[tuple[str, str]]) -> str:
    return "".join(body + end for body, end in lines)


def _set_key(lines, start: int, stop: int, key: str, value: str) -> bool:
    """Set `key`'s string value on its line between start and stop; False when
    no line there sets it. A line that sets it in another form is refused."""
    pat = re.compile(_TOML_KEY.format(key=re.escape(key)))
    bare = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for i in range(start, stop):
        body, end = lines[i]
        m = pat.match(body)
        if m:
            # A value already right, in either quoting, is left as it is.
            if tomllib.loads(f"v = {m.group('value')}")["v"] != value:
                lines[i] = (m.group("lead") + _toml_string(value) + m.group("rest"), end)
            return True
        if bare.match(body):
            raise AdoptError(f"line {i + 1} sets {key} in a form this can't rewrite line by line: {body.strip()}")
    return False


def _profile(text: str, owner: str, repo: str, name: str) -> str:
    lines = _lines(text)
    start = next((i + 1 for i, (body, _) in enumerate(lines) if _PROJECT_TABLE.match(body)), None)
    if start is None:
        raise AdoptError(f"{PROFILE} has no [project] table")
    stop = next((i for i in range(start, len(lines)) if _TABLE.match(lines[i][0])), len(lines))
    for key, value in (("name", name), ("repo", repo)):
        if not _set_key(lines, start, stop, key, value):
            raise AdoptError(f"{PROFILE}'s [project] has no `{key} = \"…\"` line")
    if not _set_key(lines, start, stop, "owner", owner):
        # An owner the profile left out goes in under repo, as the template has it.
        at = next(i for i in range(start, stop) if re.match(r"^\s*repo\s*=", lines[i][0]))
        ending = next((end for _, end in lines if end), "\n")
        if not lines[at][1]:
            lines[at] = (lines[at][0], ending)
        lines.insert(at + 1, (f"owner = {_toml_string(owner)}", ending if at + 1 < len(lines) else ""))
    return _join(lines)


def _codeowners(text: str, old: str, new: str) -> str:
    # `@old` as a whole login, any case (GitHub's logins are), but not `@old/team`
    # or an email address's domain (`ops@old.example`).
    pat = re.compile(rf"(?<!\S)@{re.escape(old)}(?![A-Za-z0-9/.-])", re.I)
    return pat.sub(f"@{new}", text)


def _wrangler(text: str, dashed_name: str) -> str | None:
    lines = _lines(text)
    stop = next((i for i, (body, _) in enumerate(lines) if _TABLE.match(body)), len(lines))
    return _join(lines) if _set_key(lines, 0, stop, "name", dashed_name) else None


def _package(text: str, dashed_name: str) -> str | None:
    """The top-level `"name"`'s string replaced in place, found by walking the
    JSON's text; the rest of the text is untouched."""
    depth, i, n = 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            # A key is a string followed by `:`; `"description": "name"` isn't one.
            if depth == 1 and text[i:j + 1] == '"name"' and re.compile(r"\s*:").match(text, j + 1):
                m = re.compile(r'\s*:\s*("(?:[^"\\]|\\.)*")').match(text, j + 1)
                if not m:
                    raise AdoptError(f"{PACKAGE}'s name isn't a string")
                return text[:m.start(1)] + json.dumps(dashed_name) + text[m.end(1):]
            i = j + 1
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        i += 1
    return None


def _readme(text: str, name: str) -> str | None:
    lines = _lines(text)
    fenced = commented = False
    for i, (body, end) in enumerate(lines):
        if commented:
            commented = "-->" not in body
        elif _FENCE.match(body):
            fenced = not fenced
        elif not fenced and "<!--" in body and "-->" not in body.split("<!--", 1)[1]:
            commented = True
        elif not fenced and body.startswith("# "):
            lines[i] = (f"# {name}", end)
            return _join(lines)
    return None


def plan(root: Path, owner: str, repo: str, name: str) -> Result:
    """What adopting would change, with each file's new bytes. Writes nothing."""
    owner, repo, name = (owner or "").strip().lstrip("@"), (repo or "").strip(), (name or "").strip()
    if not REPO.match(repo):
        raise AdoptError(f"--repo must be owner/name on GitHub, like acme/notes: got {repo!r}")
    if not OWNER.match(owner):
        raise AdoptError(f"--owner must be a GitHub login (letters, digits and hyphens), without the @: got {owner!r}")
    if not name or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise AdoptError("--name must be one line of text")
    dashed_name = dashed(name)
    if not dashed_name:
        raise AdoptError(f"--name {name!r} has no ASCII letters or digits, so it makes an empty Worker name")

    res = Result()
    text = res.read(root, PROFILE)
    if text is None:
        raise AdoptError(f"no profile at {PROFILE}: run this in a copy of the starter")
    try:
        old = tomllib.loads(text).get("project") or {}
    except tomllib.TOMLDecodeError as e:
        raise AdoptError(f"{PROFILE}: {e}") from e
    new_text = _profile(text, owner, repo, name)
    try:
        prof = parse(tomllib.loads(new_text), root)
    except (tomllib.TOMLDecodeError, ProfileError) as e:
        raise AdoptError(f"the rewritten profile wouldn't read: {e}") from e
    if (prof.name, prof.repo, prof.owner) != (name, repo, owner):
        raise AdoptError(f"{PROFILE}: the rewritten profile doesn't read back the new names")
    keys = [f"project.{k}" for k, v in (("owner", owner), ("name", name), ("repo", repo)) if (old.get(k) or "") != v]
    res.record(PROFILE, text, new_text, ", ".join(keys))

    old_owner = old.get("owner") or ""
    found = next((p for p in CODEOWNERS_PATHS if (root / p).is_file()), None)
    if found is None:
        res.notes.append("Skipped CODEOWNERS: not there")
    elif not old_owner:
        res.notes.append(f"Skipped {found}: the profile named no owner to replace")
    elif old_owner != owner:
        text = res.read(root, found)
        new_text = _codeowners(text, old_owner, owner)
        if new_text == text:
            res.notes.append(f"Left {found} as it is: it doesn't name @{old_owner}")
        res.record(found, text, new_text, f"@{old_owner} → @{owner}")

    text = res.read(root, WRANGLER)
    if text is None:
        res.notes.append(f"Skipped {WRANGLER}: not there")
    else:
        new_text = _wrangler(text, dashed_name)
        if new_text is None:
            res.notes.append(f"Skipped {WRANGLER}: no top-level name")
        else:
            try:
                ok = tomllib.loads(new_text).get("name") == dashed_name
            except tomllib.TOMLDecodeError as e:
                raise AdoptError(f"{WRANGLER}: {e}") from e
            if not ok:
                raise AdoptError(f"{WRANGLER}: the rewritten file doesn't read back the new name")
            res.record(WRANGLER, text, new_text, f"name = {dashed_name}")

    text = res.read(root, PACKAGE)
    if text is None:
        res.notes.append(f"Skipped {PACKAGE}: not there")
    else:
        try:
            json.loads(text)
        except ValueError as e:
            raise AdoptError(f"{PACKAGE} isn't valid JSON: {e}") from e
        new_text = _package(text, dashed_name)
        if new_text is None:
            res.notes.append(f"Skipped {PACKAGE}: no name")
        else:
            if json.loads(new_text).get("name") != dashed_name:
                raise AdoptError(f"{PACKAGE}: the rewritten file doesn't read back the new name")
            res.record(PACKAGE, text, new_text, f"name = {dashed_name}")

    text = res.read(root, README)
    if text is None:
        res.notes.append(f"Skipped {README}: not there")
    else:
        new_text = _readme(text, name)
        if new_text is None:
            res.notes.append(f"Skipped {README}: no `# ` title")
        else:
            res.record(README, text, new_text, f"title = {name}")
    return res


def _write(path: Path, data: bytes) -> None:
    """Through a temporary file beside it, so a failed write never leaves half a file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def adopt(root: Path, owner: str, repo: str, name: str) -> Result:
    """Write what `plan` worked out. The profile goes last: its old owner is what
    a second run reads CODEOWNERS by, so a write that fails before it can be
    run again. A failed write is an AdoptError."""
    res = plan(root, owner, repo, name)
    for rel in sorted(res.writes, key=lambda rel: rel == PROFILE):
        try:
            _write(root / rel, res.writes[rel])
        except OSError as e:
            raise AdoptError(f"couldn't write {rel}: {e.strerror or e}; run it again once that's fixed") from e
    return res

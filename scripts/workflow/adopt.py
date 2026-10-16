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

import json
import re
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

REPO = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
_TABLE = re.compile(r"^\s*\[")
_PROJECT_TABLE = re.compile(r"^\s*\[\s*project\s*\]\s*(#.*)?$")
# `key = "value"` or `key = 'value'`, then anything (a comment) after it.
_TOML_KEY = r"^(?P<lead>\s*{key}\s*=\s*)(?P<value>\"(?:[^\"\\\n]|\\.)*\"|'[^'\n]*')(?P<rest>.*)$"
_FENCE = re.compile(r"^\s*(```|~~~)")


class AdoptError(ValueError):
    pass


@dataclass
class Result:
    changed: list[tuple[str, str]] = field(default_factory=list)  # (path, what changed)
    notes: list[str] = field(default_factory=list)
    writes: dict[str, bytes] = field(default_factory=dict)

    def record(self, rel: str, old: str, new: str, what: str) -> None:
        if new != old:
            self.changed.append((rel, what))
            self.writes[rel] = new.encode("utf-8")

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
            lines[i] = (m.group("lead") + _toml_string(value) + m.group("rest"), end)
            return True
        if bare.match(body):
            raise AdoptError(f"line {i + 1} sets {key} in a form this can't rewrite line by line: {body.strip()}")
    return False


def _read(root: Path, rel: str) -> str | None:
    path = root / rel
    if not path.is_file():
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as e:
        raise AdoptError(f"{rel} isn't UTF-8 text") from e


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
        lines.insert(at + 1, (f"owner = {_toml_string(owner)}", lines[at][1] or "\n"))
    return _join(lines)


def _codeowners(text: str, old: str, new: str) -> str:
    # `@old` as a whole login, any case (GitHub's logins are), but not `@old/team`.
    pat = re.compile(rf"@{re.escape(old)}(?![A-Za-z0-9/-])", re.I)
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
    fenced = False
    for i, (body, end) in enumerate(lines):
        if _FENCE.match(body):
            fenced = not fenced
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
        raise AdoptError(f"--name {name!r} has no letters or digits, so it makes an empty Worker name")

    res = Result()
    text = _read(root, PROFILE)
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
    keys = [f"project.{k}" for k, v in (("owner", owner), ("name", name), ("repo", repo)) if old.get(k) != v]
    res.record(PROFILE, text, new_text, ", ".join(keys))

    old_owner = old.get("owner") or ""
    found = next((p for p in CODEOWNERS_PATHS if (root / p).is_file()), None)
    if found is None:
        res.notes.append("Skipped CODEOWNERS: not there")
    elif not old_owner:
        res.notes.append(f"Skipped {found}: the profile named no owner to replace")
    elif old_owner != owner:
        text = _read(root, found)
        res.record(found, text, _codeowners(text, old_owner, owner), f"@{old_owner} → @{owner}")

    text = _read(root, WRANGLER)
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

    text = _read(root, PACKAGE)
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

    text = _read(root, README)
    if text is None:
        res.notes.append(f"Skipped {README}: not there")
    else:
        new_text = _readme(text, name)
        if new_text is None:
            res.notes.append(f"Skipped {README}: no `# ` title")
        else:
            res.record(README, text, new_text, f"title = {name}")
    return res


def adopt(root: Path, owner: str, repo: str, name: str) -> Result:
    res = plan(root, owner, repo, name)
    for rel, data in res.writes.items():
        (root / rel).write_bytes(data)
    return res

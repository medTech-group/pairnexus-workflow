"""The pull request template set-up installs, behind `workflow pr-template`.

`build` works out the file to write and changes nothing:

- with no existing template, the kit's (`templates/github/pull_request_template.md`);
- with one, the kit's headings above it. Its content is kept whole beneath
  them, in its own line endings; a byte order mark moves to the top;
- when it already starts with `## In plain words` (after any blank lines and
  HTML comments), the file unchanged, with a note, so running it twice adds nothing;
- for a folder of templates (`.github/PULL_REQUEST_TEMPLATE/`), nothing to
  write. GitHub picks those through a query string, so the headings go in by hand.

The headings are `build-ticket`'s (#82); `tests/test_pr_template.py` reads both
files, so the two can't drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

TEMPLATE = "templates/github/pull_request_template.md"
TOP = "## In plain words"
BOM = b"\xef\xbb\xbf"

# Blank lines and HTML comments before the first line that shows.
_LEADING = re.compile(rb"(?:\s+|<!--.*?-->)*", re.S)


@dataclass
class Result:
    text: bytes | None  # the file to write; None for a folder: the headings go in by hand
    note: str


def _starts_with_headings(text: bytes) -> bool:
    text = text.removeprefix(BOM)
    first = text[_LEADING.match(text).end():].splitlines()[:1]
    return bool(first) and first[0].strip() == TOP.encode()


def build(kit_root: Path, existing: Path | None = None) -> Result:
    """The file to write, from the kit's template and the project's, if any.
    Raises OSError when either can't be read."""
    kit = (kit_root / TEMPLATE).read_bytes().replace(b"\r\n", b"\n")
    if existing is None:
        return Result(kit, "")
    if existing.is_dir():
        return Result(
            None,
            f"{existing} holds several templates, which GitHub picks through a query string: "
            f"left alone. Add the headings to the top of each by hand, from {TEMPLATE}.",
        )
    mine = existing.read_bytes()
    if _starts_with_headings(mine):
        return Result(mine, f"{existing} already starts with {TOP}: printed unchanged, nothing to add.")
    bom = BOM if mine.startswith(BOM) else b""
    mine = mine[len(bom):]
    newline = b"\r\n" if b"\r\n" in mine else b"\n"
    kit = kit.replace(b"\n", newline)
    return Result(bom + kit + newline + mine, f"The kit's headings, above {existing}'s content, kept whole.")

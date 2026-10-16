"""The pull request template set-up installs, behind `workflow pr-template`.

`build` works out the file to write and changes nothing:

- with no existing template: the kit's (`templates/github/pull_request_template.md`);
- with one: the kit's headings above it, its content kept whole beneath them,
  in its own line endings (a byte order mark moves to the top);
- when it already starts with `## In plain words`: it unchanged, with a note,
  so running it twice adds nothing;
- a folder of templates (`.github/PULL_REQUEST_TEMPLATE/`): nothing to write.
  GitHub picks those through a query string, so the headings go in by hand.

The headings are `build-ticket`'s (#82); `tests/test_pr_template.py` reads both
files, so the two can't drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEMPLATE = "templates/github/pull_request_template.md"
TOP = "## In plain words"

WRITE, FOLDER = "write", "folder"


@dataclass
class Result:
    kind: str  # WRITE (`text` is the file to write) or FOLDER (nothing to write)
    text: bytes
    note: str


def _starts_with_headings(text: bytes) -> bool:
    for line in text.removeprefix(b"\xef\xbb\xbf").splitlines():
        if line.strip():
            return line.strip() == TOP.encode()
    return False


def build(kit_root: Path, existing: Path | None = None) -> Result:
    """The file to write, from the kit's template and the project's, if any.
    Raises OSError when `existing` can't be read."""
    kit = (kit_root / TEMPLATE).read_bytes()
    if existing is None:
        return Result(WRITE, kit, "")
    if existing.is_dir():
        return Result(
            FOLDER,
            b"",
            f"{existing} holds several templates, which GitHub picks through a query string: "
            f"left alone. Add the headings to the top of each by hand, from {TEMPLATE}.",
        )
    mine = existing.read_bytes()
    if _starts_with_headings(mine):
        return Result(WRITE, mine, f"{existing} already starts with {TOP}: printed unchanged, nothing to add.")
    bom = b"\xef\xbb\xbf" if mine.startswith(b"\xef\xbb\xbf") else b""
    mine = mine[len(bom):]
    if b"\r\n" in mine:
        kit = kit.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        gap = b"\r\n"
    else:
        gap = b"\n"
    return Result(WRITE, bom + kit + gap + mine, f"The kit's headings, above {existing}'s content, kept whole.")

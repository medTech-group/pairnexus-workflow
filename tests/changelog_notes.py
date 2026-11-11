"""The changelog notes written since 0.1.10.

Build tickets add their notes under "## Unreleased", and a release moves them
under its own version heading, so a test that checks a ticket's note reads
everything from "## Unreleased" down to "## 0.1.10" instead of the
"## Unreleased" section alone.
"""

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]


def since_0110(text: str | None = None) -> str:
    text = (KIT / "CHANGELOG.md").read_text() if text is None else text
    start = text.index("## Unreleased")
    return text[start:text.index("\n## 0.1.10\n", start)]


def released(text: str | None = None) -> str:
    """The latest released version: the heading after "## Unreleased",
    without a leading "v"."""
    text = (KIT / "CHANGELOG.md").read_text() if text is None else text
    return text.split("\n## ")[2].split()[0].lstrip("v")


def entry(ticket: str, notes: str | None = None) -> str:
    """The note whose heading ends with `(<ticket>).`, from that heading down
    to the next note's (#717)."""
    notes = since_0110() if notes is None else notes
    start = notes.index(f"({ticket}).")
    return notes[start:notes.index("\n\n**", start)]

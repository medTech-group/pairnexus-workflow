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

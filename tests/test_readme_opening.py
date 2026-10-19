"""#98: the README opens on the reader's project, and PAIR's story moves to
"Where it came from" (#37's seam 1: the text, read by tests)."""

import re

from conftest import KIT

from changelog_notes import since_0110

START_HERE = "**[New to building? Start here](docs/quickstart.md)**"


def _text(path: str = "README.md") -> str:
    return (KIT / path).read_text(encoding="utf-8")


def _plain(text: str) -> str:
    """Words only: links reduced to their words, emphasis and code marks gone."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    return " ".join(re.sub(r"[*`]", "", text).split())


def _opening() -> str:
    """From the "Start here" line to the status note, both left out."""
    readme = _text()
    start = readme.index(START_HERE) + len(START_HERE)
    return readme[start:readme.index("> [!NOTE]", start)]


def _section(readme: str, heading: str) -> str:
    """A `## ` section's text, to the next `## ` heading."""
    assert f"\n{heading}\n" in readme, f"no {heading!r}"
    return readme.split(f"\n{heading}\n", 1)[1].split("\n## ", 1)[0]


def _opening_note(path: str) -> str:
    """The first paragraph after a doc's title, which must be a note."""
    note = _text(path).split("\n", 1)[1].lstrip("\n").split("\n\n", 1)[0]
    assert note.startswith("> [!NOTE]"), f"{path} doesn't open with a note"
    return _plain(note)


def _headings(readme: str) -> list[str]:
    readme = re.sub(r"^```.*?^```", "", readme, flags=re.M | re.S)
    return re.findall(r"^(#{1,6} .+?)[ \t]*$", readme, re.M)


def test_the_plain_lines_come_after_start_here_and_before_the_status_note():
    lines = [l for l in _text().splitlines() if l.strip()]
    assert lines[:2] == ["# pairnexus-workflow", START_HERE]
    # The first note is the status note, and the plain lines before it are
    # the whole opening: no heading or Contents between.
    note = lines.index("> [!NOTE]")
    assert note > 2
    assert lines[note + 1].startswith("> **Status: beta.**")
    assert "**Contents**" not in _opening()
    assert not re.search(r"^#", _opening(), re.M)
    opening = _plain(_opening())
    assert "You describe what you want" in opening
    assert "Claude plans it, builds it in small reviewed pieces and merges what passes" in opening
    assert "your own project" in opening


def test_the_opening_names_attended_work_before_unattended_runs():
    opening = _plain(_opening()).lower()
    attended = re.search(r"(?<!un)attended work", opening)
    assert attended and attended.start() < opening.index("unattended runs")
    assert "add later" in opening
    assert "conductor" in opening


def test_the_opening_keeps_the_guided_start_and_the_flow_in_short():
    opening = _plain(_opening())
    assert "choices to click" in opening
    assert "plan → spec → build tickets → one session per ticket → review panel → merge" in opening
    assert "](#using-it)" in _opening()


def test_the_conductor_paragraph_moved_to_unattended():
    readme = _text()
    assert "\n#### Unattended\n" in readme, "no '#### Unattended'"
    unattended = readme.split("\n#### Unattended\n", 1)[1].split("\n1. ", 1)[0]
    words = _plain(unattended)
    assert "a conductor asks the owner a few questions once (the run charter)" in words
    assert "builds every ready ticket in parallel sessions, merges what passes, releases if allowed, and reports" in words
    assert "Mid-run it waits on you only for your own tasks and for questions it asked you" in words


def test_where_it_came_from_is_before_licence_and_in_the_contents():
    readme = _text()
    headings = _headings(readme)
    assert headings.index("## Where it came from") == headings.index("## Licence") - 1
    contents = readme.split("**Contents**", 1)[1].split("\n## ", 1)[0]
    assert "[Where it came from](#where-it-came-from)" in contents
    words = _plain(_section(readme, "## Where it came from"))
    assert "9–12 Oct 2026" in words
    assert "about 50 tickets" in words
    assert "with fixes for what didn't" in words
    assert "PAIR's own project" in words


def test_no_other_part_of_the_readme_names_pair_drop():
    # #37's names test (#99) widens this to shipped files.
    readme = _text()
    elsewhere = readme.replace(_section(readme, "## Where it came from"), "")
    assert not re.search(r"pair[-_ ]?drop", elsewhere, re.I)
    assert re.search(r"pair-drop", _section(readme, "## Where it came from"))


def test_the_history_docs_open_with_their_background_notes():
    spike = _opening_note("docs/spike.md")
    assert "the kit's record of what has been verified" in spike
    assert "PAIR's own runs" in spike and "the demo repository's (the sandbox" in spike
    proposal = _opening_note("docs/proposal.md")
    assert "PAIR's original proposal" in proposal
    assert "Historical design record, kept as written." in proposal


def test_the_readme_still_says_who_maintains_it():
    assert "maintained by PAIR (MedTech LLC)" in _text()


def test_changelog_note_is_under_unreleased():
    notes = since_0110()
    assert "#98" in notes
    assert "Where it came from" in notes

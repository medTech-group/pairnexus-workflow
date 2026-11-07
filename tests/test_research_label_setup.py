"""#507: set-up creates the `research` label (spec #505, "The label" and
"Set-up"). Seam 2: the shipped text, read as a text contract, as
`tests/test_solo_setup.py` reads set-up's steps."""

import re

from conftest import KIT
from changelog_notes import since_0110

SETUP = KIT / "skills/setup-workflow/SKILL.md"


def _labels_step():
    """Set-up's step 9, "Labels", down to its next numbered step."""
    text = SETUP.read_text(encoding="utf-8")
    m = re.search(r"^\*\*9\. Labels,\*\*(.*?)(?=^\*\*10\. )", text, re.M | re.S)
    assert m, "no step 9, Labels, in setup-workflow"
    return m.group(1)


def _created_labels():
    """Every backticked name in the step's bullet list: the labels it creates."""
    bullets = [l for l in _labels_step().splitlines() if l.startswith("- ")]
    return [name for l in bullets for name in re.findall(r"`([^`]+)`", l)]


def test_setup_creates_the_research_label_with_the_others():
    labels = _created_labels()
    assert "research" in labels
    # Created as the others are: once, never twice, and the old ones kept.
    assert labels.count("research") == 1
    for kept in ("ready-for-agent", "spec", "workflow:in-progress", "wayfinder:research"):
        assert kept in labels, kept


def test_setup_says_what_the_research_label_is_for():
    step = _labels_step()
    # A reader can tell it from `wayfinder:research`, a map's research decision.
    assert "`research` marks a study's issue" in step
    assert "`wayfinder:research`" in step


def _note():
    """The ticket's changelog note: its paragraph and list, read from
    "## Unreleased" down, so it still counts once a release moves it."""
    notes = since_0110()
    start = notes.index("(#507")
    start = notes.rindex("\n\n", 0, start)
    end = notes.find("\n\n**", start + 2)
    return notes[start:end if end != -1 else len(notes)]


def test_the_changelog_notes_it_with_what_projects_updating_do():
    note = _note()
    assert "`research` label" in note
    updating = next(l for l in note.splitlines() if "**For projects updating" in l)
    # Create it, or leave it to a session, which creates it when it's missing.
    assert "create the `research` label" in updating
    assert "creates it when it's missing" in updating


def test_version_is_not_bumped():
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = log[log.index("\n## ", log.index("## Unreleased") + 1) + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released

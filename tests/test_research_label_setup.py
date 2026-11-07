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
    # The step's own sentence on it, outside the bullet list: what it marks,
    # and that it isn't `wayfinder:research`, a map's research decision.
    (line,) = [l for l in _labels_step().splitlines()
               if l.startswith("`research`") and not l.startswith("- ")]
    assert "study" in line
    assert "`wayfinder:research`" in line


def _note():
    """The ticket's changelog note, from its lead to the next note or heading,
    read from "## Unreleased" down so it still counts once a release moves it."""
    notes = since_0110()
    start = notes.index("**Set-up creates the `research` label** (#507")
    ends = [i for i in (notes.find("\n\n**", start + 2), notes.find("\n## ", start)) if i != -1]
    return notes[start:min(ends, default=len(notes))]


def test_the_changelog_notes_it_with_what_projects_updating_do():
    note = _note()
    updating = [l for l in note.splitlines() if l.startswith("- **For projects updating")]
    assert len(updating) == 1
    # Create it, or leave it to a session, which creates it when it's missing.
    assert "`research` label" in updating[0]
    assert "create" in updating[0] and "missing" in updating[0]


def test_version_is_not_bumped():
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = log[log.index("\n## ", log.index("## Unreleased") + 1) + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released

"""#73: the kit's glossary, `docs/glossary.md`, read as a file (#35's seam 1)."""

import re
from pathlib import Path

import pytest
from conftest import KIT

from workflow import vendor

GLOSSARY = KIT / "docs/glossary.md"

# The two parts and their words, each with the anchor the quickstart links to.
# GitHub makes the anchor from the heading, so a renamed heading breaks links.
PARTS = {
    "Building words": {
        "Repository": "repository",
        "Branch": "branch",
        "`main`": "main",
        "Commit": "commit",
        "Pull request (PR)": "pull-request-pr",
        "Checks (CI)": "checks-ci",
        "Merge": "merge",
        "Revert": "revert",
        "Preview link": "preview-link",
        "Cloud session": "cloud-session",
    },
    "The kit's words": {
        "Guided start": "guided-start",
        "Experience level": "experience-level",
        "Ticket": "ticket",
        "Spec": "spec",
        "Map": "map",
        "Review panel": "review-panel",
        "Solo mode": "solo-mode",
        "Protect `main`": "protect-main",
        "Unattended run": "unattended-run",
        "Conductor": "conductor",
        "Profile": "profile",
        "Check the set-up": "check-the-set-up",
    },
}

# How each word shows up in another entry's text. An entry that uses one links
# to its entry, so no glossary word is left unexplained.
MENTIONS = {
    "repository": r"\brepositor(?:y|ies)\b",
    "branch": r"\bbranch(?:es)?\b",
    "main": r"(?<!Protect `)(?<![-#])\bmain\b",
    "commit": r"\bcommits?\b",
    "pull-request-pr": r"\bpull requests?\b|\bPRs?\b",
    "checks-ci": r"\bchecks?\b(?! the set-up|-setup)|\bCI\b",
    "merge": r"\bmerg(?:e|es|ed|ing)\b",
    "revert": r"\brevert",
    "preview-link": r"\bpreview links?\b",
    "cloud-session": r"\bcloud sessions?\b",
    "guided-start": r"\bguided start\b",
    "experience-level": r"\bexperience levels?\b",
    "ticket": r"\btickets?\b",
    "spec": r"\bspecs?\b",
    "map": r"\bmaps?\b",
    "review-panel": r"\breview panels?\b",
    "solo-mode": r"\bsolo mode\b",
    "protect-main": r"Protect `main`",
    "unattended-run": r"\bunattended runs?\b",
    "conductor": r"\bconductors?\b",
    "profile": r"\bprofiles?\b",
    "check-the-set-up": r"\bcheck the set-up\b",
}

WHY = "**Why it matters to you:**"


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return s.replace(" ", "-")


def _text() -> str:
    return GLOSSARY.read_text(encoding="utf-8")


def _parts() -> dict[str, dict[str, str]]:
    """Part -> {entry heading -> entry body}, from the `##` and `###` headings."""
    parts: dict[str, dict[str, str]] = {}
    part = entry = None
    for line in _text().splitlines():
        if line.startswith("### "):
            entry = line[4:].strip()
            assert part is not None, f"entry {entry!r} comes before any part"
            parts[part][entry] = ""
        elif line.startswith("## "):
            part, entry = line[3:].strip(), None
            parts[part] = {}
        elif entry is not None:
            parts[part][entry] += line + "\n"
    return parts


def _entries() -> dict[str, str]:
    return {h: b for p in _parts().values() for h, b in p.items()}


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])[\"')*_`]*\s+(?=[A-Z*\"`(\[])", " ".join(text.split())) if s]


def test_the_glossary_has_the_two_parts_with_each_word_under_its_part():
    parts = _parts()
    assert list(parts) == list(PARTS)
    for part, words in PARTS.items():
        assert list(parts[part]) == list(words), part
    assert sum(len(w) for w in PARTS.values()) == 22


def test_each_heading_has_its_stable_anchor():
    for words in PARTS.values():
        for heading, anchor in words.items():
            assert _slug(heading) == anchor
    # GitHub's own anchors for the headings with punctuation, as it renders them.
    assert _slug("Pull request (PR)") == "pull-request-pr"
    assert _slug("Protect `main`") == "protect-main"
    assert _slug("Check the set-up") == "check-the-set-up"
    # GitHub numbers a repeated heading's anchor, so every heading must be distinct.
    headings = re.findall(r"^#{1,6} (.+)$", _text(), re.M)
    assert len({_slug(h) for h in headings}) == len(headings)


@pytest.mark.parametrize("heading", [h for w in PARTS.values() for h in w])
def test_each_entry_is_one_or_two_sentences_then_why_it_matters(heading):
    body = _entries()[heading]
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    assert len(paragraphs) == 2, f"{heading}: the explanation, then the why line"
    what, why = paragraphs
    assert not what.startswith(WHY)
    assert 1 <= len(_sentences(what)) <= 2, f"{heading}: one or two sentences"
    assert why.startswith(WHY), f"{heading}: ends with {WHY!r}"
    assert len(_sentences(why[len(WHY):])) == 1, f"{heading}: the why line is one sentence"


@pytest.mark.parametrize("heading", [h for w in PARTS.values() for h in w])
def test_each_glossary_word_an_entry_uses_links_to_its_entry(heading):
    anchors = {a for w in PARTS.values() for a in w.values()}
    own = _slug(heading)
    body = _entries()[heading]
    for anchor in anchors - {own}:
        if re.search(MENTIONS[anchor], body, re.I if anchor != "main" else 0):
            assert f"](#{anchor})" in body, f"{heading} uses {anchor!r} without linking to its entry"


def test_every_link_resolves_to_a_heading_or_file_that_exists():
    text = _text()
    headings = {_slug(m) for m in re.findall(r"^#{1,6} (.+)$", text, re.M)}
    links = re.findall(r"\]\(([^)\s]+)\)", text)
    assert links
    # A link this check can't read (a title, a reference) would go unchecked.
    assert text.count("](") == len(links) and "][" not in text
    for link in links:
        if link.startswith(("http://", "https://")):
            continue
        path, _, anchor = link.partition("#")
        if path:
            # A relative file link would break in a project's vendored copy.
            pytest.fail(f"{link}: link only to this page's own headings")
        assert anchor in headings, f"{link}: no such heading"


def test_the_glossary_says_it_is_the_kits_words_not_a_projects_glossary():
    intro = _text().split("\n## ", 1)[0]
    assert "kit's words" in intro
    assert "`GLOSSARY.md`" in intro


def test_the_glossary_stays_under_6000_characters():
    n = len(_text())
    assert n < 6000, (
        f"docs/glossary.md is {n} characters: keep it under 6,000. The context hook adds it whole "
        "at a session's first prompt, and Claude Code caps a hook's added context at 10,000 characters, "
        "so the glossary must leave room for the rest."
    )


def test_a_vendored_copy_carries_the_glossary():
    files = vendor.plan(KIT, None)
    assert files[".claude/workflow/docs/glossary.md"] == KIT / "docs/glossary.md"


def test_vendoring_writes_the_glossary_into_a_project(tmp_path):
    vendor.install(KIT, tmp_path, None, no_mattpocock=True)
    assert (tmp_path / ".claude/workflow/docs/glossary.md").read_text(encoding="utf-8") == _text()


def test_contributing_names_the_glossary_for_new_kit_terms():
    text = (KIT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    writing = text.split("**Writing.**", 1)[1].split("\n## ", 1)[0]
    assert "`docs/glossary.md`" in writing
    assert "same pull request" in writing
    assert "6,000 characters" in writing
    assert "`domain-modeling`" in writing


def test_the_glossary_names_no_project_of_ours():
    # #37's names test: the kit's docs name no project's own data or app.
    low = _text().lower()
    assert "patient" not in low
    assert "pair-drop" not in low


def test_the_guided_start_names_where_to_read_the_glossary():
    text = (KIT / "skills/start/SKILL.md").read_text(encoding="utf-8")
    assert "`.claude/workflow/docs/glossary.md` vendored, or `docs/glossary.md` beside `skills/` in the plugin" in text

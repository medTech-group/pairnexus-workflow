"""#122: the light review offered second by `next` and `start`, and the
merge-check skill's "Review it now" as a light review, read as the
kit-release tests read skills (#42's seam 4)."""

import re

from conftest import KIT

LIGHT = "**Build it with a light review**"


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _never_recommended(text: str) -> None:
    # No choice's label offers the light review with "(Recommended)".
    labels = re.findall(r"\*\*([^*]+)\*\*", text)
    assert not [l for l in labels if "light review" in l.lower() and "(Recommended)" in l]


def test_next_offers_the_light_review_second_after_the_full_build():
    pick = _section("skills/next/SKILL.md", "## 2. Pick one", "\n## 3.")
    full = pick.index("**Build it (Recommended)**")
    assert full < pick.index(LIGHT)
    assert "never recommended, and never chosen for them" in pick
    # Asked for by name, it isn't asked again; a ticket session asks nothing.
    assert '"build #12 with a light review"' in pick
    assert "In a ticket session, ask nothing" in pick
    # The shape lives in one place.
    assert '`review-panel` §6, "The light review"' in pick
    _never_recommended(_read("skills/next/SKILL.md"))


def test_start_offers_the_light_review_second_after_build_it_now():
    quick = _section("skills/start/SKILL.md", "**Quick ticket** (flow §2", "**Find the cause first:**")
    assert quick.index("**Build it now (Recommended)**") < quick.index(LIGHT)
    assert quick.index(LIGHT) < quick.index("**Leave it ready for later**")
    assert '`review-panel` §6, "The light review"' in quick
    assert "never the recommendation" in quick
    _never_recommended(_read("skills/start/SKILL.md"))


def test_start_says_the_light_review_is_never_first_or_recommended():
    text = _read("skills/start/SKILL.md")
    rule = _section("skills/start/SKILL.md", "## Choices\n", "\n## Where things are")
    assert f"{LIGHT} is always the second choice, after the full build" in rule
    assert "never first, never \"(Recommended)\", never chosen for them" in rule
    assert text.count(LIGHT) >= 2


def test_merge_check_review_it_now_is_the_light_review_in_attended_sessions():
    not_yet = _section("skills/merge-check/SKILL.md", '## 3. "Not yet"', "\n## 4.")
    row = next(line for line in not_yet.splitlines() if line.startswith('| `review` | **"Review it now"** |'))
    assert "light review" in row
    assert '`review-panel` §6, "The light review"' in row
    assert "posting its records" in row
    assert "until the light review comes" not in _read("skills/merge-check/SKILL.md")


def test_the_glossarys_review_panel_entry_mentions_the_light_review():
    text = _read("docs/glossary.md")
    entry = text.split("\n### Review panel\n", 1)[1].split("\n### ", 1)[0]
    assert "light review" in entry
    assert "one round without the walk-through" in entry and "small changes" in entry
    assert "never chosen for you" in entry
    assert "### light review" not in text.lower()
    assert len(text) < 6000


def test_the_readme_lists_the_light_review_among_the_build_choices():
    readme = _read("README.md")
    asks = next(line for line in readme.splitlines() if "**Leave it ready for later**" in line)
    assert asks.index("**Build it now**") < asks.index(LIGHT) < asks.index("**Leave it ready for later**")


def test_changelog_notes_under_unreleased_and_no_version_bump():
    log = _read("CHANGELOG.md")
    unreleased = log.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "#122" in unreleased and '"Build it with a light review"' in unreleased
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert _read("VERSION").strip() == released[0]

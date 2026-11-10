"""#614: the glossary's "Architecture" entry, the cap raised to 6,500 characters
in every place that asserts it, and `docs/profile.md`'s note that the
architecture overview is in `project.rules` (spec #611, seam 3: the kit's text)."""

import re

import pytest
from conftest import KIT

from test_glossary import _parts

# The eight places the glossary's cap is asserted (spec #611, "Docs").
CAP_PLACES = [
    "tests/test_glossary.py",
    "tests/test_light_review_offers.py",
    "tests/test_merge_check_skill.py",
    "tests/test_previews_doc.py",
    "tests/test_small_review_build.py",
    "tests/test_rule_docs.py",
    "CONTRIBUTING.md",
    "docs/agents/domain.md",
]


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _entry():
    return " ".join(_parts()["The kit's words"]["Architecture"].split())


def test_the_architecture_entry_is_among_the_kits_words():
    assert "Architecture" in _parts()["The kit's words"]


def test_the_entry_covers_the_overview_the_pages_and_the_pages_list():
    entry = _entry()
    assert "`docs/architecture/`" in entry
    assert "overview" in entry
    assert "page" in entry
    assert "pages list" in entry and "built by the kit" in entry


def test_the_entry_says_what_reaches_a_change():
    entry = _entry()
    assert "[review panel](#review-panel)" in entry
    assert "a change touches" in entry


def test_the_glossary_with_the_entry_stays_under_the_new_cap():
    assert len(_read("docs/glossary.md")) < 6500


@pytest.mark.parametrize("place", CAP_PLACES)
def test_each_place_asserting_the_cap_says_6500(place):
    text = _read(place)
    assert re.search(r"\b6,?500\b", text), f"{place}: the cap is 6,500"
    assert not re.search(r"\b6,?000\b", text), f"{place}: still names the old cap"


def test_contributing_and_the_domain_doc_give_the_cap_in_words():
    assert "under 6,500 characters" in _read("CONTRIBUTING.md")
    assert "under 6,500 characters" in _read("docs/agents/domain.md")


def test_the_profile_doc_says_the_overview_is_in_project_rules():
    rows = [l for l in _read("docs/profile.md").splitlines() if l.startswith("| `rules` |")]
    assert len(rows) == 1
    assert "`docs/architecture/README.md`" in rows[0]
    assert "architecture overview" in rows[0]


def _rules_row():
    rows = [l for l in _read("docs/profile.md").splitlines() if l.startswith("| `rules` |")]
    assert len(rows) == 1
    return rows[0]


def test_the_profile_doc_gives_the_plugin_path_to_the_overview():
    # The kit's update writes the overview only in a vendored project; a plugin
    # project gets it from `upgrade-setup`'s "Write the architecture overview".
    row = _rules_row()
    assert "vendored project" in row
    assert "plugin" in row
    assert '"Write the architecture overview"' in row
    assert "`upgrade-setup`" in row
    assert row.count("|") == 4, "the row stays three cells"

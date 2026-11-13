"""#823: one shared test for Unicode's Cc set (`issues.has_control`), so the
profile's `project.repo` check keeps no copy of its own. `escape_controls`
builds its own set from the same one, and still escapes the separators and the
bidirectional characters besides.
"""

import sys
import tomllib
import unicodedata

import pytest

from changelog_notes import KIT, entry
from workflow import issues as issues_mod
from workflow import profile as profile_mod


def test_has_control_is_exactly_unicode_s_cc_set():
    wrong = [cp for cp in range(sys.maxunicode + 1) if issues_mod.has_control(chr(cp)) != (unicodedata.category(chr(cp)) == "Cc")]
    assert wrong == []


@pytest.mark.parametrize("text", ["acme/demo", "", "acme/de‮mo", "acme/de`mo", " ", " é😀", "\ud800"])
def test_has_control_takes_text_without_one(text):
    assert issues_mod.has_control(text) is False


@pytest.mark.parametrize("text", ["\x00", "a\nb", "\x1b[31m", "x\x7f", "\x85", "end\x9f"])
def test_has_control_finds_one_anywhere(text):
    assert issues_mod.has_control(text) is True


def test_escape_controls_still_escapes_every_cc_character_and_its_extras():
    for cp in range(0x110000):
        c = chr(cp)
        extra = c in "  " or 0x202A <= cp <= 0x202E or 0x2066 <= cp <= 0x2069
        escaped = issues_mod.escape_controls(c) != c
        assert escaped == (unicodedata.category(c) == "Cc" or extra), hex(cp)


def test_the_profile_keeps_no_control_set_of_its_own():
    assert not hasattr(profile_mod, "CONTROL")


def test_the_profile_s_repo_check_calls_the_shared_helper(monkeypatch, tmp_path):
    """With the shared helper told to find nothing, a newline in project.repo
    gets past the profile: the check has no other copy behind it."""
    data = tomllib.loads('[project]\nname = "demo"\nrepo = "acme/de\\nmo"\n')
    with pytest.raises(profile_mod.ProfileError):
        profile_mod.parse(data, tmp_path)
    monkeypatch.setattr(issues_mod, "CC", issues_mod.re.compile(r"(?!)"))
    assert profile_mod.parse(data, tmp_path).repo == "acme/de\nmo"


def test_the_architecture_page_lists_the_helper_and_its_callers():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `has_control`: in `issues.py`"))
    assert "`profile.parse`" in line
    assert "`escape_controls`" in line


def test_the_changelog_note():
    note = entry("#823, found in the review of #821's pull request")
    assert "`issues.has_control`" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_control_set.py" in note

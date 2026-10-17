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
    # No choice that offers the light review carries "(Recommended)", in its label or after it.
    labels = re.findall(r"\*\*([^*]+)\*\*", text)
    assert not [l for l in labels if "light review" in l.lower() and "(Recommended)" in l]
    for line in text.splitlines():
        if LIGHT in line and not line.startswith("- **Building a ticket:**"):
            assert "(Recommended)" not in line, line


def test_next_offers_the_light_review_second_after_the_full_build():
    pick = _section("skills/next/SKILL.md", "## 2. Pick one", "\n## 3.")
    full = pick.index("**Build it now (Recommended)**")
    assert full < pick.index(LIGHT)
    assert "never recommended, and never chosen for them" in pick
    assert "or as a numbered list where it isn't available" in pick
    # Asked before the claim, so a dismissed question leaves nothing claimed.
    assert pick.index("ask how first") < pick.index("Then claim it")
    # Said how already, it isn't asked again; a ticket session asks nothing.
    said = pick.split("When they already said how", 1)[1].split("\n", 1)[0]
    for phrase in ('"build #12"', '"build #12 with a light review"', '"quick build #12"', "the `build` argument alone isn't saying how", "don't ask again"):
        assert phrase in said, phrase
    assert "(`WORKFLOW_ROLE` set to anything but `attended`, or a branch named like the profile's `run.ticket_branch`), ask nothing" in pick
    # The shape lives in one place.
    assert '`review-panel` §6, "The light review"' in pick
    _never_recommended(_read("skills/next/SKILL.md"))


def test_start_offers_the_light_review_second_after_build_it_now():
    quick = _section("skills/start/SKILL.md", "**Quick ticket** (flow §2", "**Find the cause first:**")
    assert quick.index("**Build it now (Recommended)**") < quick.index(LIGHT)
    assert quick.index(LIGHT) < quick.index("**Leave it ready for later**")
    assert '`review-panel` §6, "The light review"' in quick
    _never_recommended(_read("skills/start/SKILL.md"))


def test_start_says_the_light_review_is_never_first_or_recommended():
    rule = _section("skills/start/SKILL.md", "## Choices\n", "\n## Where things are")
    assert f"{LIGHT} is always the second choice, after the full build" in rule
    assert "never first, never \"(Recommended)\", never chosen for them" in rule


def test_merge_check_review_it_now_is_the_light_review_or_the_reasons_correctness_check():
    not_yet = _section("skills/merge-check/SKILL.md", '## 3. "Not yet"', "\n## 4.")
    row = next(line for line in not_yet.splitlines() if line.startswith('| `review` | **"Review it now"** |'))
    assert "light review" in row
    assert '(`no_review`), its light review (§6, "The light review"); say so in the choice' in row
    assert "posting its records" in row
    # Every reason the command sends here has its step.
    from workflow.merge import REASONS

    for rid, reason in REASONS.items():
        if reason.action == "review":
            assert f"(`{rid}`)" in row, rid
    # A round that wasn't clean keeps its shape: never lighter than the person chose.
    # Decided by the review records, never by the pull request's body, which its author writes.
    assert "a Correctness-only round (§6) when the round the reason counts (its `wording.developer.message` names it:" in row
    assert "a record from an account with write access, for a commit in the pull request; never another comment) names only `correctness` (a light review's later round), else the full panel (§5), never lighter than before" in row
    assert "body" not in row
    assert "`no_review` runs §6 in full; each other choice is one more round or pass, beyond §5's and §6's limits, since they chose it" in row
    assert "(`pass_not_clean`), fix the findings, then another Correctness pass (§5)" in row
    assert "(`review_stale`), a Correctness pass on the head (§5)" in row
    # On a fork, Claude can't push the fixes for findings.
    fork = not_yet.split("**A branch Claude can't push to**", 1)[1].split("\n\n", 1)[0]
    assert "only for `no_review`, as round 1 alone, and `review_stale`: findings are the author's to fix" in fork
    assert "until the light review comes" not in _read("skills/merge-check/SKILL.md")


def test_the_glossarys_review_panel_entry_mentions_the_light_review():
    text = _read("docs/glossary.md")
    entry = text.split("\n### Review panel\n", 1)[1].split("\n### ", 1)[0]
    assert "light review" in entry
    assert "one round with no walk-through of the screens" in entry and "small changes" in entry
    assert "never chosen for you" in entry
    assert "### light review" not in text.lower()
    assert len(text) < 6000


def test_the_readme_lists_the_light_review_among_the_build_choices():
    readme = _read("README.md")
    asks = next(line for line in readme.splitlines() if "**Leave it ready for later**" in line)
    assert asks.index("**Build it now**") < asks.index(LIGHT) < asks.index("**Leave it ready for later**")
    assert "(Recommended)" not in asks


def test_changelog_notes_under_unreleased_and_no_version_bump():
    log = _read("CHANGELOG.md")
    unreleased = log.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "#122" in unreleased and '"Build it with a light review"' in unreleased
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert _read("VERSION").strip() == released[0]

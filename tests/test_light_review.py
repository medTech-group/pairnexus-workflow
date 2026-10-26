"""#121: the light review, "build #12 with a light review", read as the
kit-release tests read skills (#42's seam 4)."""

import re

from conftest import KIT
from changelog_notes import since_0110


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _light() -> str:
    """review-panel's light review section, up to the next heading."""
    return _section("skills/review-panel/SKILL.md", ". The light review\n", "\n## ")


def _commands(text: str) -> list[str]:
    """The fenced commands in a section."""
    return [block.strip() for block in re.findall(r"```\n(.*?)```", text, re.S)]


def test_build_ticket_understands_the_request_phrases():
    text = _read("skills/build-ticket/SKILL.md")
    head = text.split("\n---\n", 1)[0]
    # The description names both, so the skill loads for either.
    assert '"build #N with a light review"' in head and '"quick build #N"' in head
    review = _section("skills/build-ticket/SKILL.md", "## 3. Review it", "\n## 4.")
    assert '"build #12 with a light review"' in review
    assert '"quick build #12"' in review
    # "Light review" is the name; "quick build" is only understood.
    assert '"Light review" is its name; "quick build" is only understood' in review
    # Not the guided start's quick ticket.
    assert "quick ticket" in review and "writes a build ticket on the spot" in review


def test_a_light_review_is_never_chosen_for_the_person():
    review = _section("skills/build-ticket/SKILL.md", "## 3. Review it", "\n## 4.")
    assert "A light review is never chosen for the person, in attended or unattended work" in review
    assert "never chosen for the person" in _light()
    # In a run the owner chose it, by the run's one review round.
    assert "the owner chose it, by giving the run one review round" in _light()


def test_the_pr_body_says_light_review_above_the_findings_table():
    step = _section("skills/build-ticket/SKILL.md", "## 4. Open the pull request", "\n## 5.")
    line = '"Light review: one round, no UI explorer"'
    assert line in step
    assert '"plus N Correctness rounds for the fixes"' in step
    assert step.index(line) < step.index("the findings table: round, reviewer")
    assert "above the findings table" in step
    # A run's one-round session writes it too, though nobody asked by name.
    assert "after a light review (asked for, or a briefing's review rounds at 1), the line" in step


def test_review_panel_describes_the_light_shape():
    light = _light()
    # Round 1: the full panel, without the explorer.
    assert "**Round 1** runs the full panel (Standards, Spec, Correctness, and the security review where it applies) but no UI explorer" in light
    # The fixes: Correctness-only rounds, at most 2 more.
    assert "Correctness-only rounds until one is clean, at most 2 more" in light
    assert "goes to the owner in the PR body" in light


def test_each_light_round_posts_a_round_record_without_the_explorer():
    light = _light()
    commands = _commands(light)
    assert len(commands) == 2
    first, fixes = commands
    assert first.startswith("WF review-record --kind round --round 1 --commit <sha> --reviewers standards,spec,correctness ")
    assert fixes.startswith("WF review-record --kind round --round <n> --commit <sha> --reviewers correctness ")
    # Records are rounds, never passes, and never name the explorer.
    for command in commands:
        assert "--kind pass" not in command and "explorer" not in command
    assert "section 4" in light


def test_a_correctness_only_round_says_when_it_isnt_clean():
    light = _light()
    fixes = light.split("Correctness-only rounds until one is clean", 1)[1]
    assert "`--not-clean` when it found something to fix" in fixes


def test_the_two_correctness_rounds_come_on_top_of_a_briefings_one_round():
    on_top = 'these rounds come on top of its "at most 1"'
    assert "The 2 is fixed, whatever `run.review_rounds` says" in _light()
    assert on_top in _light()
    review = _section("skills/build-ticket/SKILL.md", "## 3. Review it", "\n## 4.")
    assert 'on top of the briefing\'s "at most 1"' in review


def test_review_panel_uses_the_light_shape_when_the_briefings_review_rounds_are_1():
    light = _light()
    assert "when the briefing's review rounds are 1" in light
    assert "one full-panel round" in light
    # The stop rule points at it, so a run's single round isn't the plain one.
    stop = _section("skills/review-panel/SKILL.md", "## 5. When to stop", "\n## ")
    assert "light review (section 6)" in stop
    # Either one is enough: an asked-for light review, or a run's one round.
    assert "For a light review, or when the briefing's review rounds are 1" in stop


def test_it_never_changes_the_merge_rule():
    light = _light()
    assert "never changes the merge rule (flow §4)" in light


def test_flow_section_3_mentions_the_light_review():
    flow = _section("docs/flow.md", "## 3. Building", "\n## 4.")
    assert "light review" in flow
    assert '"build #12 with a light review"' in flow


def test_the_done_checklists_review_line():
    # The checklist gate reads these lines; #261 added the exception for a merge of the base to the review line.
    text = _read("skills/build-ticket/SKILL.md")
    assert "- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass, except a merge of the base that `merge-check` carried a review over" in text


def test_changelog_notes_under_unreleased_and_no_version_bump():
    log = _read("CHANGELOG.md")
    unreleased = since_0110(log)
    assert "#121" in unreleased and "light review" in unreleased.lower()
    # Updating projects with one review round are told what changes.
    assert "a profile with `run.review_rounds = 1` now gets the light shape" in unreleased
    # VERSION is still the newest released heading.
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert _read("VERSION").strip() == released[0]

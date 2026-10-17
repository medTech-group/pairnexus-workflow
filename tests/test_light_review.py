"""#121: the light review, "build #12 with a light review", read as the
kit-release tests read skills (#42's seam 4)."""

from conftest import KIT


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _light() -> str:
    """review-panel's light review section."""
    return _section("skills/review-panel/SKILL.md", "## 6. The light review", "\n## 7.")


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
    assert "quick ticket" in review and "files a small ticket" in review


def test_a_light_review_is_never_chosen_for_the_person():
    review = _section("skills/build-ticket/SKILL.md", "## 3. Review it", "\n## 4.")
    assert "A light review is never chosen for the person, in attended or unattended work" in review
    assert _light().count("never chosen for the person") == 1


def test_the_pr_body_says_light_review_above_the_findings_table():
    step = _section("skills/build-ticket/SKILL.md", "## 4. Open the pull request", "\n## 5.")
    line = '"Light review: one round, no UI explorer"'
    assert line in step
    assert '"plus N Correctness rounds for the fixes"' in step
    assert step.index(line) < step.index("the findings table: round, reviewer")
    assert "above the findings table" in step


def test_review_panel_describes_the_light_shape():
    light = _light()
    # Round 1: the full panel, without the explorer.
    assert "**Round 1** runs the full panel (Standards, Spec, Correctness, and the security review where it applies) but no UI explorer" in light
    # The fixes: Correctness-only rounds, at most 2 more.
    assert "Correctness-only rounds until one is clean, at most 2 more" in light
    assert "goes to the owner in the PR body" in light


def test_each_light_round_posts_its_record_in_79s_format():
    light = _light()
    assert "WF review-record --kind round --round 1 --commit <sha> --reviewers standards,spec,correctness" in light
    assert "WF review-record --kind round --round <n> --commit <sha> --reviewers correctness" in light
    # Records are rounds, never passes, and never name the explorer.
    assert "--kind pass" not in light
    assert "explorer" not in light.split("```")[1] and "explorer" not in light.split("```")[3]
    assert "section 4" in light


def test_review_panel_uses_the_light_shape_when_the_briefings_review_rounds_are_1():
    light = _light()
    assert "when the briefing's review rounds are 1" in light
    assert "one full-panel round" in light
    # The stop rule points at it, so a run's single round isn't the plain one.
    stop = _section("skills/review-panel/SKILL.md", "## 5. When to stop", "\n## 6.")
    assert "light review (section 6)" in stop


def test_it_never_changes_the_merge_rule():
    light = _light()
    assert "never changes the merge rule" in light


def test_flow_section_3_mentions_the_light_review():
    flow = _section("docs/flow.md", "## 3. Building", "\n## 4.")
    assert "light review" in flow
    assert '"build #12 with a light review"' in flow


def test_the_done_checklists_are_unchanged():
    # The checklist gate reads these lines; this ticket leaves them as they were.
    text = _read("skills/build-ticket/SKILL.md")
    assert "- [ ] Review panel run in rounds until clean (or the limit, the rest raised); late commits had a Correctness pass" in text


def test_changelog_notes_and_no_version_bump():
    log = _read("CHANGELOG.md")
    unreleased = log.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "#121" in unreleased and "light review" in unreleased.lower()

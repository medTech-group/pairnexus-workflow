"""#260: building with the small review, read as the kit-release tests read
skills (#255's seam 5): `Review: small` on tickets, `review-panel`'s small
review, `build-ticket`'s mark, measuring, fallback and PR line, the three build
choices in `start` and `next`, planning writing the mark, and the glossary."""

import re

from conftest import KIT
from changelog_notes import since_0110

MARK = "`Review: small`"
NOW = "**Build it now (Recommended)**"
LIGHT = "**Build it with a light review**"
FULL = "**Build it with the full panel**"
LATER = "**Leave it ready for later**"
# What a ticket marked small adds: no new surface.
NO_NEW_SURFACE = "no endpoint, table, screen or setting"


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _section(rel: str, start: str, end: str) -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _flat(text: str) -> str:
    return " ".join(text.split())


def _small() -> str:
    """review-panel's small review section, up to the next heading."""
    return _section("skills/review-panel/SKILL.md", ". The small review\n", "\n## ")


def _build_review() -> str:
    return _flat(_section("skills/build-ticket/SKILL.md", "## 3. Review it", "\n## 4."))


def _flow3() -> str:
    return _flat(_section("docs/flow.md", "## 3. Building", "\n## 4."))


def _commands(text: str) -> list[str]:
    return [block.strip() for block in re.findall(r"```\n(.*?)```", text, re.S)]


def _labels(text: str) -> list[str]:
    """The choices' bold labels, in order, from a list's `- **…**` lines."""
    return re.findall(r"^\s*(?:- |\d\. )(\*\*[^*]+\*\*)", text, re.M)


# ---------- review-panel: the small review ----------


def test_review_panel_has_the_small_review_beside_the_light_review():
    text = _read("skills/review-panel/SKILL.md")
    headings = re.findall(r"^## \d+\. (.+)$", text, re.M)
    assert headings.index("The small review") == headings.index("The light review") + 1
    # The planning review keeps its number, which flow §1, §2 and `start` cite.
    assert re.search(r"^## 8\. The planning review$", text, re.M)


def test_the_small_review_is_one_round_of_correctness_with_security_and_the_explorer_where_they_apply():
    small = _flat(_small())
    assert MARK in small
    assert "**One round.**" in small
    assert "Correctness" in small
    assert "the security review, where it applies" in small
    # The explorer only where it would run in any round.
    assert "the explorer, only where it would run in any round: the explorer isn't `none` and the change touches a screen, an endpoint or a command" in small
    assert "No Standards and no Spec reviewer" in small


def test_the_small_reviews_record_is_an_ordinary_round_record():
    small = _small()
    [command] = _commands(small)
    assert command.startswith("WF review-record --kind round --round 1 --commit <sha> --reviewers correctness ")
    assert "--kind pass" not in command
    flat = _flat(small)
    for names in ("`correctness,security`", "`correctness,explorer`", "`correctness,security,explorer`"):
        assert names in flat, names
    assert "`--not-clean` when it found something to fix" in flat
    assert "section 4" in flat


def test_fixes_after_the_small_review_are_correctness_passes_under_the_cap():
    small = _flat(_small())
    assert "Correctness passes (section 5), under the pass cap" in small
    assert "There are no further rounds" in small


def test_past_the_threshold_it_is_the_full_panel_or_the_light_review_in_a_one_round_run():
    small = _flat(_small())
    assert "past the small threshold" in small.lower()
    assert "the full panel (section 5)" in small
    assert "the light review (section 6) in a 1-round run" in small
    # After a small round, as merge-check's `after_small`: one full-panel round past the limit, then passes.
    assert "one full-panel round (the light review's round 1 in a 1-round run, without the explorer) with the next round number, allowed past the round limit" in small
    assert "if it isn't clean, fix its findings and run a Correctness pass, with no further round" in small
    assert "allowed past the round limit" in _build_review()
    assert "never changes the merge rule (flow §4)" in small


def test_review_panel_stop_rule_and_light_review_point_at_the_small_review():
    stop = _flat(_section("skills/review-panel/SKILL.md", "## 5. When to stop", "\n## "))
    assert "unless the ticket gets the small review (section 7)" in stop
    light = _flat(_section("skills/review-panel/SKILL.md", ". The light review\n", "\n## "))
    assert "except on a ticket that gets the small review (section 7)" in light


# ---------- build-ticket: the mark, measuring, the fallback, the PR line ----------


def test_build_ticket_reads_the_mark_and_when_the_small_review_is_allowed():
    review = _build_review()
    assert f"**The small review,** on a ticket marked {MARK}" in review
    assert "In attended work it is always allowed" in review
    assert "in a ticket session, when the briefing's \"Small review\" line says on" in review
    # The mark wins over a 1-round briefing; unmarked tickets keep the light review.
    assert "A ticket marked small gets it in a 1-round run too; unmarked tickets keep the light review" in review


def test_build_ticket_measures_before_reviewing_and_falls_back_past_the_threshold():
    review = _build_review()
    assert "Before reviewing, measure the diff: `WF review-record --measure --commit <sha>`" in review
    assert "with the briefing's `--small-max-lines` and `--small-max-files`" in review
    assert "Within the threshold, follow `review-panel`'s small review (section 7)" in review
    assert "Past it, run the full panel (the light review in a 1-round run), and the PR body says the diff overruled the mark" in review
    assert review.index("measure the diff") < review.index("Within the threshold")


def test_a_build_the_person_chose_wins_over_the_mark():
    review = _build_review()
    assert "\"build #12 with the full panel\"" in review
    assert "the person's choice wins over the mark" in review


def test_the_pr_body_says_small_review_above_the_findings_table():
    step = _flat(_section("skills/build-ticket/SKILL.md", "## 4. Open the pull request", "\n## 5."))
    line = '"Small review: one round, Correctness"'
    assert line in step
    assert '", security"' in step and '", explorer"' in step
    assert step.index(line) < step.index("the findings table: round, reviewer")
    assert "the diff overruled the mark" in step


def test_flow_section_3_names_the_small_review():
    flow = _flow3()
    assert "**The small review,**" in flow
    assert MARK in flow
    assert "one round of Correctness, with the security review and the explorer where they apply" in flow
    assert "Correctness passes under the pass cap" in flow
    assert "the full panel (the light review in a 1-round run)" in flow
    # The light review is now for unmarked tickets in a 1-round run.
    assert "used when the briefing's review rounds are 1 on a ticket that doesn't get the small review" in flow


def test_the_skills_and_the_flow_say_the_same_things():
    texts = {"review-panel": _flat(_small()), "build-ticket": _build_review(), "flow §3": _flow3()}
    for phrase in (MARK, "one round", "Correctness", "the security review", "the explorer", "pass cap", "the full panel", "light review", "1-round run"):
        for name, text in texts.items():
            assert phrase.lower() in text.lower(), f"{name} lacks {phrase!r}"


# ---------- start and next: the three build choices ----------


def _marked(rel: str, start: str, end: str) -> str:
    section = _section(rel, start, end)
    head = f"**On a ticket marked {MARK}**"
    assert head in section, f"{rel} names the marked ticket's choices"
    return section.split(head, 1)[1]


def test_next_offers_three_choices_on_a_ticket_marked_small():
    marked = _marked("skills/next/SKILL.md", "## 2. Pick one", "\n## 3.")
    block = marked.split("\n\n", 1)[0]
    assert _labels(block) == [NOW, LIGHT, FULL]
    now = next(l for l in block.splitlines() if NOW in l)
    assert "small review" in now
    assert '`review-panel` §7, "The small review"' in now


def test_next_keeps_the_unmarked_choices():
    pick = _section("skills/next/SKILL.md", "## 2. Pick one", "\n## 3.")
    unmarked = pick.split("**How to build it, in an attended session:**", 1)[1].split("\n\n", 1)[0]
    assert _labels(unmarked) == [NOW, LIGHT]
    assert f"- {NOW}: the full review panel;" in unmarked


def test_start_offers_three_choices_on_a_quick_ticket_marked_small():
    quick = _section("skills/start/SKILL.md", "**Quick ticket** (flow §2", "**Find the cause first:**")
    marked = quick.split(f"**On a ticket marked {MARK}**", 1)[1].split("\n\n", 1)[0]
    assert _labels(marked) == [NOW, LIGHT, FULL, LATER, "**Next item**"]
    now = next(l for l in marked.splitlines() if NOW in l)
    assert "small review" in now


def test_start_keeps_the_unmarked_choices():
    quick = _section("skills/start/SKILL.md", "**Quick ticket** (flow §2", "**Find the cause first:**")
    step3 = quick.split("3. Ask", 1)[1].split(f"**On a ticket marked {MARK}**", 1)[0]
    assert _labels(step3) == [NOW, LIGHT, LATER, "**Next item**"]


def test_starts_choice_rule_names_the_three_choices_on_a_ticket_marked_small():
    rule = _flat(_section("skills/start/SKILL.md", "## Choices\n", "\n## Where things are"))
    assert f"{LIGHT} is always the second choice, after the full build" in rule
    assert f"on a ticket marked {MARK}, after {NOW} (the small review) and before {FULL}" in rule


# ---------- planning writes the mark ----------

def test_flow_section_2_writes_the_mark():
    step = _flat(_section("docs/flow.md", "## 2. A spec", "\n## 3."))
    assert f"{MARK} if the change should stay within the small threshold and add {NO_NEW_SURFACE}" in step
    # The opt-out is in §3, keeping §2 short enough for the first flow context.
    assert "removing the line opts the ticket out" in _flow3()


def test_the_quick_ticket_and_the_sorting_write_the_mark():
    quick = _flat(_section("skills/start/SKILL.md", "**Quick ticket** (flow §2", "**Find the cause first:**"))
    assert MARK in quick and NO_NEW_SURFACE in quick and "small threshold" in quick
    sorting = _flat(_section("skills/start/SKILL.md", "## 5. Sorting new issues", "\n## "))
    ready = sorting.split("**Ready to build**", 1)[1].split(" - **", 1)[0]
    assert MARK in ready


def test_the_build_ticket_issue_template_names_the_mark_without_writing_it():
    template = _read("templates/github/ISSUE_TEMPLATE/build-ticket.md")
    # Opt-in: a ticket filed from the template isn't marked small unless the planner adds the line.
    assert not re.search(r"^\s*Review: small\s*$", template, re.M)
    note = _flat(template)
    assert f"Add a line reading {MARK} here only when" in note
    assert NO_NEW_SURFACE in note and "small threshold" in note
    assert "Without the line it gets the usual review" in note


# ---------- the glossary and the wording ----------


def test_the_glossarys_review_panel_names_both_reviews():
    text = _read("docs/glossary.md")
    entry = _flat(text.split("\n### Review panel\n", 1)[1].split("\n### ", 1)[0])
    assert "small review is one round of Correctness for a [ticket](#ticket) marked small" in entry
    assert "light review" in entry and "asked for" in entry and "no walk-through of the screens" in entry
    assert "never chosen for you" in entry
    assert "\n### Merge queue\n" in text
    assert len(text) < 6000


def test_no_text_calls_the_light_review_for_small_changes():
    for root in ("skills", "docs", "templates", "agents"):
        for path in (KIT / root).rglob("*.md"):
            text = _flat(path.read_text(encoding="utf-8"))
            for phrase in ("for small changes", "for a small change", "for a small, low-risk", "files a small ticket"):
                assert phrase not in text, f"{path.relative_to(KIT)} says {phrase!r}"
    readme = _flat(_read("README.md"))
    assert "for small changes" not in readme and "for a small change" not in readme


def test_changelog_notes_260_without_bumping_version():
    log = _read("CHANGELOG.md")
    assert "(#260" in since_0110(log)
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert _read("VERSION").strip() == released[0]

"""#383: the docs and the glossary for the rule for build reviewers (spec #412, "Docs").

The kit's text contracts: `docs/flow.md` §3 to §5, `docs/charter.md`,
`docs/profile.md` and `run-report` describe the rule for build reviewers, the
fixer, the safe fallback and the split, carry-on and attended work's 10
reviews, in plain words; the glossary gains "Bar" and rewords "Review panel",
within 6,000 characters."""

import re
from pathlib import Path

from changelog_notes import since_0110

KIT = Path(__file__).resolve().parents[1]


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text):
    return " ".join(text.split())


def _section(rel, start, end):
    text = _read(rel)
    assert start in text, f"{rel}: no {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _flow(n):
    return _section("docs/flow.md", f"\n## {n}. ", "\n## ")


def _step_3():
    """§3 step 3, its rule paragraph and bullets included, up to step 4."""
    return _flow(3).split("\n3. **Review**", 1)[1].split("\n4. **Pull request**", 1)[0]


def _rule_part(text):
    """The part of a text from "Under the rule for build reviewers" on."""
    assert "Under the rule for build reviewers" in text
    return text.split("Under the rule for build reviewers", 1)[1]


def _outside_code(text):
    return re.sub(r"`[^`]*`", "", text)


# ---------- docs/flow.md §3 ----------


def test_flow_3_says_when_the_rule_applies_and_that_it_never_asks_the_owner():
    rule = _flat(_rule_part(_step_3()))
    # The holds for the owner are the skills' (in a run, a security problem on the base branch; a fix the
    # guard refuses): pointed to, never listed, since which apply differs between runs and attended work.
    assert "(`review-panel` §10), a review never stops to ask the owner, except where `build-ticket` §3 or `review-panel` §3 hold the ticket for them." in rule
    assert "such as" not in rule.split("Build reviews follow it", 1)[0]
    assert 'Build reviews follow it in attended work always, and in a ticket session when its briefing has a "Findings:" line.' in rule
    assert "Where the rule differs from the above, it wins:" in rule


def test_flow_3_describes_what_blocks_the_fixer_and_the_bar():
    rule = _flat(_rule_part(_step_3()))
    assert "A finding blocks only with a reproducer, a concrete case that fails; without one it is a note." in rule
    # Filed ready; when it is built (a run, or an offer after the merge) is build-ticket's.
    assert "becomes a ticket to fix it, filed ready (`build-ticket` §3)." in rule
    assert "built next" not in rule
    assert "A review is clean when no finding blocks." in rule
    assert "A fresh `fixer` agent makes each review's fixes, round 1's included" in rule
    assert "each starting with a failing test from its finding" in rule
    assert "preferring a fix that removes a case over one that adds an exception" in rule
    assert "From the second review, reviewers check what changed since the last one and what it reaches." in rule
    assert "A ticket's `## Bar` (\"The bar\") says where the hunt stops: a gap it accepts is a note." in rule


def test_flow_3_describes_the_safe_fallback_and_the_split_in_plain_words():
    rule = _flat(_rule_part(_step_3()))
    assert "When the same part of the change blocks in two reviews in a row, `workflow merge-check` says what comes next (`mechanism_repeats`), and the session does it" in rule
    assert "and the session does it. The part takes the safe fallback the bar describes;" in rule
    assert "or it is split out to a ticket of its own, filed first with the acceptance criteria that need it, and the pull request merges without it;" in rule
    # merge-check's third answer, no `next`: neither is left.
    assert "or, when neither is left, its findings are fixed as usual and the review goes on." in rule
    assert "A part is split only once" in rule
    assert "a security problem the change adds is fixed, never split out" in rule
    # Plain words: "the part", never the records' "mechanism" outside code.
    assert "mechanism" not in _outside_code(rule)


def test_flow_3_says_no_pass_cap_carry_on_and_attended_works_10_reviews():
    rule = _flat(_rule_part(_step_3()))
    assert "**No pass cap.** Correctness passes follow the last round until one is clean." in rule
    assert "In a run, the end time is the only limit (§5)." in rule
    assert "the session prints one progress line at each review that isn't clean" in rule
    assert "after 10 such reviews in one session it stops: it leaves the hand-off on the pull request and labels the ticket `workflow:carry-on`" in rule
    assert "which `start` lists with a **Carry on** choice" in rule
    assert '"Carry on #<n>" in a fresh session goes on, with a fresh 10.' in rule


def test_flow_3_keeps_todays_rule_above_the_rules_paragraph():
    step = _flat(_step_3())
    today, rule = step.split("**Under the rule for build reviewers**", 1)
    # Today's rule stands for a run started on an older kit.
    assert "after which the owner decides" in today
    assert "Verify each finding, fix the real ones with a test, answer the rest with a reason." in today
    assert "after which the owner decides" not in rule


def test_flow_3_small_and_light_reviews_carry_on_until_clean_under_the_rule():
    small = _flat(_flow(3).split("**The small review,**", 1)[1].split("\n\n", 1)[0])
    assert "then Correctness passes under the pass cap (under the rule, until one is clean), with no further rounds" in small
    light = _flat(_flow(3).split("**A light review,**", 1)[1].split("\n\n", 1)[0])
    assert "under the rule, Correctness passes then follow until one is clean" in light


# ---------- docs/flow.md §4 and §5 ----------


def test_flow_4_keeps_the_pass_cap_to_todays_rule_and_never_waits_on_the_owner_for_a_part():
    item = _flat(_flow(4).split("\n4. **The reviews are clean**", 1)[1].split("\n\n", 1)[0])
    assert "Under today's rule, passes stop at the pass cap (§3 step 3): where one more would be needed past it, the pull request waits on the owner" in item
    assert "A review recorded under the rule for build reviewers (a `rule=2` record" in item
    assert "spec #412's rule" not in item
    assert "When the same part has a blocking finding in two such records in a row, `workflow merge-check` names what the session does before the next review (`mechanism_repeats`, §3 step 3), never the owner." in item


def test_flow_5_points_to_the_charter_for_the_end_time_and_the_joined_tickets():
    s5 = _flat(_flow(5))
    assert "the review reached its pass cap (with the open findings in the PR body; only under today's rule)" in s5
    # The security hold is build-ticket §3's, with its area-only reason: not restated beside "says exactly why".
    assert "security" not in s5.split("**under the rule for build reviewers**", 1)[0].split("if CI is still red", 1)[1]
    bullet = s5.split("**under the rule for build reviewers**", 1)[1].split(" - ", 1)[0]
    assert "there is no pass cap: the run's end time is handled as `charter.md`'s \"The end time\" says" in bullet
    assert "the tickets the session files join the run as its \"Tickets filed during the run join it\" says" in bullet
    # The charter holds the end time's conditions and exceptions: nothing restated here.
    for restated in ("never waits on the owner", "not set aside", "is carried on", "adopts it first"):
        assert restated not in bullet, restated


# ---------- docs/charter.md ----------


def _charter_rule():
    return _flat(_section("docs/charter.md", "- **How a ticket's review settles under the rule for build reviewers**", "\n- **A charter change"))


def test_charter_describes_the_rule_the_fixer_the_safe_fallback_and_the_split():
    text = _charter_rule()
    assert "(the charter's `rule: 2`; flow §3 step 3 has the whole rule)" in text
    assert "No question about a ticket's review is asked mid-run, except where `build-ticket` §3 or `review-panel` §3 hold the ticket for the owner, such as for a security or safety problem in code already on the base branch:" in text
    # Owner tasks never join: the joining section says which do.
    assert 'becomes a ticket to fix it ("Tickets filed during the run join it", below, says which join the run)' in text
    assert "a finding blocks only with a reproducer" in text
    assert "a fresh `fixer` agent makes each review's fixes, a failing test first" in text
    assert "`workflow merge-check` says what the session does: give it the safe fallback the ticket's bar describes, split it out to a ticket of its own (which joins the run, while the pull request merges without the part), or, when neither is left, fix it as usual" in text
    assert 'there is no pass cap: the end time is the only limit on a ticket\'s reviews ("The end time", below).' in text
    assert "never set aside" not in text
    assert "which parts kept blocking and what was done, and the report lists them (`run-report`)" in text
    assert "mechanism" not in _outside_code(text)


def test_charter_is_in_section_4_and_its_end_time_names_the_rule_in_plain_words():
    during = _section("docs/charter.md", "\n## 4. During the run\n", "\n## 5.")
    assert "- **How a ticket's review settles under the rule for build reviewers**" in during
    end = _flat(during.split("- **The end time**", 1)[1])
    # As the conductor decides it: by the latest counted record's rule.
    assert "A ticket whose review isn't clean then, under the rule for build reviewers (its latest counted review record is a `rule=2` one, or it has none yet in a run whose charter has `rule: 2`), is carried on (#380)" in end
    first = _flat(during.split("- **The ticket sessions' review comes from the charter.**", 1)[1].split("\n- ", 1)[0])
    assert 'and the pass cap (under `rule: 2`, the "Findings:" line in its place)' in first
    assert "under spec #412's rule" not in end


# ---------- docs/profile.md ----------


def test_profile_says_which_run_keys_apply_under_the_rule():
    text = _flat(_section("docs/profile.md", "**Build reviews under the rule for build reviewers**", "\n## "))
    assert "(spec #412, flow §3 step 3), which attended work always follows, and a run whose charter has `rule: 2`" in text
    assert "`review_rounds` still sets a review's rounds; `review_passes` doesn't apply, since there is no pass cap" in text
    assert "A fresh `fixer` agent makes each review's fixes. A part that keeps blocking takes the safe fallback its ticket's bar describes, is split out to a ticket of its own, or, with neither left, is fixed as usual." in text
    assert " may " not in text
    assert "`bar_areas` names the areas whose tickets need that bar" in text
    assert "Attended work stops after 10 reviews that weren't clean in one session, leaving a hand-off and the label `workflow:carry-on`" in text
    assert 'a run carries such a ticket on at its end time (`charter.md`, "The end time")' in text
    assert "The 10 is fixed: no profile key changes it." in text
    # It sits under `[run]`, after its table.
    run = _section("docs/profile.md", "\n## `[run]`\n", "\n## ")
    assert run.index("| `bar_areas` |") < run.index("**Build reviews under the rule for build reviewers**")


# ---------- run-report ----------


def test_run_report_lists_each_part_that_kept_blocking_and_what_was_done():
    text = _read("skills/run-report/SKILL.md")
    gather = _flat(text.split("- **Each merged PR's body:**", 1)[1].split("\n- ", 1)[0])
    assert "also its **Parts that kept blocking** and **Split out**" in gather
    assert "each part of the change that blocked in two reviews in a row, and what was done." in gather
    merged = _flat(text.split("2. **Merged.**", 1)[1].split("\n3. ", 1)[0])
    assert "A table of ticket, title, PR, review rounds, wall time" in merged
    assert "a part that kept blocking was settled without the owner, so the report is where they hear of it" in merged
    # Every part gathered is printed, the safe fallback, the split and neither left alike.
    assert "one plain line for each part named under **Parts that kept blocking**, with what was done and why" in merged
    assert "mechanism" not in _outside_code(gather + merged)


def test_run_report_still_lists_carried_on_tickets():
    text = _flat(_read("skills/run-report/SKILL.md"))
    assert "how many were carried on" in text
    assert "it needs nothing from the owner, since the next run adopts it first" in text


# ---------- the glossary ----------


def _entry(heading):
    return _section("docs/glossary.md", f"\n### {heading}\n", "\n### ")


def test_the_glossary_has_bar_after_review_panel_in_plain_words():
    text = _read("docs/glossary.md")
    assert text.index("\n### Review panel\n") < text.index("\n### Bar\n") < text.index("\n### Solo mode\n")
    bar = _flat(_entry("Bar"))
    assert "Where a [ticket](#ticket)'s review stops: what it must handle, its safe fallback when unsure, and the limits it accepts." in bar
    assert "**Why it matters to you:** reviews end at what you asked for." in bar
    assert "fail closed" not in bar.lower() and "mechanism" not in bar.lower()


def test_the_glossarys_review_panel_is_reworded_for_the_rule():
    entry = _flat(_entry("Review panel"))
    # True of planning reviews and of today's rule too, which can end unclean.
    assert "decision from one side, round after round." in entry
    assert "blocks" not in entry
    assert "each round leaving its record" not in entry


def test_the_glossary_stays_within_6000_characters_with_bar():
    text = _read("docs/glossary.md")
    assert "\n### Bar\n" in text and len(text) < 6000


# ---------- the changelog ----------


def test_the_changelog_notes_the_docs():
    notes = since_0110()
    head = "**The docs and the glossary describe the rule for build reviewers** (#383, part of spec #412)."
    assert head in notes
    note = _flat(notes.split(head, 1)[1].split("\n\n**", 1)[0])
    for name in ("`docs/flow.md` §3 to §5", "`docs/charter.md`", "`docs/profile.md`", "`run-report`", '"Bar"', '"Review panel"'):
        assert name in note, name
    assert "Tests: `tests/test_rule_docs.py`" in note

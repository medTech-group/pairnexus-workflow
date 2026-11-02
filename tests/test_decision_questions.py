"""#439: the flow's rules for decision questions (spec #436's "Which questions",
"What a recommendation carries", "Records" and "Not a planning review"; answers
1 to 4, 7, 17, 18 and 19 on #433), read as a text contract on `docs/flow.md` §1
and §2, as `tests/test_planning_review.py` reads the flow: each test reads one
part of the text, and checks what it requires rather than its exact wording, so
a later rewording that keeps the rule passes."""

import re

from changelog_notes import since_0110
from conftest import KIT
from workflow import context

FLOW = KIT / "docs/flow.md"


def _text() -> str:
    return FLOW.read_text(encoding="utf-8")


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _flow(n: int) -> str:
    """Section n of the flow, as written."""
    text = _text()
    assert f"\n## {n}. " in text
    return text.split(f"\n## {n}. ", 1)[1].split("\n## ", 1)[0]


def _block() -> str:
    """The flow's "Decision questions" section (§1 and §2's rules), as written."""
    text = _text()
    assert "\n## Decision questions\n" in text, "the flow has a `## Decision questions` section"
    return text.split("\n## Decision questions\n", 1)[1].split("\n## ", 1)[0]


def _intro() -> str:
    """The block's opening paragraph, before its rules, flattened."""
    return _flatten(_block().split("\n- **", 1)[0])


def _rule(name: str) -> str:
    """One `- **name` rule of the block, flattened."""
    raw = _block()
    assert f"\n- **{name}" in raw, f"the block has a `- **{name}` rule"
    return _flatten(raw.split(f"\n- **{name}", 1)[1].split("\n- **", 1)[0])


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _step(n: int, section: str) -> str:
    """Step n of a flow section's numbered list, flattened."""
    raw = _flow(int(section))
    assert f"\n{n}. " in raw
    return _flatten(raw.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0].split("\n**Checklist:**", 1)[0])


def _checklist(n: int) -> str:
    return _flatten(_flow(n).split("**Checklist:**", 1)[1])


# --- which questions --------------------------------------------------------


def test_decision_questions_are_the_ones_posted_as_the_owner_s_and_named():
    intro = _intro()
    assert "posted as the owner's" in intro
    # The five kinds, each by where it's asked.
    assert "map decision" in intro
    assert "interview" in intro and "`start`" in intro and "`next`" in intro
    assert "seams" in intro
    assert "**Fixes**" in intro and "draft" in intro and "§8" in intro
    assert "after publishing" in intro
    assert "**Edit the spec first**" in intro and "**Add to an existing issue**" in intro


def test_the_skills_point_here_and_matt_pocock_s_stay_unedited():
    intro = _intro()
    for skill in ("`start`", "`next`", "`review-panel` §8", "`conductor`"):
        assert skill in intro, skill
    # A map decision's rounds run through Matt Pocock's skills, which aren't edited.
    assert "`wayfinder`" in intro and "`grilling`" in intro


def test_quick_tickets_get_the_end_check_and_the_decided_for_you_list_without_posted_answers():
    s = _sentence(_intro(), "quick ticket")
    assert "end check" in s
    assert "Decided for you" in s
    assert "without" in s and "posted answers" in s


def test_the_run_charter_gets_the_evidence_rule_only():
    s = _sentence(_intro(), "charter")
    assert "evidence" in s
    assert "only" in s
    assert "no checks" in s


def test_routing_choices_get_neither():
    s = _sentence(_intro(), "Routing choices")
    assert "neither" in s
    assert "**Build it now**" in s or "**Write the spec**" in s


# --- what a recommendation carries ------------------------------------------


def test_each_recommendation_carries_its_evidence():
    r = _rule("Evidence")
    assert "what it rests on" in r
    assert "what it gives up" in r
    assert "what would make it wrong" in r
    # What it rests on is something checked.
    for kind in ("file", "issue", "ADR", "answer"):
        assert kind in r, kind


def test_no_recommended_without_a_basis():
    s = _sentence(_rule("Evidence"), "(Recommended)")
    assert "no basis" in s or "nothing" in s
    assert "no \"(Recommended)\"" in s
    assert "options" in s


def test_the_evidence_follows_the_sensitive_data_rule_before_anything_is_posted():
    s = _sentence(_rule("Evidence"), "profile.md")
    assert "sensitive" in s and "findings" in s
    assert "left out and marked as left out" in s
    assert "before anything is posted" in s


def test_yes_to_all_answers_only_questions_with_a_recommendation():
    r = _rule('"Yes to all"')
    assert "only" in r and "with a recommendation" in r
    assert "again on its own" in r


def test_a_finding_about_the_owner_s_own_words_is_asked_on_its_own():
    s = _sentence(_rule('"Yes to all"'), "own words")
    assert "finding" in s and "asked on its own" in s
    # What "own words" means: typed, not accepted.
    assert "typed" in s and "accepted" in s


# --- records ------------------------------------------------------------------


def test_each_round_is_posted_as_soon_as_it_s_answered_where_the_answers_go():
    r = _rule("Each round")
    assert "as soon as it's answered" in r
    assert "not only at" in r
    # Where §1 and §2 post the owner's answers.
    assert "decision ticket" in r and "item's issue" in r and "Destination item" in r
    # The breakdown check's rounds, and an edit after publishing, go on the spec's issue.
    assert "spec's issue" in r


def test_each_round_post_carries_tags_evidence_findings_and_the_reply_word_for_word():
    r = _rule("Each round")
    assert "**accepted recommendation**" in r and "**the owner's own words**" in r
    assert "evidence" in r
    assert "findings" in r
    assert "word for word" in r


def test_confirmed_replacements_are_plain_lines():
    s = _sentence(_rule("Each round"), "confirmed")
    assert "replace" in s and "narrow" in s
    assert "plain line" in s
    assert re.search(r"answer \d+ replaces \d+: confirmed", s)


def test_flow_1_asks_its_rounds_under_decision_questions():
    assert '"Decision questions"' in _step(2, "1")
    step3 = _step(3, "1")
    assert "**Post the owner's answers**" in step3
    # The existing rule stays: word for word, never a summary.
    assert "each question with the answer quoted word for word" in step3


def test_flow_2_files_an_item_s_issue_first_instead_of_the_spec_s_first_comment():
    s2 = _flatten(_flow(2))
    assert "spec's first comment" not in s2
    step1 = _step(1, "2")
    s = _sentence(step1, "files an item's issue")
    assert "before the spec is published" in s
    assert "as soon as it's answered" in step1
    assert "files an item's issue first" in _rule("Each round")


# --- the checks: fixes, what's left, and not the planning review -------------


def test_what_s_left_after_a_last_read_goes_into_further_notes_or_a_comment_on_the_spec():
    r = _rule("What's left")
    assert "last read" in r
    assert "Further Notes" in r and "before" in r and "published" in r
    assert "comment on the spec's issue" in r
    assert "never only" in r


def test_each_read_s_fixes_are_listed_where_the_owner_can_object():
    r = _rule("Each read's fixes")
    assert "where the owner can object" in r
    # With a round after the read, in its post; with none, a comment straight after it; a quick ticket, above Publish it.
    assert "round" in r and "post" in r
    assert "comment on the same issue" in r
    assert "**Publish it**" in r


def test_the_checks_are_named_and_are_not_the_planning_review():
    r = _rule("Not the planning review")
    for check in ("before each round", "end check", "re-read", "breakdown check"):
        assert check in r, check
    assert "`review-panel` §8's planning review" in r
    assert "reads once" in r and "re-reads once" in r
    assert "no spec record" in r


def test_the_checks_are_named_with_the_checker_that_runs_them():
    r = _rule("The checks")
    assert "`planning-checker`" in r and "read-only" in r
    for check in ("before it's asked", "end check", "re-read"):
        assert check in r, check
    # The end check reads all the answers before the spec or the ADR is written.
    s = _sentence(r, "(the end check)")
    assert "all the answers" in s and "before the spec" in s and "ADR" in s
    # Its round lets the owner leave a finding open; then one re-read, and it stops.
    assert "**Leave them open**" in s
    s = _sentence(r, "(the re-read)")
    assert "once" in s and "only what that round changed" in s and "stops" in s
    # Rounds after a draft exists get one re-read against all earlier answers.
    s = _sentence(r, "after a draft")
    assert "one re-read" in s and "all earlier answers" in s


def test_flow_2_names_the_breakdown_check_after_agree_these():
    step2 = _step(2, "2")
    agree = step2.index("**Agree these**")
    check = step2.index("breakdown check")
    publish = step2.index("publish build tickets")
    assert agree < check < publish
    assert '"Decision questions"' in step2


def test_the_breakdown_check_reads_the_tickets_against_the_spec():
    r = _rule("The breakdown check")
    assert "**Agree these**" in r and "`planning-checker`" in r and "against the spec" in r
    assert "exactly one build ticket, owner task or edit" in r
    assert "`## Blocked by`" in r and "`## Bar`" in r
    assert "Only wording is a **fix**" in r
    assert "before the tickets are published" in r
    # A finding left open keeps its tickets from being built.
    s = _sentence(r, "left open")
    assert "out of `ready-for-agent`" in s


def test_flow_2_s_interview_and_seams_are_decision_questions():
    step1 = _step(1, "2")
    assert "decision questions" in step1
    assert "seams" in _intro() and "interview" in _intro()


# --- checklists, the hook's context and the changelog -----------------------


def test_the_checklists_carry_the_checked_and_posted_rounds():
    for n in (1, 2):
        c = _checklist(n)
        assert "each round checked, posted as answered and tagged" in c, n
        # The existing lines stay.
        assert "answers posted verbatim; reviewed until clean, records posted" in c, n
    assert "tickets agreed, checked, published" in _checklist(2)


def test_a_planning_session_is_sent_to_the_rules_by_the_hook_s_first_flow_context():
    # The first flow context carries the flow's start as far as it fits: §1 and
    # §2 with their pointers, and the rules themselves or the line naming them.
    ctx = context.first_flow([FLOW])
    for heading in ("\n## 1. Planning", "\n## 2. A spec and its build tickets"):
        assert heading in ctx, heading
    assert "\n## Decision questions\n" in ctx or 'stops before "Decision questions"' in ctx


def test_the_changelog_has_a_note_and_version_is_untouched():
    notes = since_0110()
    assert "(#439, part of spec #436)" in notes
    unreleased = notes.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "#439" in unreleased

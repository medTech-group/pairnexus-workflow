"""#440: spec #436's interview rules in `start` and `next` (its "What a
recommendation carries" and "Records"; answers 1, 3, 4 and 18 on #433), read as
a text contract on the shipped skills, as `tests/test_decision_questions.py`
reads the flow: each test reads one part of the text (a rule, a step, a row) and
checks what it requires rather than its exact wording, so a later rewording that
keeps the rule passes."""

import re

from changelog_notes import since_0110
from conftest import KIT

START = KIT / "skills/start/SKILL.md"
NEXT = KIT / "skills/next/SKILL.md"


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _between(text: str, start: str, end: str) -> str:
    assert start in text, f"has {start!r}"
    return text.split(start, 1)[1].split(end, 1)[0]


def _start() -> str:
    return START.read_text(encoding="utf-8")


def _next() -> str:
    return NEXT.read_text(encoding="utf-8")


def _block(text: str) -> str:
    """A skill's `**Decision questions**` paragraph and its rules, as written."""
    assert "\n**Decision questions**" in text, "the skill has a **Decision questions** paragraph"
    return text.split("\n**Decision questions**", 1)[1].split("\n\n", 1)[0]


def _intro(text: str) -> str:
    """The paragraph's opening, before its rules, flattened."""
    return _flatten(_block(text).split("\n- **", 1)[0])


def _rule(text: str, name: str) -> str:
    """One `- **name` rule of the paragraph, flattened."""
    raw = _block(text)
    assert f"\n- **{name}" in raw, f"the paragraph has a `- **{name}` rule"
    return _flatten(raw.split(f"\n- **{name}", 1)[1].split("\n- **", 1)[0])


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _choices() -> str:
    return _between(_start(), "\n## Choices\n", "\n## ")


def _path(name: str) -> str:
    """`start`'s step 4 path, from its bold name to the next path, flattened."""
    step = _between(_start(), "## 4. Work through the plan", "\n## 5.")
    assert f"\n**{name}**" in step, f"step 4 has a **{name}** path"
    return _flatten(step.split(f"\n**{name}**", 1)[1].split("\n**", 1)[0])


def _spec_step(n: int) -> str:
    """Step n of `start`'s Spec path, flattened."""
    spec = _between(_start(), "\n**Spec** (flow §2)", "\n**Map**")
    assert f"\n{n}. " in spec, f"the Spec path has a step {n}"
    return _flatten(spec.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0])


# --- start: which questions -------------------------------------------------


def test_start_names_its_decision_questions_and_points_to_the_flow():
    intro = _intro(_choices())
    assert 'flow, "Decision questions"' in intro
    # Every kind `start` asks: the interview, the seams, a map decision's rounds,
    # and the two edits after publishing.
    for kind in ("interview", "seams", "map decision", "**Edit the spec first**", "**Add to an existing issue**"):
        assert kind in intro, kind
    # The questions a planning review's fixes raise once a draft exists, as the flow counts them.
    s = _sentence(intro, "**Fixes**")
    assert "draft" in s


def test_start_keeps_routing_choices_out_of_the_rules():
    s = _sentence(_intro(_choices()), "Routing choices")
    assert "**Write the spec**" in s or "**Build it now**" in s
    # Still one line of why, not the evidence.
    assert "one line" in s


def test_an_option_comes_first_only_when_one_is_recommended():
    options = _flatten(_between(_choices(), "- **Options:**", "\n- **"))
    # Not every question has a recommendation any more: one comes first only when there is one.
    s = _sentence(options, "(Recommended)")
    assert "recommend" in s.split('"(Recommended)"')[0].lower() and "first" in s
    assert re.search(r"\b(when|if)\b", s, re.I)
    assert "evidence" in options


# --- start: what a recommendation carries -----------------------------------


def test_start_s_recommendation_carries_its_evidence():
    r = _rule(_choices(), "Evidence")
    s = _sentence(r, "rests on")
    assert "what it rests on" in s and "what it gives up" in s and "what would make it wrong" in s
    for kind in ("file", "issue", "ADR", "answer"):
        assert kind in s, kind


def test_start_has_no_recommended_without_a_basis():
    s = _sentence(_rule(_choices(), "Evidence"), "(Recommended)")
    assert "no basis" in s
    assert "none is" in s or "no \"(Recommended)\"" in s
    assert "lay the options out" in s


def test_start_s_yes_to_all_answers_only_questions_with_a_recommendation():
    r = _rule(_choices(), '"Yes to all"')
    s = _sentence(r, "only")
    assert "with a recommendation" in s or "that have a recommendation" in s
    s = _sentence(r, "without one")
    assert "again" in s and "on its own" in s


def test_start_asks_a_finding_about_their_own_words_on_its_own():
    s = _sentence(_rule(_choices(), '"Yes to all"'), "own words")
    assert "finding" in s and "on its own" in s
    assert "typed" in s and "accepted" in s
    # Never in a round "yes to all" can answer.
    assert "never" in s


# --- start: each round posted -----------------------------------------------


def test_start_posts_each_round_as_soon_as_it_s_answered():
    r = _rule(_choices(), "Each round")
    s = _sentence(r, "as soon as it's answered")
    assert "not only at **Stop here**" in s


def test_start_posts_each_round_where_the_flow_says():
    r = _rule(_choices(), "Each round")
    s = _sentence(r, "comment on the map")
    assert "interview" in s and "seams" in s and "item's issue" in s
    # A map's Destination item: a comment on the map naming it.
    assert "naming it" in s
    # With nowhere to post, an item's issue is filed first.
    assert "file" in s and "first" in s
    # A map decision's on its ticket; an edit after publishing on the spec's issue.
    assert "decision ticket" in _sentence(r, "A map decision's rounds")
    assert "spec's issue" in _sentence(r, "edit after publishing")


def test_start_s_round_post_has_the_flow_s_form():
    r = _rule(_choices(), "Each round")
    s = _sentence(r, "word for word")
    assert "each question" in s
    # The recommendation itself, with its evidence.
    assert "recommendation with its evidence" in s
    assert "findings" in s
    s = _sentence(r, "tagged")
    assert "**accepted recommendation**" in s and "**the owner's own words**" in s


def test_start_posts_the_checks_findings_only_when_a_check_ran():
    s = _sentence(_rule(_choices(), "Each round"), "findings")
    assert "when a check ran" in s


def test_start_numbers_the_answers_across_issues_so_a_line_can_name_one():
    s = _sentence(_rule(_choices(), "Each round"), "numbers the answers")
    # On from the last answer for the same spec or decision, wherever it was posted,
    # so an edit's first round on the spec's issue doesn't start again at 1.
    assert "spec or decision" in s
    assert "item's issue" in s and "spec's issue" in s
    # Older posts without numbers still count.
    s = _sentence(_rule(_choices(), "Each round"), "without numbers")
    assert "order" in s


def test_a_replacement_line_names_the_issue_of_an_answer_posted_elsewhere():
    s = _sentence(_rule(_choices(), "Each round"), "confirmed")
    assert re.search(r"answer \d+ on #\d+", s)


def test_start_posts_confirmed_replacements_as_plain_lines():
    s = _sentence(_rule(_choices(), "Each round"), "confirmed")
    assert "replacement" in s and "narrowing" in s
    assert "plain line" in s
    assert re.search(r"answer \d+ replaces \d+: confirmed", s)


def test_a_reply_that_isn_t_an_accepted_recommendation_is_the_owner_s_own_words():
    s = _sentence(_rule(_choices(), "Each round"), "any reply but")
    assert "own words" in s
    # An option picked over the recommendation, or where none was recommended, as well as one typed.
    assert "picked" in s and "typed" in s and "accepted" in s


def test_a_question_a_fix_raises_is_posted_with_the_current_rounds():
    s = _sentence(_rule(_choices(), "Each round"), "fix raises")
    assert "current rounds" in s
    # Never on an issue closed when the spec was published: the spec's issue after it.
    assert "item's issue" in s and "before the spec is published" in s
    assert "spec's issue after" in s
    assert "decision ticket" in s


def test_start_s_round_posts_leave_out_sensitive_data():
    s = _sentence(_rule(_choices(), "Each round"), "profile.md")
    assert "sensitive" in s.lower() and "left out" in s


# --- start: the steps follow the rules ---------------------------------------


def test_the_interview_asks_under_the_rules_and_posts_each_round():
    interview = _spec_step(1)
    assert "Decision questions" in interview
    assert "evidence" in interview
    s = _sentence(interview, "as soon as it's answered")
    assert "each round" in s.lower() and "posted" in s and "tagged" in s


def test_stopping_mid_interview_finds_the_rounds_already_posted():
    stop = _spec_step(1).split("**Stop here**", 1)[1]
    assert "already posted" in stop
    # What it posts is in the same form as each round.
    assert "tagged" in stop and "same form" in stop
    # The next session carries on from them.
    assert "next session" in stop


def test_the_seams_carry_their_evidence_and_are_posted_as_answered():
    seams = _spec_step(2)
    s = _sentence(seams, "**These seams (Recommended)**")
    assert "evidence" in s
    post = seams.split("Post their answers, the seams among them", 1)[1].split(" - ", 1)[0]
    assert "as soon as it's answered" in post
    assert "tagged" in post
    # The interview's rounds are already there: only the seams' round is posted now.
    assert "already there" in post and "seams' round" in post


def test_a_question_a_planning_review_fix_raises_is_a_decision_question():
    s = _sentence(_spec_step(2), "A fix that would change what a decision means")
    assert "Decision questions" in s and "posted" in s
    # Where the interview's rounds are: a map's Destination item has no item's issue.
    assert "where the interview's rounds are" in s
    s = _sentence(_path("Map"), "a fix raises")
    assert "decision question" in s


def test_edit_the_spec_first_asks_under_the_same_rules():
    s = _sentence(_spec_step(2), "**Edit the spec first**")
    assert "Decision questions" in s
    assert "spec's issue" in s
    assert "posted" in s and "tagged" in s


def test_a_map_decision_s_rounds_are_posted_as_answered_and_tagged():
    m = _path("Map")
    s = _sentence(m, "**Each decision,**")
    assert "Decision questions" in s
    assert "as soon as it's answered" in s and "tagged" in s
    assert "evidence" in s


def test_add_to_an_existing_issue_on_a_spec_asks_under_the_same_rules():
    step = _flatten(_between(_start(), "\n**Add to an existing issue:**\n", "\n## "))
    s = _sentence(step, "the questions the change raises")
    assert "spec" in s and "Decision questions" in s
    assert "spec's issue" in s and "tagged" in s
    # Asked before the change is shown for the yes.
    assert step.index("the questions the change raises") < step.index("**Make this change (Recommended)**")


def test_a_spec_edited_mid_session_asks_under_the_same_rules():
    course = _flatten(_between(_start(), "\n## 7. Changing course", "\n## "))
    s = _sentence(course, "a spec you edit")
    assert "Decision questions" in s


# --- start: carrying on reads the posts --------------------------------------


def test_carry_on_reads_the_posted_rounds():
    row = _flatten(_between(_start(), "| A planned item |", "\n"))
    for part in ("rounds", "tag", "evidence", "findings", "confirmed"):
        assert part in row, part
    # A confirmed line says which answer stands.
    assert "answer stands" in row
    # Then the interview carries on, or the spec.
    assert "carry on the interview" in row


def test_carry_on_reads_an_open_spec_s_posted_rounds_before_its_tickets():
    row = _flatten(_between(_start(), "| An open spec with no tickets |", "\n"))
    assert "spec's issue" in row and "rounds" in row
    assert row.index("rounds") < row.index("`to-tickets`")


# --- next ---------------------------------------------------------------------


def test_next_points_to_the_flow_for_its_decision_questions():
    intro = _intro(_next())
    assert 'flow, "Decision questions"' in intro
    for kind in ("map decision", "interview", "seams"):
        assert kind in intro, kind
    assert "draft" in _sentence(intro, "**Fixes**")


def test_next_takes_the_rules_from_start_s_decision_questions():
    # One copy of the rules: a `next` session reads `start`'s, and is told where.
    s = _sentence(_intro(_next()), "Choices")
    assert "`start`" in s and "SKILL.md" in s and "read" in s
    assert '"Decision questions"' in s
    for part in ("evidence", '"yes to all"', "post", "leaves out", "tags", "confirmed replacement lines"):
        assert part in s, part
    # Not restated: no rules of its own on evidence or "yes to all".
    block = _block(_next())
    assert "\n- **Evidence" not in block and '\n- **"Yes to all"' not in block


def test_next_keeps_how_to_build_it_out_of_the_rules():
    s = _sentence(_intro(_next()), "Routing choices")
    assert "How to build it" in s


def test_next_posts_each_round_where_the_flow_says():
    r = _rule(_next(), "Each round")
    s = _sentence(r, "as soon as it's answered")
    for place in ("decision ticket", "item's issue", "map"):
        assert place in s, place
    s = _sentence(r, "fix raises")
    assert "current rounds" in s and "before the spec is published" in s
    # After publishing (a later planning review, such as the ADR pull request's): the spec's issue.
    assert "spec's issue after" in s
    # A map decision's on its decision ticket, whatever the spec's state.
    assert "decision ticket" in s


def test_next_reads_this_spec_s_or_decision_s_rounds_before_asking():
    r = _rule(_next(), "Before asking")
    s = _sentence(r, "already posted")
    assert "spec or decision" in s and "Destination item" in s
    s = _sentence(r, "carry on")
    assert "number on from the last answer" in s


def test_next_s_rules_are_part_of_picking_one():
    text = _flatten(_between(_next(), "\n## 2. Pick one", "\n## 3."))
    assert "**Decision questions**" in text


# --- changelog -----------------------------------------------------------------


def test_the_changelog_note_gives_both_skills_the_fixes_questions():
    note = since_0110().split("(#440, part of spec #436)", 1)[1].split("\n\n", 1)[0]
    assert note.index("planning review's fixes") < note.index("in `start`")


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#440, part of spec #436)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released

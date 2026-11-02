"""#442: questions after the draft, and what the planning review reads (spec
#436's "After the draft" and "Records"; answers 3, 6, 18 and 22 on #433), read
as a text contract on `review-panel` §8, as `tests/test_planning_review.py`
reads it: each test reads one part of the section (a bullet or a bold
paragraph), and checks what it requires rather than its exact wording, so a
later rewording that keeps the rule passes."""

import re

from changelog_notes import since_0110
from conftest import KIT

SKILL = KIT / "skills/review-panel/SKILL.md"


def _flatten(text: str) -> str:
    return " ".join(text.split())


def _planning_raw() -> str:
    """review-panel's planning review section, as written, up to the next heading."""
    text = SKILL.read_text(encoding="utf-8")
    assert ". The planning review\n" in text
    return text.split(". The planning review\n", 1)[1].split("\n## ", 1)[0]


def _planning() -> str:
    return _flatten(_planning_raw())


def _para(name: str) -> str:
    """The §8 paragraph that opens with `**name`, up to the next bold paragraph, flattened."""
    raw = _planning_raw()
    assert f"\n**{name}" in raw, f"§8 has a `**{name}` paragraph"
    return _flatten(raw.split(f"\n**{name}", 1)[1].split("\n\n**", 1)[0])


def _bullet(name: str) -> str:
    """The §8 bullet that opens with `name` (a reviewer's bold name, or an input's words), flattened."""
    raw = _planning_raw()
    assert f"\n- {name}" in raw, f"§8 has a `- {name}` bullet"
    return _flatten(raw.split(f"\n- {name}", 1)[1].split("\n- ", 1)[0].split("\n\n", 1)[0])


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = [s for s in re.split(r"(?<=[.;:])\s+(?=[A-Z*\"(])", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


# --- the questions Fixes sends are decision questions ----------------------


def test_the_questions_fixes_sends_are_decision_questions_under_the_flow():
    fixes = _para("Fixes:")
    # It still puts a fix that changes a decision to the owner first.
    assert "put to the owner as a question first" in fixes
    # Under the flow's own section, named as the other skills name it.
    assert "decision questions" in fixes
    assert '"Decision questions"' in fixes


def test_each_recommendation_carries_its_evidence_and_yes_to_all_answers_only_those_with_one():
    fixes = _para("Fixes:")
    s = _sentence(fixes, "carries its evidence")
    assert "recommendation" in s
    # What the evidence is, as the flow's **Evidence** rule has it.
    for words in ("rests on", "gives up", "would make it wrong"):
        assert words in s, words
    s = _sentence(fixes.lower(), '"yes to all"')
    assert "only" in s and "with a recommendation" in s


def test_each_round_is_posted_as_answered_tagged_word_for_word_before_the_next_round():
    fixes = _para("Fixes:")
    s = _sentence(fixes, "posted")
    assert "as soon as it's answered" in s
    assert "**accepted recommendation**" in s and "**the owner's own words**" in s
    assert "word for word" in s
    # The post carries the evidence and the checks' findings beside the reply.
    assert "evidence" in s and "findings" in s
    # The old untagged form is gone.
    assert "posted word for word like the others" not in _planning()


# --- one re-read, then stop ------------------------------------------------


def test_each_round_gets_one_re_read_by_the_planning_checker_against_all_earlier_answers_then_stops():
    reread = _para("The re-read:")
    assert "`planning-checker`" in reread
    s = _sentence(reread, "`planning-checker`")
    assert "once" in s
    assert "what that round" in s and "changed" in s
    assert "all the earlier answers" in s
    assert "stops" in s
    # Before the next planning round reads the draft again.
    assert "before the next round" in reread.lower() or "before the next planning round" in reread.lower()


def test_the_re_read_is_no_planning_round_and_nothing_reads_its_result_again():
    reread = _para("The re-read:")
    assert "isn't a planning round" in reread or "not a planning round" in reread
    assert "nothing reads its result again" in reread.lower()


def test_the_re_read_is_given_what_the_planning_checker_needs():
    s = _sentence(_para("The re-read:"), "/tmp/plan-check-")
    # The agent's own scratch directory, for a re-read.
    assert "/tmp/plan-check-<issue>-reread-<n>/" in s
    # #438: which read it follows, what that round changed, and the fixes made after it.
    assert "follows" in s
    assert "fixes listed in the round's post" in s


def test_the_re_read_makes_its_fixes_and_never_asks_its_ask_findings():
    reread = _para("The re-read:")
    assert "**fix** findings" in _sentence(reread, "**fix** findings")
    s = _sentence(reread, "**ask** findings are never asked")
    assert "never asked" in s


def test_what_the_re_read_leaves_goes_in_a_comment_and_where_the_flow_says():
    reread = _para("The re-read:")
    s = _sentence(reread, "in a comment")
    assert "fixes" in s and "what it leaves" in s
    assert "the issue the round was posted on" in s
    s = _sentence(reread, "What's left")
    # The flow's rule: Further Notes before publishing, a comment on the spec's issue after.
    assert "Further Notes" in s
    assert "comment on the spec's issue" in s


# --- an edit after publishing ----------------------------------------------


def test_an_edit_after_publishing_posts_its_rounds_tagged_on_the_spec_s_issue():
    edit = _para("An edit after publishing")
    assert "decision questions" in edit
    s = _sentence(edit, "on the spec's issue as soon as")
    assert "**accepted recommendation**" in s and "**the owner's own words**" in s
    assert "word for word" in s
    assert "evidence" in s and "findings" in s
    # The owner's request for the change is their own words.
    assert "request" in s
    assert "any sensitive data (`profile.md`) left out and marked as left out" in s
    # The old untagged form is gone.
    assert "First post the owner's words for the change" not in edit


def test_an_edit_after_publishing_gets_one_re_read_before_its_planning_round():
    edit = _para("An edit after publishing")
    s = _sentence(edit, "re-read")
    assert "all the earlier answers" in s
    assert "before the planning round" in s
    # Still another planning round and its record before any tickets.
    assert "another planning round, its own spec record, before any tickets are written from it" in edit


# --- what the planning review reads ----------------------------------------


def test_answers_md_is_each_round_s_post_with_its_tags_and_confirmed_lines():
    answers = _bullet("the owner's answers as posted, as `answers.md`")
    assert "never the session's summary" in answers
    assert "**accepted recommendation**" in answers and "**the owner's own words**" in answers
    assert "evidence" in answers and "findings" in answers
    # What settles which answer stands is in the file for the Spec reviewer to read.
    assert "confirmed replacement line" in answers
    assert "fixes" in answers


def test_the_spec_s_first_comment_is_gone_from_the_planning_review():
    p = _planning()
    assert "(once the spec is published, its first comment)" not in p
    assert "When the answers are the spec's first comment" not in p
    assert "first comment" not in p
    # The answers are posted before the spec, round by round (flow §2).
    records = _para("Records:")
    s = _sentence(records, "round by round")
    assert "flow §2" in s
    assert "item's issue" in s


def test_the_spec_reviewer_is_told_what_is_not_the_owner_s_words():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "aren't the owner's words")
    assert "evidence" in s and "findings" in s
    # Never reported as dropped, or as the owner's.
    assert "dropped" in s and "as the owner's" in s


def test_a_confirmed_line_or_an_unobjected_listed_fix_settles_which_answer_stands():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "settles")
    assert "confirmed replacement line" in s
    assert "fix listed in a post" in s and "no objection" in s


def test_the_later_words_stand_only_where_neither_settles_it():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "the later words stand")
    assert "neither" in s
    assert "plainly" in s
    # A doubt still goes to the owner.
    assert "where it's unclear whether they do, report it, so it goes to the owner (**Fixes**)" in brief


# --- the changelog ---------------------------------------------------------


def test_the_changelog_notes_it():
    notes = since_0110()
    head = "(#442, part of spec #436)."
    assert head in notes
    note = notes.split(head, 1)[1].split("\n\n**", 1)[0]
    for words in ("re-read", "`planning-checker`", "accepted recommendation", "confirmed", "first comment"):
        assert words in note, words
    assert "tests/test_planning_after_draft.py" in note

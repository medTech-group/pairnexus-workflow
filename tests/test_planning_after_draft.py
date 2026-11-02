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
    """The one sentence of `text` that names `word`, in any case. §8 also breaks a
    sentence at a colon before a capital, a bold name or a quote, so this splits
    there too (`tests/test_decision_questions.py`'s splits at `.` and `;` only)."""
    found = [s for s in re.split(r"(?<=[.;:])\s+(?=[A-Z*\"(])", text) if word.lower() in s.lower()]
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
    # The rules are the flow's: §8 names them, and points there for every rule.
    assert "every rule" in _sentence(fixes, '"Decision questions"')
    s = _sentence(fixes, '"yes to all"')
    assert "only" in s and "with a recommendation" in s


def test_each_question_round_is_posted_as_answered_tagged_word_for_word():
    fixes = _para("Fixes:")
    s = _sentence(fixes, "as soon as it's answered")
    assert "posted" in s
    assert "**accepted recommendation**" in s and "**the owner's own words**" in s
    assert "word for word" in s
    # The post carries the evidence and the checks' findings beside the reply.
    assert "evidence" in s and "findings" in s
    # The old untagged form is gone.
    assert "posted word for word like the others" not in _planning()


def test_a_confirmed_replacement_is_posted_as_a_plain_line():
    s = _sentence(_para("Fixes:"), "confirmed")
    assert "plain line" in s
    assert "replacement" in s and "narrowing" in s


def test_a_question_round_after_publishing_goes_on_the_spec_s_issue():
    s = _sentence(_para("Fixes:"), "once the spec is published")
    assert "on the spec's issue" in s
    # An edit's, and a spec session's pull request's, reviewed after the spec is out.
    assert "edit" in s and "pull request" in s


# --- one re-read, then stop ------------------------------------------------


def test_each_question_round_gets_one_re_read_by_the_planning_checker_against_all_earlier_answers_then_stops():
    reread = _para("The re-read:")
    assert "`planning-checker`" in reread
    s = _sentence(reread, "`planning-checker`")
    assert "after each question round" in s
    assert "once" in s and "changed" in s
    assert "all the earlier answers" in s
    assert "stops" in s
    # Before the next planning round reads the draft, and after the last, before publishing.
    s = _sentence(reread, "before the next planning round")
    assert "after the last" in s
    assert "before the spec is published" in s and "pull request offered" in s


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
    # A planning round's question round, or an edit's (`agents/planning-checker.md`'s two cases).
    assert "planning round" in s and "edit" in s
    assert "fixes listed" in s


def test_the_re_read_makes_its_fixes_and_never_asks_its_ask_findings():
    reread = _para("The re-read:")
    assert "Make" in _sentence(reread, "**fix** findings")
    s = _sentence(reread, "never asked")
    assert "**ask** findings" in s
    assert "left open" in s


def test_what_the_re_read_leaves_goes_in_a_comment_and_where_the_flow_says():
    reread = _para("The re-read:")
    s = _sentence(reread, "in a comment")
    assert "fixes" in s and "what it leaves" in s
    assert "question round" in s and "posted on" in s
    # No round follows a re-read, so its fixes have no round's post to go in (flow, **Each read's fixes**).
    assert "no round follows a re-read" in s
    s = _sentence(reread, "What's left")
    # The flow's rule: Further Notes before publishing, a comment on the spec's issue after.
    assert "Further Notes" in s
    assert "comment on the spec's issue" in s
    # A map decision's planning review leaves its open questions in the resolution comment.
    assert "map decision" in s and "resolution comment" in s


def test_a_question_round_after_the_last_planning_round_gets_its_re_read_in_the_published_spec():
    records = _para("Records:")
    s = _sentence(records, "re-read")
    assert "before the body is published" in s
    # An edit's body is saved, not published.
    assert "saved" in s
    assert "Further Notes" in s and "`spec.md`" in s


# --- an edit after publishing ----------------------------------------------


def test_an_edit_after_publishing_posts_its_rounds_tagged_on_the_spec_s_issue():
    edit = _para("An edit after publishing")
    assert "decision questions" in edit
    s = _sentence(edit, "on the spec's issue as soon as")
    # The tagged form is **Fixes**'s, pointed to rather than restated.
    assert "tagged form" in s and "**Fixes**" in s
    # The owner's request for the change is among the round, as their own words.
    assert "request" in s and "word for word" in s and "**the owner's own words**" in s
    # The old untagged form is gone.
    assert "First post the owner's words for the change" not in edit


def test_an_edit_after_publishing_gets_one_re_read_before_its_planning_round():
    edit = _para("An edit after publishing")
    s = _sentence(edit, "re-read")
    assert "before the planning round" in s
    # What it leaves goes in a comment on the spec's issue.
    assert "comment on the spec's issue" in s


# --- what the planning review reads ----------------------------------------


def test_answers_md_is_each_question_round_s_post_with_its_tags_and_confirmed_lines():
    answers = _bullet("the owner's answers as posted, as `answers.md`")
    s = _sentence(answers, "copied as posted")
    assert "never the session's summary" in s
    # The post's form is **Fixes**'s, tags, evidence and findings included.
    assert "question round" in s and "**Fixes**" in s
    assert "tags" in s and "evidence" in s and "findings" in s
    # What settles which answer stands is in the file for the Spec reviewer to read.
    assert "confirmed replacement line" in s
    # Every comment a check posts, its leftovers included, even one with no fixes.
    assert "every comment a check posts" in s and "what it leaves" in s


def test_the_spec_s_first_comment_is_gone_from_the_planning_review():
    p = _planning()
    # Neither "(once the spec is published, its first comment)" nor "When the answers are
    # the spec's first comment (flow §2), post them before the records" is left.
    assert "first comment" not in p
    # The answers are posted before the spec, round by round (flow §2).
    records = _para("Records:")
    s = _sentence(records, "before the records")
    assert "as soon as it was answered" in s
    assert "flow §2" in s and "item's issue first" in s


def test_the_spec_reviewer_is_told_what_is_not_the_owner_s_words():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "aren't the owner's words")
    assert "evidence" in s and "findings" in s
    # Never reported as dropped, or as the owner's.
    assert "dropped" in s and "as the owner's" in s


def test_a_confirmed_line_or_an_unobjected_listed_fix_settles_which_answer_stands():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "confirmed replacement line")
    assert "confirmed replacement line" in s
    assert "fix listed in a question round's post" in s and "no objection" in s
    # The re-read's fixes are listed in a comment, not a round's post: they settle too.
    assert "check's comment" in s


def test_a_conflict_a_check_left_open_is_never_settled_by_later_words():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "left open")
    # Neither a confirmed line nor a listed fix settles it, and nor do later words...
    assert "neither" in s and "later words" in s
    assert "report" in s
    # ...until the owner answers it.
    assert "until" in s and "owner" in s and "answer" in s


def test_the_spec_reviewer_never_holds_the_spec_to_the_breakdown_check_s_rounds():
    s = _sentence(_bullet("**Spec:**"), "breakdown check's rounds")
    assert "ticket" in s and "never" in s and "dropped" in s


def test_the_later_words_stand_only_where_neither_settles_it():
    brief = _bullet("**Spec:**")
    s = _sentence(brief, "the later words stand")
    assert "none of these" in s
    assert "plainly" in s


def test_a_review_after_publishing_reads_what_was_posted_on_the_spec_s_issue():
    answers = _bullet("the owner's answers as posted, as `answers.md`")
    s = _sentence(answers, "Once the spec is published")
    # An edit's review and a spec session's pull request's alike.
    assert "edit" in s and "pull request" in s
    assert "on the spec's issue" in s
    for words in ("question round", "confirmed line", "check's comment"):
        assert words in s, words
    # The breakdown check's rounds are among them, held to the tickets, not the spec's words.
    assert "breakdown check's" in s and "not the spec's words" in s


def test_an_edit_s_last_re_read_comes_before_any_tickets_are_written_from_it():
    s = _sentence(_para("The re-read:"), "before the next planning round")
    assert "edit after publishing" in s and "any tickets" in s
    assert "saved" in s
    assert "after the last planning round" in s


def test_the_re_read_s_comment_on_a_map_names_its_destination_item():
    s = _sentence(_para("The re-read:"), "in a comment")
    assert "map" in s and "Destination item" in s


def test_the_re_read_s_directory_counts_re_reads_on_its_issue():
    s = _sentence(_para("The re-read:"), "/tmp/plan-check-")
    assert "`<n>`" in s and "re-reads on that issue" in s


def test_the_re_read_reads_every_earlier_answer_wherever_it_was_posted():
    s = _sentence(_para("The re-read:"), "/tmp/plan-check-")
    assert "every answer `answers.md` takes" in s and "wherever it was posted" in s


# --- the changelog ---------------------------------------------------------


def test_the_changelog_notes_it():
    notes = since_0110()
    head = "(#442, part of spec #436)."
    assert head in notes
    note = notes.split(head, 1)[1].split("\n\n**", 1)[0]
    for words in ("re-read", "`planning-checker`", "accepted recommendation", "confirmed", "first comment"):
        assert words in note, words
    assert "tests/test_planning_after_draft.py" in note

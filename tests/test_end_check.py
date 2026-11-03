"""#441: spec #436's end check ("The end check, and re-reads"; answers 6, 14, 16
and 18 on #433), read as a text contract on the shipped `start` (its Spec and Map
steps, and "That's enough, write it up") and `next`, as
`tests/test_interview_evidence.py` reads their interview rules: each test reads
one part of the text (a step, a bullet, a sentence) and checks what it requires
rather than its exact wording, so a later rewording that keeps the rule passes."""

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


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = [s for s in re.split(r"(?<=[.;])\s+", text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _spec_step(n: int) -> str:
    """Step n of `start`'s Spec path, as written."""
    spec = _between(_start(), "\n**Spec** (flow §2)", "\n**Map**")
    assert f"\n{n}. " in spec, f"the Spec path has a step {n}"
    return spec.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0]


def _bullets() -> list[str]:
    """Step 2's bullets at any depth, each as written up to the next bullet."""
    return re.split(r"\n\s*- ", "\n" + _spec_step(2))[1:]


def _end_check() -> str:
    """The Spec path's end-check bullet (its opening, not its own bullets), flattened."""
    found = [b for b in _bullets() if b.startswith("**The end check")]
    assert len(found) == 1, "the Spec path's step 2 has one **The end check** bullet"
    return _flatten(found[0])


def _part(word: str) -> str:
    """The one bullet under the end check whose opening words name `word`, flattened."""
    bullets = _bullets()
    starts = [i for i, b in enumerate(bullets) if b.startswith("**The end check")]
    assert len(starts) == 1, "the Spec path's step 2 has one **The end check** bullet"
    first = starts[0]
    found = []
    for b in bullets[first + 1:]:
        if not b.startswith("**"):
            break  # the end check's own bullets are bold-led; the step's next bullet isn't
        # Its opening words: the bold lead and a few after it, without the markup.
        opening = re.sub(r"\*", "", b).split(" (", 1)[0][:30].lower()
        if word.lower() in opening:
            found.append(b)
    assert len(found) == 1, f"the end check has one bullet opening with {word!r}: {found}"
    return _flatten(found[0])


def _map_step(n: int) -> str:
    m = _between(_start(), "\n**Map** (flow §1)", "\n**Add to an existing issue:**")
    assert f"\n{n}. " in m, f"the Map path has a step {n}"
    return _flatten(m.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0])


# --- start's Spec step: when it runs ------------------------------------------


def test_the_end_check_runs_after_the_last_round_and_before_the_draft():
    step = _flatten(_spec_step(2))
    end = step.index("**The end check")
    # After the seams, the last round, are posted.
    assert step.index("Post their answers, the seams among them") < end
    # Before the draft is reviewed and published.
    assert end < step.index("Review the draft before publishing it")
    assert end < step.index("Publish the reviewed text as is")
    # The draft's own planning review still comes before publishing.
    assert step.index("Review the draft before publishing it") < step.index("Publish the reviewed text as is")
    first = re.split(r"(?<=[.;])\s+", _end_check())[0]
    # Before the draft is written, never after it.
    assert re.search(r"\bbefore (you write )?the (draft|spec is written)", first)
    assert not re.search(r"\bafter (you write |writing )?the draft\b", first)


def test_the_end_check_reads_all_the_answers_together_with_the_checker():
    e = _end_check()
    assert "`planning-checker`" in e
    assert "all the answers" in e and "together" in e
    # One read.
    assert re.search(r"\bone read\b|\bonce\b", e)
    # Points to the flow's rules.
    assert 'flow, "Decision questions"' in e


def test_a_destination_item_s_end_check_reads_the_map_decisions_it_draws_on():
    s = _sentence(_end_check(), "all the answers")
    assert "Destination item" in s and "map decisions" in s
    # The same answers the planning review reads after the draft.
    assert "`answers.md`" in s or "§8" in s


def test_the_re_read_reads_against_what_the_end_check_read():
    s = _sentence(_part("re-read"), "against the rest")
    assert "what the end check read" in s


def test_the_end_check_fills_the_checker_s_scratch_directory():
    s = _sentence(_end_check(), "/tmp/plan-check-")
    assert "-end-" in s
    assert "Your inputs" in s


def test_the_end_check_isn_t_the_planning_review():
    s = _sentence(_end_check(), "planning review")
    assert re.search(r"\bnot the planning review\b|\bisn't the planning review\b", s)
    assert "no spec record" in s and "one re-read" in s


# --- its ask findings: one short round ----------------------------------------


def test_ask_findings_come_back_as_one_short_round():
    a = _part("ask findings")
    assert "one short round" in a
    assert "Decision questions" in a
    # Each question with a recommendation and its evidence, under the rules.
    assert "recommendation" in a and "evidence" in a
    assert "**Leave them open**" in a


def test_the_end_check_round_isn_t_checked_again_before_it_s_asked():
    s = _sentence(_part("ask findings"), "before it's asked")
    assert re.search(r"\bno\b|\bnever\b|\bisn't\b", s)
    # Its re-read reads what it changed instead.
    assert "re-read" in s


def test_the_end_check_round_is_posted_as_each_round_is():
    a = _part("ask findings")
    assert "posted" in a or "Post it" in a
    assert "fixes" in a or "**fix**" in a


# --- its fix findings: made and listed ----------------------------------------


def test_fix_findings_are_made_and_listed_where_they_can_object():
    f = _part("fix findings")
    assert "make" in f
    # In the round's post.
    assert "round's post" in f
    # With no round, in a comment straight after the read.
    s = _sentence(f, "straight after")
    assert "comment" in s and ("no round" in s or "nothing is asked" in s)


# --- one re-read, then stop ----------------------------------------------------


def test_then_one_re_read_of_only_what_changed_and_stop():
    r = _part("re-read")
    assert "only what" in r and "changed" in r
    assert "against the rest" in r
    assert "stop" in _sentence(r, "against the rest")


def test_the_re_read_gets_its_own_scratch_directory_and_is_told_what_changed():
    s = _sentence(_part("re-read"), "/tmp/plan-check-")
    assert "-reread-" in s
    assert "read it follows" in s and "changed" in s and "fixes" in s
    assert "Your inputs" in s


def test_the_re_read_covers_the_fixes_too():
    s = _sentence(_part("re-read"), "only what")
    assert "fixes" in s


def test_the_re_read_s_findings_are_never_asked():
    r = _part("re-read")
    s = _sentence(r, "never asked")
    assert "findings" in s
    # Its fix findings are made; its ask findings are what's left.
    assert re.search(r"make its \*\*fix\*\* findings|\*\*fix\*\* findings are made", s)
    assert "what's left" in _sentence(r, "**ask** findings are")


# --- what's left -----------------------------------------------------------------


def test_what_s_left_goes_into_further_notes_before_publishing():
    w = _part("What's left")
    for part in ("left open", "unanswered", "re-read"):
        assert part in w, part
    s = _sentence(w, "open questions")
    assert "Further Notes" in s and "before" in s and "published" in s
    # Never kept only in the session's closing choices.
    assert "never only" in w


def test_leave_them_open_sends_a_finding_to_further_notes():
    s = _sentence(_part("What's left"), "**Leave them open**")
    assert "Further Notes" in s or "what's left" in s.lower()


def test_a_finding_about_their_own_words_is_asked_on_its_own():
    s = _sentence(_part("ask findings"), "own words")
    assert "on its own" in s and '"Yes to all"' in s


def test_the_end_check_s_posts_are_headed_and_go_where_the_rounds_are():
    s = _sentence(_end_check(), "where the rounds are")
    assert '"End check"' in s and '"Re-read"' in s
    # A map's Destination item: a comment on the map naming it, where later sessions look.
    assert "comment on the map naming it" in s


def test_each_read_leaves_a_headed_post_even_when_it_finds_nothing():
    s = _sentence(_end_check(), "where the rounds are")
    assert "each read" in s and "nothing found" in s


def test_a_session_that_carries_on_never_runs_the_end_check_again():
    # In the end check itself, so a session that comes through `next` finds it too.
    e = _end_check()
    s = _sentence(e, "carries on")
    assert '"End check"' in s and "never" in s and "again" in s
    assert '"Re-read"' in s and "only if" in s
    s = _sentence(e, "left open there")
    assert "what's left" in s and "never" in s and "interview" in s


def test_an_own_words_question_is_posted_with_the_end_check_s_round():
    s = _sentence(_part("ask findings"), "own words")
    assert "post" in s and "round" in s and "answered" in s


def test_carry_on_points_to_the_end_check_once_one_is_posted():
    row = _flatten(_between(_start(), "| A planned item |", "\n"))
    s = _sentence(row, 'headed "End check"')
    assert "interview is over" in s and "end check" in s and '"Spec"' in s
    # The interview carries on only while something is left to ask.
    assert "left open" not in _sentence(row, "carry on the interview")


# --- the Map step -----------------------------------------------------------------


def test_a_map_decision_runs_the_end_check_before_its_adr_is_written():
    m = _map_step(4)
    end = m.index("end check")
    assert m.index("**Each decision,**") < end < m.index("ADR and glossary written")
    s = _sentence(m, "end check")
    assert "before" in s and "ADR" in s
    assert "Spec" in s  # run as the Spec path runs it
    # Before the glossary too; a decision that changes neither runs it before it's recorded.
    assert "glossary" in s and "recorded" in s
    assert "no rounds" in _sentence(m, "has none")


def test_a_map_decision_s_end_check_posts_on_its_decision_ticket_and_leaves_the_rest_in_its_resolution():
    m = _map_step(4)
    assert "decision ticket" in m
    s = _sentence(m, "resolution comment")
    assert "left" in s


def test_the_map_step_runs_the_spec_path_s_end_check_rather_than_a_copy():
    s = _sentence(_map_step(4), "end check")
    assert "Spec path's step 2" in s
    # One description, in the Spec path: the Map step doesn't restate its shape.
    assert "**Leave them open**" not in _map_step(4)


# --- "That's enough, write it up" ----------------------------------------------------


def test_that_s_enough_still_runs_the_end_check():
    course = _flatten(_between(_start(), "\n## 7. Changing course", "\n## "))
    line = _between(course, "**\"That's enough, write it up\":**", " - **")
    assert "end check" in line and "still" in line
    assert "**Leave them open**" in line and "Further Notes" in line
    # Before the spec is written.
    assert "before" in line
    # A map decision has no spec: its resolution comment.
    assert "resolution comment" in line


# --- next ------------------------------------------------------------------------------


def test_next_runs_the_end_check_as_start_does():
    block = _between(NEXT.read_text(encoding="utf-8"), "\n**Decision questions**", "\n\n")
    assert "\n- **After the last round" in block
    r = _flatten(block.split("\n- **After the last round", 1)[1].split("\n- **", 1)[0])
    assert "end check" in r
    assert "ADR" in r and "spec" in r
    assert "`start`" in r and '"Spec"' in r and '"Map"' in r
    # A session carrying on stops asking once the end check is posted.
    before = _flatten(block.split("\n- **Before asking", 1)[1].split("\n- **", 1)[0])
    s = _sentence(before, '"End check"')
    assert "rounds are over" in s and "`start`" in s
    # A map decision's rounds too, but never a planning review's fix questions.
    assert "map decision" in s
    assert "planning review" in s and "fix" in s and "still" in s
    assert "glossary" in r and "recorded" in r
    # A pointer, not a copy of `start`'s steps.
    assert "**Leave them open**" not in r


# --- changelog ---------------------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#441, part of spec #436)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released

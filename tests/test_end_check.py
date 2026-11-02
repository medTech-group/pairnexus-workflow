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


def _end_check() -> str:
    """The Spec path's end-check bullet with its own bullets, flattened."""
    step = _spec_step(2)
    assert "\n   - **The end check" in step, "the Spec path's step 2 has a **The end check** bullet"
    return _flatten(step.split("\n   - **The end check", 1)[1].split("\n   - ", 1)[0])


def _nested() -> str:
    """The end-check bullet's own bullets, as written."""
    step = _spec_step(2).split("\n   - **The end check", 1)[1]
    lines = []
    for line in step.split("\n")[1:]:
        if line.startswith("     ") or not line.strip():
            lines.append(line)
            continue
        break
    return "\n".join(lines)


def _part(name: str) -> str:
    """One `- **name` bullet under the end check, flattened."""
    nested = _nested()
    assert f"\n     - **{name}" in "\n" + nested, f"the end check has a `- **{name}` bullet"
    return _flatten(("\n" + nested).split(f"\n     - **{name}", 1)[1].split("\n     - **", 1)[0])


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
    first = re.split(r"(?<=[.;])\s+", _end_check())[0]
    assert "before" in first and ("draft" in first or "spec is written" in first)


def test_the_end_check_reads_all_the_answers_together_with_the_checker():
    e = _end_check()
    assert "`planning-checker`" in e
    assert "all the answers" in e and "together" in e
    # One read.
    assert re.search(r"\bone read\b|\bonce\b", e)
    # Points to the flow's rules.
    assert 'flow, "Decision questions"' in e


def test_the_end_check_fills_the_checker_s_scratch_directory():
    s = _sentence(_end_check(), "/tmp/plan-check-")
    assert "-end-" in s
    assert "Your inputs" in s


def test_the_end_check_isn_t_the_planning_review():
    s = _sentence(_end_check(), "planning review")
    assert "isn't" in s or "not" in s
    assert "spec record" in s


# --- its ask findings: one short round ----------------------------------------


def test_ask_findings_come_back_as_one_short_round():
    a = _part("Its **ask** findings")
    assert "one short round" in a
    assert "Decision questions" in a
    # Each question with a recommendation and its evidence, under the rules.
    assert "recommendation" in a and "evidence" in a
    assert "**Leave them open**" in a


def test_the_end_check_round_isn_t_checked_again_before_it_s_asked():
    s = _sentence(_part("Its **ask** findings"), "before it's asked")
    assert re.search(r"\bno\b|\bnever\b|\bisn't\b", s)
    # Its re-read reads what it changed instead.
    assert "re-read" in s


def test_the_end_check_round_is_posted_as_each_round_is():
    a = _part("Its **ask** findings")
    assert "posted" in a or "Post it" in a
    assert "fixes" in a or "**fix**" in a


# --- its fix findings: made and listed ----------------------------------------


def test_fix_findings_are_made_and_listed_where_they_can_object():
    f = _part("Its **fix** findings")
    assert "make" in f
    # In the round's post.
    assert "round's post" in f
    # With no round, in a comment straight after the read.
    s = _sentence(f, "straight after")
    assert "comment" in s and ("no round" in s or "nothing is asked" in s)


# --- one re-read, then stop ----------------------------------------------------


def test_then_one_re_read_of_only_what_changed_and_stop():
    r = _part("Then one re-read")
    assert "only what" in r and "changed" in r
    assert "against the rest" in r
    assert "stop" in r
    s = _sentence(r, "again")
    assert "nothing" in s.lower()


def test_the_re_read_covers_the_fixes_too():
    s = _sentence(_part("Then one re-read"), "only what")
    assert "fixes" in s


def test_the_re_read_s_findings_are_never_asked():
    r = _part("Then one re-read")
    s = _sentence(r, "never asked")
    assert "findings" in s
    # Its fix findings are made; its ask findings are what's left.
    assert "**fix**" in r and "made" in r or "make" in r
    assert "what's left" in _sentence(r, "**ask** findings are")


# --- what's left -----------------------------------------------------------------


def test_what_s_left_goes_into_further_notes_or_a_comment_on_the_spec():
    w = _part("What's left")
    for part in ("left open", "unanswered", "re-read"):
        assert part in w, part
    s = _sentence(w, "open questions")
    assert "Further Notes" in s and "before" in s and "published" in s
    s = _sentence(w, "spec's issue")
    assert "comment" in s and "after" in s
    # Never kept only in the session's closing choices.
    assert "never only" in w


def test_leave_them_open_sends_a_finding_to_further_notes():
    s = _sentence(_part("What's left"), "**Leave them open**")
    assert "Further Notes" in s or "what's left" in s.lower()


# --- the Map step -----------------------------------------------------------------


def test_a_map_decision_runs_the_end_check_before_its_adr_is_written():
    m = _map_step(4)
    end = m.index("end check")
    assert m.index("**Each decision,**") < end < m.index("ADR and glossary written")
    s = _sentence(m, "end check")
    assert "before" in s and "ADR" in s
    assert "Spec" in s  # run as the Spec path runs it


def test_a_map_decision_s_end_check_posts_on_its_decision_ticket_and_leaves_the_rest_in_its_resolution():
    m = _map_step(4)
    assert "decision ticket" in m
    s = _sentence(m, "resolution comment")
    assert "left" in s


def test_the_map_step_keeps_the_end_check_shape():
    m = _map_step(4)
    for part in ("**ask**", "**Leave them open**", "**fix**", "re-read", "stop"):
        assert part in m, part


# --- "That's enough, write it up" ----------------------------------------------------


def test_that_s_enough_still_runs_the_end_check():
    course = _flatten(_between(_start(), "\n## 7. Changing course", "\n## "))
    line = _between(course, "**\"That's enough, write it up\":**", " - **")
    assert "end check" in line and "still" in line
    assert "**Leave them open**" in line and "Further Notes" in line
    # Before the spec is written.
    assert "before" in line


# --- next ------------------------------------------------------------------------------


def test_next_runs_the_end_check_as_start_does():
    block = _between(NEXT.read_text(encoding="utf-8"), "\n**Decision questions**", "\n\n")
    assert "\n- **After the last round" in block
    r = _flatten(block.split("\n- **After the last round", 1)[1].split("\n- **", 1)[0])
    assert "end check" in r
    assert "ADR" in r and "spec" in r
    assert "`start`" in r and '"Spec"' in r and '"Map"' in r


# --- changelog ---------------------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#441, part of spec #436)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released

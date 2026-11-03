"""#443: spec #436's "Quick tickets" (answers 7, 17 and 19 on #433), read as a
text contract on the shipped `start`: its Quick ticket path, **File the fix as a
ticket** (after finding a bug's cause) and §5's **Ready to build**. As
`tests/test_end_check.py` reads the Spec path's end check, each test reads one
part of the text (a step, a bullet, a sentence) and checks what it requires
rather than its exact wording, so a later rewording that keeps the rule passes."""

import re

from changelog_notes import since_0110
from conftest import KIT

START = KIT / "skills/start/SKILL.md"


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


def _quick() -> str:
    """`start`'s Quick ticket path, as written."""
    return _between(_start(), "\n**Quick ticket** (flow §2", "\n**Find the cause first:**")


def _quick_step(n: int) -> str:
    q = _quick()
    assert f"\n{n}. " in q, f"the Quick ticket path has a step {n}"
    return q.split(f"\n{n}. ", 1)[1].split(f"\n{n + 1}. ", 1)[0]


def _check() -> str:
    """The quick ticket's end check: its bold-led paragraph in step 1, with its own bullets."""
    step = _quick_step(1)
    assert "**The end check" in step, "the Quick ticket's step 1 has **The end check**"
    return step.split("**The end check", 1)[1]


def _check_opening() -> str:
    """The end check's opening, without its own bullets, flattened."""
    return _flatten(re.split(r"\n\s*- ", _check(), maxsplit=1)[0])


def _part(word: str) -> str:
    """The one bullet under the quick ticket's end check whose opening names `word`, flattened."""
    bullets = re.split(r"\n\s*- ", _check())[1:]
    found = []
    for b in bullets:
        if not b.startswith("**"):
            break
        # Its opening words: the bold lead and a few after it, without the markup
        # (30 characters, as `tests/test_end_check.py` reads the Spec path's bullets).
        opening = re.sub(r"\*", "", b).split(" (", 1)[0][:30].lower()
        if word.lower() in opening:
            found.append(b.split("\n\n", 1)[0])
    assert len(found) == 1, f"the quick ticket's end check has one bullet opening with {word!r}: {found}"
    return _flatten(found[0])


def _sorting() -> str:
    return _between(_start(), "\n## 5. Sorting new issues", "\n## 6.")


# --- the end check, before Publish it --------------------------------------------------


def test_the_quick_ticket_runs_its_end_check_before_publish_it():
    step = _flatten(_quick_step(1))
    end = step.index("**The end check")
    # After the draft is written, before Publish it is asked.
    assert step.index("Write the ticket") < end < step.index("**Publish it (Recommended)**")
    o = _check_opening()
    assert "`planning-checker`" in o
    # It reads the drafted ticket against the item's issue, for the decisions made for them.
    s = _sentence(o, "`planning-checker`")
    assert "drafted ticket" in s and "item's issue" in s and "decisions" in s
    # Points to the flow's rules.
    assert 'flow, "Decision questions"' in o


def test_the_end_check_fills_its_scratch_directory():
    s = _sentence(_check_opening(), "/tmp/plan-check-")
    assert "-end-" in s and "Your inputs" in s


def test_the_quick_ticket_s_check_isn_t_the_planning_review_and_posts_no_answers():
    o = _check_opening()
    assert re.search(r"\bnot the planning review\b|\bisn't the planning review\b", o)
    s = _sentence(o, "as their answers")
    # The negation belongs to "posted", not to "not the planning review" in the same sentence.
    assert re.search(r"\b(none|nothing|never|not|no)\b[^,:;]*\bposted\b", s)


def test_a_quick_ticket_with_no_item_s_issue_files_one_first():
    s = _sentence(_check_opening(), "no item's issue")
    assert "file one first" in s
    # The two routes that reach a quick ticket without one.
    assert "step 0" in s and "**Add to an existing issue**" in s


# --- Decided for you ----------------------------------------------------------------------


def test_the_decisions_made_for_them_go_into_the_ticket_under_decided_for_you():
    d = _part("Decided for you")
    assert "`## Decided for you`" in d
    # Each with its evidence: what it rests on, what it gives up, what would make it wrong.
    assert "evidence" in d
    for part in ("rests on", "gives up", "wrong"):
        assert part in d, part
    # Never tagged as their answers.
    s = _sentence(d, "tagged")
    # The negation belongs to "tagged as their answers".
    assert re.search(r"\b(not|never)\b[^,;.]*\btagged\b[^,;.]*\btheir answers\b", s)
    # Sensitive data stays out of a section that is posted in the ticket's body.
    s = _sentence(d, "Sensitive data")
    assert "`profile.md`" in s and "left out" in s


def test_the_section_never_reads_as_a_blocker():
    d = _part("Decided for you")
    s = _sentence(d, '"see #n"')
    assert re.search(r'"see #n",?\s*never\s+"blocked by #n"', s)
    # A real dependency, or an open question about one, goes where readiness reads it.
    s = _sentence(d, "waits for")
    assert "`## Blocked by`" in s and "open question" in s


def test_see_isn_t_read_as_a_blocker_but_blocked_by_is():
    # Why the rule above: the readiness reader takes "blocked by #n" anywhere in a body.
    from workflow.issues import blockers_of

    ticket = "## Blocked by\n\nNone\n\n## Decided for you\n\n- Wrong if it {} #302.\n"
    assert blockers_of(ticket.format("needs, see")) == []
    assert blockers_of(ticket.format("is blocked by")) == [302]


def test_an_answer_takes_the_decision_it_settles_out_of_the_section():
    s = _sentence(_part("ask findings"), "settles")
    assert "`## Decided for you`" in s and "out" in s
    # The re-read doesn't put it back.
    s = _sentence(_part("One re-read"), "settle")
    assert "except" in s and "stays out" in s


def test_step_2_publishes_the_section_with_the_ticket():
    s = _flatten(_quick_step(2))
    assert "`## Decided for you`" in _sentence(s, "replace its body")


def test_the_list_is_shown_above_publish_it_with_the_fixes():
    step = _flatten(_quick_step(1))
    ask = step.rindex("**Publish it (Recommended)**")
    show = _sentence(step, "above **Publish it (Recommended)**")
    # Shown before it's asked.
    assert step.index(show) < ask
    assert "decisions" in show and "evidence" in show
    assert "fixes" in show
    # The open ones too.
    assert "open" in show


# --- ask findings first; fix findings made -------------------------------------------------


def test_ask_findings_are_asked_first():
    a = _part("ask findings")
    s = _sentence(a, "first")
    assert "asked" in s and "**Publish it**" in s
    # As decision-question-shaped choices: a recommendation with its evidence where there's a basis.
    assert "recommendation" in a and "evidence" in a
    assert "**Leave them open**" in a


def test_an_ask_finding_left_open_goes_into_decided_for_you_marked_open():
    s = _sentence(_part("ask findings"), "marked open")
    assert "`## Decided for you`" in s and re.search(r"\b(leave|left)\b[^.]*\bopen\b", s) and "marked open" in s


def test_yes_to_all_answers_only_the_questions_with_a_recommendation():
    s = _sentence(_part("ask findings"), "Yes to all\" answers")
    assert "only" in s and "recommendation" in s and "again" in s and "on its own" in s


def test_a_finding_about_their_own_words_is_asked_on_its_own():
    s = _sentence(_part("ask findings"), "own words")
    assert "on its own" in s
    # On a quick ticket their own words are the item's issue and what they typed.
    assert "item's issue" in s and "typed" in s


def test_fix_findings_are_made_and_shown_above_publish_it():
    f = _part("fix findings")
    assert "make" in f
    assert "above **Publish it**" in f


# --- one re-read in all ------------------------------------------------------------------------


def test_one_re_read_in_all_of_what_the_answers_and_change_it_changed():
    r = _part("One re-read")
    assert "one re-read in all" in r.lower()
    s = _sentence(r, "since the end check")
    assert "**ask**" in s and "**Change it**" in s and "changed" in s and "fixes" in s
    # On the draft as it stands when Publish it is last shown.
    s = _sentence(r, "last shown")
    assert "draft as it stands" in s and "**Publish it**" in s


def test_the_re_read_fills_its_own_scratch_directory():
    s = _sentence(_part("One re-read"), "/tmp/plan-check-")
    assert "-reread-" in s and "Your inputs" in s
    # It gets their replies, as the agent's inputs say.
    assert "replies" in s


def test_the_re_read_runs_once_on_a_draft_that_changed_beyond_its_section():
    s = _sentence(_part("One re-read"), "**Publish it** on a draft")
    # Once: the first such pick.
    assert "first time" in s
    # Writing the section isn't a change that calls for it.
    assert "beyond" in s and "`## Decided for you`" in s


def test_it_publishes_straight_away_only_when_nothing_new_is_left_to_show():
    s = _sentence(_part("One re-read"), "straight away")
    assert "only when" in s and "found nothing" in s
    # Its own "Decided for you" list can add items: those are shown before publishing.
    assert "section" in s and "as it was" in s


def test_the_re_read_is_given_the_replies_tagged():
    s = _sentence(_part("One re-read"), "/tmp/plan-check-")
    assert "word for word" in s and "tagged" in s and "**ask**" in s


def test_nothing_changed_means_no_re_read():
    s = _sentence(_part("One re-read"), "nothing changed")
    assert re.search(r"\bno re-read\b|\bnothing to re-read\b", s)


def test_the_re_read_s_findings_are_never_asked_and_what_it_leaves_is_marked_open():
    r = _part("One re-read")
    s = _sentence(r, "never asked")
    assert "**fix**" in s and "**ask**" in s
    s = _sentence(r, "marked open")
    assert "`## Decided for you`" in s
    # Its fixes are shown above Publish it too.
    assert "above **Publish it**" in r


def test_a_change_after_the_re_read_gets_no_second_read_and_is_marked_open():
    a = _part("After the re-read")
    s = _sentence(a, "**Change it**")
    assert re.search(r"\bno (further|second|other) read\b|\bwithout another read\b", s)
    # What it decides for them is never published as if a read had seen it.
    assert "`## Decided for you`" in s and "marked open" in s


# --- the same for File the fix as a ticket and Ready to build ------------------------------


def test_file_the_fix_as_a_ticket_gets_the_same_list():
    find = _between(_start(), "\n**Find the cause first:**", "\n**Spec** (flow §2)")
    line = _flatten(_between(find, "**File the fix as a ticket and build it (Recommended)**", "\n   - "))
    assert '"Quick ticket" above' in line
    assert "end check" in line and "`## Decided for you`" in line


def test_ready_to_build_drafts_the_ticket_and_runs_its_check_before_its_own_options():
    s = _flatten(_sorting())
    options = s.index("**Ready to build**")
    before = s[:options]
    assert "draft" in before and "end check" in before
    # The list is shown above the options.
    s1 = _sentence(before, "**Decided for you**")
    assert "above the options" in s1 and "**ask**" in s1
    # Shown there, not asked: they are asked once Ready to build is picked.
    assert "Show" in s1 and not re.search(r"\bask (its|the|them)\b", s1)
    # The issue being sorted is the item's issue, so no second issue is filed.
    assert "item's issue" in _sentence(before, "issue you're sorting")
    # The check it ran is the one Publish it shows: no second end check.
    ready = _flatten(_between(_sorting(), "**Ready to build**", "\n- **"))
    s2 = _sentence(ready, "**Publish it**")
    assert "check" in s2 and re.search(r"\bthe one\b|\bno second\b|\bnot again\b", s2)
    # Its ask findings are asked once Ready to build is picked, never before the options.
    assert "**ask**" in s2 and re.search(r"\bnow\b", s2)
    # Its one re-read runs as the Quick ticket's step 1 says, never before the draft is shown.
    assert "re-read" in s2 and "step 1" in s2


def test_needs_more_information_asks_for_what_the_check_found():
    s = _sentence(_flatten(_sorting()), "among what the comment asks")
    assert "**Needs more information**" in s and "**ask**" in s
    assert "`profile.md`" in s and "left out" in s


def test_sorting_skips_the_draft_when_a_build_ticket_is_ruled_out():
    s = _sentence(_flatten(_sorting()), "rules out")
    assert re.search(r"\b(Unless|unless|Except|except)\b[^.]*rules out", s) and "leave that option out" in s


def test_triage_run_on_its_own_isn_t_covered():
    s = _flatten(_sorting())
    sent = _sentence(s, "`triage` run on its own")
    assert re.search(r"\b(isn't|not)\s+covered\b", sent)


# `triage` stays unedited: it is Matt Pocock's, with no source in this kit (only its vendored
# copy), so no test here could see an edit to it. Not tested.


# --- the flow agrees -------------------------------------------------------------------------


def test_the_flow_names_the_quick_ticket_s_end_check_in_start():
    flow = _flatten((KIT / "docs/flow.md").read_text(encoding="utf-8"))
    rules = _between(flow, "## Decision questions", "## 3.")
    s = _sentence(rules, "A quick ticket gets")
    assert "end check" in s and '"Decided for you"' in s and "`start`" in s


# --- changelog -----------------------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    assert "(#443, part of spec #436)" in since_0110()
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released

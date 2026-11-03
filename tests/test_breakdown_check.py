"""#444: spec #436's "The breakdown check" (answers 11, 13, 15, 23 and 24 on
#433), read as a text contract on the shipped `start`: its Spec path's step 3,
"The tickets", where the breakdown is agreed and then read against the spec
before its tickets are published, and the "Carry on" row that settles a ticket a
finding held back. As `tests/test_end_check.py` reads the end check, each test
reads one part of the text (a step, a bullet, a sentence) and checks what it
requires rather than its exact wording, so a later rewording that keeps the rule
passes."""

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


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.;])\s+", text)


def _sentence(text: str, word: str) -> str:
    """The one sentence of `text` that names `word`."""
    found = [s for s in _sentences(text) if word in s]
    assert len(found) == 1, f"one sentence names {word!r}: {found}"
    return found[0]


def _tickets_step() -> str:
    """Step 3 of `start`'s Spec path, "The tickets", as written."""
    spec = _between(_start(), "\n**Spec** (flow §2)", "\n**Map**")
    assert "\n3. " in spec, "the Spec path has a step 3"
    return spec.split("\n3. ", 1)[1].split("\n4. ", 1)[0]


def _agreeing() -> str:
    """Step 3 up to the breakdown check: the breakdown shown and its question."""
    step = _tickets_step()
    assert "**The breakdown check" in step, "step 3 has **The breakdown check**"
    return step.split("**The breakdown check", 1)[0]


def _check() -> str:
    """The breakdown check, from its bold lead to the end of step 3."""
    return "**The breakdown check" + _tickets_step().split("**The breakdown check", 1)[1]


def _check_opening() -> str:
    """The breakdown check's opening paragraphs and its list of what it reads,
    before its own bold-led bullets, flattened."""
    return _flatten(re.split(r"\n\s*- \*\*", _check(), maxsplit=1)[0])


def _part(word: str) -> str:
    """The one bold-led bullet of the breakdown check whose opening words name
    `word`, flattened."""
    bullets = re.split(r"\n\s*- ", "\n" + _check())[1:]
    found = []
    for b in bullets:
        if not b.startswith("**"):
            continue  # the list of what it reads isn't bold-led
        opening = re.sub(r"\*", "", b).split(" (", 1)[0][:30].lower()
        if word.lower() in opening:
            found.append(b)
    assert len(found) == 1, f"the breakdown check has one bullet opening with {word!r}: {found}"
    return _flatten(found[0])


# --- the breakdown, shown and agreed -------------------------------------------


def test_the_tickets_step_asks_agree_these_first_and_repeats_until_they_agree():
    a = _agreeing()
    labels = re.findall(r"^\s*- \*\*([^*]+)\*\*", a, flags=re.M)
    assert labels == [
        "Agree these (Recommended)",
        "Change the sizes",
        "Change what blocks what",
        "Merge or split some",
    ], labels
    # Agreeing is no longer publishing: nothing is published from this question.
    assert "Publish these" not in _tickets_step()
    s = _sentence(_flatten(a), "Repeat until")
    assert re.search(r"\bagree\b", s), s
    assert "publish" not in s, s


def test_the_breakdown_shown_has_full_bodies_owner_tasks_edits_and_the_spec_s_link():
    a = _flatten(_agreeing())
    shown = re.split(r"\bask\b", a, maxsplit=1)[0]  # what's shown, before the question
    assert "full bod" in shown  # "their full bodies" / "its full body"
    for part in ("criteria", "`## Blocked by`", "`## Bar`", "owner task", "edits to existing issues"):
        assert part in shown, part
    assert re.search(r"\blink to the spec\b", shown), shown


# --- the check: when it runs, what it reads -------------------------------------


def test_the_breakdown_check_runs_after_agree_these_and_before_anything_is_published():
    o = _check_opening()
    first = _sentences(o)[0]
    assert "**Agree these**" in first, first
    assert re.search(r"\bbefore\b.*\bpublish", first), first
    assert "`planning-checker`" in o
    # Points to the flow's rule.
    assert 'flow, "Decision questions"' in o
    # Its own scratch directory, named as the agent's inputs name the read.
    assert "/tmp/plan-check-<" in o and "-breakdown-<n>/" in o
    assert "Your inputs" in o


def test_it_reads_the_breakdown_against_the_spec_and_the_answers():
    o = _check_opening()
    s = _sentence(o, "/tmp/plan-check-")
    for given in ("the spec", "drafted tickets", "owner tasks", "edits to existing issues"):
        assert given in o, given
    # The answers posted for the spec, so a ticket isn't read against the spec's words alone.
    assert "round" in o and "posted" in o
    assert s


def test_every_decision_and_criterion_lands_in_exactly_one_place():
    o = _check_opening()
    s = _sentence(o, "exactly one")
    assert "decision" in s and "acceptance criterion" in s
    for place in ("build ticket", "owner task", "edit to an existing issue"):
        assert place in s, place


def test_carried_criteria_and_decisions_that_build_nothing_are_left_out():
    o = _check_opening()
    s = _sentence(o, "left out")
    assert "every ticket carries" in s
    assert "changelog note" in s and "full suite" in s
    assert "build nothing" in s
    assert "out of scope" in s and "left unchanged" in s


def test_each_blocked_by_and_each_bar_are_read():
    o = _check_opening()
    blocked = _sentence(o, "`## Blocked by` against")
    assert "builds on" in blocked, blocked
    bar = _sentence(o, "`## Bar` against")
    assert re.search(r"\bwhere the spec gives one\b", bar), bar


def test_it_is_one_of_the_flow_s_checks_not_the_planning_review():
    o = _check_opening()
    s = _sentence(o, "not the planning review")
    assert "one read" in s and "one re-read" in s
    assert "no spec record" in s


def test_its_posts_go_on_the_spec_s_issue_headed_one_for_each_read():
    o = _check_opening()
    s = _sentence(o, "headed")
    assert "spec's issue" in s
    assert '"Breakdown check"' in s and '"Breakdown re-read"' in s
    assert "one for each read" in s
    assert "nothing found" in s


# --- ask and fix ------------------------------------------------------------------


def test_only_wording_is_a_fix_and_moving_work_or_a_blocker_is_an_ask():
    p = _part("ask or fix")
    assert re.search(r"\bonly wording is a \*\*fix\*\*", p), p
    ask = _sentence(p, "moves")
    for moved in ("criterion", "decision", "tickets", "owner tasks", "edits"):
        assert moved in ask, moved
    assert "`## Blocked by`" in ask and "**ask**" in ask


def test_its_ask_findings_are_one_short_round_answered_before_publishing():
    p = _part("ask findings")
    assert "one short round" in p
    assert re.search(r"\bbefore\b[^.]*\bpublish", p), p
    assert "**Leave them open**" in p
    # Asked as decision questions, and posted on the spec's issue.
    assert '"Decision questions", above' in p
    assert "spec's issue" in p
    # A check's own round gets no before-round check.
    assert re.search(r"no check of its own before it's asked", p), p


def test_its_fix_findings_are_made_and_listed_where_they_can_object():
    p = _part("fix findings")
    assert re.search(r"\bmake\b|\bmade\b", p)
    assert "round's post" in p
    # With no round, in the check's own post on the spec's issue.
    assert re.search(r"[Ww]ith no round", p), p
    assert '"Breakdown check"' in p


def test_one_re_read_whose_ask_findings_are_one_more_round_with_no_read_after_it():
    p = _part("re-read")
    assert re.search(r"\bone re-read\b", p), p
    assert "what changed" in p or "only what" in p
    # Its directory is the agent's re-read, told which read it follows.
    assert "/tmp/plan-check-<" in p and "-reread-<n>/" in p
    s = _sentence(p, "one more short round")
    assert "**ask**" in s and "asked" in s
    assert re.search(r"\bno read after it\b", p), p
    assert re.search(r"\bbefore\b[^.]*\bpublish", p), p


def test_each_last_round_question_shows_each_affected_ticket_s_resulting_blocked_by():
    p = _part("re-read")
    s = _sentence(p, "would end up with")
    assert "`## Blocked by`" in s
    assert "every ticket" in s or "each ticket" in s


def test_the_redrafted_breakdown_is_shown_before_publishing():
    p = _part("re-read")
    s = _sentence(p, "redrafted")
    assert re.search(r"\bshow", s) and re.search(r"\bbefore\b.*\bpublish", s), s


# --- what a finding left open does --------------------------------------------------


def test_a_finding_left_open_keeps_its_tickets_out_of_ready_for_agent():
    p = _part("left open")
    assert "`ready-for-agent`" in p
    assert re.search(r"\bwithout `ready-for-agent`|out of `ready-for-agent`", p), p
    # The finding goes into the affected tickets' bodies.
    assert re.search(r"\binto their bodies\b|\bin their bodies\b", p), p
    assert "`## Breakdown check`" in p
    # A label that puts them with what waits on a person, not with new issues to sort.
    assert "`needs-info`" in p


def test_a_finding_written_into_a_body_never_reads_as_a_blocker():
    p = _part("left open")
    assert '"see #n"' in p
    assert '"blocked by #n"' in p and "never" in _sentence(p, '"blocked by #n"')
    # A ticket it waits for still goes in `## Blocked by`, the only list readiness reads.
    assert "`## Blocked by`" in p


def test_a_check_with_nothing_to_ask_publishes_with_no_further_click():
    p = _part("publish")
    s = _sentence(p, "no further click")
    assert re.search(r"nothing (left )?to ask|nothing to ask", s), s
    # Its wording fixes and what's left are listed on the spec's issue.
    assert "spec's issue" in p
    assert "what's left" in p


def test_what_s_left_goes_in_a_comment_on_the_spec_s_issue():
    p = _part("what's left")
    assert "spec's issue" in p
    assert "Leave them open" in p or "left open" in p
    assert re.search(r"\bnever only in the session's closing choices\b", p), p


def test_a_session_that_stops_before_publishing_drafts_and_checks_again():
    p = _part("stops before")
    assert "spec's issue" in p
    # The answers already posted stand; the new draft gets its own check.
    assert "stand" in p
    assert re.search(r"\bruns? the (breakdown )?check\b", p), p


def test_carry_on_settles_a_ticket_a_breakdown_finding_held_back():
    row = [l for l in _start().splitlines() if l.startswith("|") and "`needs-info`" in l and "`## Breakdown check`" in l]
    assert len(row) == 1, row
    r = _flatten(row[0])
    # Asked as a decision question, posted on the spec's issue.
    assert '"Decision questions", above' in r and "spec's issue" in r
    # The answer edits the tickets, and the label goes back to ready.
    assert "`ready-for-agent`" in r and "`needs-info`" in r
    # A ticket already built isn't edited.
    assert "quick ticket" in r


def test_next_runs_the_breakdown_check_as_start_says():
    t = _flatten(NEXT.read_text(encoding="utf-8"))
    s = _sentence(t, "breakdown check")
    assert "`start`" in s and "step 3" in s


# --- docs ---------------------------------------------------------------------------


def test_the_changelog_notes_the_breakdown_check():
    notes = since_0110()
    assert "#444" in notes
    note = notes.split("#444", 1)[0].rsplit("\n\n**", 1)[-1] + notes.split("#444", 1)[1].split("\n\n**", 1)[0]
    assert "breakdown check" in note.lower()
    assert "tests/test_breakdown_check.py" in note

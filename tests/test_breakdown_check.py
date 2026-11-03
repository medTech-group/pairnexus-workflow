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
    shown = _flatten(_agreeing().split("\n   - **", 1)[0])  # what's shown, before the question's options
    assert "Agree these" not in shown
    assert "full bod" in shown  # "their full bodies" / "its full body"
    for part in ("criteria", "`## Blocked by`", "owner task", "edits to existing issues"):
        assert part in shown, part
    # A bar only where the ticket has one (ADR 0002: a ticket may carry one).
    assert "`## Bar` where it has one" in shown
    assert re.search(r"\blink to the spec\b", shown), shown


def test_an_edit_is_only_to_an_issue_not_claimed_or_built():
    s = _sentence(_flatten(_agreeing()), "An edit is only")
    assert "claimed (`workflow:in-progress`)" in s and "built (closed, or with an open PR)" in s
    assert "new build ticket" in s
    # An edited spec is reviewed again, so its tickets don't read as unreviewed.
    s = _sentence(_flatten(_agreeing()), "An edit to a spec")
    assert "planning round" in s and "spec record" in s


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
    s = _sentence(_check_opening(), "/tmp/plan-check-")
    for given in ("the spec", "drafted tickets in full", "owner tasks", "edits to existing issues"):
        assert given in s, given
    # The answers posted for the spec, so a ticket isn't read against the spec's words alone.
    assert re.search(r"\bevery round posted for the spec\b", s), s
    # A Destination item's spec: the map decisions' answers too, as the end check takes them.
    assert "map decisions" in s


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
    # Which post: the round's that follows the read, or with no round the read's own comment.
    assert "round that follows" in s and re.search(r"[Ww]ith no round, the read's own comment", s), s


# --- ask and fix ------------------------------------------------------------------


def test_only_wording_is_a_fix_and_moving_work_or_a_blocker_is_an_ask():
    p = _part("ask or fix")
    assert re.search(r"\bonly wording is a \*\*fix\*\*", p), p
    ask = _sentence(p, "moves")
    for moved in ("criterion", "decision", "tickets", "owner tasks", "edits"):
        assert moved in ask, moved
    assert "`## Blocked by`" in ask and "**ask**" in ask
    # Whatever the checker marked it: the session holds to this.
    assert "whatever the checker marked it" in ask


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
    s = _sentence(_part("ask or fix"), "**fix** findings")
    assert re.search(r"\bmake\b|\bmade\b", s), s
    assert "that read's post" in s  # one place for fixes and what's left
    # One place for both: that read's post, whose placement the posts' sentence gives.
    w = _sentence(_part("what's left"), "with each read's fixes")
    assert "spec's issue" in w and "that read's post" in w


def test_one_re_read_whose_ask_findings_are_one_more_round_with_no_read_after_it():
    p = _part("re-read")
    assert re.search(r"\bone re-read\b", p), p
    assert "what changed" in p or "only what" in p
    # Its directory is the agent's re-read, told which read it follows.
    assert "/tmp/plan-check-<" in p and "-reread-<n>/" in p
    s = _sentence(p, "one more short round")
    assert "**ask**" in s and "asked" in s
    assert re.search(r"\bno read after it\b", s), s
    assert re.search(r"\bbefore\b[^.]*\bpublish", s), s
    # Leave them open is offered here too.
    assert "**Leave them open**" in s
    # Its inputs: the spec and the redraft in full, and which read it follows.
    i = _sentence(p, "-reread-<n>/")
    assert "Your inputs" in i and "the spec" in i and "redrafted breakdown in full" in i
    assert "the read it follows" in i
    # Its round is posted on the spec's issue too.
    assert "spec's issue" in _sentences(p)[-1]


def test_each_last_round_question_shows_each_affected_ticket_s_resulting_blocked_by():
    p = _part("re-read")
    s = _sentence(p, "would end up with")
    assert "`## Blocked by`" in s
    assert "every ticket" in s or "each ticket" in s


def test_the_redrafted_breakdown_is_shown_before_publishing():
    p = _part("show the redraft")
    assert re.search(r"\bbefore\b.*\bpublish", p), p
    # Whenever it changed since it was agreed, not only after the re-read's round.
    assert "whenever" in p and "**Agree these**" in p


def test_the_first_round_s_answers_redraft_the_breakdown():
    s = _sentence(_part("ask findings"), "redraft")
    assert "answers" in s


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
    # Existing build tickets it affects are held back too, but only ready, unclaimed, unbuilt ones.
    s = _sentence(p, "the existing ones")
    assert "`ready-for-agent`" in s and "claimed" in s and "built" in s
    # A finding about an edit to anything else holds back the tickets that edit affects.
    s = _sentence(p, "anything else")
    assert "spec" in s and "build tickets that edit affects" in s
    # The section says who settles it, so triage doesn't, and marks each open finding.
    assert "settled through `/start`, not by triage" in p
    assert '"Open:"' in _sentence(p, "a line for each open finding")


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


def test_publishing_labels_build_tickets_owner_tasks_and_makes_the_edits():
    s = _sentence(_part("publish"), "blockers first")
    assert "each build ticket `ready-for-agent`" in s and "held back" in s
    assert "owner task labelled `owner-task`" in s
    assert "make the edits to existing issues" in s
    # The edits, with any held ticket's section written in, before anything is published.
    e = _sentence(_part("publish"), "make the edits")
    assert "section into its edit" in e
    assert e.index("make the edits") < e.index("publish in order")
    # An edit to an issue claimed or built since is left unmade, and said.
    s = _sentence(_part("publish"), "claimed or built since")
    assert "isn't made" in s and "spec's issue" in s


def test_the_final_breakdown_is_posted_before_publishing():
    s = _sentence(_part("publish"), '"Breakdown to publish"')
    assert "First post" in s and "spec's issue" in s
    # In full, so a session that carries on publishes it exactly as posted.
    assert "in full" in s
    for listed in ("build ticket's body", "owner task", "edit as the edit itself", "held back with its `## Breakdown check` section"):
        assert listed in s, listed


def test_what_s_left_goes_on_the_spec_s_issue():
    p = _part("what's left")
    assert "spec's issue" in p
    assert "left open" in p
    assert "holds back" in p
    assert re.search(r"\bnever only in the session's closing choices\b", p), p


def test_a_session_that_carries_on_finishes_a_final_breakdown_with_no_read():
    p = _part("carries on")
    assert "spec's issue" in p
    s = _sentence(p, 'With a "Breakdown to publish" post')
    assert "exactly as posted" in s and "no further read" in s
    # Done means any issue of that title, open or closed, so nothing is published twice.
    assert "open or closed" in s and "`## Parent`" in s
    assert "edit already in its issue's body" in p
    # "Carry on" finds such a spec, before the "no tickets" row would send it to `to-tickets`.
    rows = [l for l in _start().splitlines() if l.startswith("| An open spec")]
    assert '"Breakdown to publish" post' in rows[0], rows


def test_without_a_final_breakdown_only_the_reads_with_no_post_run():
    p = _part("carries on")
    s = _sentence(p, "Without one")
    assert "stand" in s and "**Agree these**" in s
    s = _sentence(p, "Agreed as drafted")
    assert "only the reads that have no post yet" in s
    assert '"Breakdown re-read" post' in s
    s = _sentence(p, "Changed at **Agree these**")
    assert "don't carry over" in s and re.search(r"\brun the breakdown check on that draft\b", s), s


def test_carry_on_reads_bodies_and_comments_to_find_its_rows():
    intro = _flatten(_between(_start(), "**Carrying on.**", "\n|"))
    assert "`WF status --json`" in intro and "`## Breakdown check`" in intro
    assert '"Breakdown to publish"' in intro and "comments" in intro


def test_carry_on_points_to_settling_a_held_back_ticket():
    row = [l for l in _start().splitlines() if l.startswith("| A build ticket held back")]
    assert len(row) == 1, row
    first = row[0].split(" | ", 1)[0]
    # Found by its section, whatever label it has now, so a stop part-way isn't stuck.
    assert "`## Breakdown check`" in first and "not labelled `ready-for-agent`" in first
    assert "Settling a held-back ticket" in row[0]


def test_settling_asks_every_open_finding_in_one_round_on_the_spec_s_issue():
    p = _part("settling")
    assert "every finding still open" in p and "one round" in p
    assert "spec's issue" in p
    s = _sentence(p, "isn't edited")
    assert "claimed or built" in s and "quick ticket" in s


def test_settling_is_the_last_round_carried_on_with_no_read():
    p = _part("settling")
    assert "shaped as the re-read's round" in p  # each option's resulting blockers
    s = _sentence(p, "carried on")
    assert "last round" in s and "no check before it" in s and "no read after it" in s


def test_a_new_ticket_an_answer_makes_is_published_before_it_is_named():
    s = _sentence(_part("settling"), "an answer makes")
    assert "published" in s and "before the blockers that name it" in s


def test_a_ticket_goes_back_to_ready_only_with_no_finding_left_open():
    p = _part("settling")
    s = _sentence(p, "swap")
    assert "`ready-for-agent`" in s and 'no "Open:" line left' in s
    assert '"Settled: answer <n>"' in _sentence(p, "Settled:")


def test_section_5_never_sorts_a_held_back_issue():
    five = _flatten(_between(_start(), "\n## 5. Sorting new issues", "\n## 6."))
    s = _sentence(five, "`## Breakdown check` section isn't sorted")
    assert "Carry on" in s
    # The label triage swapped is put back, so status shows it waiting again.
    assert re.search(r"put back `needs-info` in place of `needs-triage`", s), s


# --- what the held-back label and section do in the code ------------------------------


def _issue(n, title, labels=(), body=""):
    return {"number": n, "title": title, "labels": [{"name": x} for x in labels], "body": body, "state": "open"}


def _held() -> str:
    """A held-back ticket's body, its section opening as `start` writes it."""
    opening = re.search(r'opening with "([^"]+)"', _part("left open")).group(1)
    return (
        "Area: start\n\n## Blocked by\n\n- #4\n\n## Breakdown check\n\n"
        + opening.replace("<spec>", "3")
        + ".\n\n- Open: which ticket takes criterion C? If this one, it also builds on see #5.\n"
    )


def test_a_held_back_ticket_is_waiting_on_a_person_not_ready_or_to_sort(repo):
    from workflow import status

    issues = [_issue(6, "Ticket six", ["needs-info"], _held()), _issue(4, "Ticket four", ["ready-for-agent"], "Area: docs\n\n## Blocked by\n\nNone")]
    st = status.snapshot(repo, True, issues, [], repo="acme/demo", areas=["start", "docs"])
    assert [i.number for i in st.waiting] == [6]
    assert all(i.number != 6 for i in st.to_triage + st.ready)


def test_the_section_s_issues_are_never_read_as_blockers():
    from workflow.issues import blockers_of

    assert blockers_of(_held()) == [4]
    assert blockers_of(_held().replace("see #5", "blocked by #5")) == [4, 5]


def test_start_names_the_breakdown_check_s_rounds_among_its_decision_questions():
    t = _flatten(_between(_start(), "**Decision questions** are", "- **\"Yes to all\"**"))
    assert "the breakdown check's rounds" in t
    s = _sentence(_flatten(_between(_start(), "- **Each round** is posted", "\n")), "the breakdown check's rounds")
    assert "spec's issue" in s


def test_next_runs_the_breakdown_check_as_start_says():
    t = _flatten(NEXT.read_text(encoding="utf-8"))
    s = _sentence(t, "breakdown check")
    assert "`start`" in s and "step 3" in s


# --- docs ---------------------------------------------------------------------------


def test_the_changelog_has_a_note_and_version_is_untouched():
    notes = since_0110()
    assert "(#444, part of spec #436)" in notes
    assert "tests/test_breakdown_check.py" in notes
    log = (KIT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released

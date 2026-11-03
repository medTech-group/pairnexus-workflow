"""#375: attended work builds and reviews under spec #412's rule (spec #412,
"The fixer", "Records and clean", "The circuit breaker", "Attended work").

`build-ticket` turns the rule for build reviewers (`review-panel` §10) on for
attended work, and for a ticket session only when its briefing has a
"Findings:" line. Under it: a fresh fixer makes every review's fixes, round
1's included; the pull request opens as a draft after round 1 and is marked
ready once `merge-check` gives no review reason; `mechanism_repeats` is acted
on by its `next`, with the pull request body saying which and why; attended
work prints one status line at each review that isn't clean and stops after
10, with the hand-off and `workflow:carry-on`; the light and small reviews
carry on with Correctness passes until clean; a security problem in code on
the base branch is shown to the person and fixed by a fresh fixer. Read as
the kit's other text contracts are (prior art: tests/test_planning_review.py,
tests/test_fixer.py), each check scoped to its own bullet or section.
"""

import re

from changelog_notes import since_0110
from conftest import KIT
from workflow import gate, merge

BUILD = "skills/build-ticket/SKILL.md"
PANEL = "skills/review-panel/SKILL.md"
RULE_HEADING = "### The rule for build reviewers\n"


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _section(rel: str, start: str, end: str = "\n## ") -> str:
    text = _read(rel)
    assert start in text, f"{rel} has {start!r}"
    return _flat(text.split(start, 1)[1].split(end, 1)[0])


def _rule() -> str:
    """`build-ticket` §3's subsection that turns the rule on, up to the next subsection."""
    return _section(BUILD, RULE_HEADING, "\n### ")


def _review() -> str:
    return _section(BUILD, "## 3. Review it\n", "\n## 4. ")


def _pr_step() -> str:
    return _section(BUILD, "## 4. Open the pull request\n", "\n## 5. ")


def _merge_step() -> str:
    return _section(BUILD, "## 6. Post the evidence and merge\n", "\n## 7. ")


def _bullet(text: str, opening: str) -> str:
    """From `opening` to the next bullet (` - **`) or the end, in flattened text."""
    assert opening in text, opening
    return opening + re.split(r" - \*\*", text.split(opening, 1)[1], maxsplit=1)[0]


def _panel(start: str, end: str = "\n## ") -> str:
    return _section(PANEL, start, end)


# --- which rule ---------------------------------------------------------------


def test_build_ticket_turns_the_rule_on_for_attended_work_and_for_a_run_only_with_its_findings_line():
    which = _bullet(_rule(), "**Which rule.**")
    assert "In attended work, build reviews always follow the rule for build reviewers (`review-panel` §10)" in which
    assert "In a ticket session, only when its briefing has a \"Findings:\" line" in which
    assert "a briefing without one means today's rule throughout" in which
    # §3's own review steps point to it.
    assert "Under the rule (\"The rule for build reviewers\", below), a fresh fixer makes every review's fixes" in _review()


def test_review_panel_says_where_build_ticket_turns_it_on():
    rule = _panel("## 10. The rule for build reviewers\n")
    assert "In attended work, `build-ticket` says they always do." in rule
    # The run's line stays: a run keeps the rule it started with.
    assert "in a run, only when the briefing has a \"Findings:\" line, since a run keeps the rule it started with" in rule


# --- the fixer ----------------------------------------------------------------


def test_every_reviews_fixes_round_1s_included_go_to_a_fresh_fixer():
    fixer = _bullet(_rule(), "**A fresh fixer makes every review's fixes,**")
    assert "round 1's included" in fixer
    assert "`review-panel` §3, **The fixer**" in fixer
    assert "in the order it gives" in fixer
    # The session builds and coordinates; it fixes nothing itself.
    assert "You build the change, start the reviewers and the fixers, file the tickets, post the records and keep short summaries" in fixer
    assert "you fix no finding yourself" in fixer
    assert "A failure `review-panel` §3's step 5 finds after a fixer goes to the next review, never to you" in fixer
    # §3's step list says so too.
    assert "a fresh fixer makes every review's fixes and you make none" in _review()


def test_a_red_required_check_is_still_section_5s():
    """Round 1, Correctness: "fix nothing yourself" and §5's red check answered a red check differently."""
    fixer = _bullet(_rule(), "**A fresh fixer makes every review's fixes,**")
    assert "A required check that goes red is still §5's." in fixer
    assert "**A required check is red:** find the cause" in _section(BUILD, "## 5. Get it green\n", "\n## 6. ")


# --- the draft ----------------------------------------------------------------


def test_the_pull_request_opens_as_a_draft_after_round_1_with_its_record():
    draft = _bullet(_rule(), "**The pull request opens as a draft after round 1:**")
    assert "with `draft: true`" in draft
    assert "post round 1's record on it" in draft
    # Before the fixer: merge-check reads every review from the start.
    assert "before its fixer" in draft
    assert "so `WF merge-check` reads every review from the start" in draft


def test_it_is_marked_ready_once_merge_check_gives_no_review_reason():
    draft = _bullet(_rule(), "**The pull request opens as a draft after round 1:**")
    assert "Mark it ready for review (`update_pull_request` with `draft: false`) once `WF merge-check --fetch <PR> --json`" in draft
    assert "gives no review reason: none whose `rule` is `review_panel`, and no `couldnt_read`" in draft
    # The draft's own reason isn't a review reason.
    assert "Its `draft` reason never holds a review" in draft


def test_section_4_opens_it_as_a_draft_under_the_rule_and_carries_on_with_the_review():
    step = _pr_step()
    assert "Under the rule (§3), it opens as a draft after round 1" in step
    assert "carry on with the review" in step


def test_couldnt_read_is_no_review_reason_so_the_draft_names_it():
    """Round 1, Correctness: an input merge-check couldn't read gives `couldnt_read` with no rule."""
    assert merge.REASONS["couldnt_read"].rule != "review_panel"


def test_the_review_reason_named_is_one_merge_check_gives():
    """`review_panel` is the rule of every review reason, and `draft` isn't one."""
    review = {rid for rid, r in merge.REASONS.items() if r.rule == "review_panel"}
    assert {"no_review", "review_not_clean", "pass_not_clean", "review_stale", "passes_used_up", "mechanism_repeats", "past_small_threshold"} <= review
    assert merge.REASONS["draft"].rule != "review_panel"


# --- the pass cap -------------------------------------------------------------


def test_under_the_rule_there_is_no_pass_cap_in_runs_or_attended_work():
    # One source: review-panel §5 says it in full, build-ticket points there.
    cap = _bullet(_rule(), "**No pass cap** (`review-panel` §5)")
    assert "Correctness passes until one is clean" in cap
    assert "passes_used_up" not in cap
    assert "Under the rule (below), there is no pass cap, and a fresh fixer makes each pass's fixes." in _review()


def test_review_panel_section_5_says_there_is_no_pass_cap_under_the_rule():
    s5 = _panel("## 5. When to stop\n")
    cap = s5.split("**Under the rule** (section 10), there is no pass cap", 1)
    assert len(cap) == 2, "§5 has the bullet"
    assert "in runs and attended work alike, whatever the briefing or the profile says" in cap[1]
    assert "`merge-check` never says `passes_used_up` for its records" in cap[1]
    assert "Nothing still open goes to the owner" in cap[1]
    assert "in attended work the session stops after 10 reviews that weren't clean" in cap[1]
    # The last round's leftovers are carried on, not handed to the owner.
    assert "under the rule (section 10), Correctness passes carry it on until one is clean instead" in s5


def test_the_light_and_small_reviews_keep_their_shapes_and_carry_on_until_clean():
    light = _panel("## 6. The light review\n")
    small = _panel("## 7. The small review\n")
    for shape in (light, small):
        assert "Under the rule (section 10), nothing does: Correctness passes follow until one is clean (section 5), with no hand-off to the owner." in shape
    # Their shapes stay: the light review's Correctness-only rounds, the small review's one round.
    assert "at most 2 more" in light
    assert "**One round.**" in small
    assert "under the pass cap (under the rule, there is none: section 5)" in small
    # build-ticket's own small-review lines agree.
    review = _review()
    assert "then Correctness passes under the pass cap (under the rule, none: below)" in review
    assert "under the rule, where it opens before round 1's fixer, measure again after that fixer, before the next review" in review


# --- the circuit breaker ------------------------------------------------------


def test_mechanism_repeats_is_acted_on_by_its_next_not_the_sessions_judgement():
    breaker = _bullet(_rule(), "**When the same part keeps blocking**")
    assert "(`mechanism_repeats`)" in breaker
    assert "do what its `next` says, not what you judge" in breaker
    # The safe fallback, by a fixer.
    assert "`fail_closed`: the fresh fixer gets the part in `part.md`, with `fail_closed`" in breaker
    assert "the safe fallback the ticket's bar describes" in breaker
    # A split: the ticket filed first (#373), then a fixer takes the part out.
    assert "`split`: file its split ticket first" in breaker
    assert "\"Filing tickets to fix findings, and split tickets\"" in breaker
    assert "then the fresh fixer gets the part in `part.md`, with `split`, and takes it out of the pull request" in breaker
    assert breaker.index("file its split ticket first") < breaker.index("with `split`, and takes it out")
    # Neither left: the review goes on.
    assert "no `next`: neither is left" in breaker
    assert "then the review its `then` names" in breaker
    assert "before bringing the branch up to date" in breaker


def test_the_pull_request_body_says_which_was_done_and_why_in_plain_words():
    breaker = _bullet(_rule(), "**When the same part keeps blocking**")
    assert "The pull request body says which was done and why, in plain words (§4, **Parts that kept blocking**)" in breaker
    step = _pr_step()
    assert "after `mechanism_repeats`, under **Parts that kept blocking**" in step
    for words in ("the safe fallback", "split out to #<n>", "it blocked in two reviews in a row"):
        assert words in step, words
    # Plain words: never the answer's own names in what a person reads.
    line = step.split("under **Parts that kept blocking**", 1)[1].split(";", 1)[0]
    for code in ("fail_closed", "mechanism_repeats", "mechanism"):
        assert code not in line, code


def test_the_findings_table_gains_the_mark_and_the_part_under_the_rule():
    assert "(under the rule, with each finding's mark and part too: `review-panel` §9)" in _pr_step()


# --- attended work: the status line and the stop ------------------------------


def test_attended_work_prints_one_status_line_at_each_review_that_isnt_clean():
    status = _bullet(_rule(), "**In attended work, one status line at each review that isn't clean,**")
    assert "once its record is posted and `WF merge-check` has answered" in status
    assert "(\"#12: pass 3 not clean; the requeue part split out to #415\")" in status
    assert "It asks nothing: the loop goes on." in status


def test_attended_work_stops_after_10_reviews_that_werent_clean_in_one_session():
    stop = _bullet(_rule(), "**The attended stop, after 10 reviews that weren't clean in one session.**")
    # Counted from the records since the last hand-off.
    assert "Count the pull request's review records (rounds and passes) posted since its latest hand-off comment, or since it opened when it has none, that aren't clean (`result=not-clean` on the record's machine line)" in stop
    # Counted as merge-check counts: write access only, a review posted twice once.
    assert "only those from an account with write access, and a review posted twice once" in stop
    assert "only a hand-off comment from such an account starts the count again" in stop
    # After that review's fixer has reported (it may push nothing), before the next review.
    assert "Once the 10th such review's fixer has reported, and pushed what it committed, and its tests have run (`review-panel` §3, step 5), stop before the next review" in stop
    # The hand-off (#371), posted as it is.
    assert "`WF hand-off --commit <head> --round <N> --passes <P> --record <F> [--tickets <n,n>]`" in stop
    assert "`<N>` the last round's number, `<P>` the passes since it" in stop
    assert "post its output on the pull request as it is" in stop
    assert "If it refuses, fix what it names and run it again: never write one by hand" in stop
    # Labelled carry-on; neither claimed nor ready, so nothing builds it again from the start.
    assert "label the ticket `workflow:carry-on`, keeping its other labels, and remove `workflow:in-progress` and `ready-for-agent`" in stop
    # A status line, and the handed-off status.
    assert "say one status line" in stop
    assert "`WORKFLOW-STATUS: handed-off`" in stop
    assert stop.index("WF hand-off") < stop.index("workflow:carry-on") < stop.index("handed-off")


def test_nothing_waits_and_carry_on_starts_a_fresh_session_with_a_fresh_10():
    stop = _bullet(_rule(), "**The attended stop, after 10 reviews that weren't clean in one session.**")
    assert "Nothing waits for an answer." in stop
    assert "\"Carry on\" from the person, at any time, goes on in a fresh session, with a fresh 10" in stop
    assert "say 'carry on'" in stop  # no quotes nested in the example's own
    carry = _bullet(_rule(), "**Carrying on after a hand-off.**")
    assert "The fresh session takes `workflow:carry-on` off and claims the ticket (§1)" in carry
    assert "reads the hand-off (`WF merge-check --fetch <PR> --json`'s `hand_off`)" in carry
    assert "its count starts at that hand-off" in carry


def test_a_carry_on_ticket_reaches_build_ticket_and_skips_the_build():
    """Round 1, Correctness: "carry on #N" wasn't a trigger, and §2 came before the carry-on steps."""
    description = _read(BUILD).split("\n---", 1)[0]
    assert '"carry on #N"' in description
    claim = _section(BUILD, "## 1. Claim it\n", "\n## 2. ")
    assert "**A ticket labelled `workflow:carry-on`** with an open pull request" in claim
    assert "take `workflow:carry-on` off and put `ready-for-agent` back" in claim
    assert "go on from §3's \"Carrying on after a hand-off\" instead of §2" in claim


def test_a_contest_open_at_the_hand_off_is_ruled_on_by_the_fresh_session():
    carry = _bullet(_rule(), "**Carrying on after a hand-off.**")
    assert "A contest still open at the hand-off goes under \"Contests to rule on\"" in carry


def test_no_security_detail_crosses_sessions_at_the_attended_stop():
    carry = _bullet(_rule(), "**Carrying on after a hand-off.**")
    assert "its first review gets no `since.patch`, so its reviewers treat the whole change as new (`review-panel` §1)" in carry
    assert "none cross sessions" in carry
    # And review-panel §1 says what no since.patch means.
    assert "with none, the reviewers treat the whole change as new" in _panel("## 1. Gather the inputs", "\n## 2.")


def test_a_run_has_no_such_stop():
    stop = _bullet(_rule(), "**The attended stop, after 10 reviews that weren't clean in one session.**")
    assert "In a run there is no such stop: the end time is the limit, and the conductor writes the hand-off." in stop


# --- security in code on the base branch -------------------------------------


def test_attended_work_shows_the_person_a_security_problem_on_main_and_a_fresh_fixer_fixes_it():
    filing = _section(BUILD, "### Filing tickets to fix findings, and split tickets\n", "\n## 4. ")
    assert "In attended work, a blocking one is fixed here instead, its details shown to the person and given privately to whoever fixes it." in filing
    assert "Under the rule (§3), that is the review's fresh fixer: show the person its details in the session's chat, give them to the fixer only in its `findings.md`, and name only its area in public." in filing
    # In a run, a blocking one still holds the ticket.
    assert "In a run it holds this ticket for the owner" in filing
    # And the fixer's hand-off takes it only in attended work (#429).
    s3 = _panel("## 3. After each round\n", "\n## 4.")
    assert "goes in only in attended work" in s3


# --- the merge, attended ------------------------------------------------------


def test_attended_work_names_the_tickets_filed_with_an_offer_to_build_the_first():
    step = _merge_step()
    assert "Under the rule (§3), mark it ready for review first, once `WF merge-check` gives no review reason (§3)" in step
    assert "`review_not_clean`: fix the findings, under the rule by a fresh fixer (§3)" in step
    assert "name the tickets filed for its findings and its splits, with an offer to build the first" in step


def test_section_7_lists_the_handed_off_status():
    end = _section(BUILD, "## 7. End each turn\n")
    assert "WORKFLOW-STATUS: done | waiting | needs-human | stopped | handed-off" in end
    assert "`handed-off` once you have posted the hand-off comment" in end
    assert gate.STATUS.search("WORKFLOW-STATUS: handed-off")


# --- the changelog ------------------------------------------------------------


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    own = "(#375, part of spec #412)"
    assert own in notes
    head = notes.split(own, 1)[0].rsplit("\n\n**", 1)[1]
    note = head + notes.split(own, 1)[1].split("\n\n**", 1)[0]
    for words in ("attended work", "fresh fixer", "draft", "`mechanism_repeats`", "10 reviews", "`workflow:carry-on`", "pass cap"):
        assert words in note, words

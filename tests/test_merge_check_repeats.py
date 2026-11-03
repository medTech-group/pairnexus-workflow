"""#427 (spec #412, "The circuit breaker"): when the same part (mechanism) has a
blocking finding in two `rule=2` records in a row, `workflow merge-check` says
`mechanism_repeats`, naming it, in place of the review reason, with what comes
next, and with the review after it in `then` (`round` or `pass`, as the round
limit chooses it):

- `next: fail_closed` when the reviewer marked the part as one the bar's
  fail-closed form covers and it hasn't taken that form;
- else `next: split` when the part hasn't been split from this ticket and the
  ticket wasn't made by a split;
- else no `next`: the review goes on.

Names are compared exactly; security findings never count; a contested finding
the next reviewer kept counts once, with the review that first reported it, and
a review whose only findings on the part are kept re-entries neither counts nor
breaks the run; an overturned finding counts for nothing. A ruling is about the
last review before the review that gives it (first posted before it and no
later in history). A review posted more than once is one review, wherever its
copies were posted. The count starts
again after an action (the safe fallback taken, a split), and
`mechanism_repeats` is given only while the head is the latest record's commit.
"In a row" is by the pull request's history, as the rule choice ranks records
(#426): the head newest, then by posting.
"""

import pytest

from changelog_notes import since_0110
from test_merge_check import EARLIER, HEAD, check, comment, project, rec  # noqa: F401 (project is a fixture)
from test_merge_check_passes import KIT, MIDDLE, review_reasons
from test_merge_check_rule2 import BLOCKS, ELSEWHERE as OTHER, KEPT, NOTE, TICKET, new, with_records

PART = BLOCKS["mechanism"]
COVERED = {**BLOCKS, "covered": True}
KEPT_1 = [{"outcome": "contested", "finding": 1, "ruling": "kept"}]
OVERTURNED_1 = [{"outcome": "contested", "finding": 1, "ruling": "overturned"}]
FELL_BACK = [{"outcome": "fail-closed", "mechanism": PART}]
SPLIT_OUT = [{"outcome": "split", "mechanism": PART, "issue": 470}]


def repeats(got):
    return [r for r in review_reasons(got) if r["id"] == "mechanism_repeats"]


def nexts(got):
    return [(r["mechanism"], r.get("next")) for r in repeats(got)]


def run(project, capsys, *recs, rounds="3"):
    got, code = check(project, capsys, with_records(*recs), "--review-rounds", rounds)
    assert code == 0
    return got


# ---------- what comes next ----------


def test_a_covered_part_blocking_twice_takes_the_safe_fallback(project, capsys):
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2))
    assert got["decision"] == "not_yet"
    [r] = review_reasons(got)  # in place of review_not_clean: the session acts on it
    assert (r["id"], r["mechanism"], r["next"], r["action"], r["round"]) == ("mechanism_repeats", PART, "fail_closed", "review", 2)


def test_a_part_the_bar_doesnt_cover_is_split(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2))
    assert nexts(got) == [(PART, "split")]
    assert [r["id"] for r in review_reasons(got)] == ["mechanism_repeats"]


def test_the_latest_reviewer_says_whether_the_bar_covers_it(project, capsys):
    # The earlier review marked it covered; the latest didn't: split.
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2))
    assert nexts(got) == [(PART, "split")]
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([COVERED], rnd=2))
    assert nexts(got) == [(PART, "fail_closed")]


def test_fail_closed_then_split_then_none(project, capsys):
    first = [new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2, commit=MIDDLE)]
    # The safe fallback taken (the next review records it), and the part blocks twice again: split.
    second = [new([COVERED], rnd=3, commit=MIDDLE, outcomes=FELL_BACK), new([COVERED], kind="pass", rnd=3, commit=MIDDLE)]
    assert nexts(run(project, capsys, *first[:1], new([COVERED], rnd=2))) == [(PART, "fail_closed")]
    assert nexts(run(project, capsys, *first, *second[:1], new([COVERED], kind="pass", rnd=3))) == [(PART, "split")]
    # Split out too, and it blocks twice again: nothing more; the review goes on.
    third = [new([COVERED], kind="pass", rnd=3, commit=MIDDLE, outcomes=SPLIT_OUT), new([COVERED], kind="pass", rnd=3)]
    got = run(project, capsys, *first, *second, *third)
    [r] = review_reasons(got)
    assert r["id"] == "mechanism_repeats" and r["mechanism"] == PART and "next" not in r


def test_a_part_split_out_earlier_isnt_split_again(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, commit=MIDDLE, outcomes=SPLIT_OUT),
              new([BLOCKS], kind="pass", rnd=2, commit=MIDDLE), new([BLOCKS], kind="pass", rnd=2), rounds="2")
    [r] = repeats(got)
    assert "next" not in r


def test_on_a_split_made_ticket_the_safe_fallback_then_nothing_more(project, capsys):
    assert nexts(run(project, capsys, new([COVERED], rnd=1, commit=EARLIER, split=True), new([COVERED], rnd=2, split=True))) == [(PART, "fail_closed")]
    assert nexts(run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER, split=True), new([BLOCKS], rnd=2, split=True))) == [(PART, None)]
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER, split=True), new([COVERED], rnd=2, commit=MIDDLE, split=True),
              new([COVERED], rnd=3, commit=MIDDLE, outcomes=FELL_BACK, split=True), new([COVERED], kind="pass", rnd=3, split=True))
    assert nexts(got) == [(PART, None)]


# ---------- what counts ----------


def test_one_blocking_review_is_no_repeat(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=2))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]


@pytest.mark.parametrize("name", ["The requeue order", "the requeue-order", "requeue order", "the requeue  order"])
def test_names_are_compared_exactly(project, capsys, name):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([{**BLOCKS, "mechanism": name}], rnd=2))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]


@pytest.mark.parametrize("security", ["change", "main"])
def test_security_findings_never_count(project, capsys, security):
    secret = {**BLOCKS, "mechanism": "token scope", "security": security, "area": PART}
    for recs in ([new([secret], rnd=1, commit=EARLIER), new([secret], rnd=2)],
                 [new([BLOCKS], rnd=1, commit=EARLIER), new([secret], rnd=2)],
                 [new([secret], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2)]):
        got = run(project, capsys, *recs)
        assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"], recs


@pytest.mark.parametrize("found", [[{**BLOCKS, "mark": "note"}, OTHER], [{**BLOCKS, "mark": "ticket", "issue": 471}, OTHER], [TICKET, NOTE, OTHER]])
def test_a_note_or_a_ticket_on_the_part_breaks_the_run(project, capsys, found):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new(found, rnd=2, commit=MIDDLE), new([BLOCKS], rnd=3))
    assert not repeats(got)


def test_a_kept_contest_counts_once(project, capsys):
    # Round 2's only finding on the part is round 1's, kept: it neither counts nor breaks the run.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([KEPT], rnd=2, outcomes=KEPT_1))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([KEPT], rnd=2, commit=MIDDLE, outcomes=KEPT_1), new([BLOCKS], rnd=3))
    assert nexts(got) == [(PART, "split")]


def test_a_review_with_a_kept_contest_and_a_new_finding_on_the_part_counts(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([KEPT, BLOCKS], rnd=2, outcomes=KEPT_1))
    assert nexts(got) == [(PART, "split")]


def test_an_overturned_finding_counts_for_nothing(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, outcomes=OVERTURNED_1))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]
    # Only that finding: another on the part in the same review still counts.
    got = run(project, capsys, new([BLOCKS, BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, outcomes=OVERTURNED_1))
    assert nexts(got) == [(PART, "split")]


def test_a_contest_is_read_against_the_review_just_before_it(project, capsys):
    # Round 3 overturns round 2's finding 1 (the other part), so round 2's finding on the part still counts.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([OTHER, BLOCKS], rnd=2, commit=MIDDLE),
              new([BLOCKS], rnd=3, outcomes=OVERTURNED_1))
    assert nexts(got) == [(PART, "split")]


@pytest.mark.parametrize("action", [FELL_BACK, SPLIT_OUT], ids=["fail-closed", "split"])
def test_the_count_starts_again_after_an_action(project, capsys, action):
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2, outcomes=action))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]


def test_an_action_on_another_part_doesnt_restart_this_ones(project, capsys):
    other = [{"outcome": "fail-closed", "mechanism": "the label sync"}]
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2, outcomes=other))
    assert nexts(got) == [(PART, "fail_closed")]


def test_an_old_rule_record_between_breaks_the_run(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), rec(rnd=2, commit=MIDDLE, clean=False), new([BLOCKS], rnd=3))
    assert not repeats(got)


def test_rounds_and_passes_alike(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=3, commit=EARLIER), new([BLOCKS], kind="pass", rnd=3))
    assert nexts(got) == [(PART, "split")]
    assert [r["id"] for r in review_reasons(got)] == ["mechanism_repeats"]


def test_each_part_that_repeats_has_its_own_reason(project, capsys):
    got = run(project, capsys, new([BLOCKS, {**OTHER, "covered": True}], rnd=1, commit=EARLIER), new([{**OTHER, "covered": True}, BLOCKS], rnd=2))
    assert nexts(got) == [("the label sync", "fail_closed"), (PART, "split")]


# ---------- only on the latest record's head ----------


def test_none_once_the_head_has_moved_past_the_latest_record(project, capsys):
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2, commit=MIDDLE))
    assert not repeats(got)
    assert [(r["id"], r.get("next")) for r in review_reasons(got)] == [("review_not_clean", "round")]


def test_in_a_row_is_by_the_history_not_by_posting(project, capsys):
    # Posted head first, the earlier commit's record late: still two in a row.
    got = run(project, capsys, new([BLOCKS], rnd=2), new([BLOCKS], rnd=1, commit=EARLIER))
    assert nexts(got) == [(PART, "split")]
    # A late record for a commit between them, on another part, breaks the run.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=3), new([OTHER], rnd=2, commit=MIDDLE))
    assert not repeats(got)


def test_a_late_record_for_an_older_commit_doesnt_hide_the_head(project, capsys):
    # The latest record by history is still the head's, though another was posted after it.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2), new([NOTE], rnd=1, commit=EARLIER))
    assert not repeats(got)  # by history: EARLIER (blocks), EARLIER (note), HEAD: the note broke the run
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, commit=MIDDLE), new([BLOCKS], rnd=3),
              new([NOTE], rnd=1, commit=EARLIER))
    assert nexts(got) == [(PART, "split")]


def test_records_from_accounts_without_write_access_dont_count(project, capsys):
    data = with_records(new([BLOCKS], rnd=2))
    data["comments"].insert(0, comment(new([BLOCKS], rnd=1, commit=EARLIER), author="stranger", cid=99))
    got, _ = check(project, capsys, data, "--review-rounds", "3")
    assert not repeats(got)


# ---------- the words ----------


@pytest.mark.parametrize("recs, case", [
    (lambda: [new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2)], "fail_closed"),
    (lambda: [new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2)], "split"),
    (lambda: [new([BLOCKS], rnd=1, commit=EARLIER, split=True), new([BLOCKS], rnd=2, split=True)], None),
], ids=["fail-closed", "split", "none"])
def test_what_a_person_reads_says_the_part_and_the_safe_fallback(project, capsys, recs, case):
    [r] = repeats(run(project, capsys, *recs()))
    assert r.get("next") == case
    for level in ("new", "developer"):
        words = r["wording"][level]["message"] + " " + r["wording"][level]["fix"]
        assert f"the part `{PART}`" in words and "mechanism" not in words, words
        assert "the safe fallback" in words, words
    if case == "split":
        assert "split" in r["wording"]["new"]["fix"].lower()


def test_the_text_answer_names_the_part(project, capsys):
    out, _ = check(project, capsys, with_records(new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2)), "--review-rounds", "3", as_json=False)
    assert out.startswith("Not yet") and f"- The part `{PART}` has a blocking finding in 2 reviews in a row" in out


# ---------- docs ----------


def test_the_changelog_notes_it():
    assert "(#427, part of spec #412)" in since_0110()


def test_the_merge_check_skill_names_the_reason_and_its_next():
    text = (KIT / "skills/merge-check/SKILL.md").read_text(encoding="utf-8")
    assert "`mechanism_repeats`" in text
    for word in ("`fail_closed`", "`split`", "the safe fallback", "its `then`: `round` or `pass`", "fixing the review's other blocking findings as well"):
        assert word in text, word


# ---------- round 1's findings ----------


@pytest.mark.parametrize("rounds, then", [("3", "round"), ("2", "pass")])
def test_then_says_which_review_follows(project, capsys, rounds, then):
    # The round limit still chooses the review's shape: round 2 of 3 is followed by a round; of 2, by a pass.
    for split in (False, True):
        got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER, split=split), new([BLOCKS], rnd=2, split=split), rounds=rounds)
        [r] = repeats(got)
        assert r["then"] == then, (split, r)


def test_then_after_a_pass_is_a_pass(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=3, commit=EARLIER), new([BLOCKS], kind="pass", rnd=3))
    [r] = repeats(got)
    assert r["then"] == "pass"


@pytest.mark.parametrize("copy", ["same", "corrected"])
def test_a_review_posted_twice_counts_once(project, capsys, copy):
    second = new([BLOCKS], rnd=1) if copy == "same" else new([BLOCKS, NOTE], rnd=1)
    got = run(project, capsys, new([OTHER], rnd=1, commit=EARLIER), new([BLOCKS], rnd=1), second, rounds="1")
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]
    assert not repeats(run(project, capsys, new([BLOCKS], rnd=1), new([BLOCKS], rnd=1)))


def test_two_passes_on_one_commit_with_other_findings_are_two_reviews(project, capsys):
    # A fixer may contest everything and push nothing: the next pass is on the same commit, and is a review of its own.
    got = run(project, capsys, new([BLOCKS], rnd=3, commit=EARLIER), new([BLOCKS, OTHER], kind="pass", rnd=3),
              new([BLOCKS], kind="pass", rnd=3, outcomes=[{"outcome": "contested", "finding": 2, "ruling": "overturned"}]))
    assert nexts(got) == [(PART, "split")]


def test_a_ruling_is_read_against_the_review_posted_before_it(project, capsys):
    # Round 2 on the head overturns round 1's finding; a pass for MIDDLE is posted late, after it. By history the
    # pass comes between them, but the ruling is about round 1, the review posted before it.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, outcomes=OVERTURNED_1),
              new([BLOCKS], kind="pass", rnd=1, commit=MIDDLE))
    assert nexts(got) == [(PART, "split")]


def test_a_kept_contest_beside_a_note_on_the_part_breaks_the_run(project, capsys):
    # The review's only finding on the part isn't the kept contest: the note is one too.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([KEPT, {**NOTE, "mechanism": PART}], rnd=2, commit=MIDDLE, outcomes=KEPT_1),
              new([BLOCKS], rnd=3))
    assert not repeats(got)


def test_a_merge_of_the_base_waits_for_the_next_review(project, capsys):
    # The head merges the base into MIDDLE and leaves the pull request's own changes as they were: MIDDLE's
    # review covers it (`review_carried`), but the head isn't the latest record's commit, so no breaker: the
    # usual reason asks for the next review, which reports the part again if it still blocks.
    from test_merge_check_carry_over import MIDDLE as MERGED_INTO, REVIEWED, hashes_of, merged_in
    from test_merge_check_passes import records

    reviewed = hashes_of(project, capsys, REVIEWED)
    data = merged_in(REVIEWED)
    data["comments"] = records(new([BLOCKS], rnd=1, commit=EARLIER, hashes=reviewed), new([BLOCKS], rnd=2, commit=MERGED_INTO, hashes=reviewed))
    got, _ = check(project, capsys, data, "--review-rounds", "3")
    assert "review_carried" in [n["id"] for n in got["notes"]], got
    assert not repeats(got) and [(r["id"], r.get("next")) for r in review_reasons(got)] == [("review_not_clean", "round")]


def test_the_words_name_the_other_findings_and_the_limits(project, capsys):
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS, OTHER], rnd=2))
    [r] = repeats(got)
    assert "other" in r["wording"]["new"]["fix"] and "other blocking findings" in r["wording"]["developer"]["fix"]
    [r] = repeats(run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER, split=True), new([BLOCKS], rnd=2, split=True)))
    assert "10 reviews" in r["wording"]["developer"]["fix"] and "end time" in r["wording"]["developer"]["fix"]


# ---------- round 2's findings ----------


def test_a_ruling_posted_twice_overturns_once(project, capsys):
    # Round 2 overturns round 1's finding 1 (the other part), and is posted again: the copy's ruling is about round 1 too.
    for rnd, rounds, kind in ((2, "3", "round"), (3, "3", "pass")):
        first = new([OTHER, BLOCKS], rnd=1 if kind == "round" else 3, commit=EARLIER)
        ruling = new([BLOCKS], kind=kind, rnd=rnd, outcomes=OVERTURNED_1)
        assert nexts(run(project, capsys, first, ruling, rounds=rounds)) == [(PART, "split")]
        assert nexts(run(project, capsys, first, ruling, ruling, rounds=rounds)) == [(PART, "split")], kind


def test_a_late_copy_before_a_ruling_doesnt_take_it(project, capsys):
    # Round 3 overturns round 2's finding on the part; round 1 was posted again, late, just before it.
    got = run(project, capsys, new([OTHER], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, commit=MIDDLE),
              new([OTHER], rnd=1, commit=EARLIER), new([BLOCKS], rnd=3, outcomes=OVERTURNED_1))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]


def test_a_late_copy_of_a_ruling_doesnt_rule_on_a_later_review(project, capsys):
    # Round 2 overturns round 1's finding 1; a copy of round 2 is posted after round 3, on the head.
    got = run(project, capsys, new([OTHER, BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, commit=MIDDLE, outcomes=OVERTURNED_1),
              new([BLOCKS], rnd=3), new([BLOCKS], rnd=2, commit=MIDDLE, outcomes=OVERTURNED_1))
    assert nexts(got) == [(PART, "split")]
    # A late re-post of a review that ruled on the one before it never rules on a later commit's review: round 2
    # (overturning round 1's other part) is posted again after round 3, whose finding 1 is the part.
    got = run(project, capsys, new([OTHER, BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, commit=MIDDLE, outcomes=OVERTURNED_1),
              new([BLOCKS, OTHER], rnd=3), new([BLOCKS], rnd=2, commit=MIDDLE, outcomes=OVERTURNED_1))
    assert nexts(got) == [(PART, "split")]


def test_an_old_rule_record_posted_late_between_doesnt_take_a_ruling(project, capsys):
    # Round 1 on MIDDLE; an old-rule record for EARLIER posted late; round 2 on the head overturns round 1's finding
    # on the part, so round 1 counts for nothing.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=MIDDLE), rec(rnd=1, commit=EARLIER, clean=False),
              new([BLOCKS], rnd=2, outcomes=OVERTURNED_1))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]


@pytest.mark.parametrize("rounds, then", [("3", "round"), ("2", "pass")])
def test_the_text_names_the_review_that_follows(project, capsys, monkeypatch, rounds, then):
    data = with_records(new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2))
    said = {"round": ("run another round", "ask for another review"),
            "pass": ("run a Correctness pass on the head", "ask for a short check of the latest changes")}[then]
    for level, words in zip(("developer", "new"), said):
        monkeypatch.setenv("WORKFLOW_EXPERIENCE", level)
        out, _ = check(project, capsys, data, "--review-rounds", rounds, as_json=False)
        assert words in out, (level, out)


def test_the_new_words_read_as_a_sentence(project, capsys):
    [r] = repeats(run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2)))
    assert r["wording"]["new"]["message"].startswith(f"Not yet: the part `{PART}` blocked 2 reviews in a row,")


def test_two_parts_at_once_dont_ask_to_fix_each_other(project, capsys):
    got = run(project, capsys, new([BLOCKS, OTHER], rnd=1, commit=EARLIER), new([BLOCKS, OTHER], rnd=2))
    for r in repeats(got):
        assert "other than the parts this answer names" in r["wording"]["developer"]["fix"]
        assert "other than the parts this answer names" in r["wording"]["new"]["fix"]


# ---------- round 3's findings ----------


def test_a_ruling_survives_its_target_posted_again_after_it(project, capsys):
    # Round 2 overturns round 1's finding on the part; round 1 is then posted again (a missed record re-posted).
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, outcomes=OVERTURNED_1),
              new([BLOCKS], rnd=1, commit=EARLIER))
    assert not repeats(got) and [r["id"] for r in review_reasons(got)] == ["review_not_clean"]


def test_a_copy_of_a_ruling_posted_after_another_review_on_its_commit_rules_as_its_original(project, capsys):
    # Round 2 on the head overturns round 1's finding; a pass on the head; then round 2 posted again. The copy's
    # ruling is round 2's, about round 1, never about the pass.
    first = [new([OTHER, BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, outcomes=OVERTURNED_1), new([BLOCKS], kind="pass", rnd=2)]
    want = nexts(run(project, capsys, *first, rounds="2"))
    assert want == [(PART, "split")]
    assert nexts(run(project, capsys, *first, new([BLOCKS], rnd=2, outcomes=OVERTURNED_1), rounds="2")) == want


@pytest.mark.parametrize("case", ["revives", "between", "count"])
def test_a_copy_posted_anywhere_later_counts_once(project, capsys, case):
    if case == "revives":
        # A note on the part between a review and its late copy still breaks the run.
        recs = [new([OTHER], rnd=1, commit=EARLIER), new([BLOCKS], kind="pass", rnd=1, commit=MIDDLE), new([NOTE | {"mechanism": PART}], kind="pass", rnd=1, commit=MIDDLE),
                new([BLOCKS], rnd=2)]
        copy, at = new([BLOCKS], kind="pass", rnd=1, commit=MIDDLE), 3
    elif case == "between":
        recs = [new([OTHER], rnd=1, commit=EARLIER), new([TICKET | {"mechanism": PART}], rnd=2), new([BLOCKS], kind="pass", rnd=2), new([BLOCKS], rnd=3)]
        copy, at = new([TICKET | {"mechanism": PART}], rnd=2), 3
    else:
        recs = [new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2), new([BLOCKS], kind="pass", rnd=2)]
        copy, at = new([BLOCKS], rnd=2), 3
    once = run(project, capsys, *recs)
    twice = run(project, capsys, *recs[:at], copy, *recs[at:])
    assert [(r["id"], r.get("next"), r.get("mechanism")) for r in review_reasons(twice)] == [(r["id"], r.get("next"), r.get("mechanism")) for r in review_reasons(once)]
    if case == "count":
        [r] = repeats(twice)
        assert "3 reviews in a row" in r["wording"]["developer"]["message"]


def test_the_skill_says_to_act_on_the_breaker_before_updating_the_branch():
    text = (KIT / "skills/merge-check/SKILL.md").read_text(encoding="utf-8")
    assert "act on it before bringing the branch up to date" in text


def test_posting_any_review_again_later_never_changes_the_breaker(project, capsys):
    # A fixed set of made-up histories (seeded, so it never fails by chance): a copy of any record, posted at any
    # later place, leaves the breaker's answer as it was. Each round has its own number, so a copy is never a
    # correction.
    import random

    rng = random.Random(427)
    found = [[BLOCKS]] * 4 + [[COVERED], [BLOCKS, OTHER], [OTHER, BLOCKS], [NOTE | {"mechanism": PART}], [TICKET | {"mechanism": PART}], [], [BLOCKS, BLOCKS]]
    outcomes = [[], [], [], OVERTURNED_1, FELL_BACK, SPLIT_OUT]
    kept = [([KEPT], KEPT_1), ([KEPT, BLOCKS], KEPT_1)]  # a kept contest re-entered, with its ruling
    fired = 0
    for trial in range(80):
        recs, rnd, split = [], rng.randint(0, 2), rng.random() < 0.2
        for commit in sorted(rng.choices([EARLIER, MIDDLE, HEAD], k=rng.randint(2, 5)), key=[EARLIER, MIDDLE, HEAD].index):
            kind = "round" if not recs or rng.random() < 0.5 else "pass"
            rnd += kind == "round"
            what, ruled = rng.choice(kept) if recs and rng.random() < 0.2 else (rng.choice(found), rng.choice(outcomes))
            recs.append(new(what, kind=kind, rnd=rnd, commit=commit, outcomes=ruled, split=split))
        if rng.random() < 0.3:  # sometimes a record posted late, for an older commit
            recs.insert(rng.randrange(len(recs)), recs.pop())
        at = rng.randrange(len(recs))
        later = rng.randint(at + 1, len(recs))
        twice = recs[:later] + [recs[at]] + recs[later:]
        once_got, twice_got = (run(project, capsys, *r) for r in (recs, twice))
        said = [[(r["mechanism"], r.get("next"), r["wording"]["developer"]["message"]) for r in repeats(got)] for got in (once_got, twice_got)]
        assert said[1] == said[0], (trial, at, later)
        fired += bool(repeats(once_got))
    assert fired >= 10  # the histories reach the breaker


# ---------- Correctness pass 1's findings ----------


@pytest.mark.parametrize("between", [False, True])
def test_a_corrected_copy_is_read_as_the_review(project, capsys, between):
    # Round 2 on the head is posted again, corrected: only a note on the part. Its latest copy is the review, so the
    # note breaks the run, whether the correction comes right after it or after a pass on the head.
    first = [new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2)]
    middle = [new([BLOCKS], kind="pass", rnd=2)] if between else []
    got = run(project, capsys, *first, *middle, new([NOTE | {"mechanism": PART}], rnd=2))
    assert not repeats(got)
    # And the other way: the correction adds the part.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([OTHER], rnd=2), *middle, new([BLOCKS], rnd=2))
    assert nexts(got) == [(PART, "split")]


def test_a_corrected_copy_without_an_action_takes_it_back(project, capsys):
    # Round 2 was posted with the safe fallback taken by mistake, then corrected without it: the part hasn't
    # taken that form, so the count runs on and the safe fallback is next.
    got = run(project, capsys, new([COVERED], rnd=1, commit=EARLIER), new([COVERED], rnd=2, commit=MIDDLE, outcomes=FELL_BACK),
              new([COVERED], rnd=2, commit=MIDDLE), new([COVERED], rnd=3))
    assert nexts(got) == [(PART, "fail_closed")]
    [r] = repeats(got)
    assert "3 reviews in a row" in r["wording"]["developer"]["message"]


def test_a_corrected_copy_without_the_split_flag_takes_it_back(project, capsys):
    # Round 2 was posted saying the ticket was made by a split, then corrected: the ticket wasn't, so split.
    got = run(project, capsys, new([BLOCKS], rnd=1, commit=EARLIER), new([BLOCKS], rnd=2, commit=MIDDLE, split=True),
              new([BLOCKS], rnd=2, commit=MIDDLE), new([BLOCKS], rnd=3))
    assert nexts(got) == [(PART, "split")]

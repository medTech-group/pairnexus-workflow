"""#686, split out of #664: a session staying for its evidence report
(`build-ticket` §6 step 5) on a pull request still open, left with the owner,
merges the base in when `WF merge-check` gives a `conflict`, and the conductor
keeps it until that merge is pushed and the next `WF merge-check` acted on.

#683 tried this twice. Round 1: §4's watch merged the base in while §6 step 5
said to leave the checkout as it is, two answers. Round 2: the session posted
"Evidence for `<sha>`: no report" before merging, and the conductor's hold,
counting nothing still to come once that note was up, archived the session
before the merge was pushed. Here §4 and §6 step 5 give one answer, the session
posts a conflict note before it merges, posts no "no report" for the run it
stops, and the hold counts from that note and the pushes after it until the
session's next note. Both skills are read as text contracts (seam 2)."""

import re
from pathlib import Path

from changelog_notes import since_0110

KIT = Path(__file__).resolve().parents[1]
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
CONDUCTOR = KIT / "skills/conductor/SKILL.md"
WATCH = "**Every waiting check-in watches the base.**"
CONFLICT = "**A conflict while you stay.**"
NOTE = "#<n>: merging the base in for a conflict on #<PR>"
HOLD = "**Keeping a session for its evidence report**"
HOLD_CONFLICT = "**A conflict while it stays**"


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _section(text, start, end):
    assert start in text, start
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _watch():
    four = _section(BUILD_TICKET.read_text(), "## 4. Open the pull request", "## 5. Get it green")
    i = four.index(WATCH)
    end = four.find("\n\n", i)
    return _flat(four[i:end if end != -1 else len(four)])


def _step5():
    six = _section(BUILD_TICKET.read_text(), "## 6. Post the evidence and merge", "## 7. End each turn")
    return _flat(_section(six, "\n5. **", "\n6. **"))


def _stay():
    five = _step5()
    return five[five.index("**Then stay**"):five.index(CONFLICT)]


def _conflict():
    five = _step5()
    return five[five.index(CONFLICT):]


def _hold():
    return _flat(_section(CONDUCTOR.read_text(), HOLD, "**The merge queue's state.**"))


def _hold_conflict():
    hold = _hold()
    i = hold.index(HOLD_CONFLICT)
    nxt = hold.find("- **", i + len(HOLD_CONFLICT))
    return hold[i:nxt if nxt != -1 else len(hold)]


# ---------- build-ticket: §4 and §6 step 5 give one answer ----------


def test_the_watch_no_longer_stops_at_the_stay():
    # round 1 of #683: §4 merged the base in, §6 step 5 left the checkout alone
    p = _watch()
    assert "This watch doesn't apply while you stay for your evidence report" not in p
    assert (
        "While you stay for your evidence report, §6 step 5's \"Then stay\" says what the stay does, and it gives "
        "the same answer: with the pull request still open, a `conflict` is merged in as above, the run stopped "
        "first and started again after (step 5's \"A conflict while you stay\")."
    ) in p


def test_the_stay_leaves_the_checkout_as_it_is_except_as_the_conflict_bullet_says():
    # round 1 of #686: an exception for the merge of the base alone forbade the
    # fixes the conflict bullet's next `WF merge-check` can ask for (a red
    # check, a Correctness pass's findings)
    stay = _stay()
    assert "except to merge the base in for a conflict" not in stay
    assert (
        "Leave your checkout as it is (no pull, no edit: the run stops if your head moves), except as \"A conflict "
        "while you stay\" says (below), schedule a check-in, and end the turn `waiting`."
    ) in stay
    # the bullet it points at is the one that acts on the next `WF merge-check`, as step 3 says
    assert "act on the next `WF merge-check` as step 3 says" in _conflict()


def test_a_conflict_while_you_stay_merges_the_base_in_as_section_4_says():
    c = _conflict()
    assert (
        "While the pull request is still open (left with the owner: `owner` mode's `ready`, `owner_review`, a "
        "`queue_unsure` note's `ready`, §5's path-filtered check), each check-in of the stay runs `WF merge-check` "
        "on the head, with step 3's flags, as §4's \"Every waiting check-in watches the base\" does"
    ) in c
    assert "acts only on a `conflict` reason: anything else stays with the owner" in c
    assert "merge the base in at once as §4 says" in c
    assert "never a rebase or force-push" in c
    assert "in a `CHANGELOG.md` conflict, keep both sides: every note from each" in c
    assert "Rerun the affected tests and push." in c


def test_the_session_posts_its_conflict_note_before_it_touches_the_checkout():
    # round 2 of #683: the conductor must hold the session from before the merge
    c = _conflict()
    note = c.index(f"post \"{NOTE}\" on the tracking issue")
    stop = c.index("stop the run (step 2's \"While it runs\")")
    merge = c.index("merge the base in at once as §4 says")
    assert note < stop < merge


def test_the_run_is_stopped_first_and_started_again_after_with_no_no_report():
    # the merge doesn't always stop the run by itself (its base comparison): stop it
    c = _conflict()
    assert "stop the run (step 2's \"While it runs\")" in c
    assert "start the run again on the new head (step 2's \"When it stops because your head moved\")" in c
    assert "The run you stopped is no \"no report\": post none for its head." in c


def test_the_session_acts_on_the_next_merge_check_until_its_note_is_up_again():
    c = _conflict()
    assert (
        "act on the next `WF merge-check` as step 3 says, at each check-in, ending each turn `waiting`, until it "
        "gives the answer that left the pull request with the owner, or it has merged: post that note again on the "
        "tracking issue."
    ) in c
    assert (
        "Until that note is up, never end `done`: a run that ends first gets its report, or its \"no report\" line, "
        "posted as above, and you go on."
    ) in c
    assert "Stopping at `needs-human` (§5) ends it as usual." in c


def test_the_note_posted_again_carries_the_to_come_line_only_while_the_run_is_going():
    # round 1 of #686: the run on the new head ended and its report was posted
    # before the note went up again; a note that still said "to come" made the
    # conductor, which counts only a report posted after that note, keep the
    # finished session to its limit and say the report was never posted
    c = _conflict()
    assert "with the line naming the run's head now, and stay as above" not in c
    assert (
        "While the run is still going, the note carries the line naming the run's head now, and you stay as above."
    ) in c
    assert (
        "Once the run has ended, its report or its \"no report\" line posted, the note carries no such line, since a "
        "report posted before it never counts for it, and you end `done`."
    ) in c
    going = c.index("While the run is still going, the note carries the line")
    ended = c.index("Once the run has ended, its report or its \"no report\" line posted")
    assert c.index("post that note again on the tracking issue.") < going < ended
    # the conductor reads a note without the line as nothing still to come
    hold = _hold()
    assert "a comment there, posted after that note" in hold
    assert "A note without that line leaves nothing to come." in hold


def test_the_stay_names_the_conductors_hold_for_the_conflict():
    c = _conflict()
    assert "the conductor keeps your session from that note until your next one (its \"A conflict while it stays\")" in c


# ---------- the conductor: the hold keeps the session through the merge ----------


def test_the_hold_has_the_conflict_bullet_with_the_same_note():
    h = _hold_conflict()
    assert "(`build-ticket` §6 step 5)" in h
    assert f"posting \"{NOTE.replace('#<n>', '#n').replace('#<PR>', '#PR')}\" on the tracking issue first" in h


def test_from_the_conflict_note_the_report_is_still_to_come_whatever_else_is_posted():
    # round 2 of #683: the "no report" note let the archive come before the push
    h = _hold_conflict()
    assert (
        "From that note, the report is still to come, whatever the bullets above say, a \"no report\" note and "
        "a note without the line included"
    ) in h
    assert (
        "until the session's next note after it that the pull request is ready or the owner's to merge, or its "
        "\"#n merged in #PR\": that note is then its latest note, read as above"
    ) in h


def test_the_limit_counts_from_the_conflict_note_and_the_pushes_after_it():
    # its timing: a conflict near the end of the 180 minutes never cuts it off
    h = _hold_conflict()
    assert (
        "Until that next note, the limit counts from the later of the conflict note and the last push to the pull "
        "request's branch, never from the earlier note"
    ) in h


CONDUCTOR_LINE = "#n: #PR conflicts with the base, its session kept to merge it in"


def test_before_the_session_notices_the_limit_counts_from_the_first_check_in_that_saw_the_conflict():
    # round 1 of #686: one interval of grace from the earlier note lost the race.
    # With check-ins every 20 minutes, the conflict at T0+179, the session's
    # next check-in near T0+201 and the conductor's at T0+200.5, the session
    # was archived before its conflict note.
    h = _hold_conflict()
    assert "180 minutes plus the charter's `limits.check_in_minutes`" not in h
    assert (
        "Before any conflict note, while your `WF merge-check` on its open pull request gives a `conflict` reason, "
        "the limit counts from the later of the session's latest note and the first of your check-ins that saw the "
        "conflict:"
    ) in h
    assert (
        f"at that check-in, post \"{CONDUCTOR_LINE}\" on the tracking issue, unless that line is up since the "
        "session's latest note, and count from that line's `created_at`."
    ) in h
    assert (
        "The conflict can come just before the limit, and the session's check-in a full interval after it, so a "
        "grace from the earlier note alone could archive the session before its conflict note."
    ) in h
    # the line is the conductor's, never the session's conflict note
    assert CONDUCTOR_LINE != NOTE.replace("#<n>", "#n").replace("#<PR>", "#PR")


def test_the_conductors_conflict_line_still_has_a_limit():
    # the other side: with no conflict the limit is the usual one, and from the
    # conductor's line it is still 180 minutes, past which the archive comes
    h = _hold_conflict()
    assert h.index("Before any conflict note, while your `WF merge-check`") < h.index(CONDUCTOR_LINE)
    hold = _hold()
    assert "**The limit:** 180 minutes since that note was posted (its `created_at`)" in hold
    assert "Past it, archive the session all the same" in hold
    assert "never by a count of check-ins" in hold


def test_the_hold_still_says_where_its_limit_runs_out():
    hold = _hold()
    assert "Past it, archive the session all the same" in hold
    assert hold.index(HOLD_CONFLICT) > hold.index("**The limit:**")


# ---------- changelog ----------


def test_changelog_notes_686_without_bumping_version():
    notes = since_0110()
    assert "(#686, split out of #664)" in notes
    assert "merging the base in for a conflict" in notes
    log = (KIT / "CHANGELOG.md").read_text()
    released = re.findall(r"^## (\d+\.\d+\.\d+)$", log, re.M)
    assert (KIT / "VERSION").read_text().strip() == released[0]

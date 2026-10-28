"""#361: the owner's "also #<n>" sends a pull request that needs a code fix back to a ticket session.
Seams: `workflow state put` (the ticket's `requeued_head`) and the conductor skill's lines: its one table of
cases ("A pull request that needs a code fix") and the places that point to it."""

import json
import os
import re
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT
from workflow import charter, state

CLI = KIT / "scripts/workflow.py"
SHA = "0123456789abcdef0123456789abcdef01234567"


def _text(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _conductor():
    return _flat(_text("skills/conductor/SKILL.md"))


def _section(text, start, end):
    assert start in text, start
    return text.split(start, 1)[1].split(end, 1)[0]


def _requeue():
    return _section(_text("skills/conductor/SKILL.md"), "## A pull request that needs a code fix\n", "\n## ")


def _row(n):
    rows = [ln for ln in _requeue().splitlines() if ln.startswith(f"| {n} | ")]
    assert len(rows) == 1, n
    return rows[0]


# ---------- `workflow state put`: the ticket's `requeued_head` ----------


def _put(tmp_path, head):
    c = charter.defaults(["deploy staging"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["tickets"] = {"12": {"status": "queued", "attempts": 0, "requeued_head": head}}
    (tmp_path / "s.json").write_text(json.dumps(s))
    (tmp_path / "body.md").write_text("# Run\n")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run(
        [sys.executable, str(CLI), "state", "put", "--body", "body.md", "--state", "s.json", "--out", "out.md"],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )


def test_state_put_keeps_a_full_requeued_head(tmp_path):
    r = _put(tmp_path, SHA)
    assert r.returncode == 0, r.stderr
    assert SHA in (tmp_path / "out.md").read_text()


@pytest.mark.parametrize("head", ["0123456", SHA.upper(), SHA + "0", "", 5, ["x"]])
def test_state_put_refuses_a_requeued_head_that_isnt_a_full_sha(tmp_path, head):
    r = _put(tmp_path, head)
    assert r.returncode != 0
    assert "tickets[12].requeued_head must be a full commit SHA in lower case" in r.stdout + r.stderr
    assert not (tmp_path / "out.md").exists()


def test_a_cleared_requeued_head_is_fine():
    s = state.empty(charter.defaults([]))
    s["tickets"] = {"12": {"status": "queued", "requeued_head": None}}
    assert not [p for p in state.validate(s) if "requeued_head" in p]


# ---------- the requeue: "also #<n>" on an open pull request ----------


def test_also_for_a_code_fix_requeues_the_ticket_with_its_pull_request_in_the_briefing():
    text = _flat(_requeue())
    assert "The owner's \"also #<n>\" for a ticket whose open pull request needs a code fix" in text
    assert "You write no code for it: the ticket goes back to a ticket session, on the same pull request." in text
    briefing = _section(text, "**Its briefing.**", "**The fix is there**")
    for part in (
        "Every briefing of a ticket with `requeued_head` set gives, in its `briefing` slot, that pull request as what a previous attempt left (its branch, number and `requeued_head`)",
        "the fix asked for (the owner's words, or the link to the comment that asks for it)",
        "the session merges, arms auto-merge, queues or says it's ready only once a commit carrying the fix is pushed and a review covers it",
    ):
        assert part in briefing, part
    going_on = _flat(_row(6))
    for part in (
        "The hold, then requeue it:",
        "once no session of it runs, mark it `queued` with `attempts: 0` and no `asked_at`, with `ready-for-agent` and `workflow:in-progress` on it, so it starts at check-in step 5 like any queued ticket",
        "A ticket already requeued is requeued again the same way, its briefing giving every fix asked for.",
    ):
        assert part in going_on, part
    # The briefing's slot says so.
    slots = _section(_conductor(), "## A ticket session's briefing", " ## ")
    assert "and a held pull request's fix (\"A pull request that needs a code fix\")" in slots


def test_an_in_review_ticket_is_requeued_too_and_the_entry_points_lead_here():
    text = _conductor()
    step3 = _section(text, "**3. The owner's words.**", "**4. Each ticket in flight.**")
    assert (
        "**\"also #<n>\" for a ticket whose open pull request needs a code fix** (the owner found one, as a planning "
        "session's `merge-check` hands code fixes to a run), an `in-review` ticket's too: \"A pull request that needs "
        "a code fix\" says what follows, its rows judged once every comment's charter change is applied."
    ) in step3
    named = _section(text, "**A run in progress that this session conducts**", "**A run in progress that another session conducts")
    assert "When its open pull request needs a code fix, whatever its status, \"A pull request that needs a code fix\" says what follows." in named
    # Row 6 has no status of its own: queued, running, in-review and set-aside tickets all take it.
    assert "| 6 | **The run going on** |" in _row(6)


def test_an_earlier_runs_leftover_is_adopted_then_held():
    row = _flat(_row(3))
    for part in (
        "**Not in this run's state,** its open pull request on a `run.ticket_branch` branch (an earlier run's leftover)",
        "Adopt it, as the kick-off adopts a leftover: add it to the state's tickets as `in-review`, with its `pr` and `attempts: 0`, and `workflow:in-progress` on it.",
        "Then rows 4 to 6, as for any ticket of the run.",
        "On any other branch, it isn't this section's: the \"also\" adds it to the plan as usual.",
    ):
        assert part in row, part
    # Merged before it was read comes first, for a leftover too.
    assert _requeue().index("| 2 |") < _requeue().index("| 3 |")


def test_a_needs_human_ticket_stays_an_owners_answer():
    row = _flat(_row(1))
    assert "Not this section's, and no hold: its fix is an owner's answer (check-in step 2's \"When the owner answers\")." in row
    assert "(a `set-aside` ticket labelled `needs-human` included)" in row
    assert "A ticket already held keeps its hold (row 11)." in row
    step3 = _section(_conductor(), "**3. The owner's words.**", "**4. Each ticket in flight.**")
    assert "A `needs-human` ticket's fix (a `set-aside` one labelled `needs-human` included) is an owner's answer" in step3


# ---------- the hold: nothing merges or settles before a review covers the fix ----------


def _hold():
    return _section(_flat(_requeue()), "**The hold,**", "**Its briefing.**")


def test_the_hold_starts_as_soon_as_the_also_is_read():
    hold = _hold()
    for part in (
        "which rows 4 to 6 begin with, at once, before anything else at that check-in",
        "record the pull request's head, its full SHA, as the ticket's `requeued_head`",
        "and write the state",
        "disarm auto-merge if it is armed",
        "if it is in the merge queue, take it out (GitHub's **Remove from queue**), or, where that can't be done here, say so on the tracking issue",
        "check-in step 4's held row",
    ):
        assert part in hold, part
    # Rows 1 and 2 take no hold.
    assert "no hold" in _row(1) and "No hold" in _row(2)


def test_a_session_stopped_by_the_hold_pushes_nothing_that_counts_as_the_fix():
    hold = _hold()
    for part in (
        "if a session of it runs, stop it safely (\"Stopping a stuck session safely\", or \"Stop the run\" step 2 while the run stops), adding no attempt and never labelling it `needs-human`",
        "The ticket keeps its status until that session is archived; then set `requeued_head` to the branch's head as it is then, so nothing that session pushed counts as the fix.",
    ):
        assert part in hold, part
    fix = _section(_flat(_requeue()), "**The fix is there**", "**Its `for_owner` lines.**")
    assert "Never judge it while a session stopped by the hold is still being stopped." in fix
    # Rows 5 and 6 change the status only once no session runs, so no second session starts beside it.
    assert "Once no session of it runs, mark it `in-review` rather than `queued`" in _row(5)
    assert "once no session of it runs, mark it `queued`" in _row(6)


def test_the_held_row_wins_over_every_row_that_merges():
    raw = _text("skills/conductor/SKILL.md")
    held = next(ln for ln in raw.splitlines() if ln.startswith("| **A held pull request**"))
    for part in (
        "This row wins over the `ready` rows, `owner_review`, the path-filtered row, the merge queue row, \"behind the base\", `not_yet`'s `update_branch` and \"The merge queue's state\"'s `ready`",
        "never merge it, update its branch, arm auto-merge on it or queue it, and disarm auto-merge if it is armed",
        "The other rows apply as usual.",
        "If it merged, that section's row 7; while the run winds down with the ticket `queued`, its row 8.",
        "Once the fix is there (that section), clear `requeued_head` and take the rows as usual.",
    ):
        assert part in held, part
    # It sits above the rows it wins over.
    table = raw.split("| What GitHub (or `WF merge-check`) shows | What you do |", 1)[1]
    assert table.index("| **A held pull request**") < table.index("| **Merged** |")
    assert table.index("| **A held pull request**") < table.index("| **`session` mode, `ready`**")


def test_the_fix_is_there_only_with_a_commit_of_its_own_and_a_review_over_it():
    fix = _section(_flat(_requeue()), "**The fix is there**", "**Its `for_owner` lines.**")
    for part in (
        "`WF merge-check` on the pull request gives no reason whose `action` is `review` and no \"couldn't read\" reason",
        "the branch has a commit of its own since `requeued_head`",
        "`git log --first-parent --no-merges --oneline <requeued_head>..origin/<branch>` lists one (a merge of the base brings no fix)",
        "Then clear `requeued_head` and take its fix line out of `for_owner`",
    ):
        assert part in fix, part


# ---------- its interplay: one table of cases ----------


def test_the_table_has_one_row_for_each_case():
    rows = [ln for ln in _requeue().splitlines() if re.match(r"\| \d+ \| ", ln)]
    assert [int(ln.split("|")[1]) for ln in rows] == list(range(1, 12))
    text = _flat(_requeue())
    assert "When you read the \"also\", take the first of rows 1 to 6 that fits" in text
    assert "Rows 7 to 11 cover what happens later, while `requeued_head` is set." in text


def test_rows_are_judged_with_every_charter_change_in():
    text = _flat(_requeue())
    assert (
        "whether the run is stopping or winding down is judged as check-in step 2 judges it, once every change in the "
        "owner's words read with it is applied (a raised `max_sessions` among them)"
    ) in text


def test_winding_down_holds_it_and_starts_nothing():
    row = _flat(_row(5))
    for part in (
        "**The run winding down** (check-in step 2's **Wind down**)",
        "The hold, starting nothing.",
        "Once no session of it runs, mark it `in-review` rather than `queued` (a `set-aside` one stays `set-aside`), so \"Done\" doesn't wait for a session that won't come",
        "write the fix line, and reply that it won't start in this run",
    ):
        assert part in row, part
    # A ticket requeued before the wind-down began, and not started, is held the same way.
    assert "| 8 | **The run winds down while it is `queued`** (no session of it started yet) | Row 5. |" in _requeue()


def test_the_run_stopping_holds_it_and_says_so():
    row = _flat(_row(4))
    for part in (
        "**The run stopping** (its `status` is `stopping`, or check-in step 2's **Stop now** holds)",
        "The hold, starting nothing.",
        "Write the fix line, and reply that the run is stopping",
    ):
        assert part in row, part
    report = _section(_conductor(), "4. **The report.**", "5. **Wind up.**")
    assert (
        "Before the rest too, read the owner's comments not read yet (check-in step 3's *Comments*, setting "
        "`comments_read_through`), applying none (an \"also #<n>\" for a pull request needing a code fix takes "
        "\"A pull request that needs a code fix\"'s row 4; any other change gets the reply that the run has stopped)"
    ) in report
    assert (
        "and after them look again at each ticket with `requeued_head`: that section's row 7 if its pull request "
        "merged, else its fix line written."
    ) in report
    # The sentences #349's tests pin stay, in their order.
    assert report.index("look again at each revert still `opened`") < report.index("Before the rest too") < report.index("First look again at each ticket still marked `cap_unknown_at`")


@pytest.mark.parametrize("stop", ["the `workflow:stop` label", "\"stop the run\" in this chat", "`limits.ends_at` passed"])
def test_each_owners_stop_and_the_end_time_always_stop(stop):
    row = _flat(_row(9))
    assert "**The owner's stop, or the end time**" in row and stop in row
    assert "The run stops all the same: a held ticket never keeps it going." in row
    text = _conductor()
    # Each goes straight to "Stop the run", whose step 1 reads no comments and judges nothing again.
    stop_run = _section(text, "## Stop the run", "2. **Sessions.**")
    assert "1. **Status.** Set `status: \"stopping\"` and the reason: `owner` (the `workflow:stop` label, or \"stop the run\" here), `ends_at`" in stop_run
    if "chat" not in stop:
        # The label and the end time are step 2's "Stop now", judged before any comment is read.
        step2 = _section(text, "**2. Stop or wind down?**", "**Asking about a `needs-human` ticket.**")
        stop_now = _section(step2, "- **Stop now**", "- **Wind down**")
        assert ("`workflow:stop` label" if "label" in stop else "`limits.ends_at` has passed") in stop_now
        assert "comments" not in stop_now
    step0 = _section(text, "**0. Stopping already?**", "**1. Read the state.**")
    assert step0.strip().startswith("If the state's `status` is `stopping`, skip to \"Stop the run\", step 2")


def test_done_waits_for_a_requeue_and_reads_the_owners_comments_first():
    row = _flat(_row(10))
    assert "Never while a requeued ticket is `queued` or `running`." in row
    assert "A ticket row 5 marked `in-review` doesn't hold it up." in row
    done = _section(_conductor(), "- **Done** (stop the run)", "**Asking about a `needs-human` ticket.**")
    assert (
        "Before stopping for Done, read the owner's new comments (step 3's *Comments*) and judge again with their "
        "changes in: an \"also #<n>\" among them may requeue a ticket (\"A pull request that needs a code fix\", row 10)."
    ) in done


def test_the_merge_queue_hold_and_drop_rule_and_a_merge_while_held():
    hold = _hold()
    assert "take it out (GitHub's **Remove from queue**)" in hold
    # The drop rule starts afresh, and leaving the queue while held is never a drop.
    assert "with no `base_merged`, `queue_heads`, `queue_failed` or `queue_result`, so the merge queue's drop rule starts afresh" in hold
    assert (
        "Leaving the queue, by your hand or GitHub's, is never a drop: a held pull request is never queued, so nothing "
        "goes to `WF state drop` for it"
    ) in hold
    # One the queue merged anyway is told apart.
    assert "**Its pull request merged while held** (the merge queue took it, auto-merge armed before the hold, or the owner)" in _row(7)
    held = next(ln for ln in _text("skills/conductor/SKILL.md").splitlines() if ln.startswith("| **A held pull request**"))
    assert "the merge queue row" in held and "\"The merge queue's state\"'s `ready`" in held


def test_merged_before_or_while_held():
    assert (
        "No hold, and requeue nothing. Replace the ticket's `for_owner` lines with \"#n merged before its fix (#PR): "
        "the fix needs a ticket of its own\", and say so in your reply."
    ) in _row(2)
    row = _flat(_row(7))
    assert (
        "The **Merged** row's steps, then clear `requeued_head` and replace the ticket's `for_owner` lines with "
        "\"#n merged while held for its code fix (#PR): if the fix isn't in it, the fix needs a ticket of its own\"."
    ) in row


def test_for_owner_lines_added_replaced_and_taken_out():
    lines = _section(_flat(_requeue()), "**Its `for_owner` lines.**", "**The cases.**")
    for part in (
        "Its merge lines are the ones that leave its pull request to the owner to merge: \"ready for you to merge\", a protected path, a path-filtered check, a merge-queue rule the kit can't judge.",
        "The fix line is \"#n's pull request is held for a code fix (#PR): <the fix asked for>; merge it only once a review covers the fix\".",
        "To write the fix line, take its merge lines out and put the fix line in, once, whether or not there were any.",
    ):
        assert part in lines, part
    # A requeue takes them out, with any line asking for the fix; a hold with no session writes the fix line.
    assert "Take its merge lines, any fix line and any line asking for its fix (step 7's) out of `for_owner`, and reply that it is requeued." in _row(6)
    for n in (4, 5, 9):
        assert "write the fix line" in _row(n).lower(), n
    # Each merge line named matches the line its row writes.
    raw = _text("skills/conductor/SKILL.md")
    for written in (
        "\"#n ready for you to merge (#PR)\"",
        "\"#n changes a protected path (<files>): yours to review and merge (#PR)\"",
        "(\"needs the owner to merge: path-filtered check\")",
        "\"#n: a merge-queue rule the kit can't judge, yours to merge (#PR)\"",
    ):
        assert written in raw, written


def test_a_requeued_ticket_that_ends_needs_human_keeps_its_hold():
    row = _flat(_row(11))
    assert "As for any ticket, and the hold stays" in row
    assert "a ticket at the cap takes its steps instead (check-in step 2's \"A ticket at the cap\")" in row


# ---------- #349's interim line is replaced ----------


def test_the_interim_line_is_gone():
    for rel in ("skills/conductor/SKILL.md", "docs/charter.md", "CHANGELOG.md"):
        text = _flat(_text(rel))
        assert "until #361 lands" not in text, rel
        assert "is #361's" not in text, rel
    step7 = _section(_conductor(), "**7. Infra problems**", "**8. Write the state**")
    assert (
        "A code fix an open run pull request needs is neither yours nor an infra ticket: the owner's \"also #<n>\" "
        "sends its ticket back to a ticket session (\"A pull request that needs a code fix\"), and one you find "
        "yourself goes in `for_owner` and the final report, for the owner to ask for."
    ) in step7


def test_the_charter_docs_say_so():
    text = _flat(_text("docs/charter.md"))
    assert "- **A pull request that needs a code fix** (#361)." in text
    assert "`workflow state put` refuses one that isn't a full commit SHA" in text
    assert "The owner's stop and the end time stop the run all the same, and \"Done\" waits for a requeued ticket." in text


def test_the_changelog_notes_it_under_unreleased():
    unreleased = since_0110()
    assert "**The owner's \"also #<n>\" sends a pull request that needs a code fix back to a ticket session** (#361, part of #338)" in unreleased
    assert "Tests: `tests/test_conductor_requeue.py`." in unreleased

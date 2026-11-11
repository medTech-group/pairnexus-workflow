"""#672: a ticket session stays alive to post its evidence report after the
merge. Under #663 a session's background `workflow evidence` run never holds
the merge, so the pull request can merge (or be left to the owner) before the
report is posted. `build-ticket` §6 posts its notes at once, naming the head the
run covers, and posts the report when the run ends; the conductor keeps such a
session until the report is there, for a time since the note well above an
evidence run's length, never a count of check-ins. Both skills are read as text
contracts (seam 2); the ticket's `settled_at` goes through `workflow state put`,
and the briefing's line is rendered through the CLI."""

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
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
CONDUCTOR = KIT / "skills/conductor/SKILL.md"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
TO_COME = "Evidence for `<sha>` to come on #<PR>"
NO_REPORT = "Evidence for `<sha>`: no report (<why>)"
HOLD = "**Keeping a session for its evidence report**"
HOLD_NAME = "\"Keeping a session for its evidence report\""


def _text(p):
    return p.read_text(encoding="utf-8")


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _section(text, start, end):
    assert start in text, start
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _step(n):
    six = _section(_text(BUILD_TICKET), "## 6. Post the evidence and merge", "## 7. End each turn")
    return _section(six, f"\n{n}. **", f"\n{n + 1}. **")


def _rows():
    return _section(_text(CONDUCTOR), "**4. Each ticket in flight.**", "**Stopping a stuck session safely:**")


def _row(lead):
    line = next((ln for ln in _rows().splitlines() if ln.startswith("| **" + lead)), None)
    assert line, lead
    return line


def _hold():
    return _flat(_section(_text(CONDUCTOR), HOLD, "**The merge queue's state.**"))


# ---------- build-ticket §6: the notes at once, the report when the run ends ----------


def test_the_merged_note_goes_up_at_once_with_the_notes_for_the_next_tickets():
    five = _flat(_step(5))
    assert "**Once it has merged,** tell the tracking issue at once: \"#<n> merged in #<PR>\", then notes for the next tickets." in five
    still = five[five.index("**Your evidence run still going**"):]
    # never held for the run: round 1 of #670 held it, and the session was archived first
    assert "never hold this note for it" in still
    assert f"Post each at once on the tracking issue, with the line \"{TO_COME}\"" in still
    assert "After a merge, take steps 6 and 7 at once too." in still


def test_the_note_names_the_head_the_run_covers_not_the_head_that_merged():
    still = _flat(_step(5))
    assert "`<sha>` is the head the run covers: your checkout's head when you started it, which its report's first line names" in still
    assert "can differ from the head that merged" in still


def test_every_note_that_leaves_the_pull_request_carries_the_line():
    # `owner` mode, `owner_review`, a `queue_unsure` note's `ready` and the
    # path-filtered check: the conductor archives those at once too.
    still = _flat(_step(5))
    assert (
        "or any note saying the pull request is ready or the owner's to merge (`owner` mode's `ready`, `owner_review`, "
        "a `queue_unsure` note's `ready`, §5's path-filtered check)"
    ) in still


def test_every_note_that_leaves_the_pull_request_goes_on_the_tracking_issue():
    # The conductor's hold reads the session's note on the tracking issue only:
    # a note on the pull request alone leaves it waiting for one that never comes.
    still = _flat(_step(5))
    assert f"Post each at once on the tracking issue, with the line \"{TO_COME}\"" in still
    four = _flat(_step(4))
    assert "| `owner` | Say it's ready on the PR and on the tracking issue, and leave it |" in four
    assert "`owner` mode: nothing is queued; say it's ready, and leave it, on the PR and on the tracking issue" in four
    five = _flat(_section(_text(BUILD_TICKET), "## 5. Get it green", "## 6. Post the evidence and merge"))
    assert "Then comment on the PR and on the tracking issue that the PR needs the owner to merge and end `waiting`" in five


def test_the_session_stays_and_posts_the_report_when_the_run_ends_even_after_the_merge():
    stay = _flat(_step(5))
    stay = stay[stay.index("**Then stay**"):]
    assert f"the conductor keeps your session until the report naming `<sha>` is on the pull request" in stay
    assert f"its {HOLD_NAME}" in stay
    assert "Leave your checkout as it is" in stay and "the run stops if your head moves" in stay
    assert "schedule a check-in, and end the turn `waiting`" in stay
    assert "When the run ends, post its report on the PR as step 2 says, even though the pull request has merged by then" in stay
    assert f"say so on the tracking issue instead: \"{NO_REPORT}\"" in stay


def test_the_checklist_line_still_holds():
    assert "- [ ] Typecheck and the full suite pass; evidence posted on the PR" in _text(BUILD_TICKET)


# ---------- the conductor: never archive a session whose report is still to come ----------


def test_the_hold_is_by_time_since_the_note_never_a_count_of_check_ins():
    hold = _hold()
    assert "180 minutes since that note was posted (its `created_at`)" in hold
    assert "well above an evidence run's length" in hold
    assert "never by a count of check-ins" in hold
    assert "a wake from another session counting as one" in hold
    assert "archive the session all the same, and say so on the tracking issue" in hold


def test_the_hold_names_the_note_and_ends_on_the_report_for_its_head():
    hold = _hold()
    assert f"has the line \"{TO_COME.replace('#<PR>', '#PR')}\"" in hold
    # the report counts by its first line, as `WF evidence` writes it
    assert "whose first line is `WF evidence`'s for `<sha>`" in hold
    assert "`**Local full suite on `<sha>`**` or `**Local suites its files need on `<sha>`**`" in hold
    assert f"\"{NO_REPORT}\"" in hold
    # a check-in can come before the session's note: wait for it, from `settled_at`
    assert "With no such note yet on a ticket a row has marked `merged` or `in-review`, it is still to come too" in hold
    assert "or, with no note, since the ticket's `settled_at`" in hold


def test_a_required_report_leaves_nothing_to_come_note_or_none():
    # `ci.none`, or a check waived on the head: the report came first, and the
    # session's ready note has no to-come line, or comes after the check-in.
    hold = _hold()
    assert (
        "Where the report was required (`build-ticket` §6 step 2: the profile's `ci.none`, or a check waived on the "
        "head, `WF merge-check`'s `waived` note), it was posted before the pull request merged or was left to the "
        "owner, so nothing is to come, note or none."
    ) in hold


def test_settled_at_is_recorded_once_for_each_session():
    # One rule, in the hold: a row read again at each check-in never moves the
    # clock, and a requeued ticket's new session never inherits the old one.
    hold = _hold()
    assert (
        "**`settled_at`:** when one of these rows marks the ticket `merged` or `in-review`, record the time as its "
        "`settled_at`, unless it has one since the ticket's `started_at` (its session's start): a later check-in never "
        "moves it, and one from before that `started_at` (an earlier session's, before a requeue) counts as none."
    ) in hold
    rows = [_row("Merged** |"), _row("`owner` mode, `ready`"), _row("`owner_review`"), _row("A required check never started")]
    rows.append(_flat(_section(_text(CONDUCTOR), "**The merge queue's state.**", "\n")))
    for row in rows:
        assert "settled_at" not in row


def test_the_hold_reads_only_the_notes_of_this_session():
    # A requeued ticket's earlier session left its own note: it says nothing of this one's run.
    hold = _hold()
    assert "the session's latest note on the tracking issue since the ticket's `started_at`" in hold


def test_the_hold_delays_only_the_archive():
    hold = _hold()
    assert "only the archive (and deleting the session's check-ins) waits" in hold
    assert "its counting as settled for \"Done\" happen at once" in hold


def test_the_merged_row_keeps_the_session_for_its_report():
    merged = _row("Merged** |")
    # never a count of check-ins as the hold (round 2 of #670): the archive goes through the hold
    assert "3 check-ins" not in merged
    assert "read its notes for the next tickets" in merged
    assert f"then, as {HOLD_NAME} says, delete its own pending check-ins" in merged


def test_the_merged_row_archives_a_session_whose_note_never_comes():
    # A session that dies before its "#n merged in #PR" note: the row still
    # reaches the archive, and the hold decides when. With the report required
    # (`ci.none`, a waived check) nothing is to come, so it is archived then;
    # with it still to come, at the hold's limit since `settled_at`.
    merged = _row("Merged** |")
    assert (
        "Once the session's \"#n merged in #PR\" note is on the tracking issue (or one check-in later, if it never "
        f"comes), read its notes for the next tickets; then, as {HOLD_NAME} says, delete its own pending check-ins"
    ) in merged
    hold = _hold()
    assert "so nothing is to come, note or none" in hold
    assert "or, with no note, since the ticket's `settled_at`" in hold
    assert "Past it, archive the session all the same" in hold


@pytest.mark.parametrize("lead", ["`owner` mode, `ready`", "`owner_review`", "A required check never started"])
def test_the_rows_that_archive_at_once_keep_the_session_for_its_report(lead):
    row = _row(lead)
    assert f"delete the session's check-ins and archive it as {HOLD_NAME} says" in row


def test_the_queue_unsure_ready_keeps_the_session_for_its_report():
    queue = _flat(_section(_text(CONDUCTOR), "**The merge queue's state.**", "\n"))
    assert "mark the ticket `in-review`, then delete the session's check-ins" in queue
    assert f"delete the session's check-ins and archive it as {HOLD_NAME} says" in queue


def test_the_path_filtered_row_waits_on_the_evidence_only_where_it_is_required():
    row = _row("A required check never started")
    assert "and, where the report is required (`build-ticket` §6 step 2), the evidence is posted" in row
    assert "finished and the evidence is posted" not in row


def test_the_stuck_row_leaves_a_session_kept_for_its_report():
    # A kept session waits on its run with no push, comment or label change, and
    # isn't `working`: 6 check-ins pass long before its limit. Stopping it safely
    # would archive it before the report and requeue a ticket already settled.
    stuck = _row("No movement for 6 check-ins")
    assert "It's stuck. Stop it safely and retry (below)." in stuck
    assert f"Never a session kept for its evidence report ({HOLD_NAME}): only that paragraph archives it." in stuck
    # the hold stays the only way such a session is archived
    assert "Past it, archive the session all the same" in _hold()


def test_stop_the_run_keeps_a_session_for_its_report():
    two = _flat(_section(_text(CONDUCTOR), "2. **Sessions.**", "**Set aside at the end time**"))
    assert f"A session kept for its evidence report ({HOLD_NAME}, check-in step 4) isn't interrupted" in two
    assert "archive it as that paragraph says" in two


def test_the_hold_lists_every_row_it_covers():
    hold = _hold()
    assert (
        "the **Merged** row, `owner` mode `ready`, `owner_review`, the path-filtered row, \"The merge queue's state\"'s "
        "`queue_unsure` `ready`, and \"Stop the run\" step 2"
    ) in hold


# ---------- the state: the ticket's `settled_at` ----------


def _put(tmp_path, at):
    c = charter.defaults(["deploy staging"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["tickets"] = {"12": {"status": "merged", "pr": 40, "settled_at": at}}
    (tmp_path / "s.json").write_text(json.dumps(s))
    (tmp_path / "body.md").write_text("# Run\n")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run(
        [sys.executable, str(CLI), "state", "put", "--body", "body.md", "--state", "s.json", "--out", "out.md"],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )


def test_state_put_keeps_settled_at(tmp_path):
    r = _put(tmp_path, "2026-11-10T16:05:00Z")
    assert r.returncode == 0, r.stderr
    assert "2026-11-10T16:05:00Z" in (tmp_path / "out.md").read_text()


@pytest.mark.parametrize("at", ["yesterday", "2026-11-10T16:05:00", 5])
def test_state_put_refuses_a_settled_at_that_isnt_a_time_with_its_zone(tmp_path, at):
    r = _put(tmp_path, at)
    assert r.returncode != 0
    assert "tickets[12].settled_at must be an ISO time with its zone" in r.stdout + r.stderr


# ---------- the briefing, rendered ----------


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


@pytest.mark.parametrize("waived", [[], ["unit"]])
def test_the_briefing_says_to_stay_for_the_report(tmp_path, waived):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n[ci]\nrequired_checks = ["unit"]\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    c["merge"] = {"mode": "auto-merge", "waived_checks": waived}
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    first = next(l for l in _section((tmp_path / "briefing.md").read_text(), "### Merging", "### Rules").splitlines() if l.startswith("- "))
    assert "When it ends, post its report on the PR as `workflow evidence` prints it" in first
    # the line in full, as `build-ticket` §6 step 5 and the conductor's hold give it:
    # a note with the line cut short leaves nothing to come, and the session is archived
    assert (
        f"If the PR has merged, or been left to the owner, by then, your notes say \"{TO_COME}\" "
        "and you stay to post it (`build-ticket` §6 step 5)."
    ) in first


@pytest.mark.parametrize(
    "bullet, words",
    [
        ("- **Without a merge queue**", "`owner` says it's ready on the PR and on #11, and leaves it."),
        # with the queue on, the bullet above is skipped: this one must say it too
        ("- **The merge queue:**", "`owner` mode queues nothing: on `ready` it says it's ready on the PR and on #11, and leaves it."),
    ],
)
def test_the_owner_mode_briefing_says_ready_on_the_tracking_issue(tmp_path, bullet, words):
    # The conductor's hold reads only the session's notes on the tracking issue:
    # "ready" on the PR alone leaves it waiting 180 minutes for a note that never comes.
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n[ci]\nrequired_checks = ["unit"]\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    c["merge"] = {"mode": "owner", "waived_checks": []}
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    merging = _section((tmp_path / "briefing.md").read_text(), "### Merging", "### Rules")
    line = next(l for l in merging.splitlines() if l.startswith(bullet))
    assert words in line


def test_the_ci_none_briefing_has_no_line_to_stay():
    # With `ci.none` the report comes first, so nothing is still to come after the merge.
    from workflow import render
    from workflow.profile import Profile

    words = render._evidence_words([], Profile(root=KIT, name="demo", repo="acme/demo", ci_none=True))
    assert "you stay to post it" not in words


# ---------- changelog ----------


def test_changelog_has_the_note_under_unreleased():
    notes = since_0110()
    rest = notes[len("## Unreleased"):]
    unreleased = rest[:rest.index("\n## ")] if "\n## " in rest else rest
    assert "(#672, split out of #663)" in unreleased
    assert "Evidence for `<sha>` to come" in unreleased

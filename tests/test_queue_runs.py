"""#249: runs queue instead of updating. The conductor's check-ins, `build-ticket`,
the ticket-session prompt, the run report and flow §4's merge-mode paragraph with
a merge queue, read as the kit-release tests read skills (#243's seam 6). The
commands they name go through the guard as each role runs them (seam 5), and the
rendered briefing's seal still verifies."""

import json
import os
import re
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from workflow import charter
from workflow.guard import decide
from workflow.profile import load

CLI = KIT / "scripts/workflow.py"
CONDUCTOR = "skills/conductor/SKILL.md"
BUILD_TICKET = "skills/build-ticket/SKILL.md"
ENQUEUE = "gh api -i -X PUT repos/<repo>/pulls/<n>/merge-async -f merge_action=merge_queue -f sha=<sha>"
RESULTS = ("in_queue", "waiting", "merged", "retry", "requeued", "merge_base", "needs_human")


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _section(text, start, end):
    assert start in text, start
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _row(rows, lead):
    line = next((ln for ln in rows.splitlines() if ln.startswith("| **" + lead)), None)
    assert line, lead
    return line


def _check_in_rows():
    return _section(_read(CONDUCTOR), "**4. Each ticket in flight.**", "**Stopping a stuck session safely:**")


def _merge_step():
    return _section(_read(BUILD_TICKET), "## 6. Post the evidence and merge", "**Once it has merged,**")


def _queue_paragraph():
    step = _merge_step()
    return _section(step, "**With the merge queue on**", "\n\n   If your permission settings")


# ---------- build-ticket ----------


def test_build_ticket_reads_the_queue_from_merge_check_never_the_briefing():
    step = _merge_step()
    assert "Read whether the merge queue is on from the JSON's `queue` each time, never from the briefing" in step


def test_build_ticket_enqueues_once_per_head_pinned_through_merge_async():
    para = _queue_paragraph()
    assert f"`{ENQUEUE}`" in para
    assert "once per head" in para
    assert "pinned to its `head`, your checkout's head" in para
    # Each mode: session after its own final merge-check, auto-merge as soon as ready, owner never.
    assert "`session` mode: after your own final `WF merge-check` says `ready`" in para
    assert "`auto-merge` mode: as soon as `WF merge-check` says `ready`. Never arm GitHub's auto-merge with the queue on" in para
    assert "`owner` mode: nothing is queued; say it's ready, and leave it" in para


def test_build_ticket_reads_back_the_202_and_leaves_every_re_queue_to_the_conductor():
    para = _queue_paragraph()
    assert "merge-async/<uuid>" in para and "`enqueued`" in para
    assert "every re-queue is the conductor's" in para
    assert "already in a merge queue" in para


def test_build_ticket_stays_until_merged_and_handles_the_conductors_base_merge():
    para = _queue_paragraph()
    assert "Stay with it until GitHub has merged it" in para
    assert "After the conductor merges the base in (a second drop), `git pull`, run `WF merge-check` again, and run a Correctness pass only when it asks for one" in para
    assert "fix any red check" in para
    assert "labels the ticket `needs-human`" in para and "stop" in para


def test_build_ticket_scopes_the_up_to_date_steps_to_no_queue():
    para = _queue_paragraph()
    assert "The update-branch steps, the \"behind\" handling and the \"already clean\" fallback don't apply" in para
    green = _section(_read(BUILD_TICKET), "## 5. Get it green", "## 6.")
    moved = next(ln for ln in green.splitlines() if ln.startswith("- **The base branch moved:**"))
    assert "With the merge queue on (`WF merge-check`'s `queue`), don't: the queue tests the pull request on the latest base itself" in moved
    level = next(ln for ln in _merge_step().splitlines() if ln.startswith("1. **Push everything,**"))
    assert "(with the merge queue on, the queue meets this)" in level


@pytest.fixture
def ticket(repo):
    git(repo, "checkout", "-qb", "claude/build-249")
    (repo / "x.txt").write_text("x")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-qm", "work")
    return repo


def _decide(root, cmd, role, branch="claude/build-249"):
    event = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    return decide(event, load(root), role, root, branch)


def test_the_guard_lets_a_ticket_session_queue_its_own_head_with_that_command(ticket):
    sha = git(ticket, "rev-parse", "HEAD").strip()
    cmd = ENQUEUE.replace("<repo>", "acme/demo").replace("<n>", "12").replace("<sha>", sha)
    assert _decide(ticket, cmd, "ticket").action == "allow"
    other = "0123456789abcdef0123456789abcdef01234567"
    assert _decide(ticket, cmd.replace(sha, other), "ticket").action == "deny"


# ---------- the ticket-session prompt ----------


def _render(tmp_path, mode):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\nowner="o"\n[ci]\nrequired_checks=["CI"]\n[[release.steps]]\nname="ship"\nrun="x"\n',
        encoding="utf-8",
    )
    c = charter.defaults(["ship"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"] = {"mode": mode, "waived_checks": []}
    files = {
        "charter.json": c,
        "ticket.json": {"number": 7, "title": "Readings tab"},
        "slots.json": {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"},
    }
    for name, value in files.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    out = tmp_path / "briefing.md"
    p = subprocess.run(
        [sys.executable, str(CLI), "render", "--template", str(KIT / "templates/ticket-session-prompt.md"),
         "--ticket", str(tmp_path / "ticket.json"), "--charter", str(tmp_path / "charter.json"),
         "--slots", str(tmp_path / "slots.json"), "--tracking", "232", "--out", str(out)],
        capture_output=True, text=True, cwd=tmp_path, env=env,
    )
    assert p.returncode == 0, p.stderr
    v = subprocess.run([sys.executable, str(CLI), "briefing", "verify", "--file", str(out)], capture_output=True, text=True, cwd=tmp_path, env=env)
    assert re.fullmatch(r"Briefing [0-9a-f]{12} intact\n?", v.stdout), v.stdout + v.stderr
    return _section(out.read_text(encoding="utf-8"), "### Merging", "### Rules")


@pytest.mark.parametrize("mode", ["auto-merge", "session"])
def test_the_briefing_queues_once_per_head_and_stays(tmp_path, mode):
    merging = _render(tmp_path, mode)
    line = next(ln for ln in merging.splitlines() if ln.startswith("- **The merge queue:**"))
    assert "read whether it is on from `merge-check`'s `queue` each time, never from this briefing" in line
    assert "once per head through `merge-async`, pinned to your checkout's head" in line
    assert "gh api -i -X PUT repos/a/d/pulls/<PR>/merge-async -f merge_action=merge_queue -f sha=<head>" in line
    assert "`auto-merge` mode never arms GitHub's auto-merge with the queue on" in line
    assert "`session` mode queues after your own final `merge-check` says `ready`" in line
    assert "Stay with the PR until GitHub merges it" in line
    assert "the update-branch steps, the \"behind\" handling and the \"already clean\" fallback don't apply" in line


# ---------- the conductor's check-ins ----------


def test_the_conductor_enqueues_every_ready_pr_in_auto_merge_and_session_never_owner():
    row = _row(_check_in_rows(), "The merge queue on")
    assert "`auto-merge` or `session` mode" in row
    assert "never one in `owner` mode" in row
    assert f"`{ENQUEUE}`" in row
    assert "pinned to the JSON's `head`" in row
    assert "Never arm GitHub's auto-merge with the queue on" in row


def test_the_conductor_gives_each_answer_to_state_drop_and_does_what_it_prints():
    row = _row(_check_in_rows(), "The merge queue on")
    assert "`WF state drop --body .workflow/run/body.md --ticket <n> --head <full sha> --answer <answer> --out .workflow/run/body.md`" in row
    for answer in ("`202-enqueued`", "`202-pending`", "`200-waiting`", "`200-merged`", "`409`", "`failed`", "`refused`"):
        assert answer in row, answer
    for result in RESULTS:
        assert f"`{result}`" in row, result
    assert "`gh api -X PUT repos/<repo>/pulls/<n>/update-branch -f expected_head_sha=<sha>`" in row
    assert "\"dropped from the merge queue again after the base was merged in\"" in row
    assert "GitHub's message after three `failed` answers" in row
    # After a merge_base, the pass cap applies as to any PR.
    assert "`passes_used_up`" in row and "the pass-cap row" in row


def test_the_conductors_update_branch_command_passes_the_guard(ticket):
    sha = git(ticket, "rev-parse", "HEAD").strip()
    row = _row(_check_in_rows(), "The merge queue on")
    update = re.search(r"`(gh api -X PUT repos/<repo>/pulls/<n>/update-branch [^`]*)`", row).group(1)
    cmd = update.replace("<repo>", "acme/demo").replace("<n>", "12").replace("<sha>", sha)
    assert _decide(ticket, cmd, "conductor", "main").action == "allow"
    enqueue = ENQUEUE.replace("<repo>", "acme/demo").replace("<n>", "12").replace("<sha>", sha)
    assert _decide(ticket, enqueue, "conductor", "main").action == "allow"


def test_the_up_to_date_rows_are_scoped_to_no_queue():
    rows = _check_in_rows()
    for lead in ("PR open, behind the base", "`session` mode, `ready`", "`auto-merge` mode, `ready`", "You tried to enable auto-merge"):
        assert "Without a merge queue" in _row(rows, lead) or "without a merge queue" in _row(rows, lead), lead


def test_the_stuck_row_counts_waiting_in_the_queue_as_waiting_on_ci():
    stuck = _row(_check_in_rows(), "No movement for 6 check-ins")
    assert "a PR waiting in the merge queue (`state drop`'s last answer `waiting` or `in_queue`) counts as waiting on CI" in stuck


def test_a_mid_run_change_of_the_queue_is_logged_said_followed_and_stops_waivers():
    text = _read(CONDUCTOR)
    para = _section(text, "**The merge queue's state.**", "\n\n")
    assert "`WF state queue --body .workflow/run/body.md --queue on|off --out .workflow/run/body.md`" in para
    assert "log it in the ledger" in para
    assert "say so on the tracking issue" in para
    assert "follow the ruleset from then on" in para
    assert "stop applying the charter's waivers" in para
    assert "Nothing stops" in para


def test_the_kick_off_records_the_queue_and_recommends_it_with_its_reason():
    text = _read(CONDUCTOR)
    kickoff = _section(text, "### 2. The kick-off", "## Each check-in")
    para = _section(kickoff, "**The merge queue.**", "\n\n")
    assert "doctor's JSON `merge_queue`" in para
    assert "the `check-setup` skill's rule" in para and "with its reason" in para
    assert "\"Use a merge queue\"" in para and "attended session" in para
    assert "never changes the ruleset itself" in para
    assert "never offers the upgrade while a run is in progress" in para
    assert "WF state init --charter charter.json --run-id <id> --by-hand <n> --read-through <id of the newest comment on the tracking issue, or 0> --queue <on|off>" in kickoff
    assert "`--queue on|off`" in kickoff


# ---------- the run report ----------


def test_the_run_report_flags_a_late_request_and_offers_a_revert():
    text = _read("skills/run-report/SKILL.md")
    assert "merged with a request made after it was queued" in text
    assert "changes requested" in text and "an open review thread" in text
    assert "offer a revert" in text


# ---------- flow §4 ----------


def _flow_4():
    text = _read("docs/flow.md")
    return text.split("## 4. The merge rule", 1)[1].split("\n## ", 1)[0]


def test_flow_4_says_what_each_mode_means_with_the_queue():
    para = next(ln for ln in _flow_4().splitlines() if ln.startswith("Merging is the owner's in attended work."))
    assert "With \"up to date\" (no merge queue): GitHub auto-merge behind the ruleset (the session or the conductor keeps the branch up to date until it merges)" in para
    assert "In `auto-merge` mode with \"up to date\", when GitHub refuses to enable auto-merge because the PR is already mergeable (clean)" in para
    assert "With the merge queue on, the modes keep their names and nothing merges directly" in para
    assert "In `auto-merge`, GitHub's auto-merge is never armed" in para
    assert "in `session`, the ticket session queues it, pinned, after its own final `merge-check` says `ready`" in para
    assert "in `owner`, nothing is queued unattended" in para
    assert "every re-queue after a drop is the conductor's" in para


# ---------- changelog ----------


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "(#249" in notes and "merge queue" in notes

"""#664: a waiting ticket session notices its pull request now conflicts with
the base. Every waiting check-in, whatever the session waits on, runs
`WF merge-check` on the head while the pull request is open and its head isn't
queued, and on `conflict` merges the base in at once. `build-ticket` is read as
a text contract (seam 2), and the briefing's **Check-ins** line is rendered
through the CLI, as `tests/test_evidence_never_holds_the_merge.py` renders
briefings."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from changelog_notes import since_0110
from workflow import charter

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
BUILD_TICKET = KIT / "skills/build-ticket/SKILL.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
HEADING = "**Every waiting check-in watches the base.**"


def _flat(text):
    return re.sub(r"\s+", " ", text)


def _section(text, start, end):
    assert start in text, start
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _paragraph():
    four = _section(BUILD_TICKET.read_text(), "## 4. Open the pull request", "## 5. Get it green")
    assert HEADING in four, "build-ticket §4 has no waiting check-in paragraph"
    i = four.index(HEADING)
    end = four.find("\n\n", i)
    return _flat(four[i:end if end != -1 else len(four)])


# ---------- build-ticket (seam 2) ----------


def test_it_follows_the_check_in_it_describes():
    four = _section(BUILD_TICKET.read_text(), "## 4. Open the pull request", "## 5. Get it green")
    subscribe = four.index("Then subscribe to its activity.")
    assert subscribe < four.index(HEADING)


def test_every_waiting_check_in_runs_merge_check_whatever_it_waits_on():
    p = _paragraph()
    assert "Whatever you wait on (CI, the evidence run, a review agent or the merge queue)" in p
    assert "each check-in, while the pull request is open and its head isn't one you queued" in p
    assert "runs `WF merge-check --fetch <PR> --json` on the head (in a run, with step 6.3's flags)" in p
    assert "not only once what you wait on is done" in p


def test_on_conflict_it_merges_the_base_in_at_once_never_a_rebase():
    p = _paragraph()
    assert "On a `conflict` reason (its action `resolve_conflict`), merge the base in at once" in p
    assert "disarm auto-merge first if it is armed" in p
    assert "`git fetch origin <base> && git merge origin/<base>`" in p
    assert "never a rebase or force-push" in p


def test_a_changelog_conflict_keeps_both_sides():
    p = _paragraph()
    assert "in a `CHANGELOG.md` conflict, keep both sides: every note from each" in p


def test_it_pushes_and_acts_on_the_next_merge_check():
    p = _paragraph()
    assert "push, and act on the next `WF merge-check`" in p
    assert "a Correctness pass only when it asks for one (§3)" in p


def test_an_evidence_run_still_going_holds_nothing():
    p = _paragraph()
    assert "An evidence run still going holds this merge no more than any other (§6 step 2)" in p


def test_a_queued_head_only_waits_and_re_queues_stay_the_conductors():
    p = _paragraph()
    assert "A head you queued only waits, and every re-queue is the conductor's (§6 step 4)" in p
    # §6 step 4's rule for a queued head is unchanged
    six = _section(BUILD_TICKET.read_text(), "## 6. Post the evidence and merge", "## 7. End each turn")
    assert "Never queue that head again: a head you queued only waits, whatever `WF merge-check` says of it later, and every re-queue is the conductor's" in six


def test_the_base_moved_bullet_still_resolves_a_conflict_with_the_queue_on():
    five = _section(BUILD_TICKET.read_text(), "## 5. Get it green", "## 6. Post the evidence and merge")
    assert "Still merge it in to resolve a conflict (`WF merge-check`'s `resolve_conflict`), as above." in five


# ---------- the briefing's Check-ins line, rendered (seam 2) ----------


def _project(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\nbase_branch = "trunk"\n\n'
        '[ci]\nrequired_checks = ["unit"]\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(SLOTS))


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _check_ins(tmp_path):
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["limits"]["check_in_minutes"] = 20
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(
        tmp_path, "render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
        "--slots", "slots.json", "--tracking", "11", "--out", "briefing.md",
    )
    assert p.returncode == 0, p.stderr
    v = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert v.returncode == 0 and v.stdout.endswith(" intact\n"), v.stdout
    lines = [l for l in (tmp_path / "briefing.md").read_text().splitlines() if l.startswith("- **Check-ins:**")]
    assert len(lines) == 1, lines
    return lines[0]


def test_the_rendered_check_ins_line_watches_the_base(tmp_path):
    _project(tmp_path)
    line = _check_ins(tmp_path)
    # the line as it was, kept
    assert "subscribe to the PR's activity and schedule a check-in with `send_later` about every 20 minutes." in line
    assert "End that turn with `WORKFLOW-STATUS: waiting`." in line
    # and the new sentence, with the profile's base branch filled in
    assert (
        "Whatever you wait on (CI, the evidence, a review agent or the merge queue), each check-in, while the PR is "
        "open and its head isn't one you queued, runs `merge-check` (the command under **Merging**) on the head; on "
        "`conflict`, merge `trunk` in at once (never a rebase or force-push), keeping both sides of a `CHANGELOG.md` "
        "conflict, then push and act on the next `merge-check`. A head you queued only waits."
    ) in line
    assert "{{" not in line


def test_changelog_notes_664():
    notes = since_0110()
    assert "(#664" in notes
    assert "waiting check-in" in notes

"""A ticket not clean at a run's end time is carried on: `workflow:carry-on`
(#380, spec #412 "Runs"). Its seams: the rendered briefing (the hand-off a
carried-on ticket's session starts from) and the conductor's text contracts
(the end-time step, the kick-off's adoption, the report)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import charter, render, state
from workflow.profile import Profile
from changelog_notes import since_0110

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
TEMPLATE = KIT / "templates/ticket-session-prompt.md"
SLOTS = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
HAND_OFF = "https://github.com/acme/demo/pull/41#issuecomment-6600212381"


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _project(tmp_path, slots):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n'
    )
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    (tmp_path / "slots.json").write_text(json.dumps(slots))
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["approved"] = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}
    (tmp_path / "charter.json").write_text(json.dumps(c))


def _render(tmp_path, slots):
    _project(tmp_path, slots)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    args = ["render", "--template", str(TEMPLATE), "--ticket", "ticket.json", "--charter", "charter.json",
            "--slots", "slots.json", "--tracking", "11", "--print"]
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _line(text, start):
    return next(ln for ln in text.splitlines() if ln.startswith(start))


# ---------- the rendered briefing ----------


def test_the_template_has_the_hand_off_line_after_starts_from():
    lines = _read("templates/ticket-session-prompt.md").splitlines()
    i = next(i for i, ln in enumerate(lines) if ln.startswith("**Starts from:**"))
    assert lines[i + 1] == "**Hand-off:** {{ticket.hand_off}}"


def test_a_carried_on_ticket_starts_from_its_hand_off(tmp_path):
    p = _render(tmp_path, {**SLOTS, "hand_off": HAND_OFF})
    assert p.returncode == 0, p.stderr
    line = _line(p.stdout, "**Hand-off:**")
    assert line.startswith(f"**Hand-off:** {HAND_OFF}. ")
    assert "An earlier run's end time came before this ticket's review was clean, so this run carries it on; it isn't a retry." in line
    # Its own pull request and branch, read before anything else.
    assert "pull request #41" in line and "`claude/build-7`" in line
    assert "read that hand-off comment before anything else" in line
    # The open findings first, then the next review, counted on from the records.
    assert "fix its open blocking findings first" in line and "numbered after the rounds and passes it names" in line
    # A security finding named by its area only: found again by a full review of that area, never carried across.
    assert "by its area only" in line and "full review of the change for that area" in line and "none crossed sessions" in line


@pytest.mark.parametrize("slots", [SLOTS, {**SLOTS, "hand_off": "none"}, {**SLOTS, "hand_off": " None "}])
def test_a_fresh_ticket_has_no_hand_off(tmp_path, slots):
    p = _render(tmp_path, slots)
    assert p.returncode == 0, p.stderr
    assert _line(p.stdout, "**Hand-off:**") == "**Hand-off:** none: no earlier run handed this ticket on."


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/other/demo/pull/41#issuecomment-1",  # another repository
        "https://github.com/acme/demo/issues/41#issuecomment-1",  # not on a pull request
        "https://github.com/acme/demo/pull/41",  # not a comment
        "https://github.com/acme/demo/pull/41#issuecomment-1 and more",
        "http://github.com/acme/demo/pull/41#issuecomment-1",
        "SEE_BELOW",
        "",
    ],
)
def test_a_hand_off_slot_that_isnt_a_comment_on_this_repos_pull_request_stops_the_render(tmp_path, url):
    p = _render(tmp_path, {**SLOTS, "hand_off": url})
    assert p.returncode != 0
    assert "hand_off" in p.stderr and p.stdout == ""


def test_the_repository_is_matched_without_case(tmp_path):
    p = _render(tmp_path, {**SLOTS, "hand_off": HAND_OFF.replace("acme/demo", "Acme/Demo")})
    assert p.returncode == 0, p.stderr


def test_values_give_the_hand_off_from_the_slots(tmp_path):
    prof = Profile(root=tmp_path, name="demo", repo="acme/demo")
    v = render.values(prof, {"number": 7, "title": "x"}, {}, {**SLOTS, "hand_off": HAND_OFF}, 11, None)
    assert v["ticket.hand_off"].startswith(HAND_OFF + ". ")


# ---------- the state ----------


def test_the_state_takes_a_carried_on_ticket():
    s = state.empty()
    s["tickets"]["380"] = {"status": "carry-on", "pr": 465, "attempts": 0}
    assert state.validate(s) == []


# ---------- the conductor's text ----------


def _skill():
    return _read("skills/conductor/SKILL.md")


def _stop():
    return _skill().split("## Stop the run", 1)[1].split("\n## ", 1)[0]


def _carry():
    return next(p for p in _stop().split("\n\n") if "**Carried on at the end time**" in p)


def test_the_end_time_step_reads_each_tickets_pass_cap_from_merge_check():
    aside = next(ln for ln in _stop().splitlines() if "**Set aside at the end time**" in ln)
    # The JSON's `review_passes`: `until-clean` under rule 2 whatever the run's cap (#426).
    assert "its pass cap is `until-clean`" in aside and "the JSON's `review_passes`" in aside
    assert "`mechanism_repeats`" in aside


def test_a_rule_2_ticket_is_carried_on_not_set_aside():
    carry = _carry()
    assert "`rule=2`" in carry
    assert "label it `workflow:carry-on` (not `needs-human`)" in carry
    assert "remove `workflow:in-progress` and `ready-for-agent`" in carry
    # The hand-off, from the last record and the PR body's findings table, posted as the writer prints it.
    assert "`WF hand-off --commit <head> --round <N> --passes <P> --record <F>" in carry
    assert "findings table" in carry and "post its output on the pull request as it is" in carry
    # The state first, so a resume finishes it, and never a second hand-off for the same head.
    assert carry.index("write the state to the issue") < carry.index("then write the hand-off")
    assert "`hand_off.on_head`" in carry
    assert "it isn't at the cap and it isn't a retry" in carry


def test_a_security_problems_details_stay_out_of_the_hand_off():
    carry = _carry()
    assert "only in this chat" in carry and "never in the hand-off" in carry
    assert "by its area only" in carry


def test_tickets_held_for_the_owner_go_to_the_owner_as_today():
    carry = _carry()
    assert "security or safety problem in code on the base branch" in carry and "`security=main`" in carry
    assert "`owner_review`" in carry and "a protected path" in carry
    assert "go to the owner as today" in carry


def test_the_kick_off_adopts_every_carry_on_ticket_first_without_asking():
    skill = _skill()
    work = skill.split("**The work**", 1)[1].split("\n\n", 1)[0]
    line = next(ln for ln in work.splitlines() if "`workflow:carry-on`" in ln)
    assert "without asking" in line and "first" in line and "not a retry" in line
    assert "`attempts: 0`" in line and "`hand_off.url`" in line
    assert "remove `workflow:carry-on`" in line
    # Never asked about as a leftover, and first in the plan.
    plan = skill.split("3. **The plan.**", 1)[1].split("\n", 1)[0]
    assert "carry-on tickets first" in plan
    queued = skill.split("1. **Queued tickets** in the state:", 1)[1].split("\n", 1)[0]
    assert queued.lstrip().startswith("carry-on tickets adopted at kick-off first")


def test_the_briefing_section_names_the_hand_off_slot():
    brief = _skill().split("## A ticket session's briefing", 1)[1].split("\n## ", 1)[0]
    row = next(ln for ln in brief.splitlines() if ln.startswith("| `hand_off` |"))
    assert "Optional, for a carry-on ticket" in row and "`hand_off.url`" in row


def test_the_run_report_lists_carried_on_tickets():
    report = _read("skills/run-report/SKILL.md")
    assert "`workflow:carry-on`" in report and "hand-off" in report


def test_the_charter_doc_says_the_end_time_carries_on():
    end = next(ln for ln in _read("docs/charter.md").splitlines() if ln.startswith("- **The end time**"))
    assert "`workflow:carry-on`" in end and "next run" in end


def test_the_changelog_has_the_note():
    unreleased = since_0110(_read("CHANGELOG.md"))
    assert "(#380, part of spec #412)" in unreleased and "`workflow:carry-on`" in unreleased

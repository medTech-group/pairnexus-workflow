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


def _render(tmp_path, slots, template=TEMPLATE):
    _project(tmp_path, slots)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    args = ["render", "--template", str(template), "--ticket", "ticket.json", "--charter", "charter.json",
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
    # An earlier run's end time, or attended work's stop: either way an earlier session handed it on.
    assert "An earlier session handed this ticket on before its review was clean, so this session carries it on." in line
    assert "retry" not in line
    # Its own pull request and branch, read before anything else.
    assert "pull request #41" in line and "`claude/build-7`" in line
    assert "read that hand-off comment before anything else" in line
    # The open findings first, then the next review, counted on from the records.
    assert "fix its open blocking findings first" in line and "numbered after the rounds and passes it names" in line
    # A security finding named by its area only: found again by a full review of that area, never carried across.
    assert "For a security finding it names by its area only, first review the whole change for that area" in line
    assert "none crossed sessions" in line


@pytest.mark.parametrize("slots", [SLOTS, {**SLOTS, "hand_off": "none"}, {**SLOTS, "hand_off": " None "}])
def test_a_fresh_ticket_has_no_hand_off(tmp_path, slots):
    p = _render(tmp_path, slots)
    assert p.returncode == 0, p.stderr
    assert _line(p.stdout, "**Hand-off:**") == "**Hand-off:** none: start from the ticket and what **Specific to this ticket** says."


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


def _render_with(tmp_path, template_text, slots):
    tmp_path.mkdir()
    (tmp_path / "old-template.md").write_text(template_text)
    return _render(tmp_path, slots, template=tmp_path / "old-template.md")


def test_a_template_without_the_line_never_drops_a_hand_off(tmp_path):
    # An older (vendored) template has no Hand-off line: a hand-off given to it stops the render.
    old = TEMPLATE.read_text().replace("**Hand-off:** {{ticket.hand_off}}\n", "")
    assert "ticket.hand_off" not in old
    p = _render_with(tmp_path / "given", old, {**SLOTS, "hand_off": HAND_OFF})
    assert p.returncode != 0 and "{{ticket.hand_off}}" in p.stderr and p.stdout == ""
    # Without one, it renders as before.
    p = _render_with(tmp_path / "none", old, {**SLOTS, "hand_off": "none"})
    assert p.returncode == 0, p.stderr
    assert "**Hand-off:**" not in p.stdout


def test_a_template_naming_the_slot_itself_gets_none_when_it_is_left_out(tmp_path):
    # The optional slot has a value of its own, so a template using {{hand_off}} never stops on "no value".
    text = TEMPLATE.read_text().replace("{{ticket.hand_off}}", "{{hand_off}}")
    p = _render_with(tmp_path / "out", text, SLOTS)
    assert p.returncode == 0, p.stderr
    assert _line(p.stdout, "**Hand-off:**") == "**Hand-off:** none"
    # A hand-off given to it still stops the render: the line that tells the session what to do is missing.
    p = _render_with(tmp_path / "given", text, {**SLOTS, "hand_off": HAND_OFF})
    assert p.returncode != 0 and "{{ticket.hand_off}}" in p.stderr


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
    """The carried-on paragraph, its steps and the paragraph after them, up to step 3 of "Stop the run"."""
    stop = _stop()
    return stop[stop.index("**Carried on at the end time**"):stop.index("3. **Release,**")]


def test_the_end_time_step_reads_each_tickets_pass_cap_from_merge_check():
    aside = next(ln for ln in _stop().splitlines() if "**Set aside at the end time**" in ln)
    # The JSON's `review_passes`: `until-clean` under rule 2 whatever the run's cap (#426).
    assert "its pass cap is `until-clean`" in aside and "the JSON's `review_passes`" in aside
    assert "`mechanism_repeats`" in aside
    # A run under spec #412's rule has no pass cap: a ticket with no record yet is taken too.
    assert "or the ticket belongs to a run under spec #412's rule" in aside


def test_a_rule_2_ticket_is_carried_on_not_set_aside():
    carry = _carry()
    assert "`rule=2`" in carry
    assert "Label it `workflow:carry-on` (not `needs-human`)" in carry
    assert "remove `workflow:in-progress` and `ready-for-agent`" in carry
    # The hand-off, from the last record and the PR body's findings table, posted as the writer prints it.
    assert "`WF hand-off --commit <head> --round <N> --passes <P> --record <F>" in carry
    assert "findings table" in carry and "post its output on the pull request as it is" in carry
    # The state first, so a resume finishes it, and never a second hand-off for the same head.
    assert carry.index("write the state to the issue") < carry.index("2. Then, unless")
    assert carry.index("2. Then, unless") < carry.index("Label it `workflow:carry-on`")
    # A refusal of the writer sets it aside rather than retrying on every resume.
    assert "If `WF hand-off` refuses, set the ticket aside" in carry and "the writer's message" in carry
    # One hand-off per head, every time, and a comment only with a new one.
    assert "2. Then, unless `WF merge-check`'s `hand_off.on_head` is already true, write the hand-off" in carry
    assert "when step 2 posted a hand-off, comment on it" in carry
    # A carry-on ticket adopted but never started keeps its hand-off.
    assert "A carry-on ticket this run adopted and never started (`queued`, still labelled `workflow:carry-on`) is taken too: it gets step 1 only" in carry
    # The record that decides is the one merge-check ranks latest.
    assert "ranked as `WF merge-check` ranks it" in carry
    assert "`hand_off.on_head`" in carry
    assert "it isn't at the cap and it isn't a retry" in carry


def test_a_security_problems_details_stay_out_of_the_hand_off():
    carry = _carry()
    assert "only in this chat" in carry and "never in the hand-off" in carry
    assert "by its area only" in carry


def test_tickets_held_for_the_owner_go_to_the_owner_as_today():
    carry = _carry()
    assert "security or safety problem in code on the base branch" in carry and "`security=main`" in carry
    # A review reason makes `merge-check` say `not_yet`: a protected path shows as the `kit_files` note and `files`.
    assert "touches a protected path (`WF merge-check`'s `kit_files` note: the JSON's `files` isn't empty" in carry
    assert "go to the owner as today" in carry and "never carried on" in carry
    # Files it couldn't read can't rule a protected path out.
    assert "or whose files it couldn't read" in carry


def test_the_kick_off_adopts_every_carry_on_ticket_first_without_asking():
    skill = _skill()
    work = skill.split("**The work**", 1)[1].split("\n\n", 1)[0]
    line = next(ln for ln in work.splitlines() if "`workflow:carry-on`" in ln)
    assert "without asking" in line and "first" in line and "not a retry" in line
    assert "`attempts: 0`" in line and "`hand_off.url`" in line
    # Outside the plan and scope, so exclusion questions and a ticket named in chat leave it in.
    assert "outside `charter.plan` and `scope.tickets`" in line
    assert "it keeps `workflow:carry-on` until its session is created (check-in step 5)" in line
    # The estimate and the one page count it.
    assert "give it first in the `--tickets` of `WF charter estimate` and `WF charter splice`" in line
    # A failed read is tried again, a bounded number of times.
    assert "at most 3 times" in line
    # `start` leaves a ticket its run adopted.
    assert "`start`'s \"Carry on\" leaves a ticket that also has `workflow:in-progress` to its run" in line
    # A failed read never gives `none`; a closed pull request makes it a ready ticket again.
    assert "On a \"couldn't read\" reason, run it again at the next check-in rather than start the session" in line
    assert "remove `workflow:carry-on` and add `ready-for-agent` back" in line
    plan = skill.split("3. **The plan.**", 1)[1].split("\n", 1)[0]
    assert "after the carry-on tickets first" in plan
    named = next(ln for ln in skill.splitlines() if ln.startswith("- **No run in progress**"))
    assert "and so do carry-on tickets" in named
    # The label goes only once the session exists, so a refused render or a failed start keeps it.
    record = next(ln for ln in skill.splitlines() if ln.startswith("6. Record it in the state: the session id"))
    assert "A carry-on ticket (\"The work\", in the pre-flight) then loses `workflow:carry-on` and gets `ready-for-agent` back" in record
    claim = next(ln for ln in skill.splitlines() if ln.startswith("1. Claim it:"))
    assert "carry-on" not in claim
    # Named in chat: never checked with `WF ready`, which can't list it.
    chat = skill.split("## A ticket named in chat", 1)[1].split("\n## ", 1)[0]
    named_carry = next(p for p in chat.split("\n\n") if p.startswith("**A carry-on ticket named**"))
    assert "`WF ready` never lists it" in named_carry and "add it to the state as `queued`" in named_carry
    assert "set aside, carried on." in skill
    queued = skill.split("1. **Queued tickets** in the state:", 1)[1].split("\n", 1)[0]
    assert queued.lstrip().startswith("carry-on tickets adopted at kick-off first")


def test_the_briefing_section_names_the_hand_off_slot():
    brief = _skill().split("## A ticket session's briefing", 1)[1].split("\n## ", 1)[0]
    row = next(ln for ln in brief.splitlines() if ln.startswith("| `hand_off` |"))
    assert "Optional, for a carry-on ticket" in row and "`hand_off.url`" in row
    assert "handle it as a \"Starts from:\" line that stops the render" in row


def test_the_set_up_creates_the_label():
    labels = _read("skills/setup-workflow/SKILL.md").split("**9. Labels,**", 1)[1].split("\n\n", 1)[0]
    assert "`workflow:carry-on`" in labels


def test_the_run_report_lists_carried_on_tickets():
    report = _read("skills/run-report/SKILL.md")
    assert "`workflow:carry-on`" in report and "`hand_off.url`" in report and "how many were carried on" in report


def test_the_charter_doc_says_the_end_time_carries_on():
    end = next(ln for ln in _read("docs/charter.md").splitlines() if ln.startswith("- **The end time**"))
    assert "`workflow:carry-on`" in end and "next run" in end


def test_the_changelog_has_the_note():
    unreleased = since_0110(_read("CHANGELOG.md"))
    assert "(#380, part of spec #412)" in unreleased and "`workflow:carry-on`" in unreleased

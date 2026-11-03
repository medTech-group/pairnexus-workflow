"""#376 (spec #412, "Runs" and "The bar"): in attended work, `start` lists the
tickets left `workflow:carry-on` with a "Carry on" choice that starts from the
hand-off, and the flow's §2 and `start`'s additions to it say when a ticket
needs a `## Bar`. Its seams: `workflow status` (the list `start` offers from)
and the kit's text contracts."""

import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from changelog_notes import since_0110
from workflow import issues, status

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _issue(n, labels=(), state="open", body="Area: start"):
    return {"number": n, "title": f"t{n}", "labels": [{"name": x} for x in labels], "body": body, "state": state}


def _section(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _nums(items):
    return [i.number for i in items]


# ---------- workflow status: the carry-on tickets ----------


def test_the_label_is_named_once():
    assert issues.CARRY_ON_LABEL == "workflow:carry-on"


def test_a_carry_on_ticket_is_listed(tmp_path):
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on"])], [])
    assert _nums(st.carry_on) == [41]
    assert not st.to_triage and not st.waiting and not st.ready and not st.in_progress


def test_the_label_is_read_without_case(tmp_path):
    st = status.snapshot(tmp_path, True, [_issue(41, ["Workflow:Carry-On"])], [])
    assert _nums(st.carry_on) == [41]


def test_a_closed_one_is_not_listed(tmp_path):
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on"], state="closed")], [])
    assert st.carry_on == []


@pytest.mark.parametrize("label", ["needs-human", "owner-task", "ready-for-human", "needs-info"])
def test_one_waiting_on_a_person_waits_and_is_not_offered(tmp_path, label):
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on", label])], [])
    assert st.carry_on == [] and _nums(st.waiting) == [41]


def test_one_a_run_adopted_is_left_to_the_run(tmp_path):
    # The conductor adds workflow:in-progress when it adopts a carry-on ticket (#380).
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on", "workflow:in-progress"])], [])
    assert st.carry_on == []
    assert _nums(st.in_progress) == [41] and "workflow:carry-on" in st.in_progress[0].detail


def test_several_are_listed_in_number_order(tmp_path):
    st = status.snapshot(tmp_path, True, [_issue(52, ["workflow:carry-on"]), _issue(41, ["workflow:carry-on"])], [])
    assert _nums(st.carry_on) == [41, 52]


def test_a_carry_on_ticket_never_reads_as_one_to_sort(tmp_path):
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on", "needs-triage"])], [])
    assert _nums(st.carry_on) == [41] and st.to_triage == []


def test_one_still_labelled_ready_is_carried_on_not_ready(tmp_path):
    # A stray `ready-for-agent` never offers it as a fresh build that skips the hand-off (round 1, explorer 1).
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on", "ready-for-agent"], body="Area: start\n\n## Blocked by\n\nNone")], [])
    assert _nums(st.carry_on) == [41] and st.ready == []


@pytest.mark.parametrize("labels, body, section", [
    (["spec"], "", "specs"),
    (["wayfinder:map"], "", "maps"),
    ([], "<!-- workflow:item path=ticket -->", "planned"),
])
def test_only_a_ticket_is_carried_on(tmp_path, labels, body, section):
    # A spec, a map or a planned item keeps its own section (round 1, explorer 2).
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on", *labels], body=body)], [])
    assert st.carry_on == [] and _nums(getattr(st, section)) == [41]


def test_the_text_and_the_json_list_them(tmp_path):
    st = status.snapshot(tmp_path, True, [_issue(41, ["workflow:carry-on"])], [])
    out = status.text(st)
    assert "Carried on (handed on by an earlier session, review not yet clean): 1" in out
    assert "- #41 t41" in out
    assert [i["number"] for i in st.as_dict()["carry_on"]] == [41]


def test_the_cli_lists_them(tmp_path):
    (tmp_path / "issues.json").write_text(json.dumps([_issue(41, ["workflow:carry-on"])]))
    (tmp_path / "prs.json").write_text("[]")
    p = subprocess.run([sys.executable, "-B", str(CLI), "status", "--json", "--issues", "issues.json", "--prs", "prs.json"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert [i["number"] for i in json.loads(p.stdout)["carry_on"]] == [41]


# ---------- start: the "Carry on" choice ----------


START = "skills/start/SKILL.md"


def _carrying_on():
    return _section(_read(START), "**Carrying on.**", "**What the other options lead to:**")


def test_start_offers_carry_on_first_and_recommended():
    text = _read(START)
    row = next(ln for ln in text.splitlines() if ln.startswith("| **Carry on: #<n>, handed on (Recommended)**"))
    assert "`carry_on`" in row and "first" in row
    # The kit update and the set-up check give way to it, without "(Recommended)".
    assert "a kit update or **Check the set-up** comes after it, without \"(Recommended)\"" in row


def _carry_on_row():
    return next(ln for ln in _carrying_on().splitlines() if ln.startswith("| A carry-on ticket"))


def test_start_carries_on_from_the_hand_off():
    row = _carry_on_row()
    assert "`workflow:carry-on`" in row
    assert "**Carry on (Recommended)**" in row
    # Choosing it takes the label off first, so no run adopts it as well, and claims it in the
    # same write, so a stop before `build-ticket` never leaves it unlabelled (round 1, correctness 3).
    assert re.search(r"in one label write, before any other write: remove `workflow:carry-on` and add `workflow:in-progress`", row)
    # It starts from the hand-off: merge-check's hand_off, then build-ticket on its pull request's branch.
    assert "`WF merge-check --fetch <PR> --json`" in row and "`hand_off.url`" in row
    assert "`build-ticket`" in row and "its pull request's branch" in row
    assert "not a retry" in row


def test_start_leaves_a_run_s_carry_on_ticket_to_its_run():
    row = _carry_on_row()
    assert "with a run in progress, the run adopted it: leave it to its run" in row
    # With none, it is claimed work, whose "Carry on from there" takes the label off first (round 1, correctness 4).
    claimed = next(ln for ln in _carrying_on().splitlines() if ln.startswith("| Work claimed (`workflow:in-progress`)"))
    assert "take `workflow:carry-on` off first" in claimed


def test_each_other_first_option_gives_way_to_carry_on():
    # One "(Recommended)" first option, whatever else is offered (round 1, spec 1, correctness 2).
    rows = [ln for ln in _read(START).splitlines() if ln.startswith(("| **Update the workflow kit", "| **Check the set-up**", "| **A brand-new project"))]
    assert len(rows) == 3
    for row in rows:
        assert "unless a carry-on ticket is offered (above)" in row, row[:40]


def test_a_carry_on_ticket_is_offered_once():
    row = next(ln for ln in _read(START).splitlines() if ln.startswith("| **Carry on: <the thing>**"))
    assert "a carry-on ticket has its own option (above)" in row


def test_start_reads_carry_on_tickets_in_the_look_around():
    look = _section(_read(START), "It reports:", "Tell the person what matters")
    assert "`workflow:carry-on`" in look


# ---------- the bar: flow §2 and start's additions ----------


def _flow_tickets():
    return _section(_read("docs/flow.md"), "2. Follow `to-tickets`", "3. Anything only the owner can do")


def test_flow_s_ticket_list_has_the_bar():
    text = _flow_tickets()
    bullet = next(ln for ln in text.splitlines() if ln.strip().startswith("- `## Bar`"))
    assert "may" in bullet and "`run.bar_areas`" in bullet and "must" in bullet
    for part in ("must handle", "fail closed", "the limits it accepts", "backstop"):
        assert part in bullet.casefold()
    assert "`workflow ready` notes" in bullet


def _example_bar():
    m = re.search(r"\n( *)```markdown\n(.*?)\n\1```\n", _flow_tickets(), re.S)
    assert m, "an example bar in a fenced block"
    return textwrap.dedent(m.group(2)) + "\n"


def test_flow_gives_a_plain_example_bar():
    lines = _example_bar().splitlines()
    assert lines[:2] == ["## Bar", ""] and len(lines) == 5, "a plain ## Bar section with three bullets"
    assert [ln.split(":")[0] for ln in lines[2:]] == ["- Must handle", "- Fail closed", "- Accepted limits"]


def test_the_example_bar_counts_as_a_bar():
    assert issues.has_bar(_example_bar())


def test_the_bullet_before_the_bar_still_reads_as_a_list_item():
    line = next(ln for ln in _flow_tickets().splitlines() if ln.strip().startswith("- `Review: small`"))
    assert line.endswith(";")


def test_start_s_quick_ticket_has_the_bar():
    step = _section(_read(START), "**Quick ticket** (flow §2", "**The end check,**")
    bullet = next(ln for ln in step.splitlines() if ln.strip().startswith("- `## Bar`"))
    assert "`run.bar_areas`" in bullet and "must" in bullet and "flow §2" in bullet


def test_start_s_breakdown_has_the_bar():
    step = _section(_read(START), "3. **The tickets.**", "Then ask:")
    assert "`run.bar_areas`" in step and "`## Bar`" in step


# ---------- the changelog ----------


def test_the_changelog_has_the_note():
    notes = since_0110(_read("CHANGELOG.md"))
    unreleased = notes[:notes.index("\n## 0.", 1)] if "\n## 0." in notes else notes
    assert "(#376" in unreleased
    assert "`workflow:carry-on`" in unreleased and "## Bar" in unreleased

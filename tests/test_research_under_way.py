"""#514 (spec #505, "The CLI" and "Holding back"): `workflow status` lists open
`research` issues under "Research under way", never as new issues to sort, and
shows an item held by an open owner task under its `## Blocked by` as held;
`start` offers a "Carry on" row for a research issue, and an item linking an
open research issue as that study's "Carry on"; `next` and `start` skip held
items. Its seams: `workflow status` fed files (seam 1) and the kit's text
contracts (seam 2)."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from changelog_notes import since_0110
from workflow import issues, status

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _issue(n, labels=(), state="open", body="", state_reason=None):
    i = {"number": n, "title": f"t{n}", "labels": [{"name": x} for x in labels], "body": body, "state": state}
    if state_reason:
        i["state_reason"] = state_reason
    return i


def _nums(items):
    return [i.number for i in items]


def _snap(tmp_path, issue_list, prs=()):
    return status.snapshot(tmp_path, True, issue_list, list(prs), repo="acme/demo", areas=["start"])


HELD = "Area: start\n\n## Blocked by\n\n- #9\n"


# ---------- seam 1: research issues are under way ----------


def test_the_label_is_named_once():
    assert issues.RESEARCH_LABEL == "research"


def test_a_research_issue_is_under_way_not_to_sort(tmp_path):
    st = _snap(tmp_path, [_issue(43, ["research"])])
    assert _nums(st.research) == [43]
    assert st.to_triage == [] and st.waiting == [] and st.planned == []


@pytest.mark.parametrize("extra", [["needs-triage"], ["Needs-Triage"], ["needs-info"], ["ready-for-agent"], ["owner-task"]])
def test_a_research_issue_with_another_label_is_still_under_way(tmp_path, extra):
    st = _snap(tmp_path, [_issue(43, ["research", *extra], body="Area: start\n\n## Blocked by\n\nNone")])
    assert _nums(st.research) == [43]
    assert st.to_triage == [] and st.waiting == [] and st.ready == []


def test_the_label_is_read_without_case(tmp_path):
    st = _snap(tmp_path, [_issue(43, ["Research"])])
    assert _nums(st.research) == [43] and st.to_triage == []


def test_a_closed_research_issue_is_not_listed(tmp_path):
    st = _snap(tmp_path, [_issue(43, ["research"], state="closed")])
    assert st.research == [] and st.to_triage == []


def test_a_claimed_research_issue_is_claimed_and_under_way(tmp_path):
    st = _snap(tmp_path, [_issue(43, ["research", "workflow:in-progress"])])
    assert _nums(st.in_progress) == [43] and _nums(st.research) == [43]


def test_research_issues_are_listed_in_number_order(tmp_path):
    st = _snap(tmp_path, [_issue(52, ["research"]), _issue(43, ["research"])])
    assert _nums(st.research) == [43, 52]


def test_a_research_issue_in_a_run_is_the_run_s(tmp_path):
    st = _snap(tmp_path, [_issue(43, ["research", "workflow:run"])])
    assert _nums(st.run) == [43] and st.research == []


# ---------- seam 1: items held by an open owner task ----------


@pytest.mark.parametrize("task_label", ["owner-task", "ready-for-human"])
def test_a_planned_item_held_by_an_open_owner_task_is_held(tmp_path, task_label):
    body = HELD + "\n<!-- workflow:item path=spec -->"
    st = _snap(tmp_path, [_issue(10, body=body), _issue(9, [task_label])])
    assert _nums(st.held) == [10] and "#9" in st.held[0].detail
    assert st.planned == []
    assert _nums(st.waiting) == [9]


def test_a_spec_held_by_an_open_owner_task_is_held(tmp_path):
    st = _snap(tmp_path, [_issue(3, ["spec"], body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [3] and st.specs == []


def test_a_build_ticket_held_by_an_open_owner_task_is_held_not_ready(tmp_path):
    st = _snap(tmp_path, [_issue(4, ["ready-for-agent"], body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [4] and st.ready == []


def test_an_item_with_no_label_held_by_an_owner_task_is_held_not_to_sort(tmp_path):
    st = _snap(tmp_path, [_issue(10, body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [10] and st.to_triage == []


def test_the_owner_task_closed_releases_the_item(tmp_path):
    body = HELD + "\n<!-- workflow:item path=spec -->"
    st = _snap(tmp_path, [_issue(10, body=body), _issue(9, ["owner-task"], state="closed", state_reason="completed")])
    assert st.held == [] and _nums(st.planned) == [10]


def test_an_open_blocker_that_is_not_an_owner_task_doesnt_hold_it(tmp_path):
    body = HELD + "\n<!-- workflow:item path=spec -->"
    st = _snap(tmp_path, [_issue(10, body=body), _issue(9, ["ready-for-agent"], body="Area: start")])
    assert st.held == [] and _nums(st.planned) == [10]


def test_an_owner_task_missing_from_the_list_doesnt_hold_it(tmp_path):
    body = HELD + "\n<!-- workflow:item path=spec -->"
    st = _snap(tmp_path, [_issue(10, body=body)])
    assert st.held == [] and _nums(st.planned) == [10]


def test_every_open_owner_task_is_named(tmp_path):
    body = "## Blocked by\n\n- #9\n- #8\n- #7\n\n<!-- workflow:item path=ticket -->"
    st = _snap(tmp_path, [_issue(10, body=body), _issue(9, ["owner-task"]), _issue(8, ["owner-task"]), _issue(7, ["owner-task"], state="closed")])
    assert _nums(st.held) == [10]
    assert "#9" in st.held[0].detail and "#8" in st.held[0].detail and "#7" not in st.held[0].detail


def test_a_spec_waiting_on_a_person_and_held_by_an_owner_task_is_held(tmp_path):
    # A spec is listed as a spec whatever its waiting label, so only held keeps it from being offered.
    st = _snap(tmp_path, [_issue(3, ["spec", "needs-info"], body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [3] and st.specs == [] and _nums(st.waiting) == [9]


def test_a_planned_item_waiting_on_a_person_and_held_by_an_owner_task_is_held(tmp_path):
    body = HELD + "\n<!-- workflow:item path=spec -->"
    st = _snap(tmp_path, [_issue(10, ["needs-info"], body=body), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [10] and st.planned == [] and _nums(st.waiting) == [9]


@pytest.mark.parametrize("waiting_label", ["needs-info", "needs-human", "owner-task", "ready-for-human"])
def test_an_item_waiting_on_a_person_and_held_by_an_owner_task_is_held(tmp_path, waiting_label):
    # Without the owner task it would be listed as waiting on a person; with it, it is held all the same.
    st = _snap(tmp_path, [_issue(6, [waiting_label], body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [6] and st.held[0].detail == "owner task #9"
    assert _nums(st.waiting) == [9]


def test_a_map_and_a_research_issue_keep_their_own_sections(tmp_path):
    st = _snap(tmp_path, [_issue(2, ["wayfinder:map"], body=HELD), _issue(43, ["research"], body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.maps) == [2] and _nums(st.research) == [43] and st.held == []


def test_a_held_carry_on_ticket_is_held_not_offered(tmp_path):
    st = _snap(tmp_path, [_issue(41, ["workflow:carry-on"], body=HELD), _issue(9, ["owner-task"])])
    assert _nums(st.held) == [41] and st.carry_on == []


# ---------- seam 1: the text, the JSON and the CLI ----------


def test_the_text_has_both_headings(tmp_path):
    st = _snap(tmp_path, [_issue(43, ["research"]), _issue(10, body=HELD), _issue(9, ["owner-task"])])
    out = status.text(st)
    assert "Research under way: 1" in out and "- #43 t43" in out
    held = next(ln for ln in out.splitlines() if ln.startswith("- #10 "))
    assert "#9" in held
    assert re.search(r"^Held by an open owner task.*: 1$", out, re.M), out
    assert "New issues to sort" not in out


def test_research_under_way_comes_before_the_sections_it_is_kept_out_of(tmp_path):
    keys = [k for k, _ in status._SECTIONS]
    assert keys.index("research") < keys.index("to_triage")
    assert keys.index("held") < keys.index("waiting")


def test_the_cli_lists_them(tmp_path):
    issue_list = [_issue(43, ["research", "needs-triage"]), _issue(10, body=HELD), _issue(9, ["owner-task"])]
    (tmp_path / "issues.json").write_text(json.dumps(issue_list))
    (tmp_path / "prs.json").write_text("[]")
    p = subprocess.run([sys.executable, "-B", str(CLI), "status", "--json", "--issues", "issues.json", "--prs", "prs.json"],
                       capture_output=True, text=True, cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert [i["number"] for i in out["research"]] == [43]
    assert [i["number"] for i in out["held"]] == [10] and "#9" in out["held"][0]["detail"]
    assert out["to_triage"] == []


# ---------- seam 2: start ----------


START = "skills/start/SKILL.md"
NEXT = "skills/next/SKILL.md"


def _section(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


def _carrying_on():
    return _section(_read(START), "**Carrying on.**", "**What the other options lead to:**")


def _row(table, starts):
    return next(ln for ln in table.splitlines() if ln.startswith(starts))


def test_start_reads_research_and_held_items_in_the_look_around():
    look = _section(_read(START), "It reports:", "Tell the person what matters")
    assert "`research`" in look and "Research under way" in look
    assert "`held`" in look and "owner task" in look


def test_start_has_a_carry_on_row_for_a_research_issue():
    row = _row(_carrying_on(), "| A research issue")
    assert "status's `research`" in row
    assert "**Carry on (Recommended)**" in row
    # It continues the study, or fixes the note the issue names.
    assert "continues the study" in row and "fixes the note" in row
    # It points to the study skill's section 5, the one rule for a research issue, rather than restate it.
    assert "`study` skill's section 5" in row


def test_start_offers_an_item_linking_an_open_research_issue_as_that_study_s_carry_on():
    row = _row(_carrying_on(), "| An item whose issue links an open research issue")
    assert '"Study under way: #<n>"' in row
    assert "that study's **Carry on**" in row
    assert "never started afresh" in row and "second study" in row


def test_a_destination_item_with_a_study_under_way_is_that_study_s_carry_on_not_a_spec_to_start():
    # A map's Destination item has no issue of its own: its "Study under way" link is a comment
    # on the map naming it (the study skill's section 5). `start` looks there for a clear map's
    # next spec, and `next` skips that item while the study is open.
    row = _row(_carrying_on(), "| An item whose issue links an open research issue")
    assert "Destination item" in row and "comment on the map naming it" in row
    assert "clear map" in row
    clear = next(ln for ln in _read(NEXT).splitlines() if ln.startswith("- **A clear map**"))
    assert '"Study under way: #<n>"' in clear and "comment on the map naming it" in clear
    assert "`study` skill's section 5" in clear
    # Skipped while its research issue is open, ready to spec again once it closes. Read only
    # the text after the skip: the line's "has no open children" must not stand in for it.
    skip = clear[clear.casefold().index("skipping"):]
    assert "with #<n> open" in skip
    assert "ready to spec again once #<n> closes" in skip
    assert "that study's **Carry on**" in skip


def test_start_skips_held_items():
    text = _read(START)
    rule = next(ln for ln in text.splitlines() if ln.startswith("**Held items.**"))
    assert "`## Blocked by`" in rule and "open owner task" in rule
    assert "status's `held`" in rule
    assert "never offer" in rule
    # Under "Carry on: <the thing>", a held item is never the thing.
    row = _row(text, "| **Carry on: <the thing>**")
    assert "held" in row


def test_next_skips_held_items():
    text = _read(NEXT)
    rule = next(ln for ln in text.splitlines() if ln.startswith("**Held items.**"))
    assert "`## Blocked by`" in rule and "open owner task" in rule
    assert "`held`" in rule
    assert "skip" in rule.casefold()
    # Picked by number, it says it's held and stops.
    assert "stop" in rule


def test_held_items_rule_leaves_the_destination_item_s_line_to_its_own_ticket():
    # A Destination item's `Blocked by:` line in the map's body is another ticket's (#505's
    # ticket for a finding that needs a professional): these rules name only an item's issue.
    for rel in (START, NEXT):
        rule = next(ln for ln in _read(rel).splitlines() if ln.startswith("**Held items.**"))
        assert "issue" in rule


# ---------- the changelog ----------


def _assert_the_note(text):
    notes = since_0110(text)
    start = notes.index("(#514")
    note = notes[start:notes.index("Tests: `tests/test_research_under_way.py`.", start)]
    assert "Research under way" in note and "held" in note and "Carry on" in note


def test_the_changelog_has_the_note():
    _assert_the_note(_read("CHANGELOG.md"))


def test_the_note_is_under_unreleased():
    text = _read("CHANGELOG.md")
    head = text.index("## Unreleased\n")
    nxt = text.index("\n## ", head + 1)
    assert "(#514" in text[head:nxt]

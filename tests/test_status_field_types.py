"""`workflow status --issues F --prs G` reads past an issue's or pull
request's field of the wrong type (#770): the item is treated as it would be
without that field, never a traceback. Run through `cli.main`.
"""

import copy
import json
from pathlib import Path

import pytest

from changelog_notes import entry
from workflow import cli

TICKET = {
    "number": 1,
    "title": "Add notes",
    "state": "open",
    "labels": [{"name": "ready-for-agent"}],
    "body": "Area: notes\n\n## Blocked by\n\n#2\n",
}
BLOCKER = {"number": 2, "title": "Store notes", "state": "closed", "state_reason": "completed", "labels": [], "body": ""}
SPEC = {"number": 3, "title": "Spec: notes", "state": "open", "labels": [{"name": "spec"}], "body": "", "sub_issues_summary": {"total": 3, "completed": 1}}
PR_ITEM = {"number": 4, "title": "Notes list", "state": "closed", "pull_request": {"merged_at": "2026-11-01T00:00:00Z"}}
PR = {"number": 30, "title": "Notes list", "state": "open", "body": "Closes #9", "draft": False, "head": {"ref": "claude/build-12"}}


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _status(monkeypatch, capsys, tmp_path, issues, prs, *extra):
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(json.dumps(issues), encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = cli.main(["status", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    return out.out


def _json(monkeypatch, capsys, tmp_path, issues, prs):
    return json.loads(_status(monkeypatch, capsys, tmp_path, issues, prs, "--json"))


def _set(item: dict, path: tuple, value) -> dict:
    out = copy.deepcopy(item)
    *parents, last = path
    where = out
    for p in parents:
        where = where[p]
    if value is _DROP:
        where.pop(last, None)
    else:
        where[last] = value
    return out


_DROP = object()

# (which item, the field's path, the value of the wrong type, the item as it reads: the path dropped)
ISSUE_CASES = [
    # The ticket's own cases.
    ("ticket", ("state",), 5, ("state",)),
    ("ticket", ("labels",), 5, ("labels",)),
    ("ticket", ("title",), 5, ("title",)),
    ("ticket", ("body",), 5, ("body",)),
    ("spec", ("sub_issues_summary", "total"), "3", ("sub_issues_summary",)),
    # The other fields `status` reads.
    ("spec", ("sub_issues_summary", "completed"), "1", ("sub_issues_summary",)),
    ("spec", ("sub_issues_summary",), [3], ("sub_issues_summary",)),
    ("spec", ("sub_issues_summary", "total"), True, ("sub_issues_summary",)),
    ("ticket", ("issue_dependencies_summary",), {"blocked_by": "1"}, ("issue_dependencies_summary",)),
    ("ticket", ("issue_dependencies_summary",), 5, ("issue_dependencies_summary",)),
    ("blocker", ("state",), 5, ("state",)),
    ("blocker", ("state_reason",), 5, ("state_reason",)),
    ("blocker", ("labels",), {"name": "owner-task"}, ("labels",)),
    ("blocker", ("body",), ["Area: x"], ("body",)),
    ("pr_item", ("state",), 5, ("state",)),
]


def _issues(which: str, path: tuple, value) -> list[dict]:
    items = {"ticket": TICKET, "blocker": BLOCKER, "spec": SPEC, "pr_item": PR_ITEM}
    return [_set(item, path, value) if name == which else copy.deepcopy(item) for name, item in items.items()]


@pytest.mark.parametrize("which,path,value,dropped", ISSUE_CASES, ids=lambda x: repr(x))
def test_an_issue_field_of_the_wrong_type_reads_as_missing(monkeypatch, capsys, tmp_path, which, path, value, dropped):
    got = _json(monkeypatch, capsys, tmp_path, _issues(which, path, value), [PR])
    without = _json(monkeypatch, capsys, tmp_path, _issues(which, dropped, _DROP), [PR])
    assert got == without


def test_the_tickets_own_state_case_gives_the_status_in_text(monkeypatch, capsys, tmp_path):
    """The first acceptance criterion as written: `[{"number": 1, "state": 5}]`."""
    out = _status(monkeypatch, capsys, tmp_path, [{"number": 1, "state": 5}], [PR])
    assert "Open pull requests: 1" in out
    # Read without its state, an issue is open, as GitHub's open issues are.
    assert "#1 " in out


@pytest.mark.parametrize(
    "issues",
    [
        [{"number": 1, "state": 5}],
        [{"number": 1, "labels": 5}],
        [{"number": 1, "title": 5, "labels": []}],
        [{"number": 1, "body": 5, "labels": [{"name": "x"}]}],
        [{"number": 3, "title": "Spec: notes", "labels": [{"name": "spec"}], "sub_issues_summary": {"total": "3"}}],
    ],
    ids=["state", "labels", "title", "body", "sub_issues_summary"],
)
@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_the_tickets_issue_cases_give_no_traceback(monkeypatch, capsys, tmp_path, issues, as_json):
    _status(monkeypatch, capsys, tmp_path, issues, [PR], *(["--json"] if as_json else []))


def test_a_label_of_the_wrong_type_is_read_past_and_the_others_kept(monkeypatch, capsys, tmp_path):
    labels = [{"name": 5}, 7, None, ["x"], "workflow:in-progress", {"name": "spec"}]
    got = _json(monkeypatch, capsys, tmp_path, [{**TICKET, "labels": labels}], [])
    want = _json(monkeypatch, capsys, tmp_path, [{**TICKET, "labels": ["workflow:in-progress", {"name": "spec"}]}], [])
    assert got == want
    assert [i["number"] for i in got["in_progress"]] == [1]


def test_a_pull_request_marker_of_the_wrong_type_still_marks_a_pull_request(monkeypatch, capsys, tmp_path):
    """`pull_request` says the item is a pull request: of the wrong type, it is
    still one, read without its details, never listed as an issue."""
    item = {"number": 5, "title": "Notes list", "state": "open", "labels": [], "pull_request": 5}
    got = _json(monkeypatch, capsys, tmp_path, [item], [])
    want = _json(monkeypatch, capsys, tmp_path, [{**item, "pull_request": {}}], [])
    assert got == want
    assert got["to_triage"] == []


def test_a_blocker_whose_pull_request_marker_is_of_the_wrong_type_holds_its_ticket(monkeypatch, capsys, tmp_path):
    """A closed item whose `pull_request` is `5`, named as a ticket's blocker:
    still a pull request, read without its details, so one closed without
    merging, and the ticket isn't ready. Never a traceback."""
    ticket = {**TICKET, "body": "## Blocked by\n\n#4\n"}
    got = _json(monkeypatch, capsys, tmp_path, [ticket, {"number": 4, "state": "closed", "pull_request": 5}], [])
    assert [i["number"] for i in got["ready"]] == []
    merged = {"number": 4, "state": "closed", "pull_request": {"merged_at": "2026-11-01T00:00:00Z"}}
    assert [i["number"] for i in _json(monkeypatch, capsys, tmp_path, [ticket, merged], [])["ready"]] == [1]


def test_a_null_pull_request_marker_still_marks_a_pull_request(monkeypatch, capsys, tmp_path):
    """A null `pull_request` doesn't read as missing, unlike the other fields:
    the item is still a pull request, as before #770. Named as a blocker, it
    is one closed without merging; open, it isn't listed to sort."""
    ticket = {**TICKET, "body": "## Blocked by\n\n#4\n"}
    blocker = {"number": 4, "title": "Notes list", "state": "closed", "state_reason": "completed", "pull_request": None}
    assert _json(monkeypatch, capsys, tmp_path, [ticket, blocker], [])["ready"] == []
    without = {k: v for k, v in blocker.items() if k != "pull_request"}
    assert [i["number"] for i in _json(monkeypatch, capsys, tmp_path, [ticket, without], [])["ready"]] == [1]
    item = {"number": 5, "title": "Notes list", "state": "open", "labels": [], "pull_request": None}
    assert _json(monkeypatch, capsys, tmp_path, [item], [])["to_triage"] == []


def test_the_changelog_note_says_a_null_pull_request_still_marks_one():
    note = entry("#770, found in the review of #757's pull request")
    assert "A null reads as missing, as before." not in note
    assert "except a null `pull_request`, which still marks a pull request" in note


def test_the_architecture_line_says_a_summary_with_a_bad_count_is_left_out_whole():
    page = (Path(__file__).resolve().parents[1] / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `as_read`:"))
    assert "the sub-issue and dependency summaries' counts" not in line
    assert "a sub-issue or dependency summary whose count isn't a whole number, left out whole" in line


def test_the_799_notes_claim_parity_only_on_parents():
    """`status` leaves out carried-on tickets that `ready` lists, so #799's
    lines say only that a parent is ready in neither, as `ready` reads it."""
    page = (Path(__file__).resolve().parents[1] / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `as_read`:"))
    note = entry("#799, found in the review of #780's pull request")
    assert "list the same ready tickets" not in line
    assert "hold the same numbers" not in note
    for text in (line, note):
        assert "so a parent is never a ready ticket in either, as `ready` reads it" in text


PR_CASES = [
    # The ticket's own cases.
    (("head",), "main", ("head",)),
    (("title",), 5, ("title",)),
    # The other fields `status` reads.
    (("head", "ref"), 5, ("head", "ref")),
    (("state",), 5, ("state",)),
    (("body",), 5, ("body",)),
    (("draft",), "no", ("draft",)),
]


@pytest.mark.parametrize("path,value,dropped", PR_CASES, ids=lambda x: repr(x))
def test_a_pull_request_field_of_the_wrong_type_reads_as_missing(monkeypatch, capsys, tmp_path, path, value, dropped):
    issues = [copy.deepcopy(TICKET), copy.deepcopy(BLOCKER), {**copy.deepcopy(TICKET), "number": 9}]
    got = _json(monkeypatch, capsys, tmp_path, issues, [_set(PR, path, value)])
    without = _json(monkeypatch, capsys, tmp_path, issues, [_set(PR, dropped, _DROP)])
    assert got == without


@pytest.mark.parametrize(
    "prs",
    [[{"number": 30, "head": "main"}], [{"number": 30, "title": 5}]],
    ids=["head", "title"],
)
@pytest.mark.parametrize("as_json", [False, True], ids=["text", "json"])
def test_the_tickets_pull_request_cases_give_no_traceback(monkeypatch, capsys, tmp_path, prs, as_json):
    out = _status(monkeypatch, capsys, tmp_path, [], prs, *(["--json"] if as_json else []))
    assert "30" in out


def test_well_typed_fields_are_read_as_before(monkeypatch, capsys, tmp_path):
    st = _json(monkeypatch, capsys, tmp_path, _issues("ticket", ("title",), "Add notes"), [PR])
    assert [(i["number"], i["detail"]) for i in st["ready"]] == [(1, "notes")]
    assert [(i["number"], i["detail"]) for i in st["specs"]] == [(3, "2 of 3 tickets open")]
    assert [(p["number"], p["detail"]) for p in st["prs"]] == [(30, "claude/build-12")]


# #799: a parent whose `completed` count has the wrong type is still a parent.
PARENT = {
    "number": 1,
    "title": "Parent",
    "state": "open",
    "labels": [{"name": "ready-for-agent"}],
    "body": "Area: a\n",
    "sub_issues_summary": {"total": 3, "completed": "1"},
}
BAD_COMPLETED = ["1", 1.5, True, [1]]


def _ready_json(monkeypatch, capsys, tmp_path, issues, prs):
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(json.dumps(issues), encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = cli.main(["ready", "--issues", "issues.json", "--prs", "prs.json", "--json"])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    return json.loads(out.out)


def _ready_section(text: str) -> list[str]:
    lines = text.splitlines()
    start = next((k for k, l in enumerate(lines) if l.startswith("Ready build tickets")), None)
    if start is None:
        return []
    section = []
    for l in lines[start + 1 :]:
        if not l.startswith("- "):
            break
        section.append(l)
    return section


@pytest.mark.parametrize("completed", BAD_COMPLETED, ids=repr)
def test_a_parent_whose_completed_count_has_the_wrong_type_is_never_ready(monkeypatch, capsys, tmp_path, completed):
    parent = _set(PARENT, ("sub_issues_summary", "completed"), completed)
    got = _json(monkeypatch, capsys, tmp_path, [parent], [])
    assert 1 not in [i["number"] for i in got["ready"]]
    text = _status(monkeypatch, capsys, tmp_path, [parent], [])
    assert not [l for l in _ready_section(text) if l.startswith("- #1 ")]


@pytest.mark.parametrize("completed", BAD_COMPLETED, ids=repr)
def test_such_a_parent_is_listed_as_a_parent_whose_tickets_are_unknown(monkeypatch, capsys, tmp_path, completed):
    parent = _set(PARENT, ("sub_issues_summary", "completed"), completed)
    got = _json(monkeypatch, capsys, tmp_path, [parent], [])
    assert [(i["number"], i["detail"]) for i in got["specs"]] == [(1, "parent issue, tickets unknown (no sub_issues_summary)")]


@pytest.mark.parametrize("completed", BAD_COMPLETED, ids=repr)
def test_a_spec_with_such_a_summary_still_reads_tickets_unknown(monkeypatch, capsys, tmp_path, completed):
    spec = _set(SPEC, ("sub_issues_summary", "completed"), completed)
    got = _json(monkeypatch, capsys, tmp_path, [spec], [])
    assert [(i["number"], i["detail"]) for i in got["specs"]] == [(3, "tickets unknown (no sub_issues_summary)")]


@pytest.mark.parametrize("completed", BAD_COMPLETED, ids=repr)
def test_status_and_ready_agree_on_such_a_parent(monkeypatch, capsys, tmp_path, completed):
    parent = _set(PARENT, ("sub_issues_summary", "completed"), completed)
    # A ready ticket beside it, so the agreement isn't only on an empty list.
    ticket = {**copy.deepcopy(TICKET), "number": 5, "body": "Area: notes\n"}
    issues = [parent, ticket]
    status_ready = [i["number"] for i in _json(monkeypatch, capsys, tmp_path, issues, [])["ready"]]
    ready_ready = [v["number"] for v in _ready_json(monkeypatch, capsys, tmp_path, issues, [])["ready"]]
    assert status_ready == ready_ready == [5]


# A `total` of 0 or below is no parent, whatever `completed` holds: `issues.is_build_ticket`
# needs `total > 0`, so `ready` lists the issue, and `status` lists it as ready only.
NOT_PARENT_SUMMARIES = [{"total": -1, "completed": "1"}, {"total": -2, "completed": 0}, {"total": 0, "completed": "1"}]


@pytest.mark.parametrize("summary", NOT_PARENT_SUMMARIES, ids=repr)
def test_an_issue_whose_total_is_not_above_0_is_never_a_parent(monkeypatch, capsys, tmp_path, summary):
    issue = {**copy.deepcopy(PARENT), "sub_issues_summary": summary}
    ticket = {**copy.deepcopy(TICKET), "number": 5, "body": "Area: notes\n"}
    got = _json(monkeypatch, capsys, tmp_path, [issue, ticket], [])
    assert got["specs"] == []
    assert [i["number"] for i in got["ready"]] == [1, 5]
    ready_ready = [v["number"] for v in _ready_json(monkeypatch, capsys, tmp_path, [issue, ticket], [])["ready"]]
    assert ready_ready == [1, 5]
    text = _status(monkeypatch, capsys, tmp_path, [issue, ticket], [])
    assert "parent issue" not in text
    assert [l for l in _ready_section(text) if l.startswith("- #1 ")] == ["- #1 Parent [a]"]


@pytest.mark.parametrize(
    "completed,detail",
    [(1, "parent issue, 2 of 3 tickets open"), ("1", "parent issue, tickets unknown (no sub_issues_summary)")],
    ids=repr,
)
def test_whether_an_issue_is_a_parent_is_its_own_never_its_numbers(monkeypatch, capsys, tmp_path, completed, detail):
    """Two items with one number: the one whose own `total` is 0 is no parent."""
    parent = _set(PARENT, ("sub_issues_summary", "completed"), completed)
    dup = {**copy.deepcopy(PARENT), "title": "Dup", "sub_issues_summary": {"total": 0, "completed": 1}}
    got = _json(monkeypatch, capsys, tmp_path, [parent, dup], [])
    assert [(i["number"], i["title"], i["detail"]) for i in got["specs"]] == [(1, "Parent", detail)]
    text = _status(monkeypatch, capsys, tmp_path, [parent, dup], [])
    assert "- #1 Dup [parent issue" not in text

"""`workflow ready --issues F --prs G` reads past an issue's or pull
request's field of the wrong type (#780), as `workflow status` does (#770):
each item is read through `status.as_read`, so it is treated as it would be
without that field, never a traceback. Run through `cli.main`.
"""

import copy
import json

import pytest

from changelog_notes import entry
from workflow import cli

TICKET = {
    "number": 1,
    "title": "Add notes",
    "state": "open",
    "labels": [{"name": "ready-for-agent"}],
    "body": "Area: notes\n\n## Blocked by\n\n#2\n#4\n",
    "sub_issues_summary": {"total": 0, "completed": 0},
    "issue_dependencies_summary": {"blocked_by": 0},
}
BLOCKER = {"number": 2, "title": "Store notes", "state": "closed", "state_reason": "completed", "labels": [], "body": ""}
PR_ITEM = {"number": 4, "title": "Notes list", "state": "closed", "pull_request": {"merged_at": "2026-11-01T00:00:00Z"}}
# A second ticket, which the open pull request closes.
CLOSED_BY_PR = {"number": 9, "title": "Sort notes", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: lists\n"}
PR = {"number": 30, "title": "Sort notes", "state": "open", "body": "Closes #9", "draft": False, "head": {"ref": "claude/build-9"}}


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _ready(monkeypatch, capsys, tmp_path, issues, prs, *extra):
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(json.dumps(issues), encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = cli.main(["ready", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    return out.out


def _json(monkeypatch, capsys, tmp_path, issues, prs):
    return json.loads(_ready(monkeypatch, capsys, tmp_path, issues, prs, "--json"))


_DROP = object()


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


def test_the_tickets_own_input_gives_no_traceback(monkeypatch, capsys, tmp_path):
    """The first acceptance criterion as written: the issue reads as it would without its `state`."""
    issue = {"number": 1, "title": "A", "state": 5, "labels": [{"name": "ready-for-agent"}], "body": "Area: a\n\n## Blocked by\n\nNone\n"}
    without = {k: v for k, v in issue.items() if k != "state"}
    for as_json in (False, True):
        extra = ["--json"] if as_json else []
        got = _ready(monkeypatch, capsys, tmp_path, [issue], [], *extra)
        assert got == _ready(monkeypatch, capsys, tmp_path, [without], [], *extra)
    # `ready` lists only issues that say they are open (`readiness`), so one
    # read without its state is left out, as before #780 with no state at all.
    assert _json(monkeypatch, capsys, tmp_path, [issue], []) == {"ready": [], "not_ready": [], "start_now": []}
    assert [v["number"] for v in _json(monkeypatch, capsys, tmp_path, [{**issue, "state": "open"}], [])["ready"]] == [1]


# (which item, the field's path, the value of the wrong type, the item as it reads: the path dropped)
ISSUE_CASES = [
    ("ticket", ("state",), 5, ("state",)),
    ("ticket", ("title",), 5, ("title",)),
    ("ticket", ("title",), ["Add notes"], ("title",)),
    ("ticket", ("body",), 5, ("body",)),
    ("ticket", ("body",), {"Area": "notes"}, ("body",)),
    ("ticket", ("sub_issues_summary", "total"), "3", ("sub_issues_summary",)),
    ("ticket", ("sub_issues_summary", "total"), True, ("sub_issues_summary",)),
    ("ticket", ("sub_issues_summary",), [3], ("sub_issues_summary",)),
    ("ticket", ("sub_issues_summary",), 5, ("sub_issues_summary",)),
    ("ticket", ("issue_dependencies_summary", "blocked_by"), "1", ("issue_dependencies_summary",)),
    ("ticket", ("issue_dependencies_summary", "blocked_by"), 1.5, ("issue_dependencies_summary",)),
    ("ticket", ("issue_dependencies_summary",), 5, ("issue_dependencies_summary",)),
    ("blocker", ("state",), 5, ("state",)),
    ("blocker", ("state_reason",), 5, ("state_reason",)),
    ("blocker", ("title",), 5, ("title",)),
    ("blocker", ("body",), ["Area: x"], ("body",)),
    ("pr_item", ("state",), 5, ("state",)),
    ("pr_item", ("state_reason",), 5, ("state_reason",)),
    ("closed_by_pr", ("state",), 5, ("state",)),
    ("closed_by_pr", ("body",), 5, ("body",)),
]


def _issues(which: str, path: tuple, value) -> list[dict]:
    items = {"ticket": TICKET, "blocker": BLOCKER, "pr_item": PR_ITEM, "closed_by_pr": CLOSED_BY_PR}
    return [_set(item, path, value) if name == which else copy.deepcopy(item) for name, item in items.items()]


@pytest.mark.parametrize("which,path,value,dropped", ISSUE_CASES, ids=lambda x: repr(x))
def test_an_issue_field_of_the_wrong_type_reads_as_missing(monkeypatch, capsys, tmp_path, which, path, value, dropped):
    got = _json(monkeypatch, capsys, tmp_path, _issues(which, path, value), [PR])
    without = _json(monkeypatch, capsys, tmp_path, _issues(which, dropped, _DROP), [PR])
    assert got == without


@pytest.mark.parametrize("which,path,value,dropped", ISSUE_CASES, ids=lambda x: repr(x))
def test_an_issue_field_of_the_wrong_type_gives_no_traceback_in_text(monkeypatch, capsys, tmp_path, which, path, value, dropped):
    got = _ready(monkeypatch, capsys, tmp_path, _issues(which, path, value), [PR])
    assert got == _ready(monkeypatch, capsys, tmp_path, _issues(which, dropped, _DROP), [PR])


PR_CASES = [
    (("head",), "main", ("head",)),
    (("head", "ref"), 5, ("head", "ref")),
    (("title",), 5, ("title",)),
    (("state",), 5, ("state",)),
    (("body",), 5, ("body",)),
    (("body",), ["Closes #9"], ("body",)),
    (("draft",), "no", ("draft",)),
]


@pytest.mark.parametrize("path,value,dropped", PR_CASES, ids=lambda x: repr(x))
def test_a_pull_request_field_of_the_wrong_type_reads_as_missing(monkeypatch, capsys, tmp_path, path, value, dropped):
    issues = [copy.deepcopy(i) for i in (TICKET, BLOCKER, PR_ITEM, CLOSED_BY_PR)]
    got = _json(monkeypatch, capsys, tmp_path, issues, [_set(PR, path, value)])
    without = _json(monkeypatch, capsys, tmp_path, issues, [_set(PR, dropped, _DROP)])
    assert got == without


def test_a_blocker_whose_pull_request_marker_is_of_the_wrong_type_holds_its_ticket(monkeypatch, capsys, tmp_path):
    """A closed item whose `pull_request` is `5`, named as a ticket's blocker:
    still a pull request, read without its details, so one closed without
    merging, and the ticket isn't ready, as `status` reads it."""
    issues = _issues("pr_item", ("pull_request",), 5)
    got = _json(monkeypatch, capsys, tmp_path, issues, [PR])
    assert got == _json(monkeypatch, capsys, tmp_path, _issues("pr_item", ("pull_request",), {}), [PR])
    ticket = next(v for v in got["not_ready"] if v["number"] == 1)
    assert ticket["reasons"] == ["blocker PR #4 closed without merging"]


def test_well_typed_fields_are_read_as_before(monkeypatch, capsys, tmp_path):
    got = _json(monkeypatch, capsys, tmp_path, _issues("ticket", ("title",), "Add notes"), [PR])
    assert [(v["number"], v["title"], v["area"]) for v in got["ready"]] == [(1, "Add notes", "notes")]
    assert [(v["number"], v["reasons"]) for v in got["not_ready"]] == [(9, ["open PR #30 closes it"])]
    held = _json(monkeypatch, capsys, tmp_path, _issues("ticket", ("issue_dependencies_summary", "blocked_by"), 1), [PR])
    assert [v["number"] for v in held["ready"]] == []
    parent = _json(monkeypatch, capsys, tmp_path, _issues("ticket", ("sub_issues_summary", "total"), 3), [PR])
    assert 1 not in [v["number"] for v in parent["ready"] + parent["not_ready"]]


def test_the_changelog_has_the_note():
    note = entry("#780, found in the review of #772's pull request")
    assert "`status.as_read`" in note
    assert "`VERSION` is unchanged" in note

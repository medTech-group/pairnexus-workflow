"""`workflow status --issues F --prs G` reads past an issue's or pull
request's field of the wrong type (#770): the item is treated as it would be
without that field, never a traceback. Run through `cli.main`.
"""

import copy
import json

import pytest

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

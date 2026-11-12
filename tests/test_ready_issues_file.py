"""`workflow ready --issues F --prs G` reads both files as `workflow status`
does (`_issues_file`, #757): `gh api --paginate --slurp`'s pages are
flattened, and a file that isn't JSON, or isn't a list of issues or pull
requests, is refused in one line naming it, never a traceback (#779). Run
through `cli.main`.
"""

import io
import json

import pytest

from changelog_notes import entry
from workflow import cli


def issue(n, body="", labels=("ready-for-agent",)):
    return {"number": n, "title": f"Notes {n}", "state": "open", "labels": [{"name": l} for l in labels], "body": body}


ISSUES = [issue(10, "Area: notes"), issue(11, "Area: notes"), issue(12, "Area: shop\n\n## Blocked by\n\n#10\n"), issue(13, "Area: shop")]
PRS = [{"number": 30, "title": "Notes list", "state": "open", "body": "Closes #11", "head": {"ref": "claude/build-11"}}]


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _ready(monkeypatch, capsys, tmp_path, issues: str, prs: str = json.dumps(PRS), *extra):
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(issues, encoding="utf-8")
    (tmp_path / "prs.json").write_text(prs, encoding="utf-8")
    code = cli.main(["ready", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    return code, out.out, out.err


def _refused(monkeypatch, capsys, tmp_path, issues, prs=json.dumps(PRS)) -> str:
    """One line on standard error, nothing on standard output, exit 1."""
    code, out, err = _ready(monkeypatch, capsys, tmp_path, issues, prs)
    assert code == 1
    assert out == ""
    assert "Traceback" not in err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    return lines[0]


# ---------- pages ----------


@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_two_pages_give_the_same_output_as_one_list(monkeypatch, capsys, tmp_path, extra):
    """`gh api --paginate --slurp`'s pages, as `--fetch` reads them."""
    flat = _ready(monkeypatch, capsys, tmp_path, json.dumps(ISSUES), json.dumps(PRS), *extra)
    pages = _ready(monkeypatch, capsys, tmp_path, json.dumps([ISSUES[:2], ISSUES[2:]]), json.dumps([PRS, []]), *extra)
    assert flat[0] == 0, flat[2]
    assert pages == flat


def test_the_pages_are_read_as_the_tickets_they_hold(monkeypatch, capsys, tmp_path):
    """Not only alike: each page's tickets are there, and the second page's
    pull request still holds the ticket it closes."""
    code, out, err = _ready(monkeypatch, capsys, tmp_path, json.dumps([ISSUES[:2], ISSUES[2:]]), json.dumps([[], PRS]), "--json")
    assert code == 0, err
    got = json.loads(out)
    assert [v["number"] for v in got["ready"]] == [10, 13]
    assert [v["number"] for v in got["not_ready"]] == [11, 12]
    assert got["start_now"] == [10, 13]


def test_empty_pages_are_no_tickets_not_a_refusal(monkeypatch, capsys, tmp_path):
    code, out, err = _ready(monkeypatch, capsys, tmp_path, "[[]]", "[]")
    assert code == 0, err
    assert out == "start now: nothing\n"


# ---------- a file that isn't JSON ----------


def test_an_issues_file_that_isnt_json_is_refused_in_one_line(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, "{not json")
    assert line == "workflow: can't read `issues.json`: it isn't valid JSON (Expecting property name enclosed in double quotes, line 1)"


@pytest.mark.parametrize("text", ["", "\n  \n"])
def test_an_empty_issues_file_is_refused_as_empty(monkeypatch, capsys, tmp_path, text):
    assert _refused(monkeypatch, capsys, tmp_path, text) == "workflow: can't read `issues.json`: it is empty"


def test_a_prs_file_that_isnt_json_is_refused_naming_it(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(ISSUES), "[{")
    assert line.startswith("workflow: can't read `prs.json`: it isn't valid JSON ("), line


def test_standard_input_that_isnt_json_is_named_as_standard_input(monkeypatch, capsys, tmp_path):
    _env(monkeypatch, tmp_path)
    (tmp_path / "prs.json").write_text("[]")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"oops")))
    assert cli.main(["ready", "--issues", "-", "--prs", "prs.json"]) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith("workflow: can't read standard input (-): it isn't valid JSON ("), out.err
    assert len(out.err.strip().splitlines()) == 1


# ---------- JSON that isn't a list of issues ----------


def test_githubs_error_object_as_issues_is_refused_as_not_a_list(monkeypatch, capsys, tmp_path):
    """GitHub's answer to a bad token, saved as the issues file: once a
    `TypeError` traceback in `issues.readiness`."""
    error = {"message": "Bad credentials", "documentation_url": "https://docs.github.com/rest", "status": "401"}
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(error))
    assert line == 'workflow: can\'t read `issues.json`: it isn\'t a list of issues (it is a JSON object, GitHub\'s message "Bad credentials")'


@pytest.mark.parametrize(
    "value, kind",
    [
        ({"items": []}, "a JSON object"),
        ("issues", "a string"),
        (12, "a number"),
        (None, "null"),
        ([1, 2], "a list holding something other than issues"),
        ([{"title": "no number"}], "a list holding something other than issues"),
        ([{"number": "12"}], "a list holding something other than issues"),
        ([[issue(10)], "page"], "a list holding something other than issues"),
    ],
)
def test_json_that_isnt_a_list_of_issues_is_refused(monkeypatch, capsys, tmp_path, value, kind):
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(value))
    assert line == f"workflow: can't read `issues.json`: it isn't a list of issues (it is {kind})"


def test_a_prs_file_that_isnt_a_list_says_pull_requests(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(ISSUES), json.dumps({"message": "Not Found"}))
    assert line == 'workflow: can\'t read `prs.json`: it isn\'t a list of pull requests (it is a JSON object, GitHub\'s message "Not Found")'


def test_a_pull_request_numbered_true_is_refused_as_status_refuses_it(monkeypatch, capsys, tmp_path):
    """Once read past (`test_ready_spec_note.py` now gives it through `--fetch`)."""
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(ISSUES), json.dumps([{"number": True, "state": "open", "body": ""}]))
    assert line == "workflow: can't read `prs.json`: it isn't a list of pull requests (it is a list holding something other than pull requests)"


def test_the_issues_file_is_read_before_the_prs_file(monkeypatch, capsys, tmp_path):
    """Both wrong: the refusal names `--issues`'s, as `status`'s does."""
    assert _refused(monkeypatch, capsys, tmp_path, "{", "{").startswith("workflow: can't read `issues.json`: ")


# ---------- one helper ----------


def test_ready_reads_both_files_through_the_status_helper():
    """No copy of `_issues_file`'s checks (the architecture's "Reuse, not copies")."""
    import inspect

    src = inspect.getsource(cli.cmd_ready)
    assert '_issues_file(a.issues, "issues")' in src and '_issues_file(a.prs, "pull requests")' in src
    assert "_json(a.issues)" not in src and "_json(a.prs)" not in src


# ---------- the changelog note ----------


def test_the_changelog_note_names_each_old_traceback():
    """Before #779, the pages ended in `list indices ...` and GitHub's error
    object in `string indices ...` (its keys iterated as issues)."""
    note = entry("#779, found in the review of #772's pull request")
    first = note.split("\n\n")[0]
    pages = first.index("list indices must be integers or slices, not str")
    error_object = first.index("string indices must be integers, not 'str'")
    assert first.index("--paginate --slurp") < pages
    assert first.index("Bad credentials") < error_object

"""`workflow status --issues F --prs G` refuses a file that isn't JSON, or
isn't a list of issues or pull requests, in one line naming it, never a
traceback (#757). Run through `cli.main`.
"""

import io
import json

import pytest

from workflow import cli

ISSUE = {"number": 12, "title": "Add notes", "state": "open", "labels": [], "body": ""}
PR = {"number": 30, "title": "Notes list", "state": "open", "head": {"ref": "claude/build-12"}}


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _status(monkeypatch, capsys, tmp_path, issues: str, prs: str = json.dumps([PR]), *extra):
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(issues, encoding="utf-8")
    (tmp_path / "prs.json").write_text(prs, encoding="utf-8")
    code = cli.main(["status", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    return code, out.out, out.err


def _refused(monkeypatch, capsys, tmp_path, issues, prs=json.dumps([PR])) -> str:
    """One line on standard error, nothing on standard output, a non-zero exit."""
    code, out, err = _status(monkeypatch, capsys, tmp_path, issues, prs)
    assert code != 0
    assert out == ""
    assert "Traceback" not in err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    return lines[0]


# ---------- a file that isn't JSON ----------


def test_an_issues_file_that_isnt_json_is_refused_in_one_line(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, "{not json")
    assert line == "workflow: can't read `issues.json`: it isn't valid JSON (Expecting property name enclosed in double quotes, line 1)"


@pytest.mark.parametrize("text", ["", "\n  \n"])
def test_an_empty_issues_file_is_refused_as_empty(monkeypatch, capsys, tmp_path, text):
    line = _refused(monkeypatch, capsys, tmp_path, text)
    assert line == "workflow: can't read `issues.json`: it is empty"


def test_a_prs_file_that_isnt_json_is_refused_naming_it(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps([ISSUE]), "[{")
    assert line.startswith("workflow: can't read `prs.json`: it isn't valid JSON ("), line


@pytest.mark.parametrize(
    "issues, prs, name",
    [
        ("[" * 100000 + "]" * 100000, json.dumps([PR]), "issues.json"),
        ("[" * 100000, json.dumps([PR]), "issues.json"),
        (json.dumps([ISSUE]), '{"a": ' * 100000 + "1" + "}" * 100000, "prs.json"),
    ],
)
def test_json_nested_too_deeply_is_refused_in_one_line(monkeypatch, capsys, tmp_path, issues, prs, name):
    """Read as doctor reads JSON text (`doctor._parse_json`), never a traceback."""
    line = _refused(monkeypatch, capsys, tmp_path, issues, prs)
    assert line == f"workflow: can't read `{name}`: it is nested too deeply to read"


@pytest.mark.parametrize("issues", ["1" + "0" * 4300, '[{"number": 1' + "0" * 5000 + "}]"])
def test_a_number_too_long_to_read_is_refused_in_one_line(monkeypatch, capsys, tmp_path, issues):
    line = _refused(monkeypatch, capsys, tmp_path, issues)
    assert line.startswith("workflow: can't read `issues.json`: it can't be read (ValueError: Exceeds the limit"), line


def test_standard_input_that_isnt_json_is_named_as_standard_input(monkeypatch, capsys, tmp_path):
    _env(monkeypatch, tmp_path)
    (tmp_path / "prs.json").write_text("[]")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"oops")))
    assert cli.main(["status", "--issues", "-", "--prs", "prs.json"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("workflow: can't read standard input (-): it isn't valid JSON ("), err
    assert len(err.strip().splitlines()) == 1


# ---------- JSON that isn't a list of issues ----------


def test_githubs_error_object_as_issues_is_refused_as_not_a_list(monkeypatch, capsys, tmp_path):
    """GitHub's answer to a bad token, saved as the issues file."""
    error = {"message": "Bad credentials", "documentation_url": "https://docs.github.com/rest", "status": "401"}
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(error))
    assert line == 'workflow: can\'t read `issues.json`: it isn\'t a list of issues (it is a JSON object, GitHub\'s message "Bad credentials")'


@pytest.mark.parametrize(
    "value, kind",
    [
        ({"items": []}, "a JSON object"),
        ("issues", "a string"),
        (12, "a number"),
        (True, "true or false"),
        (None, "null"),
        ([1, 2], "a list holding something other than issues"),
        ([{"title": "no number"}], "a list holding something other than issues"),
        ([{"number": "12"}], "a list holding something other than issues"),
        ([{"number": True}], "a list holding something other than issues"),
        ([[ISSUE], "page"], "a list holding something other than issues"),
        ([[[ISSUE]]], "a list holding something other than issues"),
    ],
)
def test_json_that_isnt_a_list_of_issues_is_refused(monkeypatch, capsys, tmp_path, value, kind):
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps(value))
    assert line == f"workflow: can't read `issues.json`: it isn't a list of issues (it is {kind})"


def test_a_prs_file_that_isnt_a_list_says_pull_requests(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps([ISSUE]), json.dumps({"message": "Not Found"}))
    assert line == 'workflow: can\'t read `prs.json`: it isn\'t a list of pull requests (it is a JSON object, GitHub\'s message "Not Found")'


def test_githubs_message_is_shown_escaped_and_cut(monkeypatch, capsys, tmp_path):
    """The message is the file's text: control characters escaped, cut short."""
    line = _refused(monkeypatch, capsys, tmp_path, json.dumps({"message": "Bad\x1b[31m" + "x" * 200}))
    assert "\x1b" not in line
    assert "Bad\\x1b[31m" in line
    assert line.endswith('…")')


# ---------- what it still takes ----------


def test_a_list_of_issues_still_gives_the_status(monkeypatch, capsys, tmp_path):
    code, out, err = _status(monkeypatch, capsys, tmp_path, json.dumps([ISSUE]), json.dumps([PR]), "--json")
    assert code == 0, err
    st = json.loads(out)
    assert st["issues_read"] is True
    assert [p["number"] for p in st["prs"]] == [30]


def test_pages_of_issues_are_flattened(monkeypatch, capsys, tmp_path):
    """`gh api --paginate --slurp`'s pages, as `--fetch` reads them."""
    other = {**ISSUE, "number": 13, "title": "Delete notes", "labels": [{"name": "workflow:in-progress"}]}
    code, out, err = _status(monkeypatch, capsys, tmp_path, json.dumps([[ISSUE], [other]]), json.dumps([[PR], []]), "--json")
    assert code == 0, err
    st = json.loads(out)
    assert [i["number"] for i in st["in_progress"]] == [13]
    assert [p["number"] for p in st["prs"]] == [30]


def test_empty_lists_are_no_issues_not_a_refusal(monkeypatch, capsys, tmp_path):
    code, out, err = _status(monkeypatch, capsys, tmp_path, "[]", "[[]]", "--json")
    assert code == 0, err
    assert json.loads(out)["issues_read"] is True


def test_a_byte_order_mark_is_read_past(monkeypatch, capsys, tmp_path):
    """An editor's byte order mark, as `_json_inputs` reads past it."""
    code, out, err = _status(monkeypatch, capsys, tmp_path, "﻿" + json.dumps([ISSUE]), json.dumps([PR]), "--json")
    assert code == 0, err


def test_status_reads_both_files_through_one_helper():
    """Both files go through `_issues_file`, which uses doctor's issue number
    and the pages' flattening (the architecture's "Reuse, not copies")."""
    import inspect

    src = inspect.getsource(cli._status)
    assert '_issues_file(a.issues, "issues")' in src and '_issues_file(a.prs, "pull requests")' in src
    helper = inspect.getsource(cli._issues_file)
    assert "doctor_mod._number(" in helper and "_fetch_items(" in helper


def test_the_refusal_from_standard_input_reads_as_its_reason_not_as_closed(monkeypatch):
    """`str()` of what `_issues_file` raises for standard input is its reason,
    never "standard input (-) is closed", which only a closed one says."""
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"{}")))
    with pytest.raises(cli.InputUnreadable) as e:
        cli._issues_file("-", "issues")
    assert str(e.value) == "it isn't a list of issues (it is a JSON object)"
    monkeypatch.setattr("sys.stdin", None)
    with pytest.raises(cli.InputUnreadable) as e:
        cli._issues_file("-", "issues")
    assert str(e.value) == "standard input (-) is closed"

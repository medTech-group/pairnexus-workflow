"""`workflow status --fetch` refuses, in one `workflow:` line, issues or pull
requests `gh api` gave without a whole-number `number`, as `--issues F --prs G`
refuses such a file (#757), never a traceback (#775). Run through `cli.main`,
with the fake `gh` on the PATH.
"""

import json

import pytest

import fake_gh
from changelog_notes import entry
from workflow import cli

ISSUE = {"number": 12, "title": "Add notes", "state": "open", "labels": [], "body": ""}
PR = {"number": 30, "title": "Notes list", "state": "open", "head": {"ref": "claude/build-12"}}


def _project(monkeypatch, tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _status(monkeypatch, capsys, tmp_path, issues: list, prs: list, *extra, slurp: bool = True):
    _project(monkeypatch, tmp_path)
    routes = {"repos/acme/demo/issues": fake_gh.pages(issues), "repos/acme/demo/pulls": fake_gh.pages(prs)}
    fake_gh.install(tmp_path, monkeypatch, routes, slurp=slurp)
    code = cli.main(["status", "--fetch", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    return code, out.out, out.err


def _refused(monkeypatch, capsys, tmp_path, issues, prs=(PR,), *extra, **kw) -> str:
    """One `workflow:` line on standard error, nothing on standard output, exit 1."""
    code, out, err = _status(monkeypatch, capsys, tmp_path, list(issues), list(prs), *extra, **kw)
    assert code == 1, err
    assert out == ""
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("workflow: "), lines[0]
    return lines[0]


# ---------- the ticket's cases ----------


def test_an_issue_with_no_number_is_refused_in_one_line(monkeypatch, capsys, tmp_path):
    """`gh` prints `[[{"title": "no number", "labels": []}]]`: a `KeyError` before."""
    line = _refused(monkeypatch, capsys, tmp_path, [{"title": "no number", "labels": []}])
    assert line == (
        "workflow: can't read the issues `gh api repos/acme/demo/issues` gave: 1 of 1 has no whole-number number"
        " (fetch them with the GitHub MCP tools and give --issues and --prs files instead)"
    )


def test_a_list_mixing_text_and_whole_number_numbers_is_refused(monkeypatch, capsys, tmp_path):
    """`"1"` beside `2`: a `TypeError` on sorting before."""
    issues = [{**ISSUE, "number": "1"}, {**ISSUE, "number": 2}]
    line = _refused(monkeypatch, capsys, tmp_path, issues)
    assert "the issues `gh api repos/acme/demo/issues` gave: 1 of 2 has no whole-number number" in line


# ---------- the same check as a file's ----------


@pytest.mark.parametrize("number", [None, "12", True, 12.0, [12], {"n": 12}])
def test_any_number_that_isnt_whole_is_refused(monkeypatch, capsys, tmp_path, number):
    """What `_issues_file` refuses in a file (`doctor._number`), `--fetch` refuses."""
    line = _refused(monkeypatch, capsys, tmp_path, [ISSUE, {**ISSUE, "number": number}])
    assert "1 of 2 has no whole-number number" in line


def test_several_without_one_are_counted(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, [{"title": "a"}, {**ISSUE, "number": "3"}, ISSUE])
    assert "2 of 3 have no whole-number number" in line


def test_a_pull_request_with_no_number_is_refused_naming_pull_requests(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, [ISSUE], [{"title": "no number", "head": {"ref": "x"}}])
    assert "the pull requests `gh api repos/acme/demo/pulls` gave: 1 of 1 has no whole-number number" in line


def test_the_json_is_refused_the_same_way(monkeypatch, capsys, tmp_path):
    """`--json` prints no half-read status: the same one line."""
    line = _refused(monkeypatch, capsys, tmp_path, [{"title": "no number"}], [PR], "--json")
    assert "1 of 1 has no whole-number number" in line


def test_a_gh_without_slurp_is_read_the_same_way(monkeypatch, capsys, tmp_path):
    """An old `gh` prints the pages one after another (`posts.decode_values`)."""
    line = _refused(monkeypatch, capsys, tmp_path, [{"title": "no number"}], slurp=False)
    assert "1 of 1 has no whole-number number" in line


# ---------- what it still takes ----------


def test_whole_number_numbers_still_give_the_status(monkeypatch, capsys, tmp_path):
    other = {**ISSUE, "number": 13, "title": "Delete notes", "labels": [{"name": "workflow:in-progress"}]}
    code, out, err = _status(monkeypatch, capsys, tmp_path, [ISSUE, other], [PR], "--json")
    assert code == 0, err
    st = json.loads(out)
    assert st["issues_read"] is True
    assert [i["number"] for i in st["in_progress"]] == [13]
    assert [p["number"] for p in st["prs"]] == [30]


def test_no_issues_is_no_refusal(monkeypatch, capsys, tmp_path):
    code, out, err = _status(monkeypatch, capsys, tmp_path, [], [], "--json")
    assert code == 0, err
    assert json.loads(out)["issues_read"] is True


def test_the_check_is_doctors_issue_number():
    """One whole-number check (`doctor._number`, which calls `issues.is_whole`),
    as `_issues_file` uses: no copy of it."""
    import inspect

    src = inspect.getsource(cli._unnumbered)
    assert "doctor_mod._number(" in src
    assert "isinstance" not in src


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#775, found in the review of #770's pull request")
    assert "workflow status --fetch" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_status_fetch_numbers.py" in note

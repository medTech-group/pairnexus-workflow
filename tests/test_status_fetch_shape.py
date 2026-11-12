"""`workflow status --fetch` refuses, in one `workflow:` line, an answer from
`gh api` that isn't a list of issues (#789): `5`, `"hello"`, `[5, "x"]`, or
GitHub's error object printed with exit 0. `_fetch_items` kept only the
objects, so `status` exited 0 showing no issues, or counted GitHub's error
object as an issue with no number (#775). Now `_fetch` gives each page the
check `_issues_file` gives a file (#757), `_not_a_list`, with the same reason.
"""

import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import entry
from workflow import charter, cli, state

KIT = Path(__file__).resolve().parents[1]
ISSUE = {"number": 12, "title": "Add notes", "state": "open", "labels": [], "body": ""}
PR = {"number": 30, "title": "Notes list", "state": "open", "head": {"ref": "claude/build-12"}}
INSTEAD = " (fetch them with the GitHub MCP tools and give --issues and --prs files instead)"
GAVE = {"issues": "the issues `gh api repos/acme/demo/issues` gave", "pulls": "the pull requests `gh api repos/acme/demo/pulls` gave"}

# The ticket's answers, as `gh` prints them with exit 0.
ANSWERS = {
    "number": "5",
    "string": '"hello"',
    "mixed": '[5, "x"]',
    "error": '{"message": "Bad credentials", "documentation_url": "https://docs.github.com/rest", "status": "401"}',
}
REASONS = {
    "number": "it isn't a list of issues (it is a number)",
    "string": "it isn't a list of issues (it is a string)",
    "mixed": "it isn't a list of issues (it is a list holding something other than issues)",
    "error": 'it isn\'t a list of issues (it is a JSON object, GitHub\'s message "Bad credentials")',
}


def _project(monkeypatch, tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _answer(case: str) -> dict:
    """The ticket's answer `case` as a real `gh` prints it: one page, which
    `--paginate --slurp` prints in a list of the pages, an old `gh` as it is."""
    return fake_gh.pages(json.loads(ANSWERS[case]))


def _refused(monkeypatch, capsys, tmp_path, routes: dict, *args, slurp: bool = True) -> str:
    """`cli.main` ends with one `workflow:` line, which the process prints on
    standard error when it exits 1, and nothing on standard output."""
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, routes, slurp=slurp)
    with pytest.raises(SystemExit) as e:
        cli.main(list(args or ["status", "--fetch"]))
    out = capsys.readouterr()
    assert out.out == ""
    assert "Traceback" not in out.err
    line = e.value.code
    assert isinstance(line, str), line  # Python prints it on standard error and exits 1
    assert len(line.splitlines()) == 1, line
    assert line.startswith("workflow: "), line
    return line


def _file_reason(monkeypatch, capsys, tmp_path, issues: str, prs: str = None) -> str:
    """The reason `status --issues F --prs F` gives the same text as a file."""
    _project(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(issues, encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps([PR]) if prs is None else prs, encoding="utf-8")
    code = cli.main(["status", "--issues", "issues.json", "--prs", "prs.json"])
    err = capsys.readouterr().err
    assert code == 1, err
    line = err.strip()
    assert len(line.splitlines()) == 1, line
    name = "`prs.json`" if prs is not None else "`issues.json`"
    prefix = f"workflow: can't read {name}: "
    assert line.startswith(prefix), line
    return line[len(prefix):]


# ---------- the ticket's cases ----------


@pytest.mark.parametrize("case", list(ANSWERS))
def test_an_answer_that_isnt_a_list_of_issues_is_refused_as_the_file_is(monkeypatch, capsys, tmp_path, case):
    """Each of the ticket's answers is refused in one line, with the reason
    the same text gets as an `--issues` file."""
    line = _refused(monkeypatch, capsys, tmp_path / "fetch", {"repos/acme/demo/issues": _answer(case),
                                                              "repos/acme/demo/pulls": fake_gh.pages([PR])})
    assert line == f"workflow: can't read {GAVE['issues']}: {REASONS[case]}{INSTEAD}"
    assert line == f"workflow: can't read {GAVE['issues']}: {_file_reason(monkeypatch, capsys, tmp_path / 'file', ANSWERS[case])}{INSTEAD}"


def test_githubs_error_object_is_named_by_its_message_not_counted_as_an_issue(monkeypatch, capsys, tmp_path):
    """#775 counted it as an issue with no number; it is GitHub's message."""
    line = _refused(monkeypatch, capsys, tmp_path, {"repos/acme/demo/issues": _answer("error"),
                                                    "repos/acme/demo/pulls": fake_gh.pages([PR])})
    assert "Bad credentials" in line
    assert "no whole-number number" not in line


@pytest.mark.parametrize("case", list(ANSWERS))
def test_a_gh_without_slurp_is_refused_the_same_way(monkeypatch, capsys, tmp_path, case):
    """An old `gh` prints its pages one after another: a page that isn't a
    list of issues is refused with the same reason."""
    line = _refused(monkeypatch, capsys, tmp_path, {"repos/acme/demo/issues": _answer(case),
                                                    "repos/acme/demo/pulls": fake_gh.pages([PR])}, slurp=False)
    assert line == f"workflow: can't read {GAVE['issues']}: {REASONS[case]}{INSTEAD}"


@pytest.mark.parametrize("slurp", [True, False], ids=["slurp", "old-gh"])
@pytest.mark.parametrize("case", list(ANSWERS))
def test_the_page_by_page_route_is_refused_the_same_way(monkeypatch, capsys, tmp_path, case, slurp):
    """Where the proxy refuses the next-page link (#568), the pages are read
    one at a time (`fetch.by_page`): a page that isn't a list of issues is
    refused with the same reason."""
    page = json.loads(ANSWERS[case])
    routes = {"repos/acme/demo/issues": fake_gh.pages(page, [ISSUE], numeric_refused=True), "repos/acme/demo/pulls": fake_gh.pages([PR])}
    line = _refused(monkeypatch, capsys, tmp_path, routes, slurp=slurp)
    assert line == f"workflow: can't read {GAVE['issues']}: {REASONS[case]}{INSTEAD}"
    assert "repos/acme/demo/issues?state=all&per_page=100&page=1" in fake_gh.FakeGh(tmp_path / "fake-gh-bin").paths()


@pytest.mark.parametrize("case", list(ANSWERS))
def test_the_pull_requests_are_refused_the_same_way(monkeypatch, capsys, tmp_path, case):
    line = _refused(monkeypatch, capsys, tmp_path / "fetch", {"repos/acme/demo/issues": fake_gh.pages([ISSUE]),
                                                              "repos/acme/demo/pulls": _answer(case)})
    reason = REASONS[case].replace("issues", "pull requests")
    assert line == f"workflow: can't read {GAVE['pulls']}: {reason}{INSTEAD}"
    file_reason = _file_reason(monkeypatch, capsys, tmp_path / "file", json.dumps([ISSUE]), ANSWERS[case])
    assert line == f"workflow: can't read {GAVE['pulls']}: {file_reason}{INSTEAD}"


@pytest.mark.parametrize("pages", [([{"number": 12}], ["page"]), ([None],), ([[[{"number": 12}, 5]]],), ([True],)],
                         ids=["a-page-of-strings", "null", "deep", "true"])
def test_anything_but_an_object_in_the_pages_is_refused(monkeypatch, capsys, tmp_path, pages):
    """However deep `gh`'s lists nest within the limit (#788), every entry
    must be an object."""
    line = _refused(monkeypatch, capsys, tmp_path, {"repos/acme/demo/issues": fake_gh.pages(*pages),
                                                    "repos/acme/demo/pulls": fake_gh.pages([PR])})
    assert line == f"workflow: can't read {GAVE['issues']}: {REASONS['mixed']}{INSTEAD}"


# What a real `gh --paginate --slurp` prints: a list of the pages, a page
# that isn't a list among them (#789's round 1).
SLURPED = {
    "error": ((json.loads(ANSWERS["error"]),), REASONS["error"]),
    "error-after-a-full-page": (([{**ISSUE, "number": n} for n in range(1, 101)], json.loads(ANSWERS["error"])), REASONS["error"]),
    "number": ((5,), REASONS["number"]),
    "string": (("hello",), REASONS["string"]),
    "null": ((None,), "it isn't a list of issues (it is null)"),
    "true": ((True,), "it isn't a list of issues (it is true or false)"),
}


@pytest.mark.parametrize("case", list(SLURPED))
def test_slurp_checks_each_page_it_prints(monkeypatch, capsys, tmp_path, case):
    """`--slurp` prints its pages in one list: each page gets the check, as an
    old `gh`'s pages do, so GitHub's error object as a page is named by its
    message rather than counted as an issue with no number (#775)."""
    pages, reason = SLURPED[case]
    routes = {"repos/acme/demo/issues": fake_gh.pages(*pages), "repos/acme/demo/pulls": fake_gh.pages([PR])}
    line = _refused(monkeypatch, capsys, tmp_path / "slurp", routes)
    assert line == f"workflow: can't read {GAVE['issues']}: {reason}{INSTEAD}"
    assert line == _refused(monkeypatch, capsys, tmp_path / "old-gh", routes, slurp=False)


@pytest.mark.parametrize("command", [["status", "--fetch"], ["ready", "--fetch"]])
def test_slurps_error_page_is_refused_by_status_and_ready(monkeypatch, capsys, tmp_path, command):
    """`ready --fetch` ended in `KeyError: 'number'` on it."""
    routes = {"repos/acme/demo/issues": fake_gh.pages(json.loads(ANSWERS["error"])), "repos/acme/demo/pulls": fake_gh.pages([PR])}
    line = _refused(monkeypatch, capsys, tmp_path, routes, *command)
    assert line == f"workflow: can't read {GAVE['issues']}: {REASONS['error']}{INSTEAD}"


@pytest.mark.parametrize("case", ["number", "error"])
def test_the_process_prints_one_line_and_exits_1(tmp_path, case):
    """Run as a command: one line on standard error, exit 1, nothing else."""
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    gh = fake_gh.write(tmp_path / "bin", {"repos/acme/demo/issues": _answer(case),
                                          "repos/acme/demo/pulls": fake_gh.pages([PR])})
    env = {**os.environ, "PATH": f"{gh.bin}{os.pathsep}{os.environ.get('PATH', '')}", "CLAUDE_PROJECT_DIR": str(tmp_path),
           "WORKFLOW_UPDATE_CHECK": "off"}
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "status", "--fetch"],
                       capture_output=True, text=True, cwd=tmp_path, env=env)
    assert p.returncode == 1
    assert p.stdout == ""
    assert p.stderr == f"workflow: can't read {GAVE['issues']}: {REASONS[case]}{INSTEAD}\n"


# ---------- what it still reads ----------


@pytest.mark.parametrize("text", ["", "[]", "[[]]", json.dumps([[ISSUE], [[{**ISSUE, "number": 13}]]])],
                         ids=["no-output", "empty-list", "empty-page", "nested-pages"])
def test_lists_of_issues_are_still_read(monkeypatch, capsys, tmp_path, text):
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.reply(text), "repos/acme/demo/pulls": fake_gh.pages([PR])})
    code = cli.main(["status", "--fetch", "--json"])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert json.loads(out.out)["issues_read"] is True


def test_an_issue_with_no_number_is_still_775s_refusal(monkeypatch, capsys, tmp_path):
    """A list of objects is a list of issues to this check: one with no
    whole-number number gets #775's refusal, as before."""
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.pages([{"title": "no number"}]),
                                            "repos/acme/demo/pulls": fake_gh.pages([PR])})
    code = cli.main(["status", "--fetch"])
    out = capsys.readouterr()
    assert code == 1
    assert out.err == f"workflow: can't read {GAVE['issues']}: 1 of 1 has no whole-number number{INSTEAD}\n"


# ---------- the same check, not a copy ----------


def test_fetch_and_the_file_share_one_check():
    """`_fetch` refuses through `_not_a_list`, the check `_issues_file` uses,
    and neither words the reason itself."""
    fetch, issues_file = inspect.getsource(cli._fetch), inspect.getsource(cli._issues_file)
    assert "_not_a_list(" in fetch
    assert "_not_a_list(" in issues_file
    for src in (fetch, issues_file):
        assert "it isn't a list of" not in src
        assert "a list holding something other than" not in src


def test_the_check_names_each_kind():
    assert cli._not_a_list([ISSUE], "issues") is None
    assert cli._not_a_list([5], "issues") == "it isn't a list of issues (it is a list holding something other than issues)"
    assert cli._not_a_list(None, "pull requests") == "it isn't a list of pull requests (it is null)"
    assert cli._not_a_list(True, "issues") == "it isn't a list of issues (it is true or false)"
    assert cli._not_a_list({"items": []}, "issues") == "it isn't a list of issues (it is a JSON object)"


def test_the_check_holds_the_one_test_of_the_list():
    """`_not_a_list` itself tests the list: nothing in it, however its lists
    nest, but objects. A caller gives only how deep it reads (`deepest`, as
    `_fetch_items` counts it) and what each object needs (`each`: a file's
    whole-number number), never a test of the list of its own."""
    mixed = "it isn't a list of issues (it is a list holding something other than issues)"
    assert cli._not_a_list([[ISSUE], [[ISSUE]]], "issues") is None
    assert cli._not_a_list([[[ISSUE, 5]]], "issues") == mixed
    assert cli._not_a_list([[ISSUE]], "issues", deepest=2) is None
    assert cli._not_a_list([[[ISSUE]]], "issues", deepest=2) == mixed
    assert cli._not_a_list([{"title": "no number"}], "issues") is None
    numbered = lambda x: x.get("number") is not None  # noqa: E731
    assert cli._not_a_list([[{"title": "no number"}]], "issues", each=numbered) == mixed
    assert cli._not_a_list([[ISSUE]], "issues", each=numbered) is None
    assert cli._not_a_list([[ISSUE], 5], "issues", each=lambda x: True) == mixed


def test_neither_caller_tests_the_list_itself():
    """`_issues_file` and `_fetch` leave the test of the list to `_not_a_list`:
    the file gives it only its whole-number number for each issue."""
    fetch, issues_file = inspect.getsource(cli._fetch), inspect.getsource(cli._issues_file)
    assert "only_objects" not in fetch and "NotAnObject" not in fetch
    assert "isinstance(" not in issues_file


# ---------- the other callers of `_fetch` ----------


def test_ready_fetch_is_refused_the_same_way(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, {"repos/acme/demo/issues": _answer("number"),
                                                    "repos/acme/demo/pulls": fake_gh.pages([PR])}, "ready", "--fetch")
    assert line == f"workflow: can't read {GAVE['issues']}: {REASONS['number']}{INSTEAD}"


def test_state_join_fetch_names_its_own_flags(tmp_path):
    """`state join --fetch` keeps its own wording around the same reason."""
    gh = fake_gh.write(tmp_path / "bin", {"repos/acme/demo/issues": _answer("error")})
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n[areas]\nconductor = []\n', encoding="utf-8"
    )
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-12-join"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    (tmp_path / "body.md").write_text(state.put("## Run\n", s))
    env = {**os.environ, "PATH": f"{gh.bin}{os.pathsep}{os.environ.get('PATH', '')}", "CLAUDE_PROJECT_DIR": str(tmp_path),
           "WORKFLOW_UPDATE_CHECK": "off"}
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "state", "join", "--body", "body.md", "--fetch", "--out", "new.md"],
                       capture_output=True, text=True, cwd=tmp_path, env=env)
    assert p.returncode == 1, p.stderr
    assert p.stderr == (
        f"workflow state join: the open issues couldn't be read (can't read {GAVE['issues']}: {REASONS['error']}); "
        "give --issues F and --permissions F in place of --fetch\n"
    )
    assert not (tmp_path / "new.md").exists()


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#789, found in the review of #775's pull request")
    assert "status --fetch" in note
    assert "`--issues` file" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_status_fetch_shape.py" in note


def test_the_changelog_says_only_the_depth_differs(monkeypatch, capsys, tmp_path):
    """The note claims the file's reason for a page, not the file's answer for
    any text: a file is read 2 lists deep, `gh`'s output as deep as #788 reads
    it, so `[[[{"number": 12}]]]` is refused as a file and read from `gh`."""
    note = " ".join(entry("#789, found in the review of #775's pull request").split())
    assert "as the same text given as an `--issues` file is" not in note
    assert "a file 2 lists deep" in note
    text = '[[[{"number": 12}]]]'
    assert text in note
    assert _file_reason(monkeypatch, capsys, tmp_path / "file", text) == REASONS["mixed"]
    _project(monkeypatch, tmp_path / "fetch")
    fake_gh.install(tmp_path / "fetch", monkeypatch, {"repos/acme/demo/issues": fake_gh.pages(json.loads(text)), "repos/acme/demo/pulls": fake_gh.pages([PR])})
    assert cli.main(["status", "--fetch"]) == 0, capsys.readouterr().err


def test_the_texts_name_slurps_pages():
    """The note, `_fetch`'s docstring and its architecture line say each page
    `--slurp` prints in its list is checked, as the code does."""
    said = "each page `--slurp` prints in its list"
    assert said in " ".join(entry("#789, found in the review of #775's pull request").split())
    assert said in " ".join(cli._fetch.__doc__.split())
    assert said in (KIT / "docs/architecture/scripts--workflow.md").read_text()


@pytest.mark.parametrize("slurp", [True, False], ids=["slurp", "old-gh"])
@pytest.mark.parametrize("text", ["[" * 9 + "5" + "]" * 9, "[" * 3000 + "5" + "]" * 3000, "[[[[[[[[[null, {}]]]]]]]]]"],
                         ids=["9-deep", "3000-deep", "null-9-deep"])
def test_lists_nested_too_deeply_are_788s_refusal_whatever_they_hold(monkeypatch, capsys, tmp_path, text, slurp):
    """Past `FETCH_DEPTH`, the depth is the reason, as #788 gives it, before
    what the lists hold is looked at."""
    routes = {"repos/acme/demo/issues": fake_gh.reply(text), "repos/acme/demo/pulls": fake_gh.pages([PR])}
    line = _refused(monkeypatch, capsys, tmp_path, routes, slurp=slurp)
    assert line == f"workflow: can't read {GAVE['issues']}: it is nested too deeply to read{INSTEAD}"


def test_the_changelog_gives_the_depth_first():
    note = " ".join(entry("#789, found in the review of #775's pull request").split())
    assert "past it, #788's `it is nested too deeply to read`, whatever they hold" in note

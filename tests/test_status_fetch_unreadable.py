"""`workflow status --fetch` refuses, in one `workflow:` line, output `gh api`
gave with exit 0 that it can't read: text that isn't JSON, a number past
Python's digit limit, lists nested 5000 deep (#788). It read `gh`'s output
with a plain `json.loads` and flattened its pages recursively, so each ended in
a traceback. Now it reads the output as `_issues_file` reads a file's
(`doctor._parse_json`), and flattens the pages without recursion.
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

NOT_JSON = "not json"
LONG_NUMBER = '[[{"number": ' + "9" * 5000 + "}]]"
DEEP = "[" * 5000 + "]" * 5000


def _project(monkeypatch, tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _routes(issues, prs=None) -> dict:
    """`issues` and `prs`: text `gh` prints with exit 0, or a list of items."""

    def answer(v):
        return fake_gh.reply(v) if isinstance(v, str) else fake_gh.pages(v)

    return {"repos/acme/demo/issues": answer(issues), "repos/acme/demo/pulls": answer([PR] if prs is None else prs)}


def _refused(monkeypatch, capsys, tmp_path, issues, prs=None, *extra, slurp: bool = True) -> str:
    """`cli.main` ends with one `workflow:` line, which the process prints on
    standard error when it exits 1, and nothing on standard output."""
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, _routes(issues, prs), slurp=slurp)
    with pytest.raises(SystemExit) as e:
        cli.main(["status", "--fetch", *extra])
    out = capsys.readouterr()
    assert out.out == ""
    assert "Traceback" not in out.err
    line = e.value.code
    assert isinstance(line, str), line  # Python prints it on standard error and exits 1
    assert len(line.splitlines()) == 1, line
    assert line.startswith("workflow: "), line
    return line


def _env(tmp_path, gh) -> dict:
    return {**os.environ, "PATH": f"{gh.bin}{os.pathsep}{os.environ.get('PATH', '')}", "CLAUDE_PROJECT_DIR": str(tmp_path),
            "WORKFLOW_UPDATE_CHECK": "off"}


# ---------- the ticket's cases ----------


def test_output_that_isnt_json_is_refused_in_one_line(monkeypatch, capsys, tmp_path):
    """`gh` exits 0 printing `not json`: a `JSONDecodeError` before."""
    line = _refused(monkeypatch, capsys, tmp_path, NOT_JSON)
    assert line == (
        "workflow: can't read the issues `gh api repos/acme/demo/issues` gave:"
        " it isn't valid JSON (Expecting value, line 1)" + INSTEAD
    )


def test_a_number_of_5000_digits_is_refused_in_one_line(monkeypatch, capsys, tmp_path):
    """`ValueError: Exceeds the limit (4300 digits)` before."""
    line = _refused(monkeypatch, capsys, tmp_path, LONG_NUMBER)
    assert line.startswith("workflow: can't read the issues `gh api repos/acme/demo/issues` gave: it can't be read (ValueError: ")
    assert line.endswith(INSTEAD)
    assert "9" * 100 not in line


def test_lists_nested_5000_deep_are_refused_in_one_line(monkeypatch, capsys, tmp_path):
    """`RecursionError` in `_fetch_items` before. Where Python's own reader
    can't read it (before 3.12) and where it can, the same line."""
    line = _refused(monkeypatch, capsys, tmp_path, DEEP)
    assert line == "workflow: can't read the issues `gh api repos/acme/demo/issues` gave: it is nested too deeply to read" + INSTEAD


@pytest.mark.parametrize("text", [NOT_JSON, LONG_NUMBER, DEEP], ids=["not-json", "long-number", "deep"])
def test_the_pull_requests_are_refused_the_same_way(monkeypatch, capsys, tmp_path, text):
    line = _refused(monkeypatch, capsys, tmp_path, [ISSUE], text)
    assert line.startswith("workflow: can't read the pull requests `gh api repos/acme/demo/pulls` gave: it ")


def test_the_json_is_refused_the_same_way(monkeypatch, capsys, tmp_path):
    """`--json` prints no half-read status: the same one line."""
    assert "it isn't valid JSON" in _refused(monkeypatch, capsys, tmp_path, NOT_JSON, None, "--json")


@pytest.mark.parametrize("text", [NOT_JSON, LONG_NUMBER, DEEP], ids=["not-json", "long-number", "deep"])
def test_a_gh_without_slurp_is_refused_the_same_way(monkeypatch, capsys, tmp_path, text):
    """An old `gh` prints the pages one after another (`posts.decode_values`)."""
    line = _refused(monkeypatch, capsys, tmp_path, text, slurp=False)
    assert line.startswith("workflow: can't read the issues `gh api repos/acme/demo/issues` gave: ")
    assert line.endswith(INSTEAD)


@pytest.mark.parametrize("text", [NOT_JSON, LONG_NUMBER, DEEP], ids=["not-json", "long-number", "deep"])
def test_the_process_prints_one_line_and_exits_1(tmp_path, text):
    """The command as a person runs it: one line on standard error, exit 1."""
    gh = fake_gh.write(tmp_path / "bin", _routes(text))
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "status", "--fetch"],
                       capture_output=True, text=True, cwd=tmp_path, env=_env(tmp_path, gh))
    assert p.returncode == 1, p.stderr
    assert p.stdout == ""
    assert len(p.stderr.strip().splitlines()) == 1, p.stderr
    assert p.stderr.startswith("workflow: can't read the issues `gh api repos/acme/demo/issues` gave: it "), p.stderr


# ---------- what it still reads ----------


def test_empty_output_is_still_no_issues(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, _routes("", "\n"))
    code = cli.main(["status", "--fetch", "--json"])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert json.loads(out.out)["issues_read"] is True


def test_pages_nested_as_gh_gives_them_are_still_read(monkeypatch, capsys, tmp_path):
    """`--paginate --slurp`'s pages, and a few levels more, are read as before."""
    other = {**ISSUE, "number": 13, "labels": [{"name": "workflow:in-progress"}]}
    nested = json.dumps([[ISSUE], [[[other]]]])
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, _routes(nested))
    code = cli.main(["status", "--fetch", "--json"])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert [i["number"] for i in json.loads(out.out)["in_progress"]] == [13]


# ---------- the reader and the flattening ----------


def test_fetch_reads_gh_with_doctors_json_reader():
    """The reader `_issues_file` uses (#757), not a plain `json.loads`."""
    src = inspect.getsource(cli._fetch)
    assert "doctor_mod._parse_json(" in src
    assert "json.loads" not in src


def test_the_pages_are_flattened_without_recursion():
    """Lists nested past Python's recursion limit give their objects, in order,
    for a caller that sets no limit (`graph cites`)."""
    deep = [{"number": 1}]
    for _ in range(5000):
        deep = [deep]
    assert cli._fetch_items([deep, {"number": 2}, "x", [[{"number": 3}]]]) == [{"number": 1}, {"number": 2}, {"number": 3}]


def _nested(depth: int) -> str:
    """An in-progress issue in lists `depth` deep, as `gh` would print them."""
    return "[" * depth + json.dumps({**ISSUE, "labels": [{"name": "workflow:in-progress"}]}) + "]" * depth


@pytest.mark.parametrize("slurp", [True, False], ids=["slurp", "old-gh"])
@pytest.mark.parametrize("route", ["issues", "pulls"])
def test_the_nesting_limit_is_counted_on_what_gh_prints(monkeypatch, capsys, tmp_path, slurp, route):
    """`gh`'s output 7 lists deep is read, 8 deep refused (`FETCH_DEPTH`
    counts the list `_fetch` holds it in), the same with or without
    `--slurp`, for the issues and the pull requests."""
    deepest = cli.FETCH_DEPTH - 1
    assert deepest == 7
    read = {"issues": (_nested(deepest), None), "pulls": ([ISSUE], _nested(deepest))}[route]
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, _routes(*read), slurp=slurp)
    code = cli.main(["status", "--fetch", "--json"])
    out = capsys.readouterr()
    assert code == 0, out.err
    assert json.loads(out.out)["issues_read"] is True
    if route == "issues":
        assert [i["number"] for i in json.loads(out.out)["in_progress"]] == [12]
    refused = {"issues": (_nested(deepest + 1), None), "pulls": ([ISSUE], _nested(deepest + 1))}[route]
    line = _refused(monkeypatch, capsys, tmp_path / "again", *refused, slurp=slurp)
    what = "issues `gh api repos/acme/demo/issues`" if route == "issues" else "pull requests `gh api repos/acme/demo/pulls`"
    assert line == f"workflow: can't read the {what} gave: it is nested too deeply to read" + INSTEAD


def test_a_limit_refuses_lists_nested_deeper():
    with pytest.raises(cli.TooDeep):
        cli._fetch_items([[[[{"number": 1}]]]], deepest=3)
    assert cli._fetch_items([[[{"number": 1}]]], deepest=3) == [{"number": 1}]


# ---------- the other callers of `_fetch` ----------


def test_ready_fetch_is_refused_the_same_way(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, _routes(NOT_JSON))
    with pytest.raises(SystemExit) as e:
        cli.main(["ready", "--fetch"])
    assert "Traceback" not in capsys.readouterr().err
    assert e.value.code == (
        "workflow: can't read the issues `gh api repos/acme/demo/issues` gave: it isn't valid JSON (Expecting value, line 1)" + INSTEAD
    )


def test_state_join_fetch_names_its_own_flags(tmp_path):
    """`state join --fetch` keeps its own wording: `--issues F and
    --permissions F`, never `--prs`."""
    gh = fake_gh.write(tmp_path / "bin", {"repos/acme/demo/issues": fake_gh.reply(NOT_JSON)})
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
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "state", "join", "--body", "body.md", "--fetch", "--out", "new.md"],
                       capture_output=True, text=True, cwd=tmp_path, env=_env(tmp_path, gh))
    assert p.returncode == 1, p.stderr
    assert "Traceback" not in p.stderr
    assert len(p.stderr.strip().splitlines()) == 1, p.stderr
    assert "the issues `gh api repos/acme/demo/issues` gave: it isn't valid JSON" in p.stderr
    assert "--issues F and --permissions F" in p.stderr and "--prs" not in p.stderr
    assert not (tmp_path / "new.md").exists()


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#788, found in the review of #775's pull request")
    assert "workflow status --fetch" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_status_fetch_unreadable.py" in note


def test_the_changelog_gives_the_nesting_limit_the_code_has():
    """The note counts what `gh` prints: the code reads it up to
    `FETCH_DEPTH - 1` lists deep, since `FETCH_DEPTH` counts the list
    `_fetch` holds it in."""
    note = entry("#788, found in the review of #775's pull request")
    assert f"lists nested more than {cli.FETCH_DEPTH - 1} deep (`gh` prints 2)" in note
    assert f"more than {cli.FETCH_DEPTH} deep" not in note


def test_no_text_says_output_that_isnt_utf8_is_refused():
    """The page-by-page route (`fetch.by_page`) reads bytes that aren't UTF-8
    with them replaced, so no text may say such output is refused: the
    changelog's note, `_fetch`'s line in the architecture page and its
    docstring. Reading it is #812's."""
    note = entry("#788, found in the review of #775's pull request")
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(ln for ln in page.splitlines() if ln.startswith("- `_fetch`: "))
    for where, text in (("the changelog's note", note), ("the architecture page", line), ("_fetch's docstring", cli._fetch.__doc__)):
        assert "UTF-8" not in text, where

"""`workflow ready --fetch` refuses, in one `workflow:` line, issues or pull
requests `gh api` gave without a whole-number `number`, as `workflow status
--fetch` does (#775, `cli._unnumbered`), never a traceback (#790, #815). Run
through `cli.main`, with the fake `gh` on the PATH, on each of `_fetch`'s
routes: `--slurp`, an old `gh` without it, and the pages read one at a time
where the proxy refuses the next-page link (#568).

`workflow state join --fetch` reads the issues through the same `_fetch`, but
reads past an item without a whole-number number (`state._candidates`), so it
has no traceback to refuse: its tests here pin that.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import entry
from workflow import charter, cli, state
from workflow import profile as profile_mod

KIT = Path(__file__).resolve().parents[1]

ISSUE = {"number": 12, "title": "Add notes", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: notes"}
PR = {"number": 30, "title": "Notes list", "state": "open", "body": "", "head": {"ref": "claude/build-30"}}

# #790's case is `gh`'s output as a whole; #815's is the issues page.
NO_NUMBER_790 = {"title": "no number", "labels": []}
NO_NUMBER_815 = {"title": "x", "labels": []}
MIXED = [{**ISSUE, "number": "1"}, {**ISSUE, "number": 2}]

# Each of `_fetch`'s routes, as the fake `gh` takes them.
ROUTES = {
    "slurp": {"slurp": True, "numeric_refused": False},
    "old-gh": {"slurp": False, "numeric_refused": False},
    "page-by-page": {"slurp": True, "numeric_refused": True},
}
REFUSAL = (
    "workflow: can't read the issues `gh api repos/acme/demo/issues` gave: {} has no whole-number number"
    " (fetch them with the GitHub MCP tools and give --issues and --prs files instead)"
)


def _project(monkeypatch, tmp_path, repo_toml: str = '"acme/demo"'):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(f'[project]\nname = "demo"\nrepo = {repo_toml}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _install(monkeypatch, tmp_path, issue_pages: list, pr_pages: list, route: str):
    r = ROUTES[route]
    if r["numeric_refused"]:
        # The fake proxy refuses `--paginate` only past a first page: a
        # trailing empty page makes one page read page by page too.
        issue_pages, pr_pages = [*issue_pages, []], [*pr_pages, []]
    routes = {
        "repos/acme/demo/issues": fake_gh.pages(*issue_pages, numeric_refused=r["numeric_refused"]),
        "repos/acme/demo/pulls": fake_gh.pages(*pr_pages, numeric_refused=r["numeric_refused"]),
    }
    return fake_gh.install(tmp_path, monkeypatch, routes, slurp=r["slurp"])


def _read_by_page(gh, route: str):
    """The page-by-page route really read the issues one page at a time
    (`fetch.by_page`), rather than `--slurp` answering them whole."""
    if route == "page-by-page":
        assert "repos/acme/demo/issues?state=all&per_page=100&page=1" in gh.paths(), gh.paths()


def _ready(monkeypatch, capsys, tmp_path, issues: list, prs: list, *extra, route: str = "slurp"):
    _project(monkeypatch, tmp_path)
    gh = _install(monkeypatch, tmp_path, [issues], [prs], route)
    code = cli.main(["ready", "--fetch", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    _read_by_page(gh, route)
    return code, out.out, out.err


def _refused(monkeypatch, capsys, tmp_path, issues, prs=(PR,), *extra, **kw) -> str:
    """One `workflow:` line on standard error, nothing on standard output, exit 1."""
    code, out, err = _ready(monkeypatch, capsys, tmp_path, list(issues), list(prs), *extra, **kw)
    assert code == 1, err
    assert out == ""
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("workflow: "), lines[0]
    return lines[0]


# ---------- the tickets' cases, on every route ----------


@pytest.mark.parametrize("route", list(ROUTES))
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["text", "json"])
def test_an_issue_with_no_number_is_refused_in_one_line(monkeypatch, capsys, tmp_path, route, extra):
    """#790: `gh` prints `[[{"title": "no number", "labels": []}]]`: a `KeyError: 'number'` before."""
    assert _refused(monkeypatch, capsys, tmp_path, [NO_NUMBER_790], (PR,), *extra, route=route) == REFUSAL.format("1 of 1")


@pytest.mark.parametrize("route", list(ROUTES))
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["text", "json"])
def test_815s_page_with_no_number_is_refused_in_one_line(monkeypatch, capsys, tmp_path, route, extra):
    """#815: the issues page is `[{"title": "x", "labels": []}]`."""
    assert _refused(monkeypatch, capsys, tmp_path, [NO_NUMBER_815], (PR,), *extra, route=route) == REFUSAL.format("1 of 1")


@pytest.mark.parametrize("route", list(ROUTES))
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["text", "json"])
def test_a_list_mixing_text_and_whole_number_numbers_is_refused(monkeypatch, capsys, tmp_path, route, extra):
    """#790 and #815: `"1"` beside `2`: a `TypeError` on sorting before."""
    assert _refused(monkeypatch, capsys, tmp_path, MIXED, (PR,), *extra, route=route) == REFUSAL.format("1 of 2")


@pytest.mark.parametrize("route", list(ROUTES))
def test_the_mixed_numbers_across_two_pages_are_refused(monkeypatch, capsys, tmp_path, route):
    """`"1"` on one page and `2` on the next, as `gh` pages them. The first
    page is full (100), so the page-by-page route reads the second too."""
    _project(monkeypatch, tmp_path)
    first = [{**ISSUE, "number": n} for n in range(100, 199)] + [MIXED[0]]
    gh = _install(monkeypatch, tmp_path, [first, [MIXED[1]]], [[PR]], route)
    code = cli.main(["ready", "--fetch"])
    err = capsys.readouterr().err
    assert code == 1, err
    assert "Traceback" not in err
    assert err.strip().splitlines() == [REFUSAL.format("1 of 101")]
    _read_by_page(gh, route)


# ---------- the same check as `status --fetch`'s ----------


@pytest.mark.parametrize("number", [None, "12", True, 12.0, [12], {"n": 12}])
def test_any_number_that_isnt_whole_is_refused(monkeypatch, capsys, tmp_path, number):
    """What `status --fetch` refuses (`doctor._number`), `ready --fetch` refuses."""
    assert _refused(monkeypatch, capsys, tmp_path, [ISSUE, {**ISSUE, "number": number}]) == REFUSAL.format("1 of 2")


def test_several_without_one_are_counted(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, [{"title": "a"}, {**ISSUE, "number": "3"}, ISSUE])
    assert "2 of 3 have no whole-number number" in line


def test_a_pull_request_with_no_number_is_refused_naming_pull_requests(monkeypatch, capsys, tmp_path):
    line = _refused(monkeypatch, capsys, tmp_path, [ISSUE], [{"title": "no number", "head": {"ref": "x"}}])
    assert line == (
        "workflow: can't read the pull requests `gh api repos/acme/demo/pulls` gave: 1 of 1 has no whole-number number"
        " (fetch them with the GitHub MCP tools and give --issues and --prs files instead)"
    )


@pytest.mark.parametrize("issues", [[NO_NUMBER_790], [NO_NUMBER_815], MIXED], ids=["790", "815", "mixed"])
def test_the_line_is_status_fetchs_line(monkeypatch, capsys, tmp_path, issues):
    """One refusal for both commands: the words `status --fetch` gives (#775)."""
    line = _refused(monkeypatch, capsys, tmp_path, issues)
    code = cli.main(["status", "--fetch"])
    err = capsys.readouterr().err
    assert code == 1, err
    assert err.strip() == line


def test_the_repo_is_shown_escaped(monkeypatch, capsys, tmp_path):
    """The profile's `project.repo` with a newline in it keeps the refusal one line (`cli._gave`)."""
    # The profile refuses a control character in project.repo since #821
    # (`tests/test_profile_repo_control.py`): past that check, this still
    # tests that `_gave` shows any repo it is given escaped.
    monkeypatch.setattr(profile_mod, "CONTROL", re.compile(r"(?!)"))
    _project(monkeypatch, tmp_path, '"acme/de\\nmo"')
    routes = {"repos/acme/de\nmo/issues": fake_gh.pages([NO_NUMBER_790]), "repos/acme/de\nmo/pulls": fake_gh.pages([PR])}
    fake_gh.install(tmp_path, monkeypatch, routes)
    code = cli.main(["ready", "--fetch"])
    err = capsys.readouterr().err
    assert code == 1, err
    lines = err.strip().splitlines()
    assert len(lines) == 1, err
    assert lines[0].startswith("workflow: can't read the issues `gh api repos/acme/de\\nmo/issues` gave: 1 of 1 has no"), lines[0]


def test_ready_and_status_refuse_through_one_check():
    """`ready --fetch` refuses through `cli._unnumbered`, as `status --fetch`
    does, rather than another check."""
    import inspect

    assert "_unnumbered_line(" in inspect.getsource(cli.cmd_ready)
    assert "_unnumbered_line(" in inspect.getsource(cli._status)
    assert "_unnumbered(" in inspect.getsource(cli._unnumbered_line)


# ---------- what it still takes ----------


@pytest.mark.parametrize("route", list(ROUTES))
def test_whole_number_numbers_still_give_the_answer(monkeypatch, capsys, tmp_path, route):
    other = {**ISSUE, "number": 13, "title": "Delete notes", "body": "Area: shop"}
    code, out, err = _ready(monkeypatch, capsys, tmp_path, [ISSUE, other], [PR], "--json", route=route)
    assert code == 0, err
    assert sorted(v["number"] for v in json.loads(out)["ready"]) == [12, 13]


def test_no_issues_is_no_refusal(monkeypatch, capsys, tmp_path):
    code, out, err = _ready(monkeypatch, capsys, tmp_path, [], [], "--json")
    assert code == 0, err
    assert json.loads(out)["ready"] == []


# ---------- `state join --fetch`: no traceback to refuse ----------


OWNER = "owner-login"


def _fix(n, src=378, kind="split"):
    body = f"Area: notes\n\n## Blocked by\n\nNone\n\n<!-- workflow:fix-ticket from={src} kind={kind} -->\n<!-- workflow:agent -->\n"
    return {"number": n, "title": f"Ticket {n}", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": body, "user": {"login": OWNER}}


def _state():
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-13-join"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    return s


@pytest.mark.parametrize(
    "issues",
    [[NO_NUMBER_790, _fix(501)], [NO_NUMBER_815, _fix(501)], [{**_fix(500), "number": "1"}, _fix(501)]],
    ids=["790", "815", "mixed"],
)
def test_state_join_fetch_reads_past_an_issue_without_a_whole_number_number(tmp_path, monkeypatch, issues):
    """No traceback: `state._candidates` reads past it, as it reads past any
    issue that can't be a ticket of the run; the rest still join."""
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n', encoding="utf-8")
    (tmp_path / "body.md").write_text(state.put("## Run\n", _state()), encoding="utf-8")
    fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages(issues),
        f"repos/acme/demo/collaborators/{OWNER}/permission": {"permission": "admin", "user": {"login": OWNER}},
    })
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "WORKFLOW_UPDATE_CHECK": "off"}
    p = subprocess.run(
        [sys.executable, "-B", str(KIT / "scripts/workflow.py"), "state", "join", "--body", "body.md", "--fetch", "--out", "new.md"],
        cwd=tmp_path, capture_output=True, text=True, env=env,
    )
    assert "Traceback" not in p.stderr, p.stderr
    assert p.returncode == 0, p.stderr
    assert state.get((tmp_path / "new.md").read_text())["joined"] == {"501": {"from": 378, "kind": "split"}}


# ---------- the architecture page ----------


def test_the_pages_rule_names_state_joins_read_past():
    """The rule binds a command that needs every item's number, and names
    `state join --fetch`, which reads past such an item, as no such command."""
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `_unnumbered_line`:"))
    assert "A command that reads `_fetch`'s items by their number refuses" not in line
    assert "needs every item's number" in line
    assert "`workflow state join --fetch`" in line and "`state._candidates`" in line


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#790, found in the review of #775's pull request")
    assert "workflow ready --fetch" in note
    assert "#815" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_ready_fetch_numbers.py" in note

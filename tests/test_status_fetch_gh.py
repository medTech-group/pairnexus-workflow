"""`workflow status --fetch`, `ready --fetch` and `state join --fetch` read
`gh api` through `cli._fetch`, which ran it with `subprocess.run(...,
text=True)` and nothing else, so two cases ended in a traceback:

- no `gh` on the PATH: `FileNotFoundError` (#809);
- `gh` output that isn't UTF-8, on standard output with exit 0 or on standard
  error when it fails: `UnicodeDecodeError` (#812, split out of #788).

Now `_fetch` runs `gh` through `fetch.run_exact`, which turns a `gh` that
can't be run into `GhError` as `fetch._run` does, and keeps output that isn't
UTF-8 seen: such standard output is refused in one line, `it isn't UTF-8
text`, as an `--issues` file is, and standard error is read with U+FFFD in
place of such bytes. The page-by-page route's own reads (`fetch.by_page`) are
#810's.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import entry
from workflow import charter, cli, fetch, state

KIT = Path(__file__).resolve().parents[1]
ISSUE = {"number": 12, "title": "Add notes", "state": "open", "labels": [], "body": ""}
PR = {"number": 30, "title": "Notes list", "state": "open", "head": {"ref": "claude/build-12"}}
INSTEAD = " (fetch them with the GitHub MCP tools and give --issues and --prs files instead)"
NO_GH = "workflow: can't run `gh api repos/acme/demo/issues`: gh (the GitHub CLI) isn't installed here" + INSTEAD
NOT_UTF8 = "workflow: can't read the issues `gh api repos/acme/demo/issues` gave: it isn't UTF-8 text" + INSTEAD
# #812's example: an issue's title holding the bytes FF FE, which no UTF-8 text holds.
BAD_PAGES = b'[[{"number": 12, "title": "\xff\xfe bad", "state": "open"}]]'
BAD_PAGE = b'[{"number": 12, "title": "\xff\xfe bad", "state": "open"}]'
BAD_STDERR = b"gh: Bad \xff\xfe credentials (HTTP 401)\n"
FAILED_401 = "gh api repos/acme/demo/issues?state=all&per_page=100 failed: gh: Bad \ufffd\ufffd credentials (HTTP 401)"
ROUTES = ["slurp", "old-gh"]


def _project(monkeypatch, tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _install(monkeypatch, tmp_path, issues_answer, route: str):
    return fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": issues_answer, "repos/acme/demo/pulls": fake_gh.pages([PR])},
                           slurp=route == "slurp")


def _refused(monkeypatch, capsys, args: list[str]):
    """`cli.main(args)` ends in a SystemExit whose code is the one line the
    process prints on standard error when it exits 1; nothing on standard
    output, and no traceback."""
    with pytest.raises(SystemExit) as e:
        cli.main(args)
    out = capsys.readouterr()
    assert out.out == ""
    assert "Traceback" not in out.err
    line = e.value.code
    assert isinstance(line, str), line
    return line


def _env(tmp_path, path: str) -> dict:
    return {**os.environ, "PATH": path, "CLAUDE_PROJECT_DIR": str(tmp_path), "WORKFLOW_UPDATE_CHECK": "off"}


def _join_project(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n[areas]\nconductor = []\n', encoding="utf-8"
    )
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-13-join"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    (tmp_path / "body.md").write_text(state.put("## Run\n", s))


def _join(tmp_path, path: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "state", "join", "--body", "body.md", "--fetch", "--out", "new.md"],
                          capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, env=_env(tmp_path, path))


# ---------- #809: no gh on the PATH ----------


@pytest.mark.parametrize("cmd", ["status", "ready"])
def test_no_gh_on_the_path_is_refused_in_one_line(monkeypatch, capsys, tmp_path, cmd):
    """#809: `FileNotFoundError` before."""
    _project(monkeypatch, tmp_path)
    fake_gh.without_gh(tmp_path, monkeypatch)
    assert _refused(monkeypatch, capsys, [cmd, "--fetch"]) == NO_GH


@pytest.mark.parametrize("cmd", ["status", "ready"])
def test_the_process_with_no_gh_prints_one_line_and_exits_1(tmp_path, cmd):
    """The command as a person runs it: one line on standard error, exit 1."""
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), cmd, "--fetch"],
                       capture_output=True, text=True, cwd=tmp_path, env=_env(tmp_path, str(empty)))
    assert p.returncode == 1, p.stderr
    assert p.stdout == ""
    assert p.stderr == NO_GH + "\n"


def test_state_join_with_no_gh_keeps_its_own_wording(tmp_path):
    """#809: `state join --fetch` names `--issues F and --permissions F`, never `--prs`."""
    _join_project(tmp_path)
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    p = _join(tmp_path, str(empty))
    assert p.returncode == 1, p.stderr
    assert p.stderr == (
        "workflow state join: the open issues couldn't be read (can't run `gh api repos/acme/demo/issues`:"
        " gh (the GitHub CLI) isn't installed here); give --issues F and --permissions F in place of --fetch\n"
    )
    assert not (tmp_path / "new.md").exists()


def test_a_gh_that_cant_be_started_is_refused_in_one_line(monkeypatch, capsys, tmp_path):
    """A `gh` on the PATH that isn't executable: `PermissionError`, an
    `OSError`, which `fetch._run` turns into `GhError` too."""
    _project(monkeypatch, tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text("#!/bin/sh\n")
    (bin_dir / "gh").chmod(0o644)
    monkeypatch.setenv("PATH", str(bin_dir))
    line = _refused(monkeypatch, capsys, ["status", "--fetch"])
    assert line.startswith("workflow: can't run `gh api repos/acme/demo/issues`: couldn't run gh: "), line
    assert line.endswith(INSTEAD) and len(line.splitlines()) == 1


def test_a_repo_with_a_line_break_stays_one_line(monkeypatch, capsys, tmp_path):
    """The repo is shown through `reviews._shown`, as `_gave` shows it."""
    _project(monkeypatch, tmp_path)
    fake_gh.without_gh(tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as e:
        cli._fetch("acme/de\nmo", "pulls")
    assert e.value.code == "workflow: can't run `gh api repos/acme/de\\nmo/pulls`: gh (the GitHub CLI) isn't installed here" + INSTEAD


def test_the_refusal_carries_its_words_for_a_caller_with_its_own(monkeypatch, tmp_path):
    """`said`: the refusal without `workflow: ` and the advice, as `state
    join` words it; `FetchUnreadable` gives its own the same way."""
    fake_gh.without_gh(tmp_path, monkeypatch)
    with pytest.raises(cli.FetchRefused) as e:
        cli._fetch("acme/demo", "issues")
    assert e.value.said == "can't run `gh api repos/acme/demo/issues`: gh (the GitHub CLI) isn't installed here"
    unreadable = cli.FetchUnreadable("the issues `gh api repos/acme/demo/issues` gave", "it isn't UTF-8 text")
    assert isinstance(unreadable, cli.FetchRefused)
    assert unreadable.said == "can't read the issues `gh api repos/acme/demo/issues` gave: it isn't UTF-8 text"
    assert unreadable.code == NOT_UTF8


# ---------- #812: standard output that isn't UTF-8 ----------


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("cmd", ["status", "ready"])
def test_standard_output_that_isnt_utf8_is_refused_in_one_line(monkeypatch, capsys, tmp_path, route, cmd):
    """#812: `gh` exits 0 printing bytes that aren't UTF-8: a
    `UnicodeDecodeError` before; on an old `gh`, its pages one after another."""
    _project(monkeypatch, tmp_path)
    gh = _install(monkeypatch, tmp_path, fake_gh.reply(BAD_PAGES if route == "slurp" else BAD_PAGE), route)
    assert _refused(monkeypatch, capsys, [cmd, "--fetch"]) == NOT_UTF8
    assert len(gh.calls()) == (1 if route == "slurp" else 2)


def test_the_process_prints_one_line_and_exits_1(tmp_path):
    gh = fake_gh.write(tmp_path / "bin", {"repos/acme/demo/issues": fake_gh.reply(BAD_PAGES)})
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n', encoding="utf-8")
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "status", "--fetch"],
                       capture_output=True, text=True, cwd=tmp_path, env=_env(tmp_path, f"{gh.bin}{os.pathsep}{os.environ.get('PATH', '')}"))
    assert p.returncode == 1, p.stderr
    assert p.stdout == ""
    assert p.stderr == NOT_UTF8 + "\n"


def test_the_pull_requests_are_refused_the_same_way(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.pages([ISSUE]), "repos/acme/demo/pulls": fake_gh.reply(BAD_PAGES)})
    assert _refused(monkeypatch, capsys, ["status", "--fetch"]) == (
        "workflow: can't read the pull requests `gh api repos/acme/demo/pulls` gave: it isn't UTF-8 text" + INSTEAD
    )


def test_state_join_keeps_its_own_wording(tmp_path):
    """#812: `state join --fetch` names `--issues F and --permissions F`, never `--prs`."""
    _join_project(tmp_path)
    gh = fake_gh.write(tmp_path / "bin", {"repos/acme/demo/issues": fake_gh.reply(BAD_PAGES)})
    p = _join(tmp_path, f"{gh.bin}{os.pathsep}{os.environ.get('PATH', '')}")
    assert p.returncode == 1, p.stderr
    assert p.stderr == (
        "workflow state join: the open issues couldn't be read (can't read the issues `gh api repos/acme/demo/issues` gave:"
        " it isn't UTF-8 text); give --issues F and --permissions F in place of --fetch\n"
    )
    assert not (tmp_path / "new.md").exists()


@pytest.mark.parametrize("route", ROUTES)
def test_utf8_text_outside_ascii_is_still_read(monkeypatch, capsys, tmp_path, route):
    """#812: accents and emoji are UTF-8, and read as before."""
    _project(monkeypatch, tmp_path)
    title = "Café notes ☕ 😀"
    _install(monkeypatch, tmp_path, fake_gh.pages([{**ISSUE, "title": title}]), route)
    assert [i["title"] for i in cli._fetch("acme/demo", "issues")] == [title]
    raw = json.dumps([[{**ISSUE, "title": title}]], ensure_ascii=False).encode("utf-8")
    fake_gh.install(tmp_path / "raw", monkeypatch, {"repos/acme/demo/issues": fake_gh.reply(raw if route == "slurp" else raw[1:-1])},
                    slurp=route == "slurp")
    assert [i["title"] for i in cli._fetch("acme/demo", "issues")] == [title]


# ---------- #812: standard error that isn't UTF-8 ----------


@pytest.mark.parametrize("route", ROUTES)
def test_standard_error_that_isnt_utf8_gives_the_failure(monkeypatch, capsys, tmp_path, route):
    """#812: `gh` exits 1 with bytes that aren't UTF-8 on standard error: its
    failure message as before, those bytes read as U+FFFD."""
    _project(monkeypatch, tmp_path)
    failing = fake_gh.reply(exit=1, stderr=BAD_STDERR)
    if route == "old-gh":
        failing = fake_gh.reply(exit=1, stderr=BAD_STDERR, slurp=fake_gh.reply(exit=1, stderr=b"\xff\xfe unknown flag: --slurp\n"))
    gh = _install(monkeypatch, tmp_path, failing, "slurp")
    line = _refused(monkeypatch, capsys, ["status", "--fetch"])
    assert line.splitlines()[0] == FAILED_401
    assert len(gh.calls()) == (1 if route == "slurp" else 2)


def test_unknown_flag_slurp_beside_such_bytes_still_reads_without_it(monkeypatch, tmp_path):
    """An old `gh`'s refusal of `--slurp` beside bytes that aren't UTF-8 still
    sends the read to the call without `--slurp`."""
    answer = fake_gh.reply(json.dumps([ISSUE]), slurp=fake_gh.reply(exit=1, stderr=b"\xff\xfe\nunknown flag: --slurp\n"))
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": answer})
    assert [i["number"] for i in cli._fetch("acme/demo", "issues")] == [12]
    assert len(gh.calls()) == 2 and "--slurp" not in gh.calls()[1]


@pytest.mark.parametrize("route", ROUTES)
def test_the_proxys_refusal_beside_such_bytes_still_reads_page_by_page(monkeypatch, tmp_path, route):
    """The proxy's numeric-ID refusal beside bytes that aren't UTF-8 still
    sends the read page by page (`fetch.by_page`)."""
    second = {**ISSUE, "number": 13}
    pages = fake_gh.pages([ISSUE] * 100, [second], [], numeric_refused=True, refusal=b"\xff\xfe " + fake_gh.NUMERIC_REFUSED.encode())
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": pages}, slurp=route == "slurp")
    got = cli._fetch("acme/demo", "issues")
    assert [i["number"] for i in got] == [12] * 100 + [13]
    assert "repos/acme/demo/issues?state=all&per_page=100&page=2" in gh.paths(), gh.paths()


# ---------- the runner ----------


def test_fetch_runs_gh_through_fetchs_runner():
    """`_fetch` runs `gh` through `fetch.run_exact`, never `subprocess` itself."""
    import inspect

    src = inspect.getsource(cli._fetch)
    assert "fetch_mod.run_exact(" in src
    assert "subprocess.run" not in src


def test_run_exact_keeps_bytes_that_arent_utf8_seen(tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, {"x": fake_gh.reply(b"\xff ok \xc3\xa9", exit=1, stderr=b"\xfe bad\n")})
    p = fetch.run_exact(["api", "x"])
    assert p.returncode == 1
    assert not fetch.is_utf8(p.stdout)
    assert p.stderr == "\ufffd bad\n"
    assert fetch.is_utf8("ok é 😀")


def test_run_exact_with_no_gh_raises_gh_error(tmp_path, monkeypatch):
    fake_gh.without_gh(tmp_path, monkeypatch)
    with pytest.raises(fetch.GhError, match="^gh \\(the GitHub CLI\\) isn't installed here$"):
        fetch.run_exact(["api", "x"])


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#809 and #812, found in the review of #788's pull request")
    assert "workflow status --fetch" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_status_fetch_gh.py" in note
    assert "#810" in note  # the page-by-page route's own reads

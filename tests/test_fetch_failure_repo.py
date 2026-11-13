"""`_fetch`'s `gh api … failed` lines show the profile's `project.repo`
through `reviews._shown`, as its refusals do (#775's `_gave`), so a newline,
a backtick or U+202E in the repo never splits or garbles the line (#792).
Run through `cli.main`, with the fake `gh` on the PATH, on each failure:
`--slurp`'s, an old `gh`'s, and the pages read one at a time where the proxy
refuses the next-page link (#568).
"""

import re

import pytest

import fake_gh
from changelog_notes import entry
from workflow import charter, cli, fetch, state
from workflow import profile as profile_mod

QUERY = "issues?state=all&per_page=100"
AGAIN = "Fetch with the GitHub MCP tools instead and pass --issues/--prs files."

REPOS = pytest.mark.parametrize(
    "repo_toml, repo, shown",
    [
        ('"acme/de\\nmo"', "acme/de\nmo", "acme/de\\nmo"),
        ('"acme/de`mo"', "acme/de`mo", "acme/de\\`mo"),
        ('"acme/de\\u202Emo"', "acme/de‮mo", "acme/de\\u202emo"),
    ],
    ids=["newline", "backtick", "right-to-left-override"],
)


def _project(monkeypatch, tmp_path, repo_toml: str = '"acme/demo"'):
    # The profile refuses a control character in project.repo since #821
    # (`tests/test_profile_repo_control.py`), so the newline cases reach
    # `_fetch` only past that check: they still test that `_fetch` shows any
    # repo it is given escaped.
    monkeypatch.setattr(profile_mod, "CONTROL", re.compile(r"(?!)"))
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(f'[project]\nname = "demo"\nrepo = {repo_toml}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _failure(capsys, *args) -> list[str]:
    """The command's failure, as Python prints a `SystemExit`'s text: its
    lines, nothing on standard output."""
    with pytest.raises(SystemExit) as e:
        cli.main(list(args))
    out = capsys.readouterr()
    assert out.out == ""
    assert "Traceback" not in out.err
    assert isinstance(e.value.code, str), e.value.code
    return e.value.code.splitlines()


# ---------- the ticket's cases ----------


@REPOS
@pytest.mark.parametrize("command", ["status", "ready"])
def test_a_404_shows_the_repo_escaped_on_one_line(monkeypatch, capsys, tmp_path, repo_toml, repo, shown, command):
    """No route: the fake `gh` answers `gh: Not Found (HTTP 404)`, exit 1, on `--slurp`."""
    _project(monkeypatch, tmp_path, repo_toml)
    fake_gh.install(tmp_path, monkeypatch, {})
    lines = _failure(capsys, command, "--fetch")
    assert lines == [f"gh api repos/{shown}/{QUERY} failed: gh: Not Found (HTTP 404)", AGAIN]
    assert repo not in "\n".join(lines)


@REPOS
def test_an_old_gh_s_failure_shows_the_repo_escaped(monkeypatch, capsys, tmp_path, repo_toml, repo, shown):
    """A `gh` without `--slurp` is asked again without it, and its 404 is shown the same way."""
    _project(monkeypatch, tmp_path, repo_toml)
    gh = fake_gh.install(tmp_path, monkeypatch, {}, slurp=False)
    lines = _failure(capsys, "status", "--fetch")
    assert [c for c in gh.calls() if "--slurp" not in c and c[:1] == ["api"]], gh.calls()
    assert lines == [f"gh api repos/{shown}/{QUERY} failed: gh: Not Found (HTTP 404)", AGAIN]


@REPOS
def test_the_page_by_page_failure_shows_the_repo_escaped(monkeypatch, capsys, tmp_path, repo_toml, repo, shown):
    """The proxy refuses the next-page link, and the first page read on its own
    fails too (`fetch.by_page`'s `GhError`)."""
    _project(monkeypatch, tmp_path, repo_toml)
    refused = fake_gh.reply(exit=1, stderr=fake_gh.NUMERIC_REFUSED + "\n")
    gh = fake_gh.install(tmp_path, monkeypatch, {f"repos/{repo}/issues": refused})
    lines = _failure(capsys, "status", "--fetch")
    assert f"repos/{repo}/{QUERY}&page=1" in gh.paths(), gh.paths()
    assert lines == [f"gh api repos/{shown}/{QUERY} failed: gh api failed: {fake_gh.NUMERIC_REFUSED}", AGAIN]


@REPOS
def test_too_many_pages_shows_the_repo_escaped(monkeypatch, capsys, tmp_path, repo_toml, repo, shown):
    """`fetch.by_page`'s own message names the path again: the repo in it is shown escaped too."""
    _project(monkeypatch, tmp_path, repo_toml)
    monkeypatch.setattr(fetch, "MAX_PAGES", 1)
    full = [{"number": n, "title": "t", "state": "open", "labels": []} for n in range(1, 101)]
    gh = fake_gh.install(tmp_path, monkeypatch, {f"repos/{repo}/issues": fake_gh.pages(full, full, numeric_refused=True)})
    lines = _failure(capsys, "status", "--fetch")
    assert f"repos/{repo}/{QUERY}&page=1" in gh.paths(), gh.paths()
    assert lines == [
        f"gh api repos/{shown}/{QUERY} failed: gh api repos/{shown}/issues has more than 1 pages of 100: give it as a file",
        AGAIN,
    ]
    assert repo not in "\n".join(lines)


def test_the_pull_requests_failure_shows_the_repo_escaped_too(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path, '"acme/de\\nmo"')
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/de\nmo/issues": fake_gh.pages([])})
    lines = _failure(capsys, "status", "--fetch")
    assert lines == ["gh api repos/acme/de\\nmo/pulls?state=open&per_page=100 failed: gh: Not Found (HTTP 404)", AGAIN]


def test_state_join_fetch_s_404_keeps_the_reason_with_the_repo_escaped(monkeypatch, capsys, tmp_path):
    """`state join --fetch` reads the issues through `_fetch` too: its one line
    keeps `gh api … failed`'s reason, with the repo escaped, and writes nothing."""
    _project(monkeypatch, tmp_path, '"acme/de\\nmo"')
    fake_gh.install(tmp_path, monkeypatch, {})
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-13-join"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    (tmp_path / "body.md").write_text(state.put("## Run\n", s), encoding="utf-8")
    lines = _failure(capsys, "state", "join", "--body", "body.md", "--fetch", "--out", "new.md")
    assert len(lines) == 1, lines
    assert f"gh api repos/acme/de\\nmo/{QUERY} failed: gh: Not Found (HTTP 404)" in lines[0]
    assert "acme/de\nmo" not in lines[0]
    assert not (tmp_path / "new.md").exists()


# ---------- an ordinary repo ----------


def test_an_ordinary_repo_s_failure_is_unchanged(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path)
    fake_gh.install(tmp_path, monkeypatch, {})
    assert _failure(capsys, "status", "--fetch") == [f"gh api repos/acme/demo/{QUERY} failed: gh: Not Found (HTTP 404)", AGAIN]


def test_an_ordinary_repo_s_page_by_page_failure_is_unchanged(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path)
    refused = fake_gh.reply(exit=1, stderr=fake_gh.NUMERIC_REFUSED + "\n")
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": refused})
    assert _failure(capsys, "status", "--fetch") == [
        f"gh api repos/acme/demo/{QUERY} failed: gh api failed: {fake_gh.NUMERIC_REFUSED}",
        AGAIN,
    ]


def test_the_repo_is_shown_by_reviews_shown():
    """One escape, `_gave`'s: no other."""
    import inspect

    src = inspect.getsource(cli._fetch)
    assert "_shown(" in src
    assert "repr(" not in src and "escape" not in src


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#792, found in the review of #775's pull request")
    assert "workflow status --fetch" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_fetch_failure_repo.py" in note

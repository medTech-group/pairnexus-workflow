"""`workflow ready --fetch`, `workflow status --fetch` and `workflow state join
--fetch` with no `gh` on the PATH (#857, and #809's remaining case): one
`workflow:` line on standard error in `fetch.NOT_INSTALLED`'s words, exit 1,
never a `FileNotFoundError` traceback. `state join` keeps its own wording
(`--issues F and --permissions F`, never `--prs`).

Each command runs as a person runs it, through `scripts/workflow.py`, with a
PATH that holds no `gh` (`fake_gh.without_gh`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import entry
from workflow import charter, fetch, state

KIT = Path(__file__).resolve().parents[1]

FETCH_INSTEAD = "(fetch them with the GitHub MCP tools and give --issues and --prs files instead)"
NOT_INSTALLED_LINE = f"workflow: can't run `gh api repos/acme/demo/issues`: {fetch.NOT_INSTALLED} {FETCH_INSTEAD}"


def _project(tmp_path: Path, owner: bool = False) -> None:
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    extra = 'owner = "owner-login"\n' if owner else ""
    (tmp_path / ".claude/workflow/profile.toml").write_text(f'[project]\nname = "demo"\nrepo = "acme/demo"\n{extra}', encoding="utf-8")


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE")}
    env.update(CLAUDE_PROJECT_DIR=str(tmp_path), WORKFLOW_UPDATE_CHECK="off")
    return subprocess.run(
        [sys.executable, "-B", str(KIT / "scripts/workflow.py"), *args],
        cwd=tmp_path, capture_output=True, text=True, env=env,
    )


def _one_line(p: subprocess.CompletedProcess) -> str:
    """No traceback: one line on standard error, nothing on standard output, exit 1."""
    assert "Traceback" not in p.stderr, p.stderr
    assert p.returncode == 1, p.stderr
    assert p.stdout == ""
    lines = p.stderr.strip().splitlines()
    assert len(lines) == 1, p.stderr
    return lines[0]


# ---------- #857: `ready --fetch` and `status --fetch` ----------


@pytest.mark.parametrize("command", ["ready", "status"])
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["text", "json"])
def test_no_gh_is_refused_in_one_line(tmp_path, monkeypatch, command, extra):
    _project(tmp_path)
    fake_gh.without_gh(tmp_path, monkeypatch)
    assert _one_line(_run(tmp_path, command, "--fetch", *extra)) == NOT_INSTALLED_LINE


@pytest.mark.parametrize("command", ["ready", "status"])
def test_a_gh_that_cant_be_run_is_refused_in_one_line(tmp_path, monkeypatch, command):
    """A `gh` on the PATH that the system won't start (no execute bit): as
    `fetch._run` words it, `couldn't run gh: <why>`, never a traceback."""
    _project(tmp_path)
    bin_dir = fake_gh.without_gh(tmp_path, monkeypatch)
    (bin_dir / "gh").write_text("not a program\n")
    (bin_dir / "gh").chmod(0o644)
    line = _one_line(_run(tmp_path, command, "--fetch"))
    assert line.startswith("workflow: can't run `gh api repos/acme/demo/issues`: couldn't run gh: "), line
    assert line.endswith(FETCH_INSTEAD), line


def test_with_gh_the_fetch_still_reads(tmp_path, monkeypatch):
    """Unchanged where `gh` runs: the tickets are read through it."""
    _project(tmp_path)
    issue = {"number": 12, "title": "Add notes", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: notes\n\n## Blocked by\n\nNone\n"}
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages([issue]),
        "repos/acme/demo/pulls": fake_gh.pages([]),
    })
    p = _run(tmp_path, "ready", "--fetch", "--json")
    assert "Traceback" not in p.stderr, p.stderr
    assert p.returncode == 0, p.stderr
    assert "#12" in p.stdout or '"number": 12' in p.stdout, p.stdout
    assert gh.paths()[:2] == ["repos/acme/demo/issues?state=all&per_page=100", "repos/acme/demo/pulls?state=open&per_page=100"]


# ---------- #809: `state join --fetch`, in its own words ----------


def _state():
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-13-join"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    return s


def test_state_join_fetch_with_no_gh_keeps_its_own_wording(tmp_path, monkeypatch):
    _project(tmp_path, owner=True)
    (tmp_path / "body.md").write_text(state.put("## Run\n", _state()), encoding="utf-8")
    fake_gh.without_gh(tmp_path, monkeypatch)
    line = _one_line(_run(tmp_path, "state", "join", "--body", "body.md", "--fetch", "--out", "new.md"))
    assert line == (
        "workflow state join: the open issues couldn't be read"
        f" (can't run `gh api repos/acme/demo/issues`: {fetch.NOT_INSTALLED});"
        " give --issues F and --permissions F in place of --fetch"
    ), line
    assert "--prs" not in line
    assert not (tmp_path / "new.md").exists()


# ---------- one wording of a `gh` that can't be run (`fetch.not_run`) ----------


def test_not_run_words_a_gh_that_cant_be_started():
    assert fetch.not_run(FileNotFoundError(2, "No such file or directory", "gh")) == fetch.NOT_INSTALLED
    assert fetch.not_run(PermissionError(13, "Permission denied", "gh")) == "couldn't run gh: Permission denied"
    assert fetch.not_run(OSError("something else")) == "couldn't run gh: something else"


def test_fetch_run_and_cli_fetch_word_it_through_the_one_helper(monkeypatch):
    """`fetch._run` and `cli._fetch` both take their reason from
    `fetch.not_run`, never a copy of its wording."""
    from workflow import cli

    def cant_start(*a, **k):
        raise PermissionError(13, "Permission denied", "gh")

    monkeypatch.setattr(subprocess, "run", cant_start)
    monkeypatch.setattr(fetch, "not_run", lambda e: f"the one wording ({type(e).__name__})")
    with pytest.raises(fetch.GhError) as got:
        fetch._run(["api", "user"])
    assert str(got.value) == "the one wording (PermissionError)"
    with pytest.raises(cli.GhNotRun) as got:
        cli._fetch("acme/demo", "issues")
    assert got.value.said == "can't run `gh api repos/acme/demo/issues`: the one wording (PermissionError)"


def test_the_page_lists_the_helper():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    assert "Covers: scripts/workflow/fetch.py\n" in page
    helpers = page[page.index("## Helpers"):page.index("## Rules")]
    assert "\n- `not_run`: in `fetch.py`" in helpers
    fetch_line = next(l for l in helpers.splitlines() if l.startswith("- `_fetch`: in `cli.py`"))
    assert "`fetch.not_run`" in fetch_line and "`fetch._run`'s words" not in fetch_line


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#857, found in the review of #824's pull request; covers #809's remaining case")
    assert "workflow ready --fetch" in note and "workflow status --fetch" in note and "workflow state join --fetch" in note
    assert fetch.NOT_INSTALLED in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_fetch_no_gh.py" in note

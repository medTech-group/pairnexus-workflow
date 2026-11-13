"""#833: the guard's read of the profile without the kit.

Where the kit can't read the profile, the guard still reads two plain lines
of it as text: `run.ticket_branch` (`_old_python._ticket_branch`, which the CLI
uses too) and `ruleset` (`fallback._profile_text`). An ordinary profile reads
as before.

Seams: `workflow hook guard` through the entry point on this Python (the kit's
path) and through the old-Python fallback's own entry, each in a subprocess;
and the two readers in-process."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_guard_cant_decide import _SHIM, _old_python_binary
from workflow import _old_python, fallback

KIT = Path(__file__).resolve().parents[1]
PROFILE = Path(".claude/workflow/profile.toml")
SECONDS = 20

LS = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
PUSH = {"tool_name": "Bash", "tool_input": {"command": "git push origin feature"}}

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def _project(tmp_path, branch="main"):
    root = tmp_path / "proj"
    subprocess.run(GIT + ["init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(GIT + ["-C", str(root), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    if branch != "main":
        subprocess.run(GIT + ["-C", str(root), "checkout", "-q", "-b", branch], check=True)
    (root / PROFILE).parent.mkdir(parents=True)
    return root


def _shape_1(root, tmp_path):
    os.mkfifo(root / PROFILE)


def _shape_2(root, tmp_path):
    target = tmp_path / "elsewhere"
    os.mkfifo(target)
    os.symlink(target, root / PROFILE)


def _shape_3(root, tmp_path):
    (root / PROFILE).mkdir()


def _shape_4(root, tmp_path):
    os.symlink(os.devnull, root / PROFILE)


MAKES = [
    pytest.param(_shape_1, id="shape-1"), pytest.param(_shape_2, id="shape-2"),
    pytest.param(_shape_3, id="shape-3"), pytest.param(_shape_4, id="shape-4"),
]


def _argv(path):
    if path == "kit":
        return [sys.executable, "-B", str(KIT / "scripts/workflow.py")]
    py = _old_python_binary()
    return [py, "-B", str(KIT / "scripts/workflow.py")] if py else [sys.executable, "-B", "-c", _SHIM, str(KIT / "scripts")]


PATHS = ["kit", "old-python"]


def _guard(path, root, event, role=None):
    """The hook's (exit code, decision or None, reason)."""
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", str(root)), "CLAUDE_PROJECT_DIR": str(root)}
    if role:
        env["WORKFLOW_ROLE"] = role
    p = subprocess.run(
        _argv(path) + ["hook", "guard"], input=json.dumps(dict(event, cwd=str(root))),
        capture_output=True, text=True, env=env, cwd=root, timeout=SECONDS,
    )
    if not p.stdout.strip():
        return p.returncode, None, ""
    out = json.loads(p.stdout)["hookSpecificOutput"]
    return p.returncode, out["permissionDecision"], out["permissionDecisionReason"]


# ---------- the guard ----------


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("make", MAKES)
def test_off_a_ticket_branch_a_push_is_asked(tmp_path, path, make):
    root = _project(tmp_path)
    make(root, tmp_path)
    assert _guard(path, root, LS) == (0, None, "")
    code, decision, _ = _guard(path, root, PUSH)
    assert (code, decision) == (0, "ask")


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("make", MAKES)
def test_on_a_ticket_branch_every_tool_is_refused(tmp_path, path, make):
    """The kit is set up, so the default `run.ticket_branch` decides, as for
    an invalid profile."""
    root = _project(tmp_path, "claude/build-1")
    make(root, tmp_path)
    for event in (LS, PUSH):
        code, decision, _ = _guard(path, root, event)
        assert (code, decision) == (0, "deny")


@pytest.mark.parametrize("path", PATHS)
def test_on_a_ticket_branch_with_no_profile_the_guard_leaves_it_alone(tmp_path, path):
    root = _project(tmp_path, "claude/build-1")
    assert _guard(path, root, LS) == (0, None, "")


@pytest.mark.parametrize("make", MAKES)
def test_without_the_kit_session_start_says_every_tool_is_refused(tmp_path, make):
    root = _project(tmp_path, "claude/build-1")
    make(root, tmp_path)
    env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", str(root)), "CLAUDE_PROJECT_DIR": str(root)}
    p = subprocess.run(
        _argv("old-python") + ["hook", "repair"], input=json.dumps({"cwd": str(root)}),
        capture_output=True, text=True, env=env, cwd=root, timeout=SECONDS,
    )
    assert p.returncode == 0
    assert "every tool is refused" in json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("make", MAKES)
def test_a_ticket_session_is_still_refused(tmp_path, path, make):
    root = _project(tmp_path)
    make(root, tmp_path)
    for event in (LS, PUSH):
        code, decision, _ = _guard(path, root, event, role="ticket")
        assert (code, decision) == (0, "deny")


@pytest.mark.parametrize("path", PATHS)
def test_an_ordinary_profile_still_decides_as_before(tmp_path, path):
    root = _project(tmp_path, "claude/build-1")
    (root / PROFILE).write_text('[project]\nname = 1\n[run]\nticket_branch = "claude/build-*"\n', encoding="utf-8")
    # The profile is invalid, so the guard reads its ticket_branch line as text:
    # a ticket branch, refused every tool.
    code, decision, _ = _guard(path, root, LS)
    assert (code, decision) == (0, "deny")


# ---------- the readers ----------


def _write(root, text):
    (root / PROFILE).parent.mkdir(parents=True, exist_ok=True)
    (root / PROFILE).write_text(text, encoding="utf-8")


def test_the_ticket_branch_line_reads_as_before(tmp_path):
    _write(tmp_path, '[run]\nticket_branch = "work/t-*"\n')
    assert _old_python._ticket_branch(str(tmp_path)) == "work/t-*"
    _write(tmp_path, '[project]\nname = "demo"\n')
    assert _old_python._ticket_branch(str(tmp_path)) == _old_python.DEFAULT_TICKET_BRANCH
    assert _old_python._ticket_branch(str(tmp_path / "nowhere")) is None


def test_the_ruleset_line_reads_as_before(tmp_path):
    _write(tmp_path, "ruleset = false\n")
    assert fallback.solo(tmp_path) is True
    _write(tmp_path, "ruleset = true\n")
    assert fallback.solo(tmp_path) is False
    assert fallback.solo(tmp_path / "nowhere") is False


def test_a_symlink_to_a_profile_reads_as_before(tmp_path):
    real = tmp_path / "real.toml"
    real.write_text('ruleset = false\n[run]\nticket_branch = "work/t-*"\n', encoding="utf-8")
    (tmp_path / PROFILE).parent.mkdir(parents=True)
    os.symlink(real, tmp_path / PROFILE)
    assert _old_python._ticket_branch(str(tmp_path)) == "work/t-*"
    assert fallback.solo(tmp_path) is True


def test_a_directory_gives_the_default_ticket_branch(tmp_path):
    (tmp_path / PROFILE).mkdir(parents=True)
    assert _old_python._ticket_branch(str(tmp_path)) == _old_python.DEFAULT_TICKET_BRANCH
    assert fallback.solo(tmp_path) is False


def test_a_profile_that_cant_be_opened_gives_the_default_ticket_branch(tmp_path, monkeypatch):
    _write(tmp_path, '[run]\nticket_branch = "work/t-*"\n')

    def denied(*a, **kw):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(_old_python.os, "open", denied)
    assert _old_python._ticket_branch(str(tmp_path)) == _old_python.DEFAULT_TICKET_BRANCH


def test_the_ticket_branch_is_read_through_the_profile_reader(monkeypatch):
    """One reader of the profile's text in `_old_python` (#833's review)."""
    monkeypatch.setattr(_old_python, "_profile_text", lambda root: '[run]\nticket_branch = "x/*"\n')
    assert _old_python._ticket_branch("nowhere") == "x/*"
    monkeypatch.setattr(_old_python, "_profile_text", lambda root: "")
    assert _old_python._ticket_branch("nowhere") == _old_python.DEFAULT_TICKET_BRANCH
    monkeypatch.setattr(_old_python, "_profile_text", lambda root: None)
    assert _old_python._ticket_branch("nowhere") is None


def test_the_profile_and_the_experience_file_open_through_one_helper(tmp_path, monkeypatch):
    """One opener for the files `_old_python` reads without the kit (#833's
    review), listed on its architecture page."""
    _write(tmp_path, '[run]\nticket_branch = "work/t-*"\n')
    (tmp_path / ".workflow").mkdir()
    (tmp_path / ".workflow/experience").write_text("new\n", encoding="utf-8")
    assert _old_python._profile_text(str(tmp_path)) == '[run]\nticket_branch = "work/t-*"\n'
    assert _old_python._experience_file(str(tmp_path)) == "new"
    opened = []

    def none(path, *a, **kw):
        opened.append(os.path.relpath(path, str(tmp_path)).replace(os.sep, "/"))

    monkeypatch.setattr(_old_python, "_open_file", none)
    assert _old_python._profile_text(str(tmp_path)) == ""
    assert _old_python._experience_file(str(tmp_path)) is None
    assert opened == [PROFILE.as_posix(), ".workflow/experience"]
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    assert "\n- `_open_file`: in `_old_python.py`," in page


# ---------- the changelog ----------


def test_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "a security problem in the guard" in notes.lower()

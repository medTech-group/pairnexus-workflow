"""The guard's read of the profile without the kit (#833): only a regular file.

Where the kit can't read the profile, the guard still reads two plain lines
of it as text: `run.ticket_branch` (`_old_python._ticket_branch`, which the CLI
uses too) and `ruleset` (`fallback._profile_text`). A profile path that isn't a
regular file (a pipe, or a symlink to one) is never opened: it reads as a
profile that can't be read, as a directory always has, so the guard answers at
once in an attended session as in a ticket session. An ordinary profile, or a
symlink to one, reads as before.

Seams: `workflow hook guard` through the entry point on this Python (the kit's
path) and through the old-Python fallback's own entry, each in a subprocess
with a timeout, so no case can hold up the suite; and the two readers in-process on regular files only."""

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
SECONDS = 20  # far above the guard's own budget

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


def _a_pipe(root, tmp_path):
    os.mkfifo(root / PROFILE)  # made here, never opened


def _a_link_to_a_pipe(root, tmp_path):
    target = tmp_path / "elsewhere"
    os.mkfifo(target)
    os.symlink(target, root / PROFILE)


MAKES = [pytest.param(_a_pipe, id="pipe"), pytest.param(_a_link_to_a_pipe, id="link-to-pipe")]


def _argv(path):
    if path == "kit":
        return [sys.executable, "-B", str(KIT / "scripts/workflow.py")]
    py = _old_python_binary()
    return [py, "-B", str(KIT / "scripts/workflow.py")] if py else [sys.executable, "-B", "-c", _SHIM, str(KIT / "scripts")]


PATHS = ["kit", "old-python"]


def _guard(path, root, event, role=None):
    """The hook's (exit code, decision or None, reason), run with a timeout."""
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


# ---------- the guard answers at once ----------


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("make", MAKES)
@pytest.mark.parametrize("branch", ["main", "claude/build-1"])
def test_an_attended_session_gets_the_fallback_at_once(tmp_path, path, make, branch):
    root = _project(tmp_path, branch)
    make(root, tmp_path)
    assert _guard(path, root, LS) == (0, None, "")
    code, decision, _ = _guard(path, root, PUSH)
    assert (code, decision) == (0, "ask")


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("make", MAKES)
def test_a_ticket_session_is_still_refused_at_once(tmp_path, path, make):
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


# ---------- the readers, on regular files ----------


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


def test_a_symlink_to_a_regular_profile_reads_as_before(tmp_path):
    real = tmp_path / "real.toml"
    real.write_text('ruleset = false\n[run]\nticket_branch = "work/t-*"\n', encoding="utf-8")
    (tmp_path / PROFILE).parent.mkdir(parents=True)
    os.symlink(real, tmp_path / PROFILE)
    assert _old_python._ticket_branch(str(tmp_path)) == "work/t-*"
    assert fallback.solo(tmp_path) is True


def test_a_directory_still_reads_as_unreadable(tmp_path):
    (tmp_path / PROFILE).mkdir(parents=True)
    assert _old_python._ticket_branch(str(tmp_path)) is None
    assert fallback.solo(tmp_path) is False


# ---------- the changelog ----------


def test_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "a security problem in the guard" in notes.lower()

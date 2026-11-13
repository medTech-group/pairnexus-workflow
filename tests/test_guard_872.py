"""#872: a security problem in the guard.

A project without the kit still reads as "not set up", and an ordinary project
is as before.

Seam: the guard's hook command (`vendor.hook_command`), run under `sh` in a
subprocess with a `timeout`, as Claude Code runs it, with WORKFLOW_ROLE unset
or set."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_guard_833 import GIT
from test_guard_no_python import _kit_at
from workflow import vendor

KIT = Path(__file__).resolve().parents[1]
SECONDS = 20
PUSH = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
READ = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
        "tool_input": {"file_path": "notes.md", "old_string": "a", "new_string": "b"}}
FOLDERS = [".claude", ".claude/workflow", ".claude/workflow/bin"]


def _as_anyone(argv):
    """`argv` run as an ordinary user would run it."""
    return (["unshare", "-U"] + argv) if os.geteuid() == 0 else argv


def _project(tmp_path, branch, kit=True):
    root = tmp_path / "proj"
    subprocess.run(GIT + ["init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(GIT + ["-C", str(root), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    if branch != "main":
        subprocess.run(GIT + ["-C", str(root), "checkout", "-q", "-b", branch], check=True)
    if kit:
        _kit_at(root / vendor.HOOK_TAG)
        (root / ".claude/workflow/profile.toml").write_text(
            '[project]\nrepo = "o/r"\nbase_branch = "main"\n\n[run]\nticket_branch = "claude/build-*"\n',
            encoding="utf-8")
    return root


@pytest.fixture
def shape(tmp_path):
    """A project in the shape the tests below need, put back after the test."""
    made = []

    def make(branch, folder=".claude/workflow"):
        root = _project(tmp_path, branch)
        os.chmod(root / folder, 0)
        made.append(root / folder)
        return root

    yield make
    for folder in made:
        os.chmod(folder, 0o755)


def _guard(root, event, role=None):
    """The hook command's (exit code, decision or None)."""
    env = {"PATH": os.environ["PATH"], "HOME": str(root), "CLAUDE_PROJECT_DIR": str(root)}
    if role is not None:
        env["WORKFLOW_ROLE"] = role
    p = subprocess.run(
        _as_anyone([shutil.which("sh"), "-c", vendor.hook_command("guard")]), input=json.dumps(dict(event, cwd=str(root))),
        capture_output=True, text=True, env=env, cwd=root, timeout=SECONDS,
    )
    if not p.stdout.strip():
        return p.returncode, None
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecisionReason"]
    return p.returncode, out["permissionDecision"]


# ---------- the shape ----------


@pytest.mark.parametrize("folder", FOLDERS)
def test_on_a_ticket_branch_every_tool_is_refused(shape, folder):
    """With WORKFLOW_ROLE unset, the default `run.ticket_branch` decides."""
    root = shape("claude/build-1", folder)
    assert _guard(root, PUSH) == (0, "deny")
    assert _guard(root, READ) == (0, "deny")


@pytest.mark.parametrize("folder", FOLDERS)
def test_on_another_branch_a_push_is_asked(shape, folder):
    root = shape("main", folder)
    assert _guard(root, PUSH) == (0, "ask")
    assert _guard(root, READ) == (0, "ask")


@pytest.mark.parametrize("role", ["attended", " Attended "])
def test_an_attended_session_is_asked(shape, role):
    root = shape("claude/build-1")
    assert _guard(root, PUSH, role) == (0, "ask")


@pytest.mark.parametrize("role", ["ticket", "conductor", "tikcet"])
def test_a_ticket_or_conductor_session_is_refused_every_tool(shape, role):
    root = shape("main")
    assert _guard(root, PUSH, role) == (0, "deny")
    assert _guard(root, {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "git checkout -- .claude/workflow"}}, role) == (0, "deny")


def test_a_detached_head_is_asked(shape):
    root = shape("claude/build-1")
    subprocess.run(GIT + ["-C", str(root), "checkout", "-q", "--detach"], check=True)
    assert _guard(root, PUSH) == (0, "ask")


# ---------- as before ----------


@pytest.mark.parametrize("branch", ["main", "claude/build-1"])
def test_a_project_without_the_kit_reads_as_not_set_up(tmp_path, branch):
    root = _project(tmp_path, branch, kit=False)
    assert _guard(root, PUSH) == (0, None)
    (root / ".claude").mkdir()
    assert _guard(root, PUSH) == (0, None)
    assert _guard(root, PUSH, "ticket") == (0, "deny")


def test_a_project_without_the_kit_still_lets_a_ticket_session_restore_it(tmp_path):
    root = _project(tmp_path, "main", kit=False)
    restore = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": "git checkout -- .claude/workflow"}}
    assert _guard(root, restore, "ticket") == (0, None)


def test_an_ordinary_project_is_decided_by_the_kit(tmp_path):
    root = _project(tmp_path, "claude/build-1")
    assert _guard(root, PUSH) == (0, "deny")
    root_main = _project(tmp_path / "other", "main")
    assert _guard(root_main, READ) == (0, None)


# ---------- the changelog ----------


def test_the_changelog_names_it_by_its_area_only():
    (note,) = [n for n in since_0110().split("\n\n**") if "(#872" in n.split("\n")[0]]
    assert note.lower().startswith("a security problem in the guard"), note
    for word in ("chmod", "000", "search", "permission", "unshare", "folder", "vendor.py"):
        assert word not in note.lower(), word

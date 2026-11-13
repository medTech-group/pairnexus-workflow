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

import pytest

from changelog_notes import entry, since_0110
from test_guard_833 import GIT
from test_guard_863 import VALID, _as_anyone, _project, shape  # noqa: F401 (shape is a fixture)
from test_guard_no_python import _bash, _decision
from workflow import vendor

SECONDS = 20
PUSH = _bash("git push origin main")
RESTORE = _bash("git checkout -- .claude/workflow")
EDIT = {"hook_event_name": "PreToolUse", "tool_name": "Edit",
        "tool_input": {"file_path": "notes.md", "old_string": "a", "new_string": "b"}}
FOLDERS = [".claude", ".claude/workflow", ".claude/workflow/bin"]
NAMED = VALID.replace("[project]\n", '[project]\nname = "notes"\n', 1)


def _guard(root, event, role=None, cwd=None):
    """The hook command's decision, or None when it prints nothing."""
    env = {"PATH": os.environ["PATH"], "HOME": str(root), "CLAUDE_PROJECT_DIR": str(root)}
    if role is not None:
        env["WORKFLOW_ROLE"] = role
    p = subprocess.run(
        _as_anyone([shutil.which("sh"), "-c", vendor.hook_command("guard")]), input=json.dumps(dict(event, cwd=str(root))),
        capture_output=True, text=True, env=env, cwd=cwd or root, timeout=SECONDS,
    )
    return _decision(p)


# ---------- the shape ----------


@pytest.mark.parametrize("folder", FOLDERS)
def test_on_a_ticket_branch_every_tool_is_refused(shape, folder):
    """With WORKFLOW_ROLE unset, the default `run.ticket_branch` decides."""
    root = shape("claude/build-1", folder, profile=NAMED, kit=True)
    assert _guard(root, PUSH) == "deny"
    assert _guard(root, EDIT) == "deny"


@pytest.mark.parametrize("folder", FOLDERS)
def test_on_another_branch_a_push_is_asked(shape, folder):
    root = shape("main", folder, profile=NAMED, kit=True)
    assert _guard(root, PUSH) == "ask"
    assert _guard(root, EDIT) == "ask"


@pytest.mark.parametrize("role", ["attended", " Attended "])
def test_an_attended_session_is_asked(shape, role):
    root = shape("claude/build-1", ".claude/workflow", profile=NAMED, kit=True)
    assert _guard(root, PUSH, role) == "ask"


@pytest.mark.parametrize("role", ["ticket", "conductor", "tikcet"])
def test_a_ticket_or_conductor_session_is_refused_every_tool(shape, role):
    root = shape("main", ".claude/workflow", profile=NAMED, kit=True)
    assert _guard(root, PUSH, role) == "deny"
    assert _guard(root, RESTORE, role) == "deny"


def test_a_detached_head_is_asked(shape):
    root = shape("claude/build-1", ".claude/workflow", profile=NAMED, kit=True)
    subprocess.run(GIT + ["-C", str(root), "checkout", "-q", "--detach"], check=True)
    assert _guard(root, PUSH) == "ask"


# ---------- as before ----------


@pytest.mark.parametrize("branch", ["main", "claude/build-1"])
def test_a_project_without_the_kit_reads_as_not_set_up(tmp_path, branch):
    root = _project(tmp_path, branch, profile=None)
    assert _guard(root, PUSH) is None
    (root / ".claude").mkdir()
    assert _guard(root, PUSH) is None
    assert _guard(root, PUSH, "ticket") == "deny"


def test_a_project_without_the_kit_still_lets_a_ticket_session_restore_it(tmp_path):
    root = _project(tmp_path, "main", profile=None)
    assert _guard(root, RESTORE, "ticket") is None


def test_an_ordinary_project_is_decided_by_the_kit(tmp_path):
    root = _project(tmp_path, "claude/build-1", profile=NAMED, kit=True)
    assert _guard(root, PUSH) == "deny"
    root_main = _project(tmp_path / "other", "main", profile=NAMED, kit=True)
    assert _guard(root_main, EDIT) is None


# ---------- the changelog ----------


def test_the_changelog_names_it_by_its_area_only():
    (line,) = [line for line in since_0110().splitlines() if "(#872" in line]
    assert line.lower().startswith("**a security problem in the guard"), line
    note = entry("#872, found in the review of #863's pull request")
    for word in ("chmod", "000", "search", "permission", "unshare", "folder", "link", "vendor.py"):
        assert word not in note.lower(), word

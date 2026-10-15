"""Kit 0.1.8: the hooks fail closed when python3 can't run the kit (#22)."""

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import _old_python, vendor

KIT = Path(__file__).resolve().parents[1]
BASH_PUSH = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
BASH_LS = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
EDIT = {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}


def _run(capsys, argv, event, env, cwd=None):
    stdin = event if isinstance(event, str) else json.dumps(event)
    code = _old_python.main(argv, stdin_text=stdin, env=env, version="3.9.6", cwd=cwd)
    return code, capsys.readouterr().out


def _decision(out):
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"]


def _repo(path, branch, ticket_branch=None):
    """A git repository on `branch` (with a commit, as roles.py needs) and,
    unless ticket_branch is False, the kit's profile."""
    git = ["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", "-b", branch, str(path)], check=True)
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"], check=True)
    if ticket_branch is not False:
        (path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
        body = f'[run]\nticket_branch = "{ticket_branch}"\n' if ticket_branch else "[run]\n"
        (path / ".claude/workflow/profile.toml").write_text(body)
    return path


@pytest.mark.parametrize("role", ["ticket", "conductor", "Ticket ", "tikcet"])
def test_old_python_guard_denies_every_tool_in_a_run(capsys, tmp_path, role):
    for event in (BASH_LS, EDIT, BASH_PUSH, "not json"):
        code, out = _run(capsys, ["hook", "guard"], event, {"WORKFLOW_ROLE": role}, tmp_path)
        assert code == 0 and _decision(out) == "deny", (role, event)
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        assert "3.11" in reason and "3.9.6" in reason


def test_old_python_guard_on_a_ticket_branch_denies_without_a_role(capsys, tmp_path):
    _repo(tmp_path, "claude/build-12-x")
    code, out = _run(capsys, ["hook", "guard"], BASH_LS, {}, tmp_path)
    assert _decision(out) == "deny"


def test_old_python_guard_reads_the_profiles_ticket_branch(capsys, tmp_path):
    _repo(tmp_path, "agents/t-1", "agents/*")
    code, out = _run(capsys, ["hook", "guard"], BASH_LS, {"CLAUDE_PROJECT_DIR": str(tmp_path)}, tmp_path)
    assert _decision(out) == "deny"
    _repo(tmp_path / "other", "claude/build-1", "agents/*")
    assert _run(capsys, ["hook", "guard"], BASH_LS, {}, tmp_path / "other") == (0, "")


def test_old_python_guard_takes_no_role_from_the_branch_without_a_profile(capsys, tmp_path):
    """As the CLI: no profile (plugin mode, a project without the kit), no branch role."""
    _repo(tmp_path, "claude/build-12-x", ticket_branch=False)
    assert _run(capsys, ["hook", "guard"], BASH_LS, {}, tmp_path) == (0, "")


def test_old_python_never_raises(capsys, tmp_path, monkeypatch):
    deep = "[" * 100000  # json raises RecursionError, not ValueError
    assert _run(capsys, ["hook", "guard"], deep, {}, tmp_path) == (0, "")
    code, out = _run(capsys, ["hook", "repair"], deep, {}, tmp_path)
    assert code == 0 and "systemMessage" in json.loads(out)

    def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(_old_python, "_hook", boom)
    code, out = _run(capsys, ["hook", "guard"], BASH_LS, {"WORKFLOW_ROLE": "ticket"}, tmp_path)
    assert code == 0 and _decision(out) == "deny"
    assert _run(capsys, ["hook", "guard"], BASH_LS, {}, tmp_path) == (0, "")


def test_old_python_parses_as_python_3_7():
    for f in (KIT / "scripts/workflow.py", KIT / "scripts/workflow/_old_python.py", KIT / "scripts/workflow/__init__.py"):
        ast.parse(f.read_text(), feature_version=(3, 7))


@pytest.mark.parametrize("env", [{}, {"WORKFLOW_ROLE": "attended"}])
def test_old_python_guard_in_an_attended_session_asks_before_a_push(capsys, tmp_path, env):
    for cmd in ("git push origin main", "cd x && git -C . push --force", "gh pr merge 3 --admin"):
        code, out = _run(capsys, ["hook", "guard"], {"tool_name": "Bash", "tool_input": {"command": cmd}}, env, tmp_path)
        assert code == 0 and _decision(out) == "ask", cmd
    for tool in ("mcp__github__merge_pull_request", "mcp__GitHub__push_files", "mcp__github__create_or_update_file"):
        code, out = _run(capsys, ["hook", "guard"], {"tool_name": tool, "tool_input": {}}, env, tmp_path)
        assert code == 0 and _decision(out) == "ask", tool
    assert _run(capsys, ["hook", "guard"], {"tool_name": "mcp__github__issue_read", "tool_input": {}}, env, tmp_path) == (0, "")
    for event in (BASH_LS, EDIT, "not json"):
        assert _run(capsys, ["hook", "guard"], event, env, tmp_path) == (0, ""), event


@pytest.mark.parametrize("role", [None, "ticket"])
def test_old_python_session_start_says_so(capsys, tmp_path, role):
    env = {"WORKFLOW_ROLE": role} if role else {}
    code, out = _run(capsys, ["hook", "repair"], {}, env, tmp_path)
    data = json.loads(out)
    assert code == 0 and "3.11" in data["systemMessage"] and "3.9.6" in data["systemMessage"]
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert ("refused" in ctx) == (role == "ticket")


@pytest.mark.parametrize("sub", ["gate", "context"])
def test_old_python_other_hooks_stay_quiet(capsys, tmp_path, sub):
    assert _run(capsys, ["hook", sub], {}, {"WORKFLOW_ROLE": "ticket"}, tmp_path) == (0, "")


def test_old_python_cli_use_still_says_what_it_needs(capsys, tmp_path):
    code = _old_python.main(["profile", "check"], stdin_text="", env={}, version="3.9.6", cwd=tmp_path)
    assert code == 1 and "3.11" in capsys.readouterr().err


def _old_python_binary():
    for cand in (os.environ.get("OLD_PYTHON"), shutil.which("python3.9")):
        if cand and Path(cand).exists():
            return cand
    found = sorted(Path.home().glob(".local/share/uv/python/cpython-3.9*/bin/python3.9"))
    return str(found[0]) if found else None


@pytest.mark.skipif(
    _old_python_binary() is None and not os.environ.get("CI"),
    reason="no Python 3.9 to run the entry point with (CI installs one, and fails without it)",
)
def test_the_entry_point_on_a_real_python_3_9(tmp_path):
    py = _old_python_binary()
    assert py, "set OLD_PYTHON to a Python 3.9"
    env = {"PATH": os.environ["PATH"], "WORKFLOW_ROLE": "ticket", "CLAUDE_PROJECT_DIR": str(tmp_path)}
    p = subprocess.run([py, "-B", str(KIT / "scripts/workflow.py"), "hook", "guard"], input=json.dumps(BASH_LS),
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert _decision(p.stdout) == "deny"
    env["WORKFLOW_ROLE"] = "attended"
    p = subprocess.run([py, "-B", str(KIT / "scripts/workflow.py"), "hook", "guard"], input=json.dumps(BASH_PUSH),
                       capture_output=True, text=True, env=env, cwd=tmp_path)
    assert p.returncode == 0 and _decision(p.stdout) == "ask"


# The vendored hook command when python3 itself is missing -------------------


def _no_python_path(tmp_path):
    """A PATH with sh, git, tr, printf and the like, but no python3."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sh", "tr", "sed", "head", "printf", "cat", "env", "git"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    return str(bindir)


def _vendored(tmp_path):
    cli = tmp_path / vendor.HOOK_TAG
    cli.parent.mkdir(parents=True)
    cli.write_text("raise SystemExit('should not run')\n")
    return tmp_path


@pytest.mark.parametrize("role", ["ticket", "conductor", "bogus", "atten ded"])
def test_without_python3_a_run_is_refused_every_tool(tmp_path, role):
    proj = _vendored(tmp_path)
    env = {"PATH": _no_python_path(tmp_path), "CLAUDE_PROJECT_DIR": str(proj), "WORKFLOW_ROLE": role}
    p = subprocess.run([shutil.which("sh"), "-c", vendor.hook_command("guard")], input=json.dumps(BASH_LS),
                       capture_output=True, text=True, env=env)
    assert p.returncode == 0
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "python3" in out["permissionDecisionReason"]


def test_without_python3_an_attended_session_is_told_at_the_start(tmp_path):
    proj = _vendored(tmp_path)
    env = {"PATH": _no_python_path(tmp_path), "CLAUDE_PROJECT_DIR": str(proj)}
    sh = shutil.which("sh")
    guard = subprocess.run([sh, "-c", vendor.hook_command("guard")], input="{}", capture_output=True, text=True, env=env)
    assert (guard.returncode, guard.stdout) == (0, "")
    start = subprocess.run([sh, "-c", vendor.hook_command("repair")], input="{}", capture_output=True, text=True, env=env)
    assert start.returncode == 0 and "python3" in json.loads(start.stdout)["systemMessage"]


@pytest.mark.skipif(
    _old_python_binary() is None and not os.environ.get("CI"),
    reason="no Python 3.9 to run the entry point with (CI installs one, and fails without it)",
)
def test_the_vendored_hook_on_a_real_python_3_9(tmp_path):
    """The hook command as a project's settings run it, with python3 a 3.9."""
    py = _old_python_binary()
    assert py, "set OLD_PYTHON to a Python 3.9"
    proj = tmp_path / "proj"
    shutil.copytree(KIT / "scripts/workflow", proj / ".claude/workflow/bin/workflow",
                    ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(KIT / "scripts/workflow.py", proj / ".claude/workflow/bin/workflow.py")
    path = _no_python_path(tmp_path)
    (Path(path) / "python3").symlink_to(py)
    sh = shutil.which("sh")
    env = {"PATH": path, "CLAUDE_PROJECT_DIR": str(proj), "WORKFLOW_ROLE": "conductor"}
    p = subprocess.run([sh, "-c", vendor.hook_command("guard")], input=json.dumps(EDIT),
                       capture_output=True, text=True, env=env, cwd=proj)
    assert p.returncode == 0 and _decision(p.stdout) == "deny", p.stderr
    p = subprocess.run([sh, "-c", vendor.hook_command("repair")], input="{}",
                       capture_output=True, text=True, env=env, cwd=proj)
    assert p.returncode == 0 and "3.11" in json.loads(p.stdout)["systemMessage"], p.stderr
    assert not list(proj.rglob("__pycache__"))


def _guard_sh(env, event=BASH_LS, cwd=None):
    return subprocess.run([shutil.which("sh"), "-c", vendor.hook_command("guard")], input=json.dumps(event),
                          capture_output=True, text=True, env=env, cwd=cwd)


@pytest.mark.parametrize("ticket_branch,branch", [(None, "claude/build-7-x"), ("agents/*", "agents/t-2")])
def test_without_python3_a_ticket_branch_is_refused_every_tool(tmp_path, ticket_branch, branch):
    proj = _vendored(_repo(tmp_path / "proj", branch, ticket_branch))
    p = _guard_sh({"PATH": _no_python_path(tmp_path), "CLAUDE_PROJECT_DIR": str(proj)})
    assert p.returncode == 0 and _decision(p.stdout) == "deny"


def test_without_python3_the_first_ticket_branch_line_counts(tmp_path):
    proj = _vendored(_repo(tmp_path / "proj", "agents/t-3", "agents/*"))
    with open(proj / ".claude/workflow/profile.toml", "a") as f:
        f.write('[other]\nticket_branch = "x/*"\n')
    p = _guard_sh({"PATH": _no_python_path(tmp_path), "CLAUDE_PROJECT_DIR": str(proj)})
    assert _decision(p.stdout) == "deny"


@pytest.mark.parametrize("sub", ["gate", "context"])
def test_without_python3_the_other_hooks_stay_quiet(tmp_path, sub):
    proj = _vendored(tmp_path / "proj")
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
    for path in (_no_python_path(tmp_path / "a"), _failing_python(tmp_path / "b", 0)):
        p = subprocess.run([shutil.which("sh"), "-c", vendor.hook_command(sub)], input="{}", capture_output=True,
                           text=True, env={"PATH": path, "CLAUDE_PROJECT_DIR": str(proj)})
        assert (p.returncode, p.stdout) == (0, ""), sub


def test_without_python3_another_branch_or_no_profile_is_left_alone(tmp_path):
    path = _no_python_path(tmp_path)
    for proj in (_repo(tmp_path / "a", "main"), _repo(tmp_path / "b", "claude/build-1", ticket_branch=False)):
        _vendored(proj)
        p = _guard_sh({"PATH": path, "CLAUDE_PROJECT_DIR": str(proj)})
        assert (p.returncode, p.stdout) == (0, ""), proj


def _failing_python(tmp_path, code):
    """A python3 that exits non-zero, as macOS's stub without the developer
    tools or a pyenv shim with no version does."""
    path = _no_python_path(tmp_path)
    fake = Path(path) / "python3"
    fake.write_text(f"#!/bin/sh\nexit {code}\n")
    fake.chmod(0o755)
    return path


@pytest.mark.parametrize("code", [1, 127])
def test_a_python3_that_fails_refuses_a_run_and_says_so(tmp_path, code):
    proj = _vendored(tmp_path / "proj")
    path = _failing_python(tmp_path, code)
    p = _guard_sh({"PATH": path, "CLAUDE_PROJECT_DIR": str(proj), "WORKFLOW_ROLE": "ticket"})
    assert p.returncode == 0 and _decision(p.stdout) == "deny"
    attended = _guard_sh({"PATH": path, "CLAUDE_PROJECT_DIR": str(proj)})
    assert (attended.returncode, attended.stdout) == (code, "")  # passed on, as the CLI's own errors are
    start = subprocess.run([shutil.which("sh"), "-c", vendor.hook_command("repair")], input="{}", capture_output=True,
                           text=True, env={"PATH": path, "CLAUDE_PROJECT_DIR": str(proj)})
    assert start.returncode == 0 and "python3" in json.loads(start.stdout)["systemMessage"]

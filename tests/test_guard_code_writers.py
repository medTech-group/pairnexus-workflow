"""#340 (spec #338): under `code_writers = "ticket"`, a session that doesn't
write code (#339's rule) is refused, never asked and in every permission
mode, a write to a code path: the file tools, the shell's writes the guard
places, `git apply` and `git am`, and PowerShell that names a code path.

Through `workflow hook guard`, run as Claude Code runs it (a JSON event on
stdin, the decision on stdout), in a temporary checkout whose profile names
the code paths. Every command here is data given to the hook; none is run."""

import io
import json
import os
import subprocess
import sys

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from workflow import cli

# The tests' repositories never see the developer's own git configuration.
pytestmark = pytest.mark.usefixtures("_no_user_git_config")

PROFILE = ".claude/workflow/profile.toml"
MODES = [None, "default", "acceptEdits", "plan", "auto", "bypassPermissions", "dontAsk"]
CODE = "src/app.py"


def _toml(code_writers="ticket", ticket_environment="workflow-ticket"):
    line = "" if code_writers is None else f'code_writers = "{code_writers}"\n'
    return (
        '[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n'
        "[guard]\n"
        f"{line}"
        'code_paths = ["src/**", "tests/**"]\n'
        'protected_paths = [".claude/**", ".github/workflows/**", "src/protected/**"]\n'
        "[run]\n"
        f'ticket_environment = "{ticket_environment}"\n'
        'conductor_environment = "workflow-conductor"\n'
    )


def _tree(root, code_writers="ticket", branch="feature", vendored=True, ticket_environment="workflow-ticket"):
    """A checkout on `branch` with code (`src/`, `tests/`), docs, a protected
    folder inside a code path, an ignored build folder and a tracked file
    `.gitignore` names."""
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    files = {
        PROFILE: _toml(code_writers, ticket_environment),
        CODE: "a = 1\n",
        "src/protected/keep.py": "k = 1\n",
        "tests/test_app.py": "def test_a():\n    pass\n",
        "docs/guide.md": "# Guide\n",
        ".gitignore": "src/build/\nsrc/gen.py\n",
        "fix.patch": "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-a = 1\n+a = 2\n",
        "docs.patch": "--- a/docs/guide.md\n+++ b/docs/guide.md\n@@ -1 +1 @@\n-# Guide\n+# The guide\n",
    }
    if vendored:
        files[".claude/workflow/lock.json"] = '{"kit_version": "0.1.16"}\n'
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "src/gen.py").write_text("g = 1\n")
    git(root, "add", "-A")
    git(root, "add", "-f", "src/gen.py")
    git(root, "commit", "-qm", "init")
    (root / "src/build").mkdir()
    (root / "src/build/out.py").write_text("o = 1\n")
    if branch != "main":
        git(root, "checkout", "-q", "-b", branch)
    return root


@pytest.fixture
def proj(tmp_path):
    return _tree(tmp_path / "proj")


def hook(monkeypatch, capsys, root, event, role=None, mode=None, cwd=None):
    """`workflow hook guard` with `event` on stdin: (decision, reason), the
    decision "allow" when the hook prints nothing."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    if role is None:
        monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    else:
        monkeypatch.setenv("WORKFLOW_ROLE", role)
    monkeypatch.chdir(root)
    event = {**event, "cwd": str(cwd or root)}
    if mode is not None:
        event["permission_mode"] = mode
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(event).encode()), encoding="utf-8"))
    assert cli.main(["hook", "guard"]) == 0
    out = capsys.readouterr().out
    if not out.strip():
        return "allow", ""
    h = json.loads(out)["hookSpecificOutput"]
    return h["permissionDecision"], h["permissionDecisionReason"]


def write(path, tool="Write"):
    if tool == "Write":
        return {"tool_name": "Write", "tool_input": {"file_path": path, "content": "x = 1\n"}}
    if tool == "Edit":
        return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": "a = 1", "new_string": "a = 2"}}
    if tool == "MultiEdit":
        return {"tool_name": "MultiEdit", "tool_input": {"file_path": path, "edits": [{"old_string": "a", "new_string": "b"}]}}
    return {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": path, "new_source": "x = 1"}}


def bash(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def powershell(command):
    return {"tool_name": "PowerShell", "tool_input": {"command": command}}


# A session that doesn't write code under "ticket": (WORKFLOW_ROLE, branch).
NOT_TICKET = {
    "attended": (None, "feature"),
    "attended by its role": ("attended", "feature"),
    "conductor": ("conductor", "feature"),
    "branch-only ticket session": (None, "claude/build-1"),
    "mistyped WORKFLOW_ROLE": ("tikcet", "feature"),
}


def _on(root, branch):
    if branch != "feature":
        git(root, "checkout", "-q", "-B", branch)


# ---------- the file tools ----------


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
@pytest.mark.parametrize("who", list(NOT_TICKET))
def test_a_code_write_is_refused_outside_ticket_sessions_in_every_mode(proj, monkeypatch, capsys, tool, who):
    role, branch = NOT_TICKET[who]
    _on(proj, branch)
    for mode in MODES:
        for path in (CODE, str(proj / CODE), "tests/test_new.py", "src/new/deep/mod.py"):
            d, why = hook(monkeypatch, capsys, proj, write(path, tool), role, mode)
            assert d == "deny", (who, mode, path, d, why)
            assert path.removeprefix(str(proj) + "/") in why and "code path" in why, why
            assert "src/**" in why or "tests/**" in why, why


@pytest.mark.parametrize("role", ["ticket", " Ticket ", "TICKET"])
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_a_ticket_session_writes_code(proj, monkeypatch, capsys, role, tool):
    _on(proj, "claude/build-1")
    for mode in MODES:
        assert hook(monkeypatch, capsys, proj, write(CODE, tool), role, mode)[0] == "allow", mode


@pytest.mark.parametrize("who", list(NOT_TICKET))
@pytest.mark.parametrize("path", ["docs/guide.md", "README.md", ".workflow/run/body.md", ".workflow/src/x.py", "src/protected/keep.py", ".claude/workflow/profile.toml"])
def test_what_isnt_code_decides_as_today(tmp_path, monkeypatch, capsys, who, path):
    """Docs, protected paths, `.workflow/` and a path that is both code and
    protected decide exactly as without `code_writers`; a branch-only or
    mistyped session, under "ticket", as an attended session does."""
    role, branch = NOT_TICKET[who]
    ticket = _tree(tmp_path / "ticket", "ticket", branch)
    absent = _tree(tmp_path / "absent", None, branch)
    as_attended = _tree(tmp_path / "attended", None, "feature")
    for mode in MODES:
        got = hook(monkeypatch, capsys, ticket, write(path), role, mode)
        if who in ("branch-only ticket session", "mistyped WORKFLOW_ROLE"):
            today = hook(monkeypatch, capsys, as_attended, write(path), None, mode)
        else:
            today = hook(monkeypatch, capsys, absent, write(path), role, mode)
        assert got[0] == today[0], (who, path, mode, got, today)


def test_a_branch_only_ticket_session_may_write_a_protected_path_under_ticket(tmp_path, monkeypatch, capsys):
    under = _tree(tmp_path / "ticket", "ticket", "claude/build-1")
    before = _tree(tmp_path / "absent", None, "claude/build-1")
    assert hook(monkeypatch, capsys, under, write(".claude/workflow/profile.toml"))[0] == "allow"
    assert hook(monkeypatch, capsys, under, write(".github/workflows/ci.yml"))[0] == "allow"
    # Today, and still with WORKFLOW_ROLE=ticket, a ticket session may not.
    assert hook(monkeypatch, capsys, before, write(".claude/workflow/profile.toml"))[0] == "deny"
    assert hook(monkeypatch, capsys, under, write(".claude/workflow/profile.toml"), "ticket")[0] == "deny"


def test_a_branch_only_session_may_switch_branches_under_ticket(tmp_path, monkeypatch, capsys):
    under = _tree(tmp_path / "ticket", "ticket", "claude/build-1")
    before = _tree(tmp_path / "absent", None, "claude/build-1")
    assert hook(monkeypatch, capsys, under, bash("git switch main"))[0] == "allow"
    assert hook(monkeypatch, capsys, before, bash("git switch main"))[0] == "deny"


def test_a_branch_only_or_mistyped_session_is_named_as_not_a_ticket_session(proj, monkeypatch, capsys):
    _on(proj, "claude/build-1")
    d, why = hook(monkeypatch, capsys, proj, write(CODE))
    assert d == "deny" and why.startswith("[workflow guard, attended session"), why
    assert "only by its branch, `claude/build-1`, matching `claude/build-*`" in why and "isn't a ticket session" in why, why
    d, why = hook(monkeypatch, capsys, proj, write(CODE), "tikcet")
    assert d == "deny" and why.startswith("[workflow guard, attended session"), why
    assert "WORKFLOW_ROLE='tikcet' isn't a role" in why and "treated as ticket" not in why, why


def test_the_base_branchs_ticket_holds_over_a_loosened_working_tree(proj, monkeypatch, capsys):
    git(proj, "update-ref", "refs/remotes/origin/main", "main")
    (proj / PROFILE).write_text(_toml("any"))
    d, why = hook(monkeypatch, capsys, proj, write(CODE))
    assert d == "deny" and "code path" in why, why


# ---------- Claude Code's worktrees and other clones ----------


def test_a_code_path_in_a_claude_code_worktree_is_refused(proj, monkeypatch, capsys):
    wt = proj / ".claude/worktrees/side"
    git(proj, "worktree", "add", "-q", "-b", "side", str(wt))
    for path in (str(wt / CODE), ".claude/worktrees/side/src/app.py", str(wt / "tests/test_x.py")):
        d, why = hook(monkeypatch, capsys, proj, write(path))
        assert d == "deny" and "code path" in why, (path, why)
    # Matched from the worktree's own top level: its docs, its own `.workflow/`
    # and its protected paths aren't code.
    for path in (str(wt / "docs/guide.md"), str(wt / ".workflow/x.py"), str(wt / "src/protected/keep.py")):
        assert hook(monkeypatch, capsys, proj, write(path))[0] == "allow", path
    # Ignored files are judged by the worktree's own `.gitignore`.
    (wt / ".gitignore").write_text("src/build/\nsrc/local/\n")
    assert hook(monkeypatch, capsys, proj, write(str(wt / "src/local/a.py")))[0] == "allow"
    assert hook(monkeypatch, capsys, proj, write(str(proj / "src/local/a.py")))[0] == "deny"
    # From inside the worktree, as a session working there writes.
    d, why = hook(monkeypatch, capsys, proj, write(CODE), cwd=wt)
    assert d == "deny", why
    d, why = hook(monkeypatch, capsys, proj, bash("echo x > src/app.py"), cwd=wt)
    assert d == "deny", why


def test_a_file_in_a_clone_of_another_repository_is_allowed(proj, tmp_path, monkeypatch, capsys):
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    (other / "src").mkdir()
    (other / CODE).write_text("a = 1\n")
    for event in (write(str(other / CODE)), bash(f"echo x > {other / CODE}"), bash(f"sed -i s/a/b/ {other / CODE}")):
        assert hook(monkeypatch, capsys, proj, event)[0] == "allow", event
    # Nor a repository of its own inside the worktrees' folder.
    inside = proj / ".claude/worktrees/clone"
    inside.mkdir(parents=True)
    git(inside, "init", "-q", "-b", "main")
    assert hook(monkeypatch, capsys, proj, write(str(inside / CODE)))[0] == "allow"


# ---------- Bash ----------

REFUSED_BASH = [
    "echo x > src/app.py",
    "echo x >> src/app.py",
    "printf 'x' | tee src/app.py",
    "sed -i s/a/b/ src/app.py",
    "perl -pi -e s/a/b/ src/app.py",
    "rm src/app.py",
    "rm -rf src",
    "mv src/app.py docs/",
    "mv docs/guide.md src/guide.py",
    "cp docs/guide.md tests/",
    "touch src/new.py",
    "git rm src/app.py",
    "git mv src/app.py src/b.py",
    "git apply fix.patch",
    "git am fix.patch",
    "cat fix.patch | git apply",
    "git apply < fix.patch",
    "setsid git apply fix.patch",
    "cd src && echo x > app.py",
    "cd docs && echo x > ../src/app.py",
    "bash -c 'echo x > src/app.py'",
    "echo ok; echo x > src/new.py",
    "find src -name '*.py' -delete",
]


@pytest.mark.parametrize("command", REFUSED_BASH)
@pytest.mark.parametrize("who", ["attended", "conductor", "branch-only ticket session", "mistyped WORKFLOW_ROLE"])
def test_a_shell_write_to_a_code_path_is_refused(proj, monkeypatch, capsys, command, who):
    role, branch = NOT_TICKET[who]
    _on(proj, branch)
    for mode in (None, "bypassPermissions"):
        d, why = hook(monkeypatch, capsys, proj, bash(command), role, mode)
        assert d == "deny" and "code path" in why, (command, who, d, why)


ALLOWED_BASH = [
    # Not code.
    "echo x > docs/new.md",
    "sed -i s/G/g/ docs/guide.md",
    "rm -r src/build",
    "rm src/build/out.py",
    "echo x > src/build/new.py",
    "echo x > .workflow/notes.md",
    "git apply docs.patch",
    "git apply --check fix.patch",
    "find . -name '*.pyc' -delete",
    # Targets the guard can't place: left to the commit and push rule.
    "cd $SOMEWHERE && echo x > app.py",
    "python3 -c \"open('src/app.py', 'w').write('x')\"",
    # Git checking out committed content.
    "git switch -c other",
    "git checkout main",
    "git checkout main -- src/app.py",
    "git restore src/app.py",
    "git restore --source main src",
    "git pull",
    "git merge origin/main",
    "git reset --hard HEAD",
    "git stash",
    "git stash pop",
    "git cherry-pick abc123",
    "git revert abc123",
    "git worktree add ../elsewhere",
    # Reading and running code.
    "cat src/app.py",
    "python3 src/app.py",
    "python3 -m pytest tests -q",
    "grep -rn a src",
]


@pytest.mark.parametrize("command", ALLOWED_BASH)
@pytest.mark.parametrize("who", ["attended", "conductor", "branch-only ticket session", "mistyped WORKFLOW_ROLE"])
def test_what_a_shell_command_does_without_writing_code_goes_through(proj, monkeypatch, capsys, command, who):
    role, branch = NOT_TICKET[who]
    _on(proj, branch)
    d, why = hook(monkeypatch, capsys, proj, bash(command), role)
    assert "code path" not in why, (command, who, why)
    if who != "conductor" or not command.startswith("git switch"):
        assert d == "allow", (command, who, why)


def test_monitor_is_read_as_bash(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, {"tool_name": "Monitor", "tool_input": {"command": "echo x > src/app.py"}})
    assert d == "deny" and "code path" in why, why
    assert hook(monkeypatch, capsys, proj, {"tool_name": "Monitor", "tool_input": {"command": "python3 -m pytest tests"}})[0] == "allow"


def test_a_shell_write_to_a_path_both_code_and_protected_decides_as_today(proj, monkeypatch, capsys):
    for role in (None, "conductor"):
        assert hook(monkeypatch, capsys, proj, bash("echo x > src/protected/keep.py"), role)[0] == "allow", role


def test_git_clean_judged_by_the_untracked_files_it_removes(proj, monkeypatch, capsys):
    # Nothing untracked but ignored files: nothing it removes is code.
    for command in ("git clean -fd", "git clean -fdx", "git clean -fdX", "git clean -n", "git clean -fdx src"):
        assert hook(monkeypatch, capsys, proj, bash(command))[0] == "allow", command
    (proj / "src/new.py").write_text("n = 1\n")  # untracked, not ignored: code
    for command in ("git clean -fd", "git clean -fdx", "git clean -f src"):
        d, why = hook(monkeypatch, capsys, proj, bash(command))
        assert d == "deny" and "src/new.py" in why, (command, why)
    for command in ("git clean -fdX", "git clean -nd", "git clean -fd docs"):
        assert hook(monkeypatch, capsys, proj, bash(command))[0] == "allow", command


def test_a_find_limited_by_name_reaches_code_in_a_matching_folder(proj, monkeypatch, capsys):
    (proj / "src/subpkg").mkdir()
    (proj / "src/subpkg/m.py").write_text("m = 1\n")
    git(proj, "add", "src/subpkg/m.py")
    d, why = hook(monkeypatch, capsys, proj, bash("find src -name 'sub*' -exec rm -rf {} +"))
    assert d == "deny" and "src/subpkg/m.py" in why, why
    assert hook(monkeypatch, capsys, proj, bash("find src -name 'nothing*' -exec rm -rf {} +"))[0] == "allow"


def test_removing_a_directory_above_the_project_is_refused(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, bash("rm -rf .."))
    assert d == "deny" and "code path" in why, why


def test_git_apply_is_judged_in_the_checkout_it_runs_in(proj, tmp_path, monkeypatch, capsys):
    other = tmp_path / "other"
    other.mkdir()
    git(other, "init", "-q", "-b", "main")
    (other / "src").mkdir()
    (other / CODE).write_text("a = 1\n")
    for command in (f"cd {other} && git apply {proj}/fix.patch", f"git -C {other} apply {proj}/fix.patch"):
        assert hook(monkeypatch, capsys, proj, bash(command))[0] == "allow", command
    wt = proj / ".claude/worktrees/side"
    git(proj, "worktree", "add", "-q", "-b", "side", str(wt))
    d, why = hook(monkeypatch, capsys, proj, bash(f"git apply {proj}/fix.patch"), cwd=wt)
    assert d == "deny" and "in the worktree `.claude/worktrees/side`" in why, why
    d, why = hook(monkeypatch, capsys, proj, bash("git -C .claude/worktrees/side apply ../../../fix.patch"))
    assert d == "deny" and "in the worktree `.claude/worktrees/side`" in why, why
    assert why.startswith("[workflow guard, attended session] this writes the code path `src/app.py`"), why


def test_a_shell_code_write_is_refused_even_after_an_ask(proj, monkeypatch, capsys):
    """An earlier part of the command that is asked never hides a code write."""
    git(proj, "remote", "add", "origin", str(proj))
    d, why = hook(monkeypatch, capsys, proj, bash("git push origin main; echo x > src/app.py"))
    assert d == "deny" and "code path" in why, why


def test_the_conductors_shell_code_write_is_refused(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, bash("rm src/app.py"), "conductor")
    assert d == "deny" and "code path" in why and "conductor writes no code" in why, why


# ---------- PowerShell ----------


@pytest.mark.parametrize(
    "command",
    ["Set-Content -Path src\\app.py -Value x", "Get-Content SRC\\App.py", "python .\\src\\app.py", "Remove-Item tests", f"Get-Content '{KIT}/x' ; type src/new.ps1"],
)
@pytest.mark.parametrize("who", ["attended", "conductor", "branch-only ticket session", "mistyped WORKFLOW_ROLE"])
def test_powershell_naming_a_code_path_is_refused(proj, monkeypatch, capsys, command, who):
    role, branch = NOT_TICKET[who]
    _on(proj, branch)
    for mode in (None, "default", "bypassPermissions"):
        d, why = hook(monkeypatch, capsys, proj, powershell(command), role, mode)
        assert d == "deny" and "code path" in why and "run it through Bash" in why, (command, mode, why)


def test_powershell_run_from_a_code_folder(proj, monkeypatch, capsys):
    """Words that name nothing there aren't paths: run from `src/`, `Get-Date` decides as today."""
    assert hook(monkeypatch, capsys, proj, powershell("Get-Date"), cwd=proj / "src") == ("allow", "")
    d, why = hook(monkeypatch, capsys, proj, powershell("Set-Content app.py x"), cwd=proj / "src")
    assert d == "deny" and "`src/app.py`" in why, why


def test_powershell_parameter_joined_with_a_colon(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, powershell("Set-Content -Path:src\\app.py -Value x"))
    assert d == "deny" and "run it through Bash" in why, why


def test_powershell_naming_an_absolute_code_path_is_refused(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, powershell(f"Get-Content {proj}\\src\\app.py".replace("/", "\\")))
    assert d == "deny" and "run it through Bash" in why, why


def test_powershell_naming_no_code_path_decides_as_today(tmp_path, monkeypatch, capsys):
    ticket = _tree(tmp_path / "ticket", "ticket")
    absent = _tree(tmp_path / "absent", None)
    for command in ("Get-Content docs\\guide.md", "git push origin feature", "Get-ChildItem", "Get-Content src\\protected\\keep.py"):
        for role in (None, "conductor"):
            assert hook(monkeypatch, capsys, ticket, powershell(command), role) == hook(monkeypatch, capsys, absent, powershell(command), role), command


# ---------- ignored files ----------


def test_ignored_files_judged_in_their_checkout(proj, monkeypatch, capsys):
    # An untracked file git ignores isn't code; a tracked one is, whatever `.gitignore` says.
    assert hook(monkeypatch, capsys, proj, write("src/build/out.py"))[0] == "allow"
    assert hook(monkeypatch, capsys, proj, bash("rm -r src/build"))[0] == "allow"
    d, why = hook(monkeypatch, capsys, proj, write("src/gen.py"))
    assert d == "deny" and "src/gen.py" in why, why
    assert hook(monkeypatch, capsys, proj, bash("rm src/gen.py"))[0] == "deny"
    # A tracked file inside an ignored folder is code too.
    git(proj, "add", "-f", "src/build/out.py")
    assert hook(monkeypatch, capsys, proj, bash("rm -r src/build"))[0] == "deny"


# ---------- the refusal's wording ----------


def test_the_refusal_in_a_run_set_up(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, write(CODE))
    assert d == "deny"
    assert "`src/app.py` is a code path (src/**)" in why, why
    assert 'code_writers = "ticket"' in why and "`WORKFLOW_ROLE=ticket`" in why, why
    assert "conductor run" in why and "**Run it unattended**" in why, why
    assert "**Set up unattended runs**" not in why, why
    assert "change `guard.code_writers` in a pull request" in why, why


def test_the_refusal_with_no_ticket_environment(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path / "proj", ticket_environment="")
    d, why = hook(monkeypatch, capsys, root, write(CODE))
    assert d == "deny"
    assert "**Set up unattended runs**" in why and "conductor run" in why, why
    assert "change `guard.code_writers` in a pull request" in why, why


def test_the_refusal_in_plugin_mode(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path / "proj", vendored=False)
    d, why = hook(monkeypatch, capsys, root, write(CODE))
    assert d == "deny"
    assert "on your own computer" in why and "`WORKFLOW_ROLE=ticket`" in why, why
    assert "conductor run" not in why and "**Set up unattended runs**" not in why, why
    assert "change `guard.code_writers` in a pull request" in why, why


def _run_body(root, conductor_fixes):
    from workflow import state as state_mod

    s = state_mod.empty({"conductor_fixes": conductor_fixes})
    body = "Run.\n\n" + state_mod.BEGIN + "\n```json\n" + json.dumps(s) + "\n```\n" + state_mod.END + "\n"
    (root / ".workflow/run").mkdir(parents=True, exist_ok=True)
    (root / ".workflow/run/body.md").write_text(body)


def test_the_conductors_refusal_names_its_own_way(proj, monkeypatch, capsys):
    d, why = hook(monkeypatch, capsys, proj, write(CODE), "conductor")
    assert d == "deny" and "the conductor writes no code" in why, why
    assert "`workflow:infra`" in why and "`for_owner`" in why, why  # the charter unread: both ways
    assert "Run it unattended" not in why and "guard.code_writers" not in why, why
    _run_body(proj, True)
    d, why = hook(monkeypatch, capsys, proj, write(CODE), "conductor")
    assert "`workflow:infra`" in why and "`for_owner`" not in why, why
    _run_body(proj, False)
    d, why = hook(monkeypatch, capsys, proj, write(CODE), "conductor")
    assert "`for_owner`" in why and "`workflow:infra`" not in why, why


# ---------- GitHub ----------


def test_github_and_the_mcp_file_tools_decide_as_today(tmp_path, monkeypatch, capsys):
    ticket = _tree(tmp_path / "ticket", "ticket")
    absent = _tree(tmp_path / "absent", None)
    events = [
        {"tool_name": "mcp__github__create_or_update_file", "tool_input": {"owner": "acme", "repo": "demo", "path": CODE, "branch": "feature", "content": "x", "message": "m"}},
        {"tool_name": "mcp__github__push_files", "tool_input": {"owner": "acme", "repo": "demo", "branch": "feature", "files": [{"path": CODE, "content": "x"}], "message": "m"}},
        {"tool_name": "mcp__github__delete_file", "tool_input": {"owner": "acme", "repo": "demo", "path": CODE, "branch": "feature", "message": "m"}},
        bash("gh api -X PUT repos/acme/demo/contents/src/app.py -f message=m -f content=eA== -f branch=feature"),
    ]
    for event in events:
        for role in (None, "conductor", "ticket"):
            got = hook(monkeypatch, capsys, ticket, event, role)
            assert got == hook(monkeypatch, capsys, absent, event, role), (event, role)
        assert hook(monkeypatch, capsys, ticket, event)[0] == "allow", event


# ---------- under "any" and unanswered ----------

TODAY = [
    (write(CODE), None, "allow"),
    (write(CODE), "conductor", "allow"),
    (write(".claude/workflow/profile.toml"), None, "allow"),
    (bash("echo x > src/app.py"), None, "allow"),
    (bash("rm -rf src"), "conductor", "allow"),
    (bash("git apply fix.patch"), None, "allow"),
    (powershell("Get-Content src\\app.py"), None, "allow"),
    (powershell("Get-Content src\\app.py"), "conductor", "deny"),
]


@pytest.mark.parametrize("code_writers", ["any", None])
def test_any_and_unanswered_never_refuse_a_code_write(tmp_path, monkeypatch, capsys, code_writers):
    root = _tree(tmp_path / "proj", code_writers)
    wt = root / ".claude/worktrees/side"
    git(root, "worktree", "add", "-q", "-b", "side", str(wt))
    events = [bash(c) for c in REFUSED_BASH] + [write(CODE, t) for t in ("Write", "Edit", "MultiEdit", "NotebookEdit")]
    events += [powershell("Set-Content -Path src\\app.py -Value x"), write(str(wt / CODE))]
    for event in events:
        for role in (None, "conductor", "tikcet"):
            d, why = hook(monkeypatch, capsys, root, event, role)
            assert "code path" not in why and "code_writers" not in why, (event, role, why)
        assert hook(monkeypatch, capsys, root, event)[0] in ("allow", "ask"), event


@pytest.mark.parametrize("code_writers", ["any", None])
def test_any_and_unanswered_decide_as_today(tmp_path, monkeypatch, capsys, code_writers):
    root = _tree(tmp_path / "proj", code_writers)
    for event, role, expected in TODAY:
        d, why = hook(monkeypatch, capsys, root, event, role)
        assert d == expected and "code path" not in why, (event, role, d, why)
    # A branch-only ticket session keeps a ticket session's rules.
    _on(root, "claude/build-1")
    d, why = hook(monkeypatch, capsys, root, write(".claude/workflow/profile.toml"))
    assert d == "deny" and "protected path" in why and why.startswith("[workflow guard, ticket session"), why
    d, why = hook(monkeypatch, capsys, root, write(CODE), "tikcet")
    assert d == "allow", why


def test_the_hook_as_a_process(proj):
    """The same refusal from `workflow hook guard` started as Claude Code starts it."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proj)}
    env.pop("WORKFLOW_ROLE", None)
    event = {**write(CODE), "cwd": str(proj), "permission_mode": "bypassPermissions"}
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "hook", "guard"], input=json.dumps(event), capture_output=True, text=True, cwd=proj, env=env)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "code path" in out["permissionDecisionReason"]


# ---------- docs ----------


def test_enforcement_doc_lists_the_rule_and_its_limits():
    doc = (KIT / "docs/enforcement.md").read_text()
    assert 'code_writers = "ticket"' in doc
    for phrase in ("code path", "refused, never asked", "`.workflow/`", "git ignores", "Claude Code's worktrees", "run it through Bash", "seatbelt"):
        assert phrase in doc, phrase


def test_changelog_note():
    notes = since_0110()
    assert "#340" in notes and "code path" in notes

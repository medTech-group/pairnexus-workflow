"""#342: under `code_writers = "ticket"`, the can't-decide fallbacks treat a
session that is a ticket session only by its branch, or by a mistyped
`WORKFLOW_ROLE`, as a planning session, rather than refusing it every tool.

Through `workflow hook guard` with the guard made to fail or run past its
budget (in-process, as tests/test_guard_cant_decide.py does), the old-Python
fallback's own entry, and the vendored hook command run under `sh` with
`python3` missing and failing (as tests/test_guard_no_python.py does).
"""

import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import copy_kit_package
from workflow import _old_python, cli, fallback, vendor
from workflow.profile import plain_code_writers

KIT = Path(__file__).resolve().parents[1]

PUSH = {"tool_name": "Bash", "tool_input": {"command": "git push origin claude/build-1"}, "permission_mode": "default"}
WRITE = {"tool_name": "Write", "tool_input": {"file_path": "scripts/app.py", "content": "x = 1\n"}, "permission_mode": "default"}
VALID = '[project]\nname = "demo"\nrepo = "acme/demo"\n'
INVALID = "[project]\nname = 1\n"  # name must be a string
UNPARSED = "[project\n"  # not TOML at all
TICKET = '[guard]\ncode_writers = "ticket"\n'
ANY = '[guard]\ncode_writers = "any"\n'
SOLO = "ruleset = false\n"  # under [project]

# (the session, WORKFLOW_ROLE (None: unset), the branch it is on)
BRANCH_ONLY = ("branch-only", None, "claude/build-1")
MISTYPED = ("mistyped", " Tikcet ", "feature")
TICKET_ROLE = ("ticket", "ticket", "claude/build-1")
PLANNING = [BRANCH_ONLY, MISTYPED]
# (the working tree's profile, the base's) where nothing makes them planning sessions
NOT_TICKET = {"any": (VALID + ANY, None), "absent": (VALID, None), "any on the base": (VALID, VALID + ANY)}
# Every session that keeps today's fallback: WORKFLOW_ROLE=ticket under any answer,
# and the branch-only and mistyped ones under "any" or with no answer.
STILL_REFUSED = [(TICKET_ROLE, "ticket")] + [(s, a) for s in [TICKET_ROLE] + PLANNING for a in NOT_TICKET]


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          check=True, capture_output=True, text=True).stdout


def _project(root, tree, base=None, branch="claude/build-1"):
    """A checkout at `root` on `branch`, its profile `tree`, and with `base` the
    profile on `origin/main` as last fetched."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    profile = root / ".claude/workflow/profile.toml"
    if base is not None:
        profile.write_text(base)
        _git(root, "add", ".claude/workflow/profile.toml")
        _git(root, "commit", "-qm", "base")
        _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    else:
        _git(root, "commit", "-q", "--allow-empty", "-m", "x")
    if branch != "main":
        _git(root, "checkout", "-qb", branch)
    profile.write_text(tree)
    return root


def _rule_placed(where, tree=VALID, base=VALID):
    """(the working tree's profile, the base's) with the ticket line in `where`."""
    return (tree + TICKET, None) if where == "tree" else (tree, base + TICKET)


def _answer(answer):
    return (VALID + TICKET, None) if answer == "ticket" else NOT_TICKET[answer]


# Through `workflow hook guard` ------------------------------------------------


def _hook(monkeypatch, capsys, root, failure, event, role):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    if role is None:
        monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    else:
        monkeypatch.setenv("WORKFLOW_ROLE", role)
    monkeypatch.chdir(root)
    if failure == "error":
        def boom(*a, **k):
            raise RuntimeError("guard-broke-here")

        monkeypatch.setattr(cli.guard_mod, "decide", boom)
    elif failure == "budget":
        def slow(*a, **k):
            raise cli._OverBudget()  # the guard's time ran out while it decided

        monkeypatch.setattr(cli.guard_mod, "decide", slow)
    text = json.dumps(event) + (" }trailing" if failure == "malformed" else "")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode()), encoding="utf-8"))
    assert cli.main(["hook", "guard"]) == 0
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out.strip() else None


def _tree_for(failure, tree):
    return tree.replace(VALID, INVALID) if failure == "invalid" else tree


@pytest.mark.parametrize("failure", ["error", "budget", "invalid", "malformed"])
@pytest.mark.parametrize("where", ["tree", "base"])
@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_a_branch_only_or_mistyped_session_gets_a_planning_sessions_fallback(tmp_path, monkeypatch, capsys, failure, where, session, role, branch):
    # With the line only in the base's, the base's profile doesn't parse when the
    # working tree's is invalid: nothing but the plain line can be read.
    tree, base = _rule_placed(where, base=UNPARSED if failure == "invalid" else VALID)
    root = _project(tmp_path / "proj", _tree_for(failure, tree), base, branch)
    out = _hook(monkeypatch, capsys, root, failure, PUSH, role)
    assert out and out["permissionDecision"] == "ask", (session, out)
    assert "planning session" in out["permissionDecisionReason"] and "guard isn't working" in out["permissionDecisionReason"]
    assert _hook(monkeypatch, capsys, root, failure, WRITE, role) is None, session


@pytest.mark.parametrize("failure", ["error", "budget", "invalid"])
@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_its_push_is_refused_where_nobody_is_asked(tmp_path, monkeypatch, capsys, failure, session, role, branch):
    tree, base = _rule_placed("tree")
    root = _project(tmp_path / "proj", _tree_for(failure, tree), base, branch)
    out = _hook(monkeypatch, capsys, root, failure, dict(PUSH, permission_mode="dontAsk"), role)
    assert out["permissionDecision"] == "deny" and "switch the permission mode" in out["permissionDecisionReason"]


@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_in_solo_mode_a_check_past_the_budget_is_refused_whatever_the_tool(tmp_path, monkeypatch, capsys, session, role, branch):
    root = _project(tmp_path / "proj", VALID + SOLO + TICKET, None, branch)
    for event in (PUSH, WRITE):
        out = _hook(monkeypatch, capsys, root, "budget", event, role)
        assert out["permissionDecision"] == "deny" and "ran out of time" in out["permissionDecisionReason"], event
        assert "planning session" in out["permissionDecisionReason"]
    out = _hook(monkeypatch, capsys, root, "error", PUSH, role)
    assert out["permissionDecision"] == "deny" and "solo mode" in out["permissionDecisionReason"]
    assert _hook(monkeypatch, capsys, root, "error", WRITE, role) is None


@pytest.mark.parametrize("failure", ["error", "budget", "invalid", "malformed"])
@pytest.mark.parametrize("session_answer", STILL_REFUSED, ids=lambda c: f"{c[0][0]}-{c[1]}")
def test_the_rest_are_still_refused_every_tool(tmp_path, monkeypatch, capsys, failure, session_answer):
    (session, role, branch), answer = session_answer
    tree, base = _answer(answer)
    root = _project(tmp_path / "proj", _tree_for(failure, tree), base, branch)
    for event in (PUSH, WRITE):
        out = _hook(monkeypatch, capsys, root, failure, event, role)
        assert out and out["permissionDecision"] == "deny", (session, answer, event, out)
        assert "planning session" not in out["permissionDecisionReason"]


def test_workflow_role_ticket_is_refused_with_the_line_only_on_the_base(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path / "proj", *_rule_placed("base"))
    for failure in ("error", "budget"):
        assert _hook(monkeypatch, capsys, root, failure, WRITE, "ticket")["permissionDecision"] == "deny", failure


def test_a_failure_outside_the_guard_takes_the_planning_fallback_too(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path / "proj", VALID + TICKET)

    def boom(*a, **k):
        raise RuntimeError("disk-went-away")

    monkeypatch.setattr(cli, "_hook_guard", boom)
    out = _hook(monkeypatch, capsys, root, None, PUSH, None)
    assert out["permissionDecision"] == "ask" and "disk-went-away" in out["permissionDecisionReason"]
    assert _hook(monkeypatch, capsys, root, None, WRITE, None) is None
    assert _hook(monkeypatch, capsys, root, None, WRITE, "ticket")["permissionDecision"] == "deny"


# The old-Python fallback's own entry ------------------------------------------


def _old(capsys, root, event, role):
    env = {"CLAUDE_PROJECT_DIR": str(root)}
    if role is not None:
        env["WORKFLOW_ROLE"] = role
    assert _old_python.main(["hook", "guard"], stdin_text=json.dumps(event), env=env, version="3.9.6", cwd=root) == 0
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out.strip() else None


@pytest.mark.parametrize("where", ["tree", "base"])
@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_old_python_gives_them_a_planning_sessions_fallback(tmp_path, capsys, where, session, role, branch):
    root = _project(tmp_path / "proj", *_rule_placed(where), branch=branch)
    out = _old(capsys, root, PUSH, role)
    assert out["permissionDecision"] == "ask" and "3.9.6" in out["permissionDecisionReason"], session
    assert _old(capsys, root, WRITE, role) is None


@pytest.mark.parametrize("session_answer", STILL_REFUSED, ids=lambda c: f"{c[0][0]}-{c[1]}")
def test_old_python_keeps_refusing_the_rest(tmp_path, capsys, session_answer):
    (session, role, branch), answer = session_answer
    root = _project(tmp_path / "proj", *_answer(answer), branch=branch)
    for event in (PUSH, WRITE):
        assert _old(capsys, root, event, role)["permissionDecision"] == "deny", (session, answer, event)


# The hook command without a working python3 ------------------------------------


def _path(tmp_path, kind):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sh", "tr", "sed", "awk", "head", "printf", "cat", "env", "git"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    if kind == "failing":
        (bindir / "python3").write_text("#!/bin/sh\nexit 1\n")
        (bindir / "python3").chmod(0o755)
    return str(bindir)


def _shell(tmp_path, kind, tree, base, branch):
    root = _project(tmp_path / "proj", tree, base, branch)
    cli_path = root / vendor.HOOK_TAG
    cli_path.parent.mkdir(parents=True, exist_ok=True)
    copy_kit_package(cli_path.with_suffix(""))
    shutil.copy(KIT / "scripts/workflow.py", cli_path)
    path = _path(tmp_path, kind)

    def run(event, role):
        env = {"PATH": path, "CLAUDE_PROJECT_DIR": str(root)}
        if role is not None:
            env["WORKFLOW_ROLE"] = role
        p = subprocess.run([shutil.which("sh"), "-c", vendor.hook_command("guard")], input=json.dumps(event),
                           capture_output=True, text=True, env=env, cwd=root)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None

    return run


@pytest.mark.parametrize("kind", ["missing", "failing"])
@pytest.mark.parametrize("where", ["tree", "base"])
@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_without_python_they_get_a_planning_sessions_fallback(tmp_path, kind, where, session, role, branch):
    run = _shell(tmp_path, kind, *_rule_placed(where), branch)
    assert run(PUSH, role) == "ask", session
    assert run(dict(PUSH, permission_mode="dontAsk"), role) == "deny", session
    assert run(WRITE, role) is None, session


@pytest.mark.parametrize("kind", ["missing", "failing"])
@pytest.mark.parametrize("session_answer", STILL_REFUSED, ids=lambda c: f"{c[0][0]}-{c[1]}")
def test_without_python_the_rest_are_still_refused_every_tool(tmp_path, kind, session_answer):
    (session, role, branch), answer = session_answer
    run = _shell(tmp_path, kind, *_answer(answer), branch)
    for event in (PUSH, WRITE):
        assert run(event, role) == "deny", (session, answer, event)


# Reading the line without the kit ----------------------------------------------

TEXTS = [
    'code_writers = "ticket"\n',
    '  code_writers="ticket"  # only ticket sessions\n',
    '﻿code_writers = "ticket"\n',
    '[guard]\ncode_writers = "any"\ncode_writers = "ticket"\n',
    'code_writers = "any"\n',
    '# code_writers = "ticket"\n',
    'code_writers = "ticketing"\n',
    "code_writers = 'ticket'\n",
    "[guard\ncode_writers = \"ticket\"\n",  # doesn't parse: the plain line still counts
    "",
]


def _shell_rule(root):
    return subprocess.run(["sh", str(KIT / "scripts/workflow/fallback.sh"), "--ticket-rule"], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, env={"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(root)})


@pytest.mark.parametrize("text", TEXTS)
def test_the_line_is_read_as_the_profile_reads_it_with_and_without_python(tmp_path, text):
    want = plain_code_writers(text) == "ticket"
    assert fallback.ticket_rule_from_text(text) is want
    root = _project(tmp_path / "proj", text, branch="main")
    assert fallback.ticket_rule(root) is want
    p = _shell_rule(root)
    assert (p.returncode == 0, p.stdout) == (want, "")


def _commit_with(root, profile):
    """A commit whose tree holds only `.claude/workflow/profile.toml` as `profile`."""
    def git(stdin, *args):
        return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, text=True, check=True).stdout.strip()

    obj = git(profile, "hash-object", "-w", "--stdin")
    for name, mode in (("profile.toml", "100644 blob"), ("workflow", "040000 tree"), (".claude", "040000 tree")):
        obj = git(f"{mode} {obj}\t{name}\n", "mktree")
    return git(None, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit-tree", obj, "-m", "base")


@pytest.mark.parametrize("base_line,ticket_on,others,want", [
    ('base_branch = "trunk"\n', "trunk", [], True),  # the plain base_branch line names the base
    ("", "main", [], True),  # default main
    ('base_branch = ""\n', "main", [], True),  # empty: main
    ('base_branch = "trunk"\n', "HEAD", [], True),  # no origin/trunk: origin/HEAD
    ('base_branch = "main~1"\n', "HEAD", ["main"], True),  # not a branch's name: never read
    ('base_branch = "trunk"\n', "main", ["trunk"], False),  # origin/trunk is the base, and it doesn't say so
    ('base_branch = "trunk"\n', "HEAD", ["trunk"], False),  # nor does origin/HEAD count once origin/trunk exists
])
def test_the_base_is_read_where_the_profile_names_it(tmp_path, base_line, ticket_on, others, want):
    root = _project(tmp_path / "proj", VALID + base_line, branch="main")
    ticket = _commit_with(root, VALID + TICKET)
    if ticket_on == "HEAD":
        _git(root, "update-ref", "refs/remotes/origin/elsewhere", ticket)
        _git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/elsewhere")
    else:
        _git(root, "update-ref", f"refs/remotes/origin/{ticket_on}", ticket)
    for name in others:
        _git(root, "update-ref", f"refs/remotes/origin/{name}", _commit_with(root, VALID))
    assert fallback.ticket_rule(root) is want
    assert (_shell_rule(root).returncode == 0) is want


def test_the_fallbacks_say_so():
    for f in ("fallback.py", "fallback.sh", "_old_python.py"):
        text = " ".join((KIT / "scripts/workflow" / f).read_text().split())
        assert "only by its branch" in text and "isn't a role" in text and "planning session" in text, f

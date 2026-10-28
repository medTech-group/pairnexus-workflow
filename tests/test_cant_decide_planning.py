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
import time
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
TICKET_SPACED = ("spaced ticket", " Ticket ", "feature")
CONDUCTOR = ("conductor", "conductor", "feature")
PLANNING = [BRANCH_ONLY, MISTYPED]
# (the working tree's profile, the base's) where nothing makes them planning sessions
NOT_TICKET = {"any": (VALID + ANY, None), "absent": (VALID, None), "any on the base": (VALID, VALID + ANY)}
# Every session that keeps today's fallback: WORKFLOW_ROLE=ticket under any answer,
# and the branch-only and mistyped ones under "any" or with no answer.
STILL_REFUSED = [(s, "ticket") for s in (TICKET_ROLE, TICKET_SPACED, CONDUCTOR)] + [
    (s, a) for s in [TICKET_ROLE] + PLANNING for a in NOT_TICKET]
WHERE = ["tree", "base", "base over any"]


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
    """(the working tree's profile, the base's) with the ticket line in `where`;
    "base over any": the working tree's says "any", and the base's, stricter, wins."""
    if where == "tree":
        return tree + TICKET, None
    return tree + (ANY if where == "base over any" else ""), base + TICKET


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
@pytest.mark.parametrize("where", WHERE)
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


@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_a_failure_outside_the_guard_takes_the_planning_fallback_too(tmp_path, monkeypatch, capsys, session, role, branch):
    root = _project(tmp_path / "proj", VALID + TICKET, branch=branch)

    def boom(*a, **k):
        raise RuntimeError("disk-went-away")

    monkeypatch.setattr(cli, "_hook_guard", boom)
    out = _hook(monkeypatch, capsys, root, None, PUSH, role)
    assert out["permissionDecision"] == "ask" and "disk-went-away" in out["permissionDecisionReason"]
    assert _hook(monkeypatch, capsys, root, None, WRITE, role) is None
    assert _hook(monkeypatch, capsys, root, None, WRITE, "ticket")["permissionDecision"] == "deny"


@pytest.mark.parametrize("role,answer,want", [
    (None, "ticket", "ask"),  # without WORKFLOW_ROLE=ticket, at most a planning session either way
    (None, "any", "deny"),  # the strictest, as before
    ("ticket", "ticket", "deny"),
])
def test_a_budget_spent_before_the_role_is_read(tmp_path, monkeypatch, capsys, role, answer, want):
    root = _project(tmp_path / "proj", _answer(answer)[0])

    def slow(*a, **k):
        raise cli._OverBudget()

    monkeypatch.setattr(cli.roles, "role", slow)
    out = _hook(monkeypatch, capsys, root, None, PUSH, role)
    assert out["permissionDecision"] == want and "ran out of time" in out["permissionDecisionReason"]


# The old-Python fallback's own entry ------------------------------------------


def _old(capsys, root, event, role):
    env = {"CLAUDE_PROJECT_DIR": str(root)}
    if role is not None:
        env["WORKFLOW_ROLE"] = role
    assert _old_python.main(["hook", "guard"], stdin_text=json.dumps(event), env=env, version="3.9.6", cwd=root) == 0
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out.strip() else None


@pytest.mark.parametrize("where", WHERE)
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
@pytest.mark.parametrize("where", WHERE)
@pytest.mark.parametrize("session,role,branch", PLANNING)
def test_without_python_they_get_a_planning_sessions_fallback(tmp_path, kind, where, session, role, branch):
    run = _shell(tmp_path, kind, *_rule_placed(where), branch)
    assert run(PUSH, role) == "ask", session
    assert run(dict(PUSH, permission_mode="dontAsk"), role) == "deny", session
    assert run(WRITE, role) is None, session


@pytest.mark.parametrize("role", ["ticket\u00a0", "\nticket", "conductor\u00a0", "ticket\x1f"])
def test_without_python_a_role_the_shell_trims_less_than_python_stays_refused(tmp_path, role):
    # Python's strip reads each of these as a real role; sed doesn't trim them.
    run = _shell(tmp_path, "missing", VALID + TICKET, None, "feature")
    for event in (PUSH, WRITE):
        assert run(event, role) == "deny", (role, event)


def test_without_python_a_fallback_sh_from_before_the_rule_never_loosens(tmp_path):
    # It ignores --ticket-rule and exits 0 silently: no word, no planning session.
    run = _shell(tmp_path, "missing", VALID + TICKET, None, "claude/build-1")
    (tmp_path / "proj" / vendor.HOOK_TAG).with_suffix("").joinpath("fallback.sh").write_text("cat >/dev/null; exit 0\n")
    for event in (PUSH, WRITE):
        assert run(event, None) == "deny", event


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
    assert (p.returncode, p.stdout, p.stderr) == (0, "ticket\n" if want else "", "")


def test_the_shell_says_nothing_without_a_profile(tmp_path):
    root = tmp_path / "proj"
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    p = _shell_rule(root)
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")


def _commit_with(root, profile, parent=None):
    """A commit whose tree holds only `.claude/workflow/profile.toml` as `profile`."""
    def git(stdin, *args):
        return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, text=True, check=True).stdout.strip()

    obj = git(profile, "hash-object", "-w", "--stdin")
    for name, mode in (("profile.toml", "100644 blob"), ("workflow", "040000 tree"), (".claude", "040000 tree")):
        obj = git(f"{mode} {obj}\t{name}\n", "mktree")
    return git(None, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit-tree", obj, "-m", "base",
               *(["-p", parent] if parent else []))


@pytest.mark.parametrize("base_line,refs,want", [
    # refs: each origin/<name> as last fetched, and whether its profile says "ticket"
    ('base_branch = "trunk"\n', {"trunk": True}, True),  # the plain base_branch line names the base
    ("", {"main": True}, True),  # default main
    ('base_branch = ""\n', {"main": True}, True),  # empty: main
    ('base_branch = "trunk"\n', {"HEAD": True}, True),  # no origin/trunk: origin/HEAD
    # Not a branch's name: never read, though origin/main~1 exists and doesn't say so.
    ('base_branch = "main~1"\n', {"main": "parent without", "HEAD": True}, True),
    ('base_branch = "trunk"\n', {"main": True, "trunk": False}, False),  # origin/trunk is the base, and it doesn't say so
    ('base_branch = "trunk"\n', {"HEAD": True, "trunk": False}, False),  # nor does origin/HEAD count once origin/trunk exists
    ('base_branch = "главная"\n', {"главная": False, "HEAD": True}, False),  # a branch's name in any script
    ("base_branch = 'trunk'\n", {"main": True, "trunk": False}, False),  # a literal string names it too
])
def test_the_base_is_read_where_the_profile_names_it(tmp_path, base_line, refs, want):
    root = _project(tmp_path / "proj", VALID + base_line, branch="main")
    for name, says in refs.items():
        if says == "parent without":
            sha = _commit_with(root, VALID + TICKET, parent=_commit_with(root, VALID))
        else:
            sha = _commit_with(root, VALID + (TICKET if says else ""))
        if name == "HEAD":
            _git(root, "update-ref", "refs/remotes/origin/elsewhere", sha)
            _git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/elsewhere")
        else:
            _git(root, "update-ref", f"refs/remotes/origin/{name}", sha)
    assert fallback.ticket_rule(root) is want
    assert (_shell_rule(root).stdout == "ticket\n") is want


def _fake_git(tmp_path, body):
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    (bindir / "git").write_text("#!/bin/sh\n" + body)
    (bindir / "git").chmod(0o755)
    return str(bindir) + os.pathsep + os.environ["PATH"]


def test_the_rule_spends_at_most_its_git_seconds_in_all(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(VALID)
    monkeypatch.setenv("PATH", _fake_git(tmp_path, "exec sleep 5\n"))  # every git call hangs
    started = time.monotonic()
    assert fallback.ticket_rule(root) is False
    assert time.monotonic() - started < fallback.GIT_SECONDS + 1.5


def test_the_base_is_never_fetched(tmp_path, monkeypatch):
    # A partial clone's `git show` would fetch the missing object: both readers forbid it.
    root = tmp_path / "proj"
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(VALID)
    log = tmp_path / "git.log"
    path = _fake_git(tmp_path, f'case "$*" in *show*) echo "lazy=$GIT_NO_LAZY_FETCH" >> "{log}";; esac\nexit 0\n')
    monkeypatch.setenv("PATH", path)
    fallback.ticket_rule(root)
    subprocess.run(["sh", str(KIT / "scripts/workflow/fallback.sh"), "--ticket-rule"], stdin=subprocess.DEVNULL,
                   capture_output=True, env={"PATH": path, "CLAUDE_PROJECT_DIR": str(root)}, check=True)
    assert log.read_text().split() == ["lazy=1", "lazy=1"]


def test_without_a_working_tree_profile_the_cli_still_refuses_a_mistyped_session(tmp_path, monkeypatch, capsys):
    # "ticket" on the base, but the profile is missing here: restore it, as before.
    root = _project(tmp_path / "proj", VALID, VALID + TICKET, "feature")
    (root / ".claude/workflow/profile.toml").unlink()
    for failure in ("malformed", None):
        for event in (PUSH, WRITE):
            out = _hook(monkeypatch, capsys, root, failure, event, "tikcet")
            assert out and out["permissionDecision"] == "deny", (failure, event, out)


def test_the_fallbacks_say_so():
    for f in ("fallback.py", "fallback.sh", "_old_python.py"):
        text = " ".join((KIT / "scripts/workflow" / f).read_text().split())
        assert "only by its branch" in text and "isn't a role" in text and "planning session" in text, f

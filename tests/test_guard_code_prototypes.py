"""#393 (spec #338, split from #341): under `code_writers = "ticket"`, a
planning session may try an idea in code on a `prototype/*` branch, and that
code can't reach another branch unjudged.

- A planning session (not the conductor), in a checkout on a branch named
  `prototype/*`, may write code paths and commit them, and may push to
  `project.repo` when every ref the push updates there is a `prototype/*`
  branch. The conductor's code writes, commits and pushes on `prototype/*`
  are refused (answer 32 on #338).
- A `prototype/*` branch's tracking refs don't count as already on the
  remote, so its code can't then be pushed to another branch, or merged into
  one, unjudged.
- Under `"any"` or with `code_writers` absent, as today.

Through `workflow hook guard`, run as Claude Code runs it, in temporary git
repositories cloned from a bare remote (`…/acme/demo.git`). The commands are
data given to the hook; only the set-up runs."""

import pytest

from changelog_notes import since_0110
from conftest import git
from test_guard_code_commits import CODE, _change, _clone, hook
from test_guard_code_writers import hook as event_hook
from test_guard_code_writers import powershell, write

pytestmark = pytest.mark.usefixtures("_no_user_git_config")

# A planning session under "ticket": (WORKFLOW_ROLE) — on a prototype branch, never a ticket session by its branch.
PLANNING = {"attended": None, "attended by its role": "attended", "mistyped WORKFLOW_ROLE": "tikcet"}


def _prototype(tmp_path, code_writers="ticket", branch="prototype/x"):
    root = _clone(tmp_path, code_writers)
    git(root, "checkout", "-q", "-b", branch)
    return root


def _code_commit(root, path=CODE, text="changed\n"):
    _change(root, path, text)
    git(root, "add", path)
    git(root, "commit", "-qm", "x")


def _bash(monkeypatch, capsys, root, command, role=None, mode=None, cwd=None):
    return hook(monkeypatch, capsys, root, command, role, mode, cwd)


# ---------- a planning session on `prototype/*` ----------


@pytest.mark.parametrize("who", list(PLANNING))
def test_a_planning_session_writes_commits_and_pushes_code_on_a_prototype_branch(tmp_path, monkeypatch, capsys, who):
    role = PLANNING[who]
    root = _prototype(tmp_path)
    for tool in ("Write", "Edit", "MultiEdit"):
        for mode in (None, "default", "dontAsk"):
            d, why = event_hook(monkeypatch, capsys, root, {**write(str(root / CODE), tool), "permission_mode": mode} if mode else write(str(root / CODE), tool), role)
            assert d == "allow", (who, tool, mode, why)
    for command in ("echo 'b = 2' > src/app.py", "printf x >> src/new.py", "sed -i s/a/b/ src/app.py", "rm -f tests/test_app.py"):
        d, why = _bash(monkeypatch, capsys, root, command, role)
        assert d == "allow", (who, command, why)
    _change(root, CODE)
    for command in ("git commit -am x", "git add -A && git commit -m x", "git commit -m x -- src/app.py"):
        d, why = _bash(monkeypatch, capsys, root, command, role)
        assert d == "allow", (who, command, why)
    git(root, "commit", "-qam", "x")
    for command in (
        "git push origin prototype/x",
        "git push -u origin prototype/x",
        "git push origin HEAD",
        "git push origin @",
        "git push origin $(git branch --show-current)",
        "git push",
        "git push origin",
        "git push origin HEAD:refs/heads/prototype/x",
        "git push origin prototype/x:prototype/y",
        "git push origin prototype/x:refs/heads/prototype/y/z",
        "git push origin prototype/x prototype/x:prototype/y",
    ):
        d, why = _bash(monkeypatch, capsys, root, command, role)
        assert d == "allow", (who, command, why)


def test_a_push_to_a_prototype_branch_from_another_branch_goes_through(tmp_path, monkeypatch, capsys):
    """Where a push goes decides it, not the branch it is run from: a
    prototype branch is never merged, and its tracking refs never count."""
    root = _clone(tmp_path)
    _code_commit(root)
    for command in ("git push origin feature:prototype/x", "git push origin HEAD:refs/heads/prototype/x"):
        assert _bash(monkeypatch, capsys, root, command)[0] == "allow", command
        d, why = _bash(monkeypatch, capsys, root, command, "conductor")
        assert d == "deny" and "the conductor writes no code" in why, (command, why)


def test_a_code_write_in_a_claude_code_worktree_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    """Each checkout by its own branch: a worktree on `prototype/y` beside a
    project on `feature`, and the other way round."""
    root = _clone(tmp_path)
    wt = root / ".claude/worktrees/side"
    git(root, "worktree", "add", "-q", "-b", "prototype/y", str(wt))
    assert event_hook(monkeypatch, capsys, root, write(str(wt / CODE)))[0] == "allow"
    assert _bash(monkeypatch, capsys, root, "echo x > .claude/worktrees/side/src/app.py")[0] == "allow"
    _change(wt, CODE)
    assert _bash(monkeypatch, capsys, root, "cd .claude/worktrees/side && git commit -am x")[0] == "allow"
    d, why = event_hook(monkeypatch, capsys, root, write(str(root / CODE)))
    assert d == "deny" and "code path" in why, why
    git(root, "checkout", "-q", "-b", "prototype/x")
    git(wt, "checkout", "-q", "-b", "side")
    assert event_hook(monkeypatch, capsys, root, write(str(root / CODE)))[0] == "allow"
    d, why = event_hook(monkeypatch, capsys, root, write(str(wt / CODE)))
    assert d == "deny" and "in the worktree `.claude/worktrees/side`" in why, why


# ---------- not a prototype branch ----------


@pytest.mark.parametrize("branch", ["prototypes/x", "my-prototype/x", "Prototype/x", "topic/prototype/x", "prototype"])
def test_only_a_branch_named_prototype_slash_something_counts(tmp_path, monkeypatch, capsys, branch):
    root = _prototype(tmp_path, branch=branch)
    d, why = event_hook(monkeypatch, capsys, root, write(str(root / CODE)))
    assert d == "deny" and "code path" in why, (branch, why)
    _change(root, CODE)
    d, why = _bash(monkeypatch, capsys, root, "git commit -am x")
    assert d == "deny" and "carries the code path" in why, (branch, why)
    git(root, "commit", "-qam", "x")
    d, why = _bash(monkeypatch, capsys, root, f"git push origin {branch}")
    assert d == "deny" and "carries the code path" in why, (branch, why)


def test_a_detached_head_isnt_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    git(root, "checkout", "-q", "--detach")
    d, why = event_hook(monkeypatch, capsys, root, write(str(root / CODE)))
    assert d == "deny" and "code path" in why, why
    _change(root, CODE)
    d, why = _bash(monkeypatch, capsys, root, "git commit -am x")
    assert d == "deny" and "carries the code path" in why, why


@pytest.mark.parametrize(
    "command",
    [
        "git switch feature && echo x > src/app.py",
        "git checkout -q feature; echo x > src/app.py",
        "git symbolic-ref HEAD refs/heads/feature && echo x > src/app.py",
        "echo 'ref: refs/heads/feature' > .git/HEAD && echo x > src/app.py",
        "git co feature && echo x > src/app.py",
        "gh pr checkout 12 && echo x > src/app.py",
        "git rebase main && echo x > src/app.py",
        "git branch -m feature-2 && echo x > src/app.py",
        "git stash branch other && echo x > src/app.py",
        "sh -c 'git switch feature' && echo x > src/app.py",
    ],
)
def test_a_command_that_may_change_the_branch_writes_no_code(tmp_path, monkeypatch, capsys, command):
    """The guard reads the branch as it is when the command starts, so a
    command that may change which branch HEAD names (or names a `.git`)
    gets no prototype exception."""
    root = _prototype(tmp_path)
    d, why = _bash(monkeypatch, capsys, root, command)
    assert d == "deny" and "code path" in why, (command, why)


@pytest.mark.parametrize(
    "command",
    [
        "git switch feature && git commit -am x",
        "git checkout feature; git commit -am x",
        "git symbolic-ref HEAD refs/heads/feature; git commit -am x",
        "git -C . rebase main; git commit -am x",
    ],
)
def test_a_commit_after_a_branch_change_in_the_same_command_is_judged(tmp_path, monkeypatch, capsys, command):
    root = _prototype(tmp_path)
    _change(root, CODE)
    d, why = _bash(monkeypatch, capsys, root, command)
    assert d == "deny" and "carries the code path" in why, (command, why)


def test_powershell_naming_a_code_path_is_still_refused_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    """The guard can't read PowerShell, so it can't tell the branch stays."""
    root = _prototype(tmp_path)
    d, why = event_hook(monkeypatch, capsys, root, powershell("Set-Content src/app.py 'x'"))
    assert d == "deny" and "code path" in why, why


# ---------- the conductor ----------


def test_the_conductor_writes_commits_and_pushes_no_code_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    for tool in ("Write", "Edit"):
        d, why = event_hook(monkeypatch, capsys, root, write(str(root / CODE), tool), "conductor")
        assert d == "deny" and "the conductor writes no code" in why, why
    d, why = _bash(monkeypatch, capsys, root, "echo x > src/app.py", "conductor")
    assert d == "deny" and "the conductor writes no code" in why, why
    _change(root, CODE)
    d, why = _bash(monkeypatch, capsys, root, "git commit -am x", "conductor")
    assert d == "deny" and "carries the code path" in why and "the conductor writes no code" in why, why
    git(root, "commit", "-qam", "x")
    for command in ("git push origin prototype/x", "git push origin HEAD", "git push"):
        d, why = _bash(monkeypatch, capsys, root, command, "conductor")
        assert d == "deny" and "carries the code path" in why, (command, why)


# ---------- no laundering ----------


@pytest.mark.parametrize("pushed", [False, True])
@pytest.mark.parametrize("who", ["attended", "conductor"])
def test_a_push_of_prototype_code_to_another_branch_is_refused(tmp_path, monkeypatch, capsys, pushed, who):
    role = None if who == "attended" else "conductor"
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    if pushed:
        git(root, "push", "-q", "-u", "origin", "prototype/x")
    for command in (
        "git push origin prototype/x:main",
        "git push origin HEAD:feature",
        "git push origin prototype/x:refs/heads/feature",
        "git push origin prototype/x prototype/x:feature",
        "git push origin prototype/x:heads/prototype/y",
        "git push origin prototype/x:refs/tags/prototype/x",
        "git push origin origin/prototype/x:refs/heads/feature" if pushed else "git push origin prototype/x:feature",
    ):
        d, why = _bash(monkeypatch, capsys, root, command, role)
        assert d == "deny" and f"commit {sha}" in why and "src/app.py" in why, (command, why)


@pytest.mark.parametrize("ff", ["--ff", "--no-ff"])
def test_a_push_after_merging_a_pushed_prototype_branch_is_refused(tmp_path, monkeypatch, capsys, ff):
    """#391's merges by their own changes would let this through, were the
    prototype branch's tracking ref counted as on the remote."""
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "push", "-q", "origin", "prototype/x")
    git(root, "checkout", "-q", "feature")
    git(root, "branch", "-q", "-D", "prototype/x")
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", ff, "--no-edit", "origin/prototype/x")
    for command in ("git push origin feature", "git push origin HEAD", "git push -u origin feature"):
        d, why = _bash(monkeypatch, capsys, root, command)
        assert d == "deny" and f"commit {sha}" in why and "src/app.py" in why, (command, why)


def test_a_prototype_branch_fetched_under_another_name_isnt_on_the_remote(tmp_path, monkeypatch, capsys):
    """The tracking refs git fills from a `prototype/*` branch, by the
    remote's fetch refspecs, whatever name they get."""
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "push", "-q", "origin", "prototype/x")
    git(root, "checkout", "-q", "feature")
    git(root, "branch", "-q", "-D", "prototype/x")
    git(root, "update-ref", "-d", "refs/remotes/origin/prototype/x")
    for spec, ref in (
        ("+refs/heads/prototype/*:refs/remotes/origin/proto/*", "origin/proto/x"),
        ("+refs/heads/prototype/x:refs/remotes/origin/px", "origin/px"),
        ("+refs/*:refs/remotes/origin/all/*", "origin/all/heads/prototype/x"),
    ):
        git(root, "config", "--add", "remote.origin.fetch", spec)
        git(root, "fetch", "-q", "origin")
        git(root, "reset", "-q", "--hard", "origin/main")
        git(root, "merge", "-q", "--no-ff", "--no-edit", ref)
        d, why = _bash(monkeypatch, capsys, root, "git push origin feature")
        assert d == "deny" and f"commit {sha}" in why, (spec, why)
        git(root, "config", "--unset-all", "remote.origin.fetch", spec.replace("*", r"\*").replace("+", r"\+"))
        git(root, "update-ref", "-d", "refs/remotes/" + ref)


def test_a_remote_head_pointing_at_a_prototype_branch_doesnt_count(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "push", "-q", "origin", "prototype/x")
    git(root, "remote", "set-head", "origin", "prototype/x")
    git(root, "checkout", "-q", "feature")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/prototype/x")
    d, why = _bash(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha}" in why, why


def test_code_merged_into_the_base_from_a_prototype_counts_as_on_the_remote(tmp_path, monkeypatch, capsys):
    """Once the remote's own branch holds it (the owner merged it there), it
    is on the remote like any other commit."""
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "push", "-q", "origin", "prototype/x", "prototype/x:main")
    git(root, "checkout", "-q", "feature")
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/main")
    assert _bash(monkeypatch, capsys, root, "git push origin feature")[0] == "allow"


@pytest.mark.parametrize(
    "setting, value",
    [("push.default", "upstream"), ("push.default", "matching"), ("remote.origin.push", "refs/heads/prototype/x:refs/heads/main")],
)
def test_a_bare_push_is_read_by_where_its_settings_send_it(tmp_path, monkeypatch, capsys, setting, value):
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "config", "branch.prototype/x.remote", "origin")
    git(root, "config", "branch.prototype/x.merge", "refs/heads/main")
    git(root, "config", setting, value)
    d, why = _bash(monkeypatch, capsys, root, "git push origin")
    assert d == "deny" and "carries the code path" in why, why


def test_a_push_with_prototype_push_settings_goes_through(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "config", "remote.origin.push", "refs/heads/prototype/*:refs/heads/prototype/*")
    assert _bash(monkeypatch, capsys, root, "git push origin")[0] == "allow"


@pytest.mark.parametrize("command", ['git push origin "prototype/x:$B"', "git push origin prototype/x:{prototype/y,main}", "git push --all origin", "git push --mirror origin"])
def test_a_destination_it_cant_read_is_judged_as_any_push(tmp_path, monkeypatch, capsys, command):
    root = _prototype(tmp_path)
    _code_commit(root)
    d, why = _bash(monkeypatch, capsys, root, command)
    assert d in ("deny", "ask") and ("carries the code path" in why or "can't tell" in why), (command, why)


# ---------- as today ----------


@pytest.mark.parametrize("code_writers", ["any", None])
@pytest.mark.parametrize("role", [None, "conductor"])
def test_under_any_or_absent_every_case_decides_as_today(tmp_path, monkeypatch, capsys, code_writers, role):
    root = _prototype(tmp_path, code_writers)
    assert event_hook(monkeypatch, capsys, root, write(str(root / CODE)), role)[0] == "allow"
    assert _bash(monkeypatch, capsys, root, "echo x > src/app.py", role)[0] == "allow"
    _change(root, CODE)
    assert _bash(monkeypatch, capsys, root, "git commit -am x", role)[0] == "allow"
    git(root, "commit", "-qam", "x")
    assert _bash(monkeypatch, capsys, root, "git push origin prototype/x", role)[0] == "allow"
    git(root, "push", "-q", "origin", "prototype/x")
    git(root, "checkout", "-q", "feature")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/prototype/x")
    assert _bash(monkeypatch, capsys, root, "git push origin feature", role)[0] == "allow"
    assert _bash(monkeypatch, capsys, root, "git push origin origin/prototype/x:refs/heads/feature-2", role)[0] == "allow"


def test_the_changelog_notes_it():
    text = since_0110()
    assert "#393" in text and "`prototype/*`" in text

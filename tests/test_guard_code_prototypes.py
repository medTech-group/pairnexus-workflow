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

import subprocess

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
        d, why = hook(monkeypatch, capsys, root, command, role)
        assert d == "allow", (who, command, why)
    _change(root, CODE)
    for command in ("git commit -am x", "git add -A && git commit -m x", "git commit -m x -- src/app.py"):
        d, why = hook(monkeypatch, capsys, root, command, role)
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
        "git push origin prototype/x:refs/heads/prototype/y",
        "git push origin prototype/x:refs/heads/prototype/y/z",
        "git push origin prototype/x prototype/x:refs/heads/prototype/y",
        "git push --no-follow-tags origin prototype/x",
    ):
        d, why = hook(monkeypatch, capsys, root, command, role)
        assert d == "allow", (who, command, why)


def test_a_push_to_a_prototype_branch_from_another_branch_is_judged(tmp_path, monkeypatch, capsys):
    """A push to `prototype/*` goes through only when run on a `prototype/*`
    branch, as the spec groups it."""
    root = _clone(tmp_path)
    _code_commit(root)
    for command in ("git push origin feature:refs/heads/prototype/x", "git push origin HEAD:refs/heads/prototype/x"):
        for role in (None, "conductor"):
            d, why = hook(monkeypatch, capsys, root, command, role)
            assert d == "deny" and "carries the code path" in why, (command, role, why)


def test_a_code_write_in_a_claude_code_worktree_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    """Each checkout by its own branch: a worktree on `prototype/y` beside a
    project on `feature`, and the other way round."""
    root = _clone(tmp_path)
    wt = root / ".claude/worktrees/side"
    git(root, "worktree", "add", "-q", "-b", "prototype/y", str(wt))
    assert event_hook(monkeypatch, capsys, root, write(str(wt / CODE)))[0] == "allow"
    assert hook(monkeypatch, capsys, root, "echo x > .claude/worktrees/side/src/app.py")[0] == "allow"
    _change(wt, CODE)
    assert hook(monkeypatch, capsys, root, "cd .claude/worktrees/side && git commit -am x")[0] == "allow"
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
    d, why = hook(monkeypatch, capsys, root, "git commit -am x")
    assert d == "deny" and "carries the code path" in why, (branch, why)
    git(root, "commit", "-qam", "x")
    d, why = hook(monkeypatch, capsys, root, f"git push origin {branch}")
    assert d == "deny" and "carries the code path" in why, (branch, why)


def test_a_detached_head_isnt_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    git(root, "checkout", "-q", "--detach")
    d, why = event_hook(monkeypatch, capsys, root, write(str(root / CODE)))
    assert d == "deny" and "code path" in why, why
    _change(root, CODE)
    d, why = hook(monkeypatch, capsys, root, "git commit -am x")
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
    d, why = hook(monkeypatch, capsys, root, command)
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
    d, why = hook(monkeypatch, capsys, root, command)
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
    d, why = hook(monkeypatch, capsys, root, "echo x > src/app.py", "conductor")
    assert d == "deny" and "the conductor writes no code" in why, why
    _change(root, CODE)
    d, why = hook(monkeypatch, capsys, root, "git commit -am x", "conductor")
    assert d == "deny" and "carries the code path" in why and "the conductor writes no code" in why, why
    git(root, "commit", "-qam", "x")
    for command in ("git push origin prototype/x", "git push origin HEAD", "git push"):
        d, why = hook(monkeypatch, capsys, root, command, "conductor")
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
        d, why = hook(monkeypatch, capsys, root, command, role)
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
        d, why = hook(monkeypatch, capsys, root, command)
        assert d == "deny" and f"commit {sha}" in why and "src/app.py" in why, (command, why)
    assert "is on `origin/prototype/x`, a `prototype/*` branch's tracking ref, which doesn't count as on the remote" in why, why


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
        d, why = hook(monkeypatch, capsys, root, "git push origin feature")
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
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
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
    assert hook(monkeypatch, capsys, root, "git push origin feature")[0] == "allow"


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
    d, why = hook(monkeypatch, capsys, root, "git push origin")
    assert d == "deny" and "carries the code path" in why, why


def test_a_push_with_prototype_push_settings_goes_through(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "config", "remote.origin.push", "refs/heads/prototype/*:refs/heads/prototype/*")
    assert hook(monkeypatch, capsys, root, "git push origin")[0] == "allow"


@pytest.mark.parametrize(
    "command, why",
    [
        ('git push origin "prototype/x:$B"', "the shell may expand `prototype/x:$B`"),
        ("git push origin prototype/x:{prototype/y,main}", "the shell may expand"),
        ("git push --all origin", "it pushes more than named branches"),
        ("git push --mirror origin", "it pushes more than named branches"),
        ("git push origin prototype/x:prototype/y", "isn't written in full: write it `refs/heads/prototype/y`"),
    ],
)
def test_a_destination_it_cant_read_is_judged_as_any_push(tmp_path, monkeypatch, capsys, command, why):
    root = _prototype(tmp_path)
    _code_commit(root)
    d, reason = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "carries the code path" in reason and why in reason, (command, reason)
    assert "prototype code goes to `prototype/*` branches only" in reason, reason


@pytest.mark.parametrize(
    "command",
    ["git status && git push origin prototype/x", "cd . && git push origin prototype/x", "git push origin prototype/x; git log -1 --oneline"],
)
def test_reads_beside_a_prototype_push_are_fine(tmp_path, monkeypatch, capsys, command):
    root = _prototype(tmp_path)
    _code_commit(root)
    assert hook(monkeypatch, capsys, root, command) == ("allow", ""), command


@pytest.mark.parametrize(
    "command",
    [
        "printf '[remote \"origin\"]\\n\\tpush = refs/heads/prototype/x:refs/heads/main\\n' >> .gi?/config && git push origin prototype/x",
        "./prep.sh; git push origin",
        "./prep.sh && git push origin HEAD",
        "git fetch && git push origin prototype/x",
        "git config --get remote.origin.url && git push origin prototype/x",
    ],
)
def test_a_prototype_push_beside_anything_but_reads_is_judged(tmp_path, monkeypatch, capsys, command):
    """Another part of the command may change git's config or HEAD before
    the push runs, in ways the guard can't see (a glob naming `.git`, a script)."""
    root = _prototype(tmp_path)
    _code_commit(root)
    d, why = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "carries the code path" in why and "run the push in a command of its own" in why, (command, why)


# ---------- as today ----------


@pytest.mark.parametrize("code_writers", ["any", None])
@pytest.mark.parametrize("role", [None, "conductor"])
def test_under_any_or_absent_every_case_decides_as_today(tmp_path, monkeypatch, capsys, code_writers, role):
    root = _prototype(tmp_path, code_writers)
    assert event_hook(monkeypatch, capsys, root, write(str(root / CODE)), role)[0] == "allow"
    assert hook(monkeypatch, capsys, root, "echo x > src/app.py", role)[0] == "allow"
    _change(root, CODE)
    assert hook(monkeypatch, capsys, root, "git commit -am x", role)[0] == "allow"
    git(root, "commit", "-qam", "x")
    assert hook(monkeypatch, capsys, root, "git push origin prototype/x", role)[0] == "allow"
    git(root, "push", "-q", "origin", "prototype/x")
    git(root, "checkout", "-q", "feature")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/prototype/x")
    assert hook(monkeypatch, capsys, root, "git push origin feature", role)[0] == "allow"
    assert hook(monkeypatch, capsys, root, "git push origin origin/prototype/x:refs/heads/feature-2", role)[0] == "allow"


@pytest.mark.parametrize(
    "setting, value",
    [
        ("remote.origin.push", "refs/heads/prototype/x:refs/heads/main"),
        ("push.default", "upstream"),
        ("push.default", "tracking"),
    ],
)
@pytest.mark.parametrize("command", ["git push origin prototype/x", "git push origin HEAD"])
def test_a_source_without_a_destination_is_read_as_git_maps_it(tmp_path, monkeypatch, capsys, setting, value, command):
    """git maps `git push origin prototype/x` through the remote's `push`
    refspecs, or to the branch's upstream under `push.default = upstream`."""
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "config", "branch.prototype/x.remote", "origin")
    git(root, "config", "branch.prototype/x.merge", "refs/heads/main")
    git(root, "config", setting, value)
    d, why = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "carries the code path" in why, why


def test_a_symbolic_ref_or_a_tag_named_prototype_isnt_a_prototype_branch(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "symbolic-ref", "refs/heads/prototype/alias", "refs/heads/feature")
    git(root, "branch", "-q", "-f", "feature", "prototype/x")
    git(root, "tag", "prototype/t")
    git(root, "tag", "v9")
    git(root, "update-ref", "refs/prototype/r", "HEAD")
    for command in (
        "git push origin prototype/alias",
        "git push origin prototype/t",
        "git push origin prototype/r",
        "git push origin prototype/t:prototype/u",
        "git push origin v9:prototype/u",
        "git push origin prototype/x prototype/t",
    ):
        d, why = hook(monkeypatch, capsys, root, command)
        assert d == "deny" and "carries the code path" in why, (command, why)


@pytest.mark.parametrize(
    "command, setting, decision, why",
    [
        ("git push --follow-tags origin prototype/x", None, "deny", "it sends the tags on its commits too"),
        ("git push origin prototype/x", "push.followTags", "deny", "it sends the tags on its commits too"),
        ("git -c push.followTags=true push origin prototype/x", None, "deny", "it runs with `-c push.followTags=true`"),
        ("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=push.followTags GIT_CONFIG_VALUE_0=true git push origin prototype/x", None, "deny", "it runs with the variable `GIT_CONFIG_KEY_0`"),
        ("git config push.followTags true; git push origin prototype/x", None, "deny", "run the push in a command of its own"),
        ("git tag v9 && git push origin prototype/x", None, "ask", "can't tell"),
        ("HOME=/tmp/elsewhere git push origin prototype/x", None, "ask", "can't tell"),
    ],
)
def test_a_push_that_may_send_tags_or_be_remapped_is_judged(tmp_path, monkeypatch, capsys, command, setting, decision, why):
    """Tags it follows reach the remote as tags, and a setting or another
    part of the command can change where git maps the push."""
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "tag", "-a", "v1", "-m", "v1")
    if setting:
        git(root, "config", setting, "true")
    d, reason = hook(monkeypatch, capsys, root, command)
    assert d == decision and why in reason, (command, reason)
    if decision == "deny":
        assert "carries the code path" in reason, reason


def test_a_fetch_refspec_with_a_short_destination_is_read_as_git_stores_it(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "push", "-q", "origin", "prototype/x")
    git(root, "checkout", "-q", "feature")
    git(root, "branch", "-q", "-D", "prototype/x")
    git(root, "update-ref", "-d", "refs/remotes/origin/prototype/x")
    git(root, "config", "--add", "remote.origin.fetch", "+refs/heads/prototype/x:remotes/origin/feature-p")
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/feature-p")
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha}" in why, why


def test_the_refusals_say_how_a_prototype_works(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    d, why = hook(monkeypatch, capsys, root, "git stash && echo x > src/app.py")
    assert d == "deny" and "this one runs `git stash`" in why and "commands of their own" in why, why
    _code_commit(root)
    d, why = hook(monkeypatch, capsys, root, "git push origin prototype/x:main")
    assert d == "deny" and "prototype code goes to `prototype/*` branches only" in why, why
    d, why = hook(monkeypatch, capsys, root, "git push origin prototype/x:main", "conductor")
    assert d == "deny" and "prototype" not in why.partition("main")[2], why


def _pushed_away(root):
    """A code commit on `prototype/x`, pushed, then the branch and its own tracking ref gone here."""
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "push", "-q", "origin", "prototype/x", "HEAD:refs/pull/7/head")
    git(root, "checkout", "-q", "feature")
    git(root, "branch", "-q", "-D", "prototype/x")
    git(root, "update-ref", "-d", "refs/remotes/origin/prototype/x")
    return sha


@pytest.mark.parametrize(
    "spec, ref",
    [
        ("+refs/pull/*/head:refs/remotes/origin/pr/*", "origin/pr/7"),
        ("+refs/*:refs/remotes/origin/all/*", "origin/all/pull/7/head"),
        ("+refs/heads/*/x:refs/remotes/origin/p/*/x", "origin/p/prototype/x"),
        ("+refs/heads/pro*/x:refs/remotes/origin/c*/x", "origin/ctotype/x"),
        ("+refs/heads/*type/x:refs/remotes/origin/t/*", "origin/t/proto"),
    ],
)
def test_only_tracking_refs_of_other_branches_count_as_on_the_remote(tmp_path, monkeypatch, capsys, spec, ref):
    """A pull request's ref, every ref, and patterns whose `*` stands for part
    of a prototype branch's name: none counts as on the remote."""
    root = _prototype(tmp_path)
    sha = _pushed_away(root)
    git(root, "config", "--add", "remote.origin.fetch", spec)
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-ff", "--no-edit", ref)
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha}" in why, (spec, why)


@pytest.mark.parametrize("setup", ["no fetch refspec", "single branch, another fetched by hand", "many refspecs"])
def test_tracking_refs_count_as_on_the_remote_as_before(tmp_path, monkeypatch, capsys, setup):
    """Every other tracking ref of a remote fetching from `project.repo`
    counts, as #390 counts it: a remote with no `fetch` refspec, a branch a
    single-branch clone fetched by hand, and hundreds of refspecs."""
    root = _clone(tmp_path)
    _code_commit(root)
    git(root, "push", "-q", "origin", "feature:build-7")
    if setup == "no fetch refspec":
        git(root, "config", "--unset-all", "remote.origin.fetch")
    elif setup == "single branch, another fetched by hand":
        git(root, "config", "--replace-all", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")
        git(root, "update-ref", "-d", "refs/remotes/origin/build-7")
        git(root, "fetch", "-q", "origin", "build-7:refs/remotes/origin/build-7")
    else:
        for k in range(300):
            git(root, "config", "--add", "remote.origin.fetch", f"+refs/pull/{k}/head:refs/remotes/origin/pr/{k}")
    _change(root, "docs/guide.md")
    git(root, "commit", "-qam", "d")
    assert hook(monkeypatch, capsys, root, "git push origin feature:fix-7") == ("allow", ""), setup


def test_a_tracking_ref_of_a_prototype_branch_in_another_case_doesnt_count(tmp_path, monkeypatch, capsys):
    """A case-insensitive file system can store `prototype/x` under a folder
    named `Prototype`: the name is left out in any case."""
    root = _prototype(tmp_path)
    sha = _pushed_away(root)
    git(root, "update-ref", "refs/remotes/origin/Prototype/x", sha)
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/Prototype/x")
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha}" in why, why


@pytest.mark.parametrize(
    "command",
    ["grep -rl a . | xargs sed -i s/a/b/", "find . -name app.py -exec sed -i s/a/b/ {} +", "rm -rf src .claude/worktrees/side/src"],
)
def test_a_tree_write_from_a_prototype_checkout_into_a_worktree_on_another_branch(tmp_path, monkeypatch, capsys, command):
    root = _prototype(tmp_path)
    wt = root / ".claude/worktrees/side"
    git(root, "worktree", "add", "-q", "-b", "side", str(wt))
    d, why = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "code path" in why, (command, why)
    git(wt, "checkout", "-q", "-b", "prototype/side")
    assert hook(monkeypatch, capsys, root, command)[0] == "allow", command


def _rebase_conflict(root):
    """`prototype/x` being rebased onto `other`, stopped at a conflict in a code path."""
    git(root, "checkout", "-q", "-b", "other", "main")
    _code_commit(root, CODE, "other\n")
    git(root, "checkout", "-q", "prototype/x")
    _code_commit(root, CODE, "mine\n")
    assert subprocess.run(["git", "rebase", "other"], cwd=root, capture_output=True).returncode != 0
    assert "rebase" in git(root, "status")
    _change(root, CODE, "both\n")
    git(root, "add", CODE)


def test_finishing_a_prototype_branchs_rebase(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _rebase_conflict(root)
    for command in ("git rebase --continue", "git commit -m x", "git -c core.editor=true rebase --continue"):
        assert hook(monkeypatch, capsys, root, command)[0] == "allow", command
    d, why = hook(monkeypatch, capsys, root, "git rebase --continue", "conductor")
    assert d == "deny" and "carries the code path" in why, why
    d, why = hook(monkeypatch, capsys, root, "git rebase --quit && echo x > src/app.py")
    assert d == "deny" and "code path" in why, why


def test_the_note_names_a_worktree_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    root = _clone(tmp_path)
    wt = root / ".claude/worktrees/side"
    git(root, "worktree", "add", "-q", "-b", "prototype/y", str(wt))
    d, why = hook(monkeypatch, capsys, root, "git stash && echo x > .claude/worktrees/side/src/app.py")
    assert d == "deny" and "this one runs `git stash`" in why, why


@pytest.mark.parametrize(
    "command, why",
    [
        ("git push origin prototype/x:main", "its destination `main` isn't a `prototype/*` branch"),
        ("git push origin prototype/x:refs/heads/main", "its destination `refs/heads/main` isn't a `prototype/*` branch"),
        ("git push origin 'HEAD^{/.|:refs/heads/prototype/y}:refs/heads/feature'", "its destination `refs/heads/feature` isn't"),
        ("git push origin 'HEAD:refs/heads/prototype/a..b'", "its destination"),
    ],
)
def test_a_refspec_is_split_at_its_last_colon(tmp_path, monkeypatch, capsys, command, why):
    """git splits a refspec at its last `:`; a source may hold one
    (`HEAD^{/<regex>}`, `<rev>:<path>`)."""
    root = _prototype(tmp_path)
    _code_commit(root)
    d, reason = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "carries the code path" in reason and why in reason, (command, reason)
    # A source naming a path in a commit (a gitlink there, or nothing): read whole, as git reads it.
    d, reason = hook(monkeypatch, capsys, root, "git push origin HEAD:refs/heads/prototype/y:refs/heads/feature")
    assert d == "ask" and "can't tell" in reason, reason


def test_code_already_on_a_single_branch_clones_remote_counts(tmp_path, monkeypatch, capsys):
    """A single-branch clone's refspec names one tracking ref, which counts."""
    seed = _clone(tmp_path, name="seed")
    _code_commit(seed)
    git(seed, "push", "-q", "origin", "HEAD:main")
    root = tmp_path / "single"
    git(tmp_path, "clone", "-q", "--single-branch", "-b", "main", str(tmp_path / "seed-remote/acme/demo.git"), str(root))
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    assert git(root, "config", "--get-all", "remote.origin.fetch").strip() == "+refs/heads/main:refs/remotes/origin/main"
    git(root, "checkout", "-q", "-b", "feature")
    _change(root, "docs/guide.md")
    git(root, "commit", "-qam", "d")
    assert hook(monkeypatch, capsys, root, "git push origin feature") == ("allow", "")


def test_a_fetch_refspec_storing_outside_its_remotes_tracking_refs_doesnt_count(tmp_path, monkeypatch, capsys):
    """Only `refs/remotes/<a remote fetching from project.repo>/…` can be on the remote."""
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "config", "--add", "remote.origin.fetch", "+refs/heads/main:refs/heads/prototype/x")
    git(root, "config", "--add", "remote.origin.fetch", "+refs/heads/main:refs/heads/elsewhere")
    git(root, "branch", "-q", "elsewhere")
    git(root, "checkout", "-q", "feature")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "elsewhere")
    for command in ("git push origin prototype/x:refs/heads/feature", "git push origin feature"):
        d, why = hook(monkeypatch, capsys, root, command)
        assert d == "deny" and f"commit {sha}" in why, (command, why)


def test_another_remotes_refspec_storing_among_ours_doesnt_count(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    other = tmp_path / "fork-remote" / "acme" / "fork.git"
    other.parent.mkdir(parents=True)
    git(tmp_path, "init", "-q", "--bare", str(other))
    git(root, "remote", "add", "fork", str(other))
    git(root, "config", "--replace-all", "remote.fork.fetch", "+refs/heads/*:refs/remotes/origin/zz/*")
    git(root, "push", "-q", "fork", "prototype/x")
    git(root, "fetch", "-q", "fork")
    git(root, "checkout", "-q", "feature")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "origin/zz/prototype/x")
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha}" in why, why


def test_a_remote_nested_in_ours_and_fetching_from_project_repo_counts(tmp_path, monkeypatch, capsys):
    """`origin` and `origin/x` both fetch from `project.repo`: what `origin/x` stores counts."""
    root = _clone(tmp_path)
    _code_commit(root)
    git(root, "push", "-q", "origin", "feature")
    git(root, "update-ref", "-d", "refs/remotes/origin/feature")
    url = git(root, "remote", "get-url", "origin").strip()
    git(root, "config", "remote.origin/x.url", url)
    git(root, "config", "remote.origin/x.fetch", "+refs/heads/*:refs/remotes/origin/x/*")
    git(root, "fetch", "-q", "origin/x")
    _change(root, "docs/guide.md")
    git(root, "commit", "-qam", "d")
    assert hook(monkeypatch, capsys, root, "git push origin feature") == ("allow", "")


@pytest.mark.parametrize("code_writers", ["ticket", "any"])
@pytest.mark.parametrize("role", [None, "conductor"])
def test_a_push_to_the_base_from_a_source_holding_a_colon(tmp_path, monkeypatch, capsys, code_writers, role):
    """git splits a refspec at its last `:`, so this pushes to `main`: the
    base-branch rule decides it as it decides `HEAD:main`."""
    root = _clone(tmp_path, code_writers)
    _change(root, "docs/guide.md")
    git(root, "commit", "-qam", "a:b")
    plain = hook(monkeypatch, capsys, root, "git push origin HEAD:main", role)
    d, why = hook(monkeypatch, capsys, root, "git push origin 'HEAD^{/a:b}:main'", role)
    assert plain[0] != "allow" and d == plain[0] and "main" in why, (plain, d, why)


@pytest.mark.parametrize(
    "command, setting",
    [
        ("git push --recurse-submodules=on-demand origin prototype/x", None),
        ("git push --recurse-submodules only origin prototype/x", None),
        ("git push origin prototype/x", ("push.recurseSubmodules", "on-demand")),
        ("git push origin prototype/x", ("submodule.recurse", "true")),
        ("git push --recurse on-demand origin prototype/x", None),
        ("git push --no-recurse-submodules --recurse-submodules=on-demand origin prototype/x", None),
        ("git push origin prototype/x", ("push.recurseSubmodules", "no", "submodule.recurse", "true")),
        ("git push origin prototype/x", ("submodule.recurse", "true", "push.recurseSubmodules", "no")),
    ],
)
def test_a_push_that_may_push_submodules_too_is_judged(tmp_path, monkeypatch, capsys, command, setting):
    """git pushes each submodule's commits with the same refspecs, which can
    send another branch of `project.repo` (a submodule cloned from it)."""
    root = _prototype(tmp_path)
    _code_commit(root)
    for k in range(0, len(setting or ()), 2):
        git(root, "config", setting[k], setting[k + 1])
    d, why = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "git may push submodules too" in why and "push with `--no-recurse-submodules`" in why, (command, why)


@pytest.mark.parametrize(
    "command, setting",
    [
        ("git push --recurse-submodules=check origin prototype/x", ("push.recurseSubmodules", "on-demand")),
        ("git push --no-recurse-submodules origin prototype/x", ("push.recurseSubmodules", "on-demand")),
        ("git push --recurse-submodules=on-demand --no-recurse-submodules origin prototype/x", None),
        ("git push --recurse-submodules=No origin prototype/x", None),
        ("git push --recurse-submodules= origin prototype/x", None),
        ("git push origin prototype/x", ("push.recurseSubmodules", "check")),
        ("git push origin prototype/x", ("push.recurseSubmodules", "no")),
        ("git push origin prototype/x", ("submodule.recurse", "false")),
    ],
)
def test_a_push_that_checks_submodules_or_pushes_none_goes_through(tmp_path, monkeypatch, capsys, command, setting):
    root = _prototype(tmp_path)
    _code_commit(root)
    if setting:
        git(root, "config", *setting)
    assert hook(monkeypatch, capsys, root, command) == ("allow", ""), command


def test_the_refusal_names_where_the_prototype_code_is(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    sha = git(root, "rev-parse", "--short", "HEAD").strip()
    git(root, "checkout", "-q", "feature")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "prototype/x")
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha} is on `prototype/x`, a `prototype/*` branch, and isn't on the remote yet" in why, why
    git(root, "push", "-q", "origin", "prototype/x")  # pushed, and kept here
    d, why = hook(monkeypatch, capsys, root, "git push origin feature")
    assert d == "deny" and f"commit {sha} is on `origin/prototype/x`, a `prototype/*` branch's tracking ref" in why, why
    git(root, "config", "submodule.recurse", "true")  # on `feature`: the branch is the reason given first
    d, why = hook(monkeypatch, capsys, root, "git push origin feature:refs/heads/prototype/z")
    assert d == "deny" and "it isn't run on a `prototype/*` branch" in why and "submodules" not in why, why
    git(root, "config", "--unset", "submodule.recurse")
    git(root, "checkout", "-q", "prototype/x")
    d, why = hook(monkeypatch, capsys, root, "git push origin prototype/x:heads/prototype/y")
    assert d == "deny" and "isn't written in full: write it `refs/heads/prototype/y`" in why, why


def test_a_mirroring_remote_or_the_shells_branch_elsewhere_gets_no_exception(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "config", "remote.origin.mirror", "true")
    d, why = hook(monkeypatch, capsys, root, "git push origin")
    assert d == "deny" and "its remote mirrors every ref" in why, why
    git(root, "config", "--unset", "remote.origin.mirror")
    # The shell's branch is `feature`'s, where git runs in a worktree on `prototype/y`: git pushes `feature`.
    git(root, "checkout", "-q", "feature")
    _code_commit(root, CODE, "feature's\n")
    git(root, "worktree", "add", "-q", "-b", "prototype/y", str(root / ".claude/worktrees/side"))
    d, why = hook(monkeypatch, capsys, root, "git -C .claude/worktrees/side push origin $(git branch --show-current)")
    assert d == "ask" and "the shell's branch" in why, why


@pytest.mark.parametrize("value, decision", [("current", "allow"), ("simple", "allow"), ("nothing", "deny"), ("upstream", "deny")])
def test_a_bare_push_by_push_default(tmp_path, monkeypatch, capsys, value, decision):
    root = _prototype(tmp_path)
    _code_commit(root)
    git(root, "config", "push.default", value)
    d, why = hook(monkeypatch, capsys, root, "git push origin")
    assert d == decision, (value, why)
    if decision == "deny":
        assert f"`push.default = {value}` decides where a bare push goes" in why, why


def test_finishing_a_prototype_branchs_rebase_by_the_apply_backend(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    git(root, "checkout", "-q", "-b", "other", "main")
    _code_commit(root, CODE, "other\n")
    git(root, "checkout", "-q", "prototype/x")
    _code_commit(root, CODE, "mine\n")
    assert subprocess.run(["git", "rebase", "--apply", "other"], cwd=root, capture_output=True).returncode != 0
    assert (root / ".git" / "rebase-apply" / "head-name").exists()
    _change(root, CODE, "both\n")
    git(root, "add", CODE)
    assert hook(monkeypatch, capsys, root, "git rebase --continue")[0] == "allow"
    d, why = hook(monkeypatch, capsys, root, "git rebase --continue", "conductor")
    assert d == "deny" and "carries the code path" in why, why


def test_git_clean_on_a_prototype_checkout(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _change(root, "src/new.py")
    assert hook(monkeypatch, capsys, root, "git clean -fd") == ("allow", "")
    wt = root / ".claude/worktrees/side"
    git(root, "worktree", "add", "-q", "-b", "side", str(wt))
    _change(wt, "src/new.py")
    d, why = hook(monkeypatch, capsys, root, "git -C .claude/worktrees/side clean -fd")
    assert d == "deny" and "removes the code path" in why, why


def test_a_dot_git_named_in_a_commits_message(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _change(root, CODE)
    d, why = hook(monkeypatch, capsys, root, 'git commit -am "read .git/HEAD in the reader"')
    assert d == "deny" and "this one names `.git/HEAD" in why and "`-F <file>`" in why, why
    assert hook(monkeypatch, capsys, root, 'git commit -am "read the HEAD file in the reader"') == ("allow", "")
    (root / "msg.txt").write_text("read .git/HEAD in the reader\n")
    assert hook(monkeypatch, capsys, root, "git commit -a -F msg.txt") == ("allow", "")
    d, why = hook(monkeypatch, capsys, root, "echo 'GIT = \".git\"' >> src/app.py")
    assert d == "deny" and "write a file with the file tools" in why, why
    d, why = hook(monkeypatch, capsys, root, 'git stash && git commit -am "fix .git handling"')
    assert d == "deny" and "runs `git stash`" in why and "names `.git`" in why, why


def test_a_rebase_of_another_branch_in_progress_isnt_on_a_prototype_branch(tmp_path, monkeypatch, capsys):
    """git finishes a rebase on the branch it started on, whatever HEAD names meanwhile."""
    root = _clone(tmp_path)
    git(root, "branch", "-q", "prototype/x")
    git(root, "checkout", "-q", "-b", "other", "main")
    _code_commit(root, CODE, "other\n")
    git(root, "checkout", "-q", "feature")
    _code_commit(root, CODE, "mine\n")
    assert subprocess.run(["git", "rebase", "other"], cwd=root, capture_output=True).returncode != 0
    git(root, "checkout", "-q", "-f", "prototype/x")
    _change(root, CODE, "both\n")
    for command in ("git rebase --abort && echo x > src/app.py", "git commit -am wip"):
        d, why = hook(monkeypatch, capsys, root, command)
        assert d == "deny" and "code path" in why, (command, why)


def test_a_dot_git_attached_to_a_short_option(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _change(root, CODE)
    d, why = hook(monkeypatch, capsys, root, "tar -C.git -xf h.tar; git commit -am x")
    assert d == "deny" and "code path" in why and "names `-C.git`" in why, why
    d, why = hook(monkeypatch, capsys, root, "cp -t.git HEAD && git commit -am x")
    assert d == "deny" and "code path" in why, why


@pytest.mark.parametrize(
    "command, culprit",
    [
        ("env -u HOME git push origin", "the wrapper `env`"),
        ("git push origin prototype/x 2>/tmp/elsewhere.cfg", "a redirect to `/tmp/elsewhere.cfg`"),
        ("git push origin prototype/x > push.log", "a redirect to `push.log`"),
        ("nice git push origin prototype/x", "the wrapper `nice`"),
        ("/tmp/e GIT_CONFIG_PARAMETERS=x git push origin prototype/x", "`/tmp/e` before git"),
        ("busybox env HOME=/tmp/h git push origin prototype/x", "`busybox` before git"),
        ("/usr/bin/git push origin prototype/x", "`/usr/bin/git` before git"),
        ("git --exec-path=/tmp/x push origin prototype/x", "`--exec-path=/tmp/x`"),
        ("GIT_SSH_COMMAND=/tmp/ssh git push origin prototype/x", "the variable `GIT_SSH_COMMAND`"),
    ],
)
def test_a_prototype_push_with_settings_of_its_own_is_judged(tmp_path, monkeypatch, capsys, command, culprit):
    """Only git itself as the command word, with nothing that could change which
    config it reads or where it pushes, gets the exception; the refusal names the culprit."""
    root = _prototype(tmp_path)
    _code_commit(root)
    d, why = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "carries the code path" in why and f"it runs with {culprit}" in why, (command, why)


def test_a_prototype_push_under_command_or_timeout_goes_through(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _code_commit(root)
    for ok in ("command git push origin prototype/x", "timeout 60 git push origin prototype/x", "git push origin prototype/x >/dev/null 2>&1"):
        assert hook(monkeypatch, capsys, root, ok) == ("allow", ""), ok


def _rebasing(root, start, other="other"):
    """A rebase of `start` onto `other` stopped at a conflict in a code path."""
    git(root, "checkout", "-q", "-b", other, "main")
    _code_commit(root, CODE, "other\n")
    git(root, "checkout", "-q", start)
    _code_commit(root, CODE, "mine\n")
    assert subprocess.run(["git", "rebase", other], cwd=root, capture_output=True).returncode != 0


def test_which_branch_a_rebase_counts_on(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _rebasing(root, "prototype/x")
    _change(root, CODE, "both\n")
    git(root, "add", CODE)
    assert hook(monkeypatch, capsys, root, "git commit -m x")[0] == "allow"  # detached, finishing on prototype/x
    git(root, "checkout", "-q", "-b", "prototype/y")  # attached to another prototype branch meanwhile
    assert hook(monkeypatch, capsys, root, "git commit -m x")[0] == "allow"
    git(root, "symbolic-ref", "HEAD", "refs/heads/prototype/x")  # attached to the branch it finishes on
    assert hook(monkeypatch, capsys, root, "git commit -m x")[0] == "allow"
    git(root, "symbolic-ref", "HEAD", "refs/heads/feature")
    d, why = hook(monkeypatch, capsys, root, "git commit -m x")
    assert d == "deny" and "carries the code path" in why, why


def test_a_detached_rebase_counts_on_no_branch(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    git(root, "checkout", "-q", "-b", "other", "main")
    _code_commit(root, CODE, "other\n")
    git(root, "checkout", "-q", "--detach", "prototype/x")
    _code_commit(root, CODE, "mine\n")
    assert subprocess.run(["git", "rebase", "other"], cwd=root, capture_output=True).returncode != 0
    assert (root / ".git" / "rebase-merge" / "head-name").read_text().strip() == "detached HEAD"
    _change(root, CODE, "both\n")
    git(root, "add", CODE)
    d, why = hook(monkeypatch, capsys, root, "git commit -m x")
    assert d == "deny" and "carries the code path" in why, why


def test_a_dot_git_option_in_a_variable_and_a_branch_change_both_named(tmp_path, monkeypatch, capsys):
    root = _prototype(tmp_path)
    _change(root, CODE)
    d, why = hook(monkeypatch, capsys, root, "o=-t.git; cp $o HEAD && git commit -am x")
    assert d == "deny" and "names `-t.git`" in why, why
    d, why = hook(monkeypatch, capsys, root, "git stash && cp -t.git HEAD && git commit -am x")
    assert d == "deny" and "runs `git stash`" in why, why


def test_the_changelog_notes_it():
    text = since_0110()
    assert "#393" in text and "`prototype/*`" in text

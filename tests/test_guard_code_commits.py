"""#389 (spec #338, split from #341): under `code_writers = "ticket"`, a
session that doesn't write code is refused a `git commit` in a checkout of
`project.repo` that would carry a code path: what is staged, plus what `-a`
or a pathspec adds. Code written where the guard couldn't see it
(`python3 -c …`) is caught before it is committed. A commit whose contents
can't be read is asked in an attended session and refused in the conductor.

Through `workflow hook guard`, run as Claude Code runs it (a JSON event on
stdin, the decision on stdout), in temporary git repositories cloned from a
bare remote. The commands are data given to the hook; only the set-up runs."""

import io
import json
import os
import subprocess
import sys
import time

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from workflow import cli

# The tests' repositories never see the developer's own git configuration.
pytestmark = pytest.mark.usefixtures("_no_user_git_config")

PROFILE = ".claude/workflow/profile.toml"
CODE = "src/app.py"


def _toml(code_writers="ticket"):
    line = "" if code_writers is None else f'code_writers = "{code_writers}"\n'
    return (
        '[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n'
        "[guard]\n"
        f"{line}"
        'code_paths = ["src/**", "tests/**"]\n'
        'protected_paths = [".claude/**", ".github/workflows/**", "src/protected/**"]\n'
        "[run]\n"
        'ticket_environment = "workflow-ticket"\n'
        'conductor_environment = "workflow-conductor"\n'
    )


def _clone(tmp_path, code_writers="ticket", branch="feature", name="proj"):
    """A clone of a bare remote (`…/acme/demo.git`) on `branch`, with code
    (`src/`, `tests/`), docs and a protected folder inside a code path."""
    seed = tmp_path / f"{name}-seed"
    seed.mkdir(parents=True)
    git(seed, "init", "-q", "-b", "main")
    files = {
        PROFILE: _toml(code_writers),
        ".claude/workflow/lock.json": '{"kit_version": "0.1.17"}\n',
        CODE: "a = 1\n",
        "src/protected/keep.py": "k = 1\n",
        "tests/test_app.py": "def test_a():\n    pass\n",
        "docs/guide.md": "# Guide\n",
        ".gitignore": "src/build/\n",
    }
    for f, text in files.items():
        (seed / f).parent.mkdir(parents=True, exist_ok=True)
        (seed / f).write_text(text)
    git(seed, "add", "-A")
    git(seed, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "init")
    bare = tmp_path / f"{name}-remote" / "acme" / "demo.git"
    bare.parent.mkdir(parents=True)
    git(tmp_path, "clone", "-q", "--bare", str(seed), str(bare))
    root = tmp_path / name
    git(tmp_path, "clone", "-q", str(bare), str(root))
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    if branch != "main":
        git(root, "checkout", "-q", "-b", branch)
    return root


@pytest.fixture
def proj(tmp_path):
    return _clone(tmp_path)


def hook(monkeypatch, capsys, root, command, role=None, mode=None, cwd=None):
    """`workflow hook guard` given a Bash event: (decision, reason), the
    decision "allow" when the hook prints nothing."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setattr(cli, "_STARTED", time.monotonic())  # each call its own time budget
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    if role is None:
        monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    else:
        monkeypatch.setenv("WORKFLOW_ROLE", role)
    monkeypatch.chdir(root)
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or root)}
    if mode is not None:
        event["permission_mode"] = mode
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(event).encode()), encoding="utf-8"))
    assert cli.main(["hook", "guard"]) == 0
    out = capsys.readouterr().out
    if not out.strip():
        return "allow", ""
    h = json.loads(out)["hookSpecificOutput"]
    return h["permissionDecision"], h["permissionDecisionReason"]


# A session that doesn't write code under "ticket": (WORKFLOW_ROLE, branch).
NOT_TICKET = {
    "attended": (None, "feature"),
    "conductor": ("conductor", "feature"),
    "branch-only ticket session": (None, "claude/build-1"),
    "mistyped WORKFLOW_ROLE": ("tikcet", "feature"),
}


def _on(root, branch):
    if branch != "feature":
        git(root, "checkout", "-q", "-B", branch)


def _change(root, path, text="changed\n"):
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)


# What each case sets up in the checkout, then the commit it judges.
def _staged_code(root):
    _change(root, CODE)
    git(root, "add", CODE)


def _staged_new_code(root):
    _change(root, "src/new/mod.py")
    git(root, "add", "src/new/mod.py")


def _staged_removal(root):
    git(root, "rm", "-q", "tests/test_app.py")


def _staged_rename_out_of_code(root):
    git(root, "mv", CODE, "docs/app.md")


def _changed_code(root):
    _change(root, CODE)


REFUSED = [
    (_staged_code, "git commit -m x"),
    (_staged_code, "git commit -qm 'a message naming docs/guide.md'"),
    (_staged_code, "git commit --amend --no-edit"),
    (_staged_new_code, "git commit -m x"),
    (_staged_removal, "git commit -m x"),
    (_staged_rename_out_of_code, "git commit -m x"),
    (_changed_code, "git commit -a -m x"),
    (_changed_code, "git commit -am x"),
    (_changed_code, "git commit -qam x"),
    (_changed_code, "git commit --all -m x"),
    (_changed_code, "git commit --inc -m x src/app.py"),
    (_changed_code, "printf 'y\\n' | git commit -p -m x"),
    (_changed_code, "git commit --patch -m x"),
    (_changed_code, "git commit -m x src/{app,util}.py"),
    (_changed_code, "git commit -m x {docs/guide.md,src/app.py}"),
    (_changed_code, "git commit -uno -m x src/app.py"),
    (_changed_code, "GIT_ICASE_PATHSPECS=1 git commit -m x SRC/APP.PY"),
    (_staged_code, "git commit --mess x"),
    (_changed_code, "git commit -m x src/app.py"),
    (_changed_code, "git commit -m x -- src"),
    (_changed_code, "git commit -m x 'src/*.py'"),
    (_changed_code, "git commit -o -m x src/app.py"),
    (_changed_code, "git commit -i -m x src/app.py"),
    (_changed_code, "git commit --message=x --only src/app.py"),
    (_changed_code, "cd src && git commit -m x app.py"),
    (_changed_code, "cd docs && git commit -m x ../src/app.py"),
    (_changed_code, "git -C src commit -m x app.py"),
    (_staged_code, "timeout 60 git commit -m x"),
    (_staged_code, "bash -c 'git commit -m x'"),
    (_staged_code, "echo ok; git commit -m x"),
    (_staged_code, "git merge --continue"),
    (_staged_code, "git cherry-pick --continue"),
    (_staged_code, "git revert --continue"),
    (_staged_code, "git rebase --continue"),
    (_staged_code, "git am --continue"),
    (_staged_code, "git merge --contin"),
]


@pytest.mark.parametrize("setup,command", REFUSED, ids=[f"{s.__name__}: {c}" for s, c in REFUSED])
@pytest.mark.parametrize("who", list(NOT_TICKET))
def test_a_commit_carrying_a_code_path_is_refused(tmp_path, monkeypatch, capsys, setup, command, who):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    setup(root)
    for mode in (None, "default", "bypassPermissions", "dontAsk"):
        d, why = hook(monkeypatch, capsys, root, command, role, mode)
        assert d == "deny", (who, mode, command, d, why)
        assert "commit" in why and "code path" in why and ("src/**" in why or "tests/**" in why), why
        assert "src/" in why or "tests/" in why, why


def test_the_refusal_names_the_path_and_what_to_do_instead(proj, monkeypatch, capsys):
    """Worded as the file tools' refusals (#340): the path, the code path it
    matches, and the way the skills offer instead."""
    _staged_code(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x")
    assert d == "deny" and why.startswith("[workflow guard, attended session]"), why
    assert "carries the code path `src/app.py` (src/**)" in why, why
    assert "**Run it unattended**" in why and "guard.code_writers" in why, why
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x", "conductor")
    assert d == "deny" and "the conductor writes no code" in why, why
    assert "`workflow:infra`" in why and "`for_owner`" in why, why
    _on(proj, "claude/build-1")
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x")
    assert d == "deny" and "only by its branch, `claude/build-1`" in why, why


def test_a_code_commit_is_refused_even_after_an_ask(proj, monkeypatch, capsys):
    _staged_code(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push --force origin feature; git commit -m x")
    assert d == "deny" and "code path" in why, why


def _docs_only(root):
    _change(root, "docs/guide.md")
    git(root, "add", "docs/guide.md")


def _docs_with_unstaged_code(root):
    _docs_only(root)
    _change(root, CODE)


def _docs_with_untracked_code(root):
    _docs_only(root)
    _change(root, "src/new.py")


def _docs_with_staged_code(root):
    _change(root, "docs/guide.md")
    _staged_code(root)


def _staged_protected_inside_code(root):
    _change(root, "src/protected/keep.py")
    git(root, "add", "src/protected/keep.py")


def _staged_workflow_file(root):
    _change(root, ".workflow/notes.md")
    git(root, "add", "-f", ".workflow/notes.md")


def _nothing(root):
    pass


ALLOWED = [
    (_docs_only, "git commit -m d"),
    (_changed_code, "git commit -m src/app.py"),
    (_changed_code, "git commit -F src/app.py"),
    (_changed_code, "git commit -C HEAD src/app.py --dry-run"),
    (_docs_with_unstaged_code, "git commit -m d"),
    (_docs_with_untracked_code, "git commit -m d"),
    (_docs_with_untracked_code, "git commit -am d"),
    (_docs_with_unstaged_code, "git commit -m d docs/guide.md"),
    (_docs_with_staged_code, "git commit -m d docs/guide.md"),
    (_docs_with_staged_code, "git commit -m d -- docs"),
    (_docs_with_staged_code, "git commit --dry-run -m d"),
    (_staged_protected_inside_code, "git commit -m p"),
    (_staged_workflow_file, "git commit -m w"),
    (_nothing, "git commit --allow-empty -m e"),
    (_docs_with_staged_code, "git commit --short"),
    (_docs_with_staged_code, "git commit --porcelain"),
    (_docs_with_staged_code, "git commit -h"),
    (_changed_code, "git commit -m x docs"),
    (_staged_code, "git merge --abort"),
    (_staged_code, "git log -1 --format=%s"),
]


@pytest.mark.parametrize("setup,command", ALLOWED, ids=[f"{s.__name__}: {c}" for s, c in ALLOWED])
@pytest.mark.parametrize("who", list(NOT_TICKET))
def test_a_commit_carrying_no_code_path_goes_through(tmp_path, monkeypatch, capsys, setup, command, who):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    setup(root)
    d, why = hook(monkeypatch, capsys, root, command, role)
    assert d == "allow", (who, command, why)


def test_staged_code_counts_with_include_and_not_with_only(proj, monkeypatch, capsys):
    """A pathspec commits only what it names (`--only`, git's default),
    unless `-i` adds the staged files to it."""
    _docs_with_staged_code(proj)
    assert hook(monkeypatch, capsys, proj, "git commit -m d docs/guide.md")[0] == "allow"
    d, why = hook(monkeypatch, capsys, proj, "git commit -i -m d docs/guide.md")
    assert d == "deny" and "`src/app.py`" in why, why
    d, why = hook(monkeypatch, capsys, proj, "git commit --include -m d docs/guide.md")
    assert d == "deny" and "`src/app.py`" in why, why


def test_a_pathspec_from_a_file(proj, monkeypatch, capsys):
    _changed_code(proj)
    _change(proj, ".workflow/specs.txt", "src/app.py\n")
    _change(proj, ".workflow/docs.txt", "docs/guide.md\n")
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x --pathspec-from-file=.workflow/specs.txt")
    assert d == "deny" and "`src/app.py`" in why, why
    assert hook(monkeypatch, capsys, proj, "git commit -m x --pathspec-from-file .workflow/docs.txt")[0] == "allow"


def test_a_commit_in_a_claude_code_worktree(proj, monkeypatch, capsys):
    wt = proj / ".claude/worktrees/side"
    git(proj, "worktree", "add", "-q", "-b", "side", str(wt))
    _staged_code(wt)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x", cwd=wt)
    assert d == "deny" and "`src/app.py` (in the worktree `.claude/worktrees/side`)" in why, why
    d, why = hook(monkeypatch, capsys, proj, f"git -C {wt} commit -m x")
    assert d == "deny" and "code path" in why, why
    d, why = hook(monkeypatch, capsys, proj, "cd .claude/worktrees/side && git commit -m x")
    assert d == "deny" and "code path" in why, why


def test_a_commit_in_another_clone_is_left_to_the_push_rule(proj, tmp_path, monkeypatch, capsys):
    other = _clone(tmp_path, name="other")
    _staged_code(other)
    assert hook(monkeypatch, capsys, proj, f"git -C {other} commit -m x")[0] == "allow"
    assert hook(monkeypatch, capsys, proj, f"cd {other} && git commit -m x")[0] == "allow"
    assert hook(monkeypatch, capsys, proj, "git commit -m x", cwd=other)[0] == "allow"
    # Nor a repository of its own nested inside the project.
    nested = proj / "vendor/lib"
    nested.mkdir(parents=True)
    git(nested, "init", "-q", "-b", "main")
    _change(nested, CODE)
    git(nested, "add", CODE)
    assert hook(monkeypatch, capsys, proj, "cd vendor/lib && git commit -m x")[0] == "allow"


def test_a_ticket_session_commits_code_as_today(proj, monkeypatch, capsys):
    _on(proj, "claude/build-1")
    for setup, command in REFUSED:
        git(proj, "reset", "-q", "--hard")
        git(proj, "clean", "-qfd")
        setup(proj)
        for role in ("ticket", " Ticket "):
            d, why = hook(monkeypatch, capsys, proj, command, role)
            assert d == "allow" and "code path" not in why, (command, role, why)


# Options whose value is the next word: a code path there is never a pathspec.
VALUE_OPTIONS = ["-F", "-C", "-c", "-t", "--author", "--date", "--trailer", "--cleanup", "--template", "--fixup", "--squash", "--reuse-message", "--file"]


@pytest.mark.parametrize("option", VALUE_OPTIONS)
def test_an_options_value_is_not_a_pathspec(proj, monkeypatch, capsys, option):
    _changed_code(proj)
    d, why = hook(monkeypatch, capsys, proj, f"git commit {option} src/app.py -m x")
    assert d == "allow", (option, why)
    # The word after the value is a pathspec again.
    d, why = hook(monkeypatch, capsys, proj, f"git commit {option} docs/guide.md -m x src/app.py")
    assert d == "deny" and "`src/app.py`" in why, (option, why)


UNREAD_SPECS = [
    'F=src/app.py; git commit -m x "$F"',
    "git commit -m x $(echo src/app.py)",
    "git commit -m x ~/src/app.py",
    "echo src/app.py | xargs git commit -m x",
    "find src -name app.py -exec git commit -m x {} +",
    "echo src/app.py | git commit -m x --pathspec-from-file=/dev/stdin",
]


@pytest.mark.parametrize("command", UNREAD_SPECS)
def test_pathspecs_the_guard_cant_read_are_asked_when_code_could_be_carried(proj, monkeypatch, capsys, command):
    _changed_code(proj)
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell" in why and "`src/app.py`" in why, (command, why)
    d, why = hook(monkeypatch, capsys, proj, command, "conductor")
    assert d == "deny" and "can't tell" in why, (command, why)


@pytest.mark.parametrize("command", UNREAD_SPECS)
def test_pathspecs_the_guard_cant_read_go_through_when_no_code_changed(proj, monkeypatch, capsys, command):
    _docs_with_untracked_code(proj)
    assert hook(monkeypatch, capsys, proj, command)[0] == "allow", command


def test_a_process_substitution_pathspec_file(proj, monkeypatch, capsys):
    _changed_code(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x --pathspec-from-file=<(echo src/app.py)")
    assert d == "ask" and "process substitution" in why, why


@pytest.mark.parametrize("var", ["GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE"])
def test_a_variable_that_moves_what_git_reads(proj, monkeypatch, capsys, var):
    _docs_only(proj)
    d, why = hook(monkeypatch, capsys, proj, f"{var}=.git/alt git commit -m x")
    assert d == "ask" and f"`{var}`" in why, why
    d, why = hook(monkeypatch, capsys, proj, f"{var}=.git/alt git commit -m x", "conductor")
    assert d == "deny" and f"`{var}`" in why, why
    d, why = hook(monkeypatch, capsys, proj, f"{var}+=x git commit -m x")
    assert d == "ask" and f"`{var}`" in why, why
    # Other variables change nothing.
    assert hook(monkeypatch, capsys, proj, "GIT_EDITOR=true git commit -m x")[0] == "allow"


def test_a_work_tree_elsewhere_still_commits_to_the_project(proj, tmp_path, monkeypatch, capsys):
    """`--work-tree` outside the project commits into the project's own
    repository: judged from that work tree."""
    w = tmp_path / "w"
    (w / "src").mkdir(parents=True)
    (w / CODE).write_text("other\n")
    d, why = hook(monkeypatch, capsys, proj, f"git --work-tree={w} commit -a -m x")
    assert d == "deny" and "`src/app.py`" in why, why


def test_the_can_t_tell_reason_reads_as_one_sentence(proj, monkeypatch, capsys):
    _unreadable(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x")
    assert "). under" not in why and "; under `code_writers" in why, why


def test_in_solo_mode_a_refusal_elsewhere_stands_over_the_ask(tmp_path, monkeypatch, capsys):
    root = _clone(tmp_path)
    (root / PROFILE).write_text(_toml().replace('base_branch = "main"\n', 'base_branch = "main"\nruleset = false\n'))
    _unreadable(root)
    d, why = hook(monkeypatch, capsys, root, "git commit -m x; git push origin HEAD:main")
    assert d == "deny" and "index file" not in why, why


def test_more_pathspecs_the_guard_cant_read(proj, monkeypatch, capsys):
    """Brace sequences, brace lists past the guard's limit, globs where git
    reads pathspecs literally, quoted lines in a pathspec file, and pathspecs
    from a directory made earlier in the command: widened, and asked."""
    _changed_code(proj)
    many = ",".join(f"docs/a{n}" for n in range(70)) + ",src/app.py"
    _change(proj, ".workflow/quoted.txt", '"src/app.py"\n')
    for command in (
        "git commit -m x src/app{1..3}.py",
        f"git commit -m x {{{many}}}",
        "git --literal-pathspecs commit -m x src/*.py",
        "GIT_NOGLOB_PATHSPECS=1 git commit -m x src/*.py",
        "git commit -m x --pathspec-from-file=.workflow/quoted.txt",
        "mkdir -p new && cd new && git commit -m x ../src/app.py",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "can't tell" in why and "`src/app.py`" in why, (command, why)
    # A brace list within the limit is read.
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x {" + ",".join(f"docs/a{n}" for n in range(10)) + ",src/app.py}")
    assert d == "deny" and "`src/app.py`" in why, why


def test_a_directory_made_earlier_in_the_command(proj, monkeypatch, capsys):
    _changed_code(proj)
    d, why = hook(monkeypatch, capsys, proj, "mkdir -p new && cd new && git commit -am x")
    assert d == "deny" and "`src/app.py`" in why, why


def test_a_later_no_option_cancels_a_dry_run(proj, monkeypatch, capsys):
    _changed_code(proj)
    for command in ("git commit -am x --dry-run --no-dry-run", "git commit -am x --short --no-short", "git commit -am x --porcelain --no-porcelain"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "`src/app.py`" in why, (command, why)
    assert hook(monkeypatch, capsys, proj, "git commit -am x --no-dry-run --dry-run")[0] == "allow"


@pytest.mark.parametrize("command", ["git am -r", "git am --resolved", "git am --resol"])
def test_git_am_resolved_finishes_a_commit(proj, monkeypatch, capsys, command):
    _staged_code(proj)
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "deny" and "`src/app.py`" in why, why


def test_a_repository_moved_by_variables_from_outside_the_project(proj, tmp_path, monkeypatch, capsys):
    w = tmp_path / "w"
    w.mkdir()
    d, why = hook(monkeypatch, capsys, proj, f"cd {w} && GIT_DIR={proj / '.git'} GIT_WORK_TREE={w} git commit -a -m x")
    assert d == "ask" and "`GIT_DIR`" in why, why


def test_core_worktree_is_read_as_git_reads_it(proj, tmp_path, monkeypatch, capsys):
    """The guard's reads take `-c core.worktree` as the commit does: in a
    repository git found itself, it keeps the project's own work tree."""
    w = tmp_path / "w"
    (w / "src").mkdir(parents=True)
    (w / CODE).write_text("other\n")
    assert hook(monkeypatch, capsys, proj, f"git -c core.worktree={w} commit -a -m x")[0] == "allow"
    _changed_code(proj)
    d, why = hook(monkeypatch, capsys, proj, f"git -c core.worktree={w} commit -a -m x")
    assert d == "deny" and "`src/app.py`" in why, why


def test_a_worktree_outside_claude_codes_folder(proj, tmp_path, monkeypatch, capsys):
    wt = tmp_path / "wt"
    git(proj, "worktree", "add", "-q", "-b", "side", str(wt))
    _staged_code(wt)
    d, why = hook(monkeypatch, capsys, proj, f"git -C {wt} commit -m x")
    assert d == "deny" and "`src/app.py`" in why and str(wt) in why, why


def test_a_code_file_touched_but_unchanged_isnt_carried(proj, monkeypatch, capsys):
    (proj / CODE).write_text((proj / CODE).read_text())
    os.utime(proj / CODE, (time.time() + 5, time.time() + 5))
    assert hook(monkeypatch, capsys, proj, "git commit -am x")[0] == "allow"


def test_a_repository_git_cant_place_is_asked(proj, monkeypatch, capsys):
    """`rev-parse` failing inside the project: asked, naming what failed."""
    _staged_code(proj)
    d, why = hook(monkeypatch, capsys, proj, "git --git-dir=nowhere commit -m x")
    assert d == "ask" and "`git rev-parse" in why, why


# ---------- a commit whose contents can't be read ----------


def _unreadable(root):
    """Staged code, then an index git can't read: every read of what the
    commit carries fails."""
    _staged_code(root)
    (root / ".git/index").write_bytes(b"garbage")


def test_an_unreadable_commit_is_asked_in_a_planning_session(proj, monkeypatch, capsys):
    _unreadable(proj)
    for command in ("git commit -m x", "git commit -am x", "git commit -m x src/app.py"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask", (command, d, why)
        assert "can't tell" in why and "index file" in why and "git diff" in why, why
        assert "would commit: `git diff --name-only` failed in `" in why, why
    # Asked of a branch-only or mistyped session too.
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x", "tikcet")
    assert d == "ask" and "index file" in why, why


@pytest.mark.parametrize("mode", ["bypassPermissions", "dontAsk"])
def test_an_unreadable_commit_is_refused_where_nobody_is_asked(proj, monkeypatch, capsys, mode):
    _unreadable(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x", mode=mode)
    assert d == "deny" and "index file" in why, why


def test_an_unreadable_commit_is_refused_in_the_conductor(proj, monkeypatch, capsys):
    _unreadable(proj)
    for mode in (None, "default", "bypassPermissions"):
        d, why = hook(monkeypatch, capsys, proj, "git commit -m x", "conductor", mode)
        assert d == "deny", (mode, why)
        assert "can't tell" in why and "index file" in why and "the conductor" in why, why


def test_an_unreadable_commits_ask_never_hides_a_refusal(proj, monkeypatch, capsys):
    _unreadable(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x; echo x > src/new.py")
    assert d == "deny" and "code path" in why, why
    # Another ask in the command joins it.
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x; git push origin HEAD:main")
    assert d == "ask" and "base branch" in why and "index file" in why, why


def test_an_unreadable_pathspec_file(proj, monkeypatch, capsys):
    _changed_code(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x --pathspec-from-file=missing.txt")
    assert d == "ask" and "missing.txt" in why, why
    d, why = hook(monkeypatch, capsys, proj, "git commit -m x --pathspec-from-file=missing.txt", "conductor")
    assert d == "deny" and "missing.txt" in why, why


def test_a_ticket_session_commits_what_it_cant_read_as_today(proj, monkeypatch, capsys):
    _on(proj, "claude/build-1")
    _unreadable(proj)
    assert hook(monkeypatch, capsys, proj, "git commit -m x", "ticket")[0] == "allow"


# ---------- under "any" and unanswered ----------


@pytest.mark.parametrize("code_writers", ["any", None])
def test_any_and_unanswered_decide_as_today(tmp_path, monkeypatch, capsys, code_writers):
    root = _clone(tmp_path, code_writers)
    cases = REFUSED + [(_unreadable, "git commit -m x"), (_changed_code, "git commit -m x --pathspec-from-file=missing.txt")]
    cases += [(_changed_code, c) for c in UNREAD_SPECS]
    cases += [(_staged_code, f"{v}=.git/alt git commit -m x") for v in ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE")]
    cases += [(_changed_code, f"git --work-tree={tmp_path / 'w'} commit -a -m x")]
    for setup, command in cases:
        for role in (None, "conductor", "tikcet"):
            git(root, "reset", "-q", "--hard")
            git(root, "clean", "-qfd")
            setup(root)
            d, why = hook(monkeypatch, capsys, root, command, role)
            assert "code path" not in why and "can't tell" not in why, (command, role, why)
            # `GIT_DIR=`-style prefixes are refused today in the conductor and a ticket session (a mistyped role is one here), by their own rule.
            assert d == "allow" or (role in ("conductor", "tikcet") and command.startswith("GIT_") and "setting `GIT_" in why), (command, role, why)
            (root / ".git/index").unlink(missing_ok=True)
    # A branch-only ticket session keeps a ticket session's rules.
    git(root, "reset", "-q", "--hard")
    git(root, "clean", "-qfd")
    _on(root, "claude/build-1")
    _staged_code(root)
    assert hook(monkeypatch, capsys, root, "git commit -m x")[0] == "allow"


def test_with_no_code_paths_nothing_is_code(tmp_path, monkeypatch, capsys):
    root = _clone(tmp_path)
    (root / PROFILE).write_text(_toml().replace('code_paths = ["src/**", "tests/**"]\n', ""))
    git(root, "commit", "-qam", "no code paths")
    git(root, "push", "-q", "origin", "HEAD:main")
    git(root, "fetch", "-q")
    _staged_code(root)
    assert hook(monkeypatch, capsys, root, "git commit -m x")[0] == "allow"


def test_the_hook_as_a_process(proj):
    """The same refusal from `workflow hook guard` started as Claude Code starts it."""
    _staged_code(proj)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(proj)}
    env.pop("WORKFLOW_ROLE", None)
    event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "cwd": str(proj), "permission_mode": "bypassPermissions"}
    p = subprocess.run([sys.executable, str(KIT / "scripts/workflow.py"), "hook", "guard"], input=json.dumps(event), capture_output=True, text=True, cwd=proj, env=env)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "code path" in out["permissionDecisionReason"]


# ---------- docs ----------


def test_enforcement_doc_lists_the_commit_rule():
    doc = (KIT / "docs/enforcement.md").read_text()
    section = doc[doc.index("**Who writes code**") :]
    for phrase in ("`git commit`", "`-a`", "pathspec", "can't tell", "asked", "the conductor", "#389"):
        assert phrase in section, phrase


def test_changelog_note():
    notes = since_0110()
    assert "#389" in notes and "commit" in notes

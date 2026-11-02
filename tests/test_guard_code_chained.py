"""#394 (spec #338, split from #341): under `code_writers = "ticket"`, a
commit and a push in one command are refused, so each is judged on its own
by the commit rule (#389) and the push rule (#390).

- A `git push` to `project.repo` in the same command as a git command that
  makes or finishes commits (`commit`, `merge`, `pull`, `cherry-pick`,
  `revert`, `am`, any `--continue`, and any git command the guard doesn't
  know only to move refs) is refused, whatever it carries, saying to push
  in a command of its own, on a `prototype/*` branch too. Beside one that
  only moves a ref it is asked as before, and refused while prototyping
  (#393). A chained push to another repository is as today.
- A `git add` before `git commit` in the same command counts toward what
  the commit carries: its pathspec, or for `-A` the changed and untracked
  files; one the guard can't read plainly counts every changed and
  untracked file. A `git add` after it that may run first, or any other git
  command before it that may stage what the guard doesn't read, makes it a
  commit the guard can't tell about.
- Under `"any"` or with `code_writers` absent, as today.

Through `workflow hook guard`, run as Claude Code runs it, in temporary git
repositories cloned from a bare remote (`…/acme/demo.git`). The commands are
data given to the hook; only the set-up runs."""

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from test_guard_code_commits import CODE, NOT_TICKET, _change, _clone, _on, hook
from workflow import guard as guard_mod

pytestmark = pytest.mark.usefixtures("_no_user_git_config")

OWN = "push in a command of its own"
DOLLAR = "$"  # kept apart, so this file's text never reads as a shell expansion to a guard reading it


@pytest.fixture
def proj(tmp_path):
    return _clone(tmp_path)


def _other_remote(tmp_path):
    bare = tmp_path / "other-remote" / "acme" / "elsewhere.git"
    bare.parent.mkdir(parents=True)
    git(tmp_path, "init", "-q", "--bare", str(bare))
    return bare


# ---------- a `git add` before the commit ----------


@pytest.mark.parametrize("who", list(NOT_TICKET))
@pytest.mark.parametrize(
    "command",
    [
        "git add -A && git commit -m x",
        "git add --all && git commit -m x",
        "git add . && git commit -m x",
        "git add src/app.py && git commit -m x",
        "git add src && git commit -m x",
        "git add 'src/*.py' && git commit -m x",
        "git add docs/guide.md src/app.py && git commit -m x",
        "git stage -A && git commit -m x",
        "git-add -A && git commit -m x",
        "git add -A; git commit -m x",
        "cd docs && git add -A && git commit -m x",
        "git add -vA && git commit -m x",
        "git add --al && git commit -m x",
    ],
)
def test_a_git_add_of_a_changed_code_path_before_a_commit_is_refused(tmp_path, monkeypatch, capsys, who, command):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    _change(root, CODE)  # changed, not staged: only the `git add` stages it
    _change(root, "docs/guide.md")
    d, why = hook(monkeypatch, capsys, root, command, role)
    assert d == "deny" and "carries the code path `src/app.py` (src/**)" in why, (who, command, why)


@pytest.mark.parametrize("who", list(NOT_TICKET))
def test_an_untracked_code_file_added_before_a_commit_is_refused(tmp_path, monkeypatch, capsys, who):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    _change(root, "src/new.py")
    for command in ("git add -A && git commit -m x", "git add . && git commit -m x", "git add src/ && git commit -m x"):
        d, why = hook(monkeypatch, capsys, root, command, role)
        assert d == "deny" and "`src/new.py`" in why, (who, command, why)
    # An ignored file is added only by `-f`.
    _change(root, "src/build/out.py")
    git(root, "add", "src/new.py")
    git(root, "commit", "-qm", "new")  # (as a ticket session would have: the test's own set-up)
    assert hook(monkeypatch, capsys, root, "git add -A && git commit -m x", role)[0] == "allow", who
    d, why = hook(monkeypatch, capsys, root, "git add -f src/build && git commit -m x", role)
    assert d == "deny" and "`src/build/out.py`" in why, (who, why)


@pytest.mark.parametrize("who", list(NOT_TICKET))
@pytest.mark.parametrize(
    "command",
    [
        "git add docs/guide.md && git commit -m d",
        "git add docs && git commit -m d",
        "git add 'docs/*.md' && git commit -m d",
        "cd docs && git add . && git commit -m d",
        "git add -n -A && git commit -m d",
        "git add docs/guide.md && git commit -m d -- docs/guide.md",
        "git status && git add docs/guide.md && git commit -m d",
        "git add && git commit -m d",
        "git add -A && git commit -m d -- docs/guide.md",
    ],
)
def test_a_git_add_of_docs_beside_an_unrelated_code_change_goes_through(tmp_path, monkeypatch, capsys, who, command):
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    _change(root, CODE)  # changed, never staged
    _change(root, "docs/guide.md")
    git(root, "add", "docs/guide.md")  # (for the commit naming its pathspec after the add)
    git(root, "reset", "-q")
    assert hook(monkeypatch, capsys, root, command, role) == ("allow", ""), (who, command)


@pytest.mark.parametrize(
    "command",
    [
        "git add -u && git commit -m x",
        "git add :/ && git commit -m x",
        "git add ':(top)docs' && git commit -m x",
        "git add --pathspec-from-file=list.txt && git commit -m x",
        "git -C docs add guide.md && git commit -m x",
        "git --no-pager add docs/guide.md && git commit -m x",
        "env git add docs/guide.md && git commit -m x",
        "ls docs/*.md | xargs git add && git commit -m x",
        "git add " + DOLLAR + "F && git commit -m x",
        "git add " + DOLLAR + "(cat list.txt) && git commit -m x",
        "git add --frobnicate docs && git commit -m x",
        "GIT_LITERAL_PATHSPECS=1 git add docs && git commit -m x",
    ],
)
def test_a_git_add_it_cant_read_plainly_counts_every_change(tmp_path, monkeypatch, capsys, command):
    """It counts as carrying every changed and untracked file: refused with
    a code change, through with docs only."""
    root = _clone(tmp_path)
    (root / "list.txt").write_text("docs/guide.md\n")
    _change(root, "docs/guide.md")
    for role in (None, "conductor"):
        assert hook(monkeypatch, capsys, root, command, role) == ("allow", ""), (command, role)
    _change(root, CODE)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, root, command, role)
        assert d == "deny" and "may carry the code path `src/app.py` (src/**)" in why and "can't read plainly" in why, (command, role, why)
    _change(root, "src/new.py")
    git(root, "checkout", "-q", "--", CODE)
    d, why = hook(monkeypatch, capsys, root, command)
    assert d == "deny" and "`src/new.py`" in why, (command, why)


def test_a_git_add_in_another_checkout_counts_only_there(proj, tmp_path, monkeypatch, capsys):
    other = _clone(tmp_path, name="other")
    _change(other, CODE)
    _change(proj, "docs/guide.md")
    git(proj, "add", "docs/guide.md")
    assert hook(monkeypatch, capsys, proj, f"cd {other} && git add -A && cd {proj} && git commit -m d") == ("allow", "")
    _change(proj, CODE)
    d, why = hook(monkeypatch, capsys, proj, f"cd {other} && git add -A && cd {proj} && git add src && git commit -m d")
    assert d == "deny" and "`src/app.py`" in why, why


def test_a_git_add_on_a_prototype_branch_meets_the_prototype_exception_first(tmp_path, monkeypatch, capsys):
    root = _clone(tmp_path)
    git(root, "checkout", "-q", "-b", "prototype/x")
    _change(root, CODE)
    assert hook(monkeypatch, capsys, root, "git add -A && git commit -m wip") == ("allow", "")
    d, why = hook(monkeypatch, capsys, root, "git add -A && git commit -m wip", "conductor")
    assert d == "deny" and "`src/app.py`" in why, why


# ---------- other git commands before the commit ----------


@pytest.mark.parametrize(
    "command",
    [
        "git rm -q --cached " + DOLLAR + "F && git commit -m x",
        "git restore --source=main --staged docs && git commit -m x",
        "git restore -s main docs && git commit -am x",
        "git cherry-pick -n HEAD && git commit -m x",
        "git merge --squash main; git commit -m x",
        "git checkout main -- docs/guide.md && git commit -m x",
        "git stash pop && git commit -am x",
        "git reset --soft HEAD~1 && git commit -m x",
        "git restore --staged --source=main docs && git commit -m x",
        "git update-index --add docs/guide.md && git commit -m x",
        "git read-tree main && git commit -m x",
        "git apply --cached x.patch && git commit -m x",
        "git checkout --orphan fresh && git commit -m x",
        "git checkout --ours docs/guide.md && git commit -am x",
        "git checkout -m main && git commit -m x",
        "git fetch --update-head-ok origin main:feature && git commit -m x",
        "git push . main:feature && git commit -m x",
        "git ci && git commit -m x",
        "git rm -q --cached '*.py' && git commit -m x",
        "git rm -r -q --cached ':(top)src' && git commit -m x",
        "git reset --soft HEAD~1 -q && git commit -m x",
        "git reset main && git commit -m x",
        "for b in 1 2; do git commit -m x; git checkout main -- src; done",
        "git commit -m x & git stash pop",
    ],
)
def test_another_git_command_that_may_change_what_is_staged_before_a_commit(proj, monkeypatch, capsys, command):
    """What it stages isn't read: the commit is one the guard can't tell
    about, asked in a planning session and refused in the conductor."""
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "can't tell what `git commit` would commit" in why and "may change what it commits" in why, (command, why)
    d, why = hook(monkeypatch, capsys, proj, command, "conductor")
    assert d == "deny" and "can't tell what `git commit` would commit" in why, (command, why)


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b fresh && git commit -m d",
        "git checkout -q -b fresh main && git add docs/guide.md && git commit -m d",
        "git switch -c fresh && git commit -m d",
        "git switch main && git commit -m d",
        "git branch fresh && git tag v9 && git commit -m d",
        "git fetch origin && git commit -m d",
        "git config user.name me && git commit -m d",
        "git log -1 && git diff --stat && git commit -m d",
        "git commit -m a && git commit -m d",
        "git stash list && git commit -m d",
        "git rm -q docs/old.md && git commit -m d",
        "git mv docs/guide.md docs/g.md && git commit -m d",
        "git restore docs/guide.md && git restore --staged docs/x.md && git commit -m d",
        "git reset && git add docs/guide.md && git commit -m d",
        "git reset -q HEAD -- docs && git add docs/guide.md && git commit -m d",
        "git commit -m d && git stash pop",
        "git restore --staged 'docs/*.md' && git commit -m d",
        "git commit -m \"$(cat <<'EOF'\nd\n\nmore\nEOF\n)\" && git stash pop",
        "git commit -m \"$(cat <<-'EOF'\nd\n\tEOF\n)\" && git stash pop",
    ],
)
def test_git_commands_that_leave_what_is_staged_before_a_commit_go_through(proj, monkeypatch, capsys, command):
    _change(proj, CODE)  # changed, never staged
    _change(proj, "docs/guide.md")
    git(proj, "add", "docs/guide.md")
    for role in (None, "conductor"):
        assert hook(monkeypatch, capsys, proj, command, role) == ("allow", ""), (command, role)


def test_a_quoted_heredoc_that_doesnt_end_its_substitution_isnt_taken_out(proj, monkeypatch, capsys):
    _change(proj, CODE)
    command = "git commit -m \"" + DOLLAR + "(cat <<'EOF'\nd\nEOF\ntrue)\" & git add src/app.py & echo \"\nEOF\n)\""
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "ask" and "a later part runs `git add`" in why, why


def test_a_git_add_after_the_commit_that_may_run_first(proj, monkeypatch, capsys):
    """In a loop, a pipeline or the background it may run first: when it
    would stage a code path, the commit is one the guard can't tell about
    (asked; refused in the conductor). Staging docs only, or in a plain
    sequence, which runs in order: through."""
    _change(proj, "docs/guide.md")
    git(proj, "add", "docs/guide.md")
    for command in ("git commit -m d -- docs/guide.md && git add -A", "for i in 1 2; do git commit -m d; git add -A; done"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    _change(proj, CODE)
    for command in ("git commit -m d && git add -A", "git commit -m d; git add -A", "git commit -m d || git add src"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    for command in ("for i in 1 2; do git commit -m d; git add -A; done", "git commit -m d & git add src", "git commit -m d | git add -A"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "a later part runs `git add`" in why and "`src/app.py`" in why, (command, why)
        d, why = hook(monkeypatch, capsys, proj, command, "conductor")
        assert d == "deny" and "`src/app.py`" in why, (command, why)


@pytest.mark.parametrize(
    "xargs",
    ["xargs -I{}", "xargs -0I {}", "xargs -rI {}", "xargs --replace", "xargs -0 -r -n 1 -P 2 --null --no-run-if-empty -d x", "xargs -i", "xargs"],
)
def test_xargs_add_with_its_own_options_and_docs_only_goes_through(proj, monkeypatch, capsys, xargs):
    """xargs's options read as GNU's getopt reads them: its replace word stands in its paths, not its subcommand, and
    the rest are ordinary: no push, and docs only."""
    _change(proj, "docs/guide.md")
    tail = " {}" if ("I" in xargs or "replace" in xargs or "-i" in xargs) else ""
    for role in (None, "conductor"):
        command = f"git diff --name-only docs | {xargs} git add{tail} && git commit -m d"
        assert hook(monkeypatch, capsys, proj, command, role) == ("allow", ""), (command, role)
    # With a code change, every change counts (`xargs` gives the names), never a push.
    _change(proj, CODE)
    d, why = hook(monkeypatch, capsys, proj, f"git diff --name-only | {xargs} git add{tail} && git commit -m d")
    assert d == "deny" and "may carry the code path `src/app.py`" in why and OWN not in why, why


def test_a_reset_or_restore_before_finishing_a_merge(proj, monkeypatch, capsys):
    """During a merge, a reset may end it (the commit then carries everything staged after) or take a parent's version
    of a path: the commit is one the guard can't tell about."""
    git(proj, "checkout", "-q", "-b", "other")
    _change(proj, CODE)
    git(proj, "commit", "-qam", "code")
    git(proj, "checkout", "-q", "feature")
    _change(proj, "docs/guide.md")
    git(proj, "commit", "-qam", "docs")
    git(proj, "merge", "-q", "--no-commit", "--no-ff", "other")
    for command in (
        "git reset && git add -A && git commit -m m",
        "git reset -- src/app.py && git commit -m m",
        "git restore --staged src/app.py && git commit -m m",
        "git checkout -b tmp && git commit -m m",
        "git checkout feature && git commit -m m",
        "git stash && git commit -m m",
        "git switch -c tmp && git commit -m m",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "may change what it commits" in why, (command, why)
        d, why = hook(monkeypatch, capsys, proj, command, "conductor")
        assert d == "deny", (command, why)
    # Finishing it as it stands (the merge's own changes carry no code), beside reads or a tag: through.
    for command in (
        "git commit -m m",
        "git status && git diff --stat && git commit -m m",
        "git tag pre && git commit -m m",
        "git config user.name me && git commit -m m",
        "git fetch origin && git commit -m m",
        "git rm -q docs/guide.md && git commit -m m",
        "git branch side && git commit -m m",
    ):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command


def test_a_later_add_with_another_work_tree_that_may_run_first(proj, tmp_path, monkeypatch, capsys):
    _change(proj, "docs/guide.md")
    git(proj, "add", "docs/guide.md")
    d, why = hook(monkeypatch, capsys, proj, f"git commit -m d & git --work-tree={tmp_path} add -A")
    assert d == "ask" and "another work tree" in why, why
    d, why = hook(monkeypatch, capsys, proj, f"git commit -m d & git --work-tree={tmp_path} add -A", "conductor")
    assert d == "deny" and "another work tree" in why, why
    assert hook(monkeypatch, capsys, proj, f"git commit -m d && git --work-tree={tmp_path} add -A") == ("allow", "")


def test_two_commits_after_an_add_each_read_on_their_own(proj, monkeypatch, capsys):
    """The second commit's reading isn't left with the first's (no note naming a file list)."""
    _change(proj, "docs/guide.md")
    _change(proj, "docs/a.md")
    for role in (None, "conductor"):
        assert hook(monkeypatch, capsys, proj, "git add docs/a.md docs/guide.md; git commit -m x docs/a.md; git commit -m y", role) == ("allow", ""), role


def test_a_git_add_in_a_substitution_runs_before_the_commit(proj, monkeypatch, capsys):
    _change(proj, CODE)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, 'git commit -m "' + DOLLAR + '(git add -A)"', role)
        assert d == "deny" and "`src/app.py`" in why, (role, why)


def test_the_refusal_of_an_add_it_cant_read_says_so(proj, monkeypatch, capsys):
    """Refused as carrying every change, it says why, and how to name what it adds."""
    _change(proj, CODE)
    _change(proj, "docs/guide.md")
    d, why = hook(monkeypatch, capsys, proj, "git add -u docs && git commit -m d")
    assert d == "deny" and "may carry the code path `src/app.py`" in why and "can't read plainly" in why and "`git add <path>`" in why, why
    assert "ignored ones too" in why and "no global option, variable or wrapper" in why, why
    # `xargs git add` on its own beside a commit: counted as every change, never taken for a push.
    d, why = hook(monkeypatch, capsys, proj, "ls docs/*.md | xargs git add && git commit -m d")
    assert d == "deny" and "may carry" in why and OWN not in why, why
    # A code path it reads plainly: as any refusal.
    d, why = hook(monkeypatch, capsys, proj, "git add src && git add -u docs && git commit -m d")
    assert d == "deny" and "this commit carries the code path `src/app.py`" in why, why


def test_a_forced_add_the_guard_cant_read_counts_ignored_files(proj, monkeypatch, capsys):
    _change(proj, "src/build/out.py")  # ignored by the fixture's `.gitignore`
    for command in ("git -C . add -f src/build/out.py && git commit -m x", "git add -f " + DOLLAR + "F && git commit -m x", "git --no-pager add --fo src/build && git commit -m x"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "`src/build/out.py`" in why, (command, why)
    # Without `-f`, git adds no ignored file.
    assert hook(monkeypatch, capsys, proj, "git -C . add -A && git commit -m x") == ("allow", "")


def test_a_git_add_into_the_index_a_work_tree_commit_reads(proj, tmp_path, monkeypatch, capsys):
    """The index is the git directory's: a commit with another work tree commits what the add staged."""
    (tmp_path / "e").mkdir()
    _change(proj, CODE)
    d, why = hook(monkeypatch, capsys, proj, f"git add -A && git --work-tree={tmp_path / 'e'} commit -m x")
    assert d == "deny" and "carries the code path `src/app.py`" in why, why


def test_a_git_add_into_another_work_tree_or_index_is_cant_tell(proj, tmp_path, monkeypatch, capsys):
    (tmp_path / "e" / "src").mkdir(parents=True)
    (tmp_path / "e" / "src" / "app.py").write_text("edited\n")
    for command in (
        f"git --work-tree={tmp_path / 'e'} add -A && git commit -m x",
        f"GIT_WORK_TREE={tmp_path / 'e'} git add src/app.py && git commit -m x",
        "GIT_INDEX_FILE=/tmp/i git add -A && git commit -m x",
        f"git -c core.worktree={tmp_path / 'e'} add -A && git commit -m x",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "another work tree or into another index" in why, (command, why)
        d, why = hook(monkeypatch, capsys, proj, command, "conductor")
        assert d == "deny", (command, why)


def test_a_function_defined_in_the_command_may_run_its_commit_after_the_add(proj, monkeypatch, capsys):
    _change(proj, CODE)
    for command in ("f() { git commit -m d; }; git add -A; f", "function f { git commit -m d; }; git add -A; f"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "a later part runs `git add`" in why, (command, why)


def test_a_pathspec_commit_after_an_add_carries_only_what_it_names(proj, monkeypatch, capsys):
    _change(proj, CODE)
    _change(proj, "docs/guide.md")
    assert hook(monkeypatch, capsys, proj, "git add -A && git commit -m d -- docs/guide.md") == ("allow", "")
    _change(proj, "src/new.py")
    d, why = hook(monkeypatch, capsys, proj, "git add -A && git commit -m x -- src/new.py")
    assert d == "deny" and "`src/new.py`" in why, why
    d, why = hook(monkeypatch, capsys, proj, "git add -A && git commit -i -m d -- docs/guide.md")
    assert d == "deny" and "src/" in why, why


def test_a_git_add_it_cant_read_at_all_is_asked(proj, monkeypatch, capsys):
    """A read that fails counts as may, never as nothing staged."""
    _change(proj, "docs/guide.md")
    with monkeypatch.context() as m:
        m.setattr(guard_mod, "_changed_and_untracked", lambda *a, **k: (None, "`git diff` took too long"))
        d, why = hook(monkeypatch, capsys, proj, "git add -u && git commit -m d")
        assert d == "ask" and "couldn't read what `git add` stages" in why, why
        d, why = hook(monkeypatch, capsys, proj, "git add -u && git commit -m d", "conductor")
        assert d == "deny" and "couldn't read what `git add` stages" in why, why
        # A plain add it can't read counts every change, which it can't read either.
        d, why = hook(monkeypatch, capsys, proj, "git add docs && git commit -m d")
        assert d == "ask", why


# ---------- push in a command of its own ----------


def _docs_ready(root):
    """A docs change staged, the base fetched, and a docs commit to pick."""
    _change(root, "docs/guide.md")
    git(root, "add", "docs/guide.md")
    git(root, "fetch", "-q", "origin")


@pytest.mark.parametrize("who", list(NOT_TICKET))
@pytest.mark.parametrize(
    "command",
    [
        "git merge origin/main && git push",
        "git add -A && git commit -m x && git push",
        "git cherry-pick main && git push",
        "git merge --continue && git push",
        "git add docs/guide.md && git commit -m d && git push",
        "git commit -m d && git push origin feature",
        "git commit -m d; git push -u origin HEAD",
        "git pull && git push",
        "git pull --rebase origin main && git push origin HEAD",
        "git revert --no-edit HEAD && git push",
        "git am x.patch && git push",
        "git rebase --continue && git push origin feature",
        "git cherry-pick --cont && git push",
        "git commit --qu -m d && git push origin feature",
        "git pull --qui && git push",
        "git commit -m --abort && git push origin feature",
        "git merge --abort origin/main && git push origin feature",
        "git am --resolved && git push",
        "git commit -m d && git push git@github.com:acme/demo.git HEAD:refs/heads/feature",
        "git commit -m d && git -C docs push origin feature",
        "git commit -m d && git push --dry-run origin feature && git push origin feature",
        "git push origin feature; git commit -m d && git push origin feature",
        "for m in a b; do git commit -m $m; done; git push origin feature",
        "sh -c 'git commit -m d' && git push origin feature",
        "git -c user.name=me commit -m d && git push origin feature",
        "git commit-tree HEAD^{tree} -m d && git push origin feature",
    ],
)
def test_a_push_chained_with_a_commit_is_refused(tmp_path, monkeypatch, capsys, who, command):
    """Whatever it carries, docs only included: each is judged on its own."""
    role, branch = NOT_TICKET[who]
    root = _clone(tmp_path)
    _on(root, branch)
    git(root, "config", f"branch.{branch}.remote", "origin")
    _docs_ready(root)
    d, why = hook(monkeypatch, capsys, root, command.replace("feature", branch), role)
    assert d == "deny" and OWN in why, (who, command, why)


@pytest.mark.parametrize(
    "command",
    [
        "git ci -m d && git push origin feature",  # an alias, or a command git doesn't have
        "git " + DOLLAR + "SUB && git push origin feature",
        "git " + DOLLAR + "(echo commit) -m d && git push origin feature",
    ],
)
def test_a_push_chained_with_a_git_command_the_guard_cant_name_is_refused(proj, monkeypatch, capsys, command):
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        assert d == "deny" and OWN in why, (command, role, why)


def test_a_push_beside_xargs_git_is_refused(proj, monkeypatch, capsys):
    """`xargs git` takes its subcommand from its stdin: a git command the guard can't name."""
    _change(proj, CODE)
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, "echo commit -am wip | xargs git; git push origin feature", role)
        assert d == "deny" and OWN in why, (role, why)


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m d && git " + DOLLAR + "P",
        "git commit -m d; echo push | xargs git",
        "git " + DOLLAR + "A && git " + DOLLAR + "B",
        "git commit -m d; echo push | xargs -I{} git {} origin HEAD:main",
        "git commit -m d && git {push,origin,HEAD:main}",
        "git commit -m d && echo push | xargs -I % git %",
        "git commit -m d && echo push | xargs -IX git X origin HEAD",
        "git commit -m d && echo push | xargs --replace=X git X",
        "git commit -m d && echo push | xargs -I log git log",
        "git commit -m d && echo push | xargs -i git {}",
        "git commit -m d && echo push | /usr/bin/xargs -I log git log",
        "git commit -m d && echo push | xargs --repl=log git log",
        "git commit -m d && echo push | xargs -0Ilog git log",
        "git commit -m d && echo push | xargs -I log env -i git log",
        "git commit -m d && echo push | xargs --r=log git log",
        "git commit -m d && echo push | xargs --max-lines -I log git log",
        "git commit -m d && echo push | xargs --max-a 1 -I log git log",
        "git commit -m d && echo push | xargs -I log xargs git log",
        "git commit -m d && echo push | env -S 'xargs -I log git log'",
        "git commit -m d && echo push | xargs --frobnicate git log",
    ],
)
def test_a_git_command_that_may_itself_be_the_push_beside_a_commit_is_refused(proj, monkeypatch, capsys, command):
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, command, role)
        assert d == "deny" and OWN in why and "is a push" in why, (command, role, why)
    assert hook(monkeypatch, capsys, proj, "git status && git " + DOLLAR + "P") == ("allow", "")


def test_a_push_elsewhere_before_a_commit_leaves_it_as_today(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "o", str(other))
    _docs_ready(proj)
    for command in ("git push o HEAD:x && git commit -m d", f"git push {other} HEAD:x; git commit -m d", "git push https://github.com/acme/elsewhere.git HEAD:x && git commit -m d"):
        for role in (None, "conductor"):
            assert hook(monkeypatch, capsys, proj, command, role) == ("allow", ""), (command, role)
    # Into this repository (its working tree may be updated, `updateInstead`): can't tell.
    d, why = hook(monkeypatch, capsys, proj, "git push . main:x && git commit -m d")
    assert d == "ask" and "an earlier part runs `git push .`" in why, why


def test_a_push_beside_what_makes_no_commit_is_asked_as_before(proj, monkeypatch, capsys):
    """Stopping a merge, a cherry-pick or a rebase, or a commit's dry run, makes no commit: beside a ref move
    the push is asked as before (refused in the conductor)."""
    for command in (
        "git merge --abort && git push origin feature",
        "git cherry-pick --quit; git push origin feature",
        "git rebase --abo && git push origin feature",
        "git commit --dry-run && git push origin feature",
        "git switch -c x && git push origin x",
        "git reset --hard HEAD && git push origin feature",
    ):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "can't tell" in why and OWN not in why, (command, why)
        d, why = hook(monkeypatch, capsys, proj, command, "conductor")
        assert d == "deny" and "can't tell" in why and "may make or finish commits" not in why, (command, why)


def test_ticket_sessions_decide_as_today(proj, monkeypatch, capsys):
    """A ticket session writes code: none of this ticket's rules apply to it."""
    _on(proj, "claude/build-1")
    git(proj, "config", "branch.claude/build-1.remote", "origin")
    _change(proj, CODE)
    for command in ("git add -A && git commit -m x && git push origin claude/build-1", "git commit -am x; git push -u origin HEAD", "git reset --soft HEAD~1 && git commit -m x"):
        assert hook(monkeypatch, capsys, proj, command, "ticket") == ("allow", ""), command


def test_a_bare_push_beside_a_commit_after_a_branch_change(proj, tmp_path, monkeypatch, capsys):
    """The branch git picks a bare push's remote by may change: refused when any remote of ours is one it may pick."""
    _docs_ready(proj)
    d, why = hook(monkeypatch, capsys, proj, "git switch -c x && git commit -m d && git push")
    assert d == "deny" and OWN in why, why
    # No remote of ours: as before.
    other = _other_remote(tmp_path)
    git(proj, "remote", "set-url", "--push", "origin", str(other))
    d, why = hook(monkeypatch, capsys, proj, "git switch -c x && git commit -m d && git push")
    assert d == "ask" and OWN not in why, why


def test_a_push_beside_a_commit_it_cant_otherwise_read_is_refused(proj, monkeypatch, capsys):
    """A push the guard can't read (a variable for its repository, a URL
    rewrite, `HOME=…`) that may go to `project.repo`, beside a commit: refused."""
    for command in (
        "git commit -m d && git push " + DOLLAR + "R feature",
        "git commit -m d && HOME=/tmp/h git push origin feature",
        "git commit -m d && git -c url.x.pushInsteadOf=y push origin feature",
        "git remote add up git@github.com:acme/demo.git && git commit -m d && git push up feature",
    ):
        for role in (None, "conductor"):
            d, why = hook(monkeypatch, capsys, proj, command, role)
            assert d == "deny" and OWN in why, (command, role, why)


def test_the_refusal_says_why_and_what_to_do(proj, monkeypatch, capsys):
    _docs_ready(proj)
    d, why = hook(monkeypatch, capsys, proj, "git commit -m d && git push origin feature")
    assert d == "deny" and why.startswith("[workflow guard, attended session]"), why
    assert "`git commit -m`" in why and "acme/demo" in why and "run the push in a command of its own" in why, why
    assert "judged by what it sends" in why and "unjudged" not in why and "makes or finish" not in why.partition("acme/demo`")[0], why
    assert "whatever it carries" in why and "conductor run" not in why, why
    d, why = hook(monkeypatch, capsys, proj, "git commit -m d && git push origin feature", "conductor")
    assert d == "deny" and "the conductor writes no code" in why and OWN in why, why


def test_the_same_push_on_its_own_afterwards_is_judged_by_the_push_rule(proj, monkeypatch, capsys):
    _docs_ready(proj)
    git(proj, "commit", "-qm", "d")
    assert hook(monkeypatch, capsys, proj, "git push origin feature") == ("allow", "")
    _change(proj, CODE)
    git(proj, "commit", "-qam", "code")
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "carries the code path `src/app.py` (src/**)" in why and OWN not in why, why


def test_a_chained_push_on_a_prototype_branch_is_refused(tmp_path, monkeypatch, capsys):
    root = _clone(tmp_path)
    git(root, "checkout", "-q", "-b", "prototype/x")
    _change(root, CODE)
    for command in ("git commit -am x && git push origin prototype/x", "git commit -am x && git push", "git add -A && git commit -m x; git push origin HEAD"):
        d, why = hook(monkeypatch, capsys, root, command)
        assert d == "deny" and OWN in why and "unjudged" in why and "may make or finish commits" in why, (command, why)
        assert "so its push is judged only in a command of its own" in why, why
    # Each on its own: the commit and the push to a prototype branch go through.
    assert hook(monkeypatch, capsys, root, "git commit -am x") == ("allow", "")
    git(root, "commit", "-qam", "x")
    assert hook(monkeypatch, capsys, root, "git push origin prototype/x") == ("allow", "")


def test_a_push_beside_reads_or_other_pushes_is_judged_as_before(proj, monkeypatch, capsys):
    _docs_ready(proj)
    git(proj, "commit", "-qm", "d")
    for command in (
        "git status && git push origin feature",
        "git fetch origin && git push origin feature",
        "git add docs/guide.md && git push origin feature",
        "git push origin feature && git push origin HEAD:refs/heads/feature-2",
        "git log -1 && git push origin feature",
    ):
        for role in (None, "conductor"):
            assert hook(monkeypatch, capsys, proj, command, role) == ("allow", ""), (command, role)


def test_a_chained_push_to_another_repository_decides_as_today(proj, tmp_path, monkeypatch, capsys):
    other = _other_remote(tmp_path)
    git(proj, "remote", "add", "o", str(other))
    _docs_ready(proj)
    for command in (
        "git commit -m d && git push o feature",
        f"git commit -m d && git push {other} HEAD:refs/heads/x",
        "git commit -m d && git push https://github.com/acme/elsewhere.git HEAD:refs/heads/x",
    ):
        for role in (None, "conductor"):
            d, why = hook(monkeypatch, capsys, proj, command, role)
            with monkeypatch.context() as m:
                m.setattr(guard_mod, "_push_code", lambda *a, **k: (None, None))
                today = hook(monkeypatch, capsys, proj, command, role)
            assert (d, why) == today and OWN not in why, (command, role, why)
    # A bare push whose remote is another repository's, beside a part that may move a ref, is asked as before (refused in
    # the conductor), as is one from another repository whose remotes aren't `project.repo`.
    git(proj, "config", "remote.pushDefault", "o")
    for command in ("git commit -m d && git push", f"git commit -m d && git -C {other} push"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "ask" and "can't tell" in why and OWN not in why, (command, why)
        d, why = hook(monkeypatch, capsys, proj, command, "conductor")
        assert d == "deny" and "can't tell" in why and OWN not in why, (command, why)


# ---------- as today ----------


AS_TODAY = [
    "git add -A && git commit -m x",
    "git add -u && git commit -m x",
    "git rm -q --cached docs/guide.md && git commit -m x",
    "git reset --soft HEAD && git commit -m x",
    "git commit -m d -- docs/guide.md && git add -A",
    "git commit -am x && git push origin feature",
    "git merge origin/main && git push",
    "git add -A && git commit -m x && git push",
    "git cherry-pick main && git push",
    "git merge --continue && git push",
    "git add docs/guide.md && git commit -m d && git push",
    "git ci -m d && git push origin feature",
    "echo commit -am x | xargs git; git push origin feature",
    "git commit -m d && git push o feature",
]


@pytest.mark.parametrize("code_writers", ["any", None])
@pytest.mark.parametrize("role", [None, "conductor"])
def test_under_any_or_absent_a_prototype_branch_decides_as_today(tmp_path, monkeypatch, capsys, code_writers, role):
    root = _clone(tmp_path, code_writers)
    git(root, "checkout", "-q", "-b", "prototype/x")
    _change(root, CODE)
    for command in ("git commit -am x && git push origin prototype/x", "git add -A && git commit -m x; git push"):
        assert hook(monkeypatch, capsys, root, command, role) == ("allow", ""), (code_writers, role, command)


@pytest.mark.parametrize("code_writers", ["any", None])
@pytest.mark.parametrize("role", [None, "conductor"])
def test_under_any_or_absent_every_case_decides_as_today(tmp_path, monkeypatch, capsys, code_writers, role):
    root = _clone(tmp_path, code_writers)
    git(root, "config", "branch.feature.remote", "origin")
    git(root, "remote", "add", "o", str(_other_remote(tmp_path)))
    _change(root, CODE)
    _change(root, "src/new.py")
    for command in AS_TODAY:
        assert hook(monkeypatch, capsys, root, command, role) == ("allow", ""), (code_writers, role, command)


# ---------- the changelog ----------


def test_the_changelog_says_it():
    text = since_0110()
    assert "#394" in text and "push in a command of its own" in text
    assert "git add" in text and "VERSION" not in text.partition("#394")[2].partition("\n**")[0]
    assert (KIT / "docs" / "enforcement.md").read_text().count("#394") >= 2

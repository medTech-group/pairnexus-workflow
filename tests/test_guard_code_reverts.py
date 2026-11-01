"""#392 (spec #338, split from #341): under `code_writers = "ticket"`, a
revert that exactly undoes a commit already on the base goes through #389's
commit rule and #390's push rule in a planning session. A commit made by
`git revert` names the commit it reverts ("This reverts commit <sha>"); when
that commit is on the base's remote ref and the revert's code paths are as
git's own revert of it leaves them (for a merge, of its change against its
first parent; `git merge-tree`), with no conflict in a code path, it is a
revert, not code. While a revert is in progress (`REVERT_HEAD`), its changes
are judged by that rule.
Any other revert is refused, offering GitHub's own **Revert** button where
it can revert the pull request, and otherwise a quick ticket. In the
conductor, a matched revert is allowed only for a commit the run's ledger
(the state block of `.workflow/run/body.md`) records the owner as allowing.
Under `"any"` or with `code_writers` absent, as today.

Through `workflow hook guard`, run as Claude Code runs it, in temporary git
repositories cloned from a bare remote (`…/acme/demo.git`). The commands are
data given to the hook; only the set-up runs."""

import json
import subprocess

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from test_guard_code_commits import CODE, NOT_TICKET, _change, _clone, _on, hook
from test_guard_code_merges import DOC, LINES, _commit, _edit
from workflow import guard as guard_mod
from workflow import state as state_mod

pytestmark = pytest.mark.usefixtures("_no_user_git_config")

PUSH = "git push origin feature"


def _on_base(root, change, msg="base", pr=None):
    """A change on the remote's base branch (`main`), as if a pull request
    had merged: with `pr`, a merge commit as GitHub's merge button writes
    it ("Merge pull request #<pr> from …"), else a plain commit. Returns
    the commit on the base, its full SHA."""
    here = git(root, "branch", "--show-current").strip()
    git(root, "checkout", "-q", "-B", "base-work", "origin/main")
    if pr is None:
        _commit(root, change, msg)
    else:
        git(root, "checkout", "-q", "-b", "pr-work")
        _commit(root, change, msg)
        git(root, "checkout", "-q", "base-work")
        git(root, "merge", "-q", "--no-ff", "-m", f"Merge pull request #{pr} from acme/fix\n\n{msg}", "pr-work")
        git(root, "branch", "-q", "-D", "pr-work")
    sha = git(root, "rev-parse", "HEAD").strip()
    git(root, "push", "-q", "origin", "base-work:main")
    git(root, "checkout", "-q", here)
    git(root, "branch", "-q", "-D", "base-work")
    return sha


@pytest.fixture
def proj(tmp_path):
    """A clone from a base whose code file has ten lines."""
    root = _clone(tmp_path)
    _on_base(root, lambda r: _change(r, CODE, LINES))
    return root


def _feature(root):
    git(root, "checkout", "-q", "-B", "feature", "origin/main")


def _merge_pr(root, pr=12):
    """A pull request merged into the base, changing line 5 of the code file
    and the guide; returns its merge commit."""
    return _on_base(root, lambda r: (_edit(r, CODE, "v5 = 5", "v5 = 'pr'"), _change(r, DOC, "# PR\n")), "fix", pr=pr)


def _revert(root, sha, *args):
    """`git revert` of `sha` (a merge by its first parent), as the skills make one."""
    mainline = ["-m", "1"] if len(git(root, "rev-list", "--parents", "-n1", sha).split()) > 2 else []
    return subprocess.run(["git", "revert", "--no-edit", *mainline, *args, sha], cwd=root, capture_output=True).returncode


def _run_body(root, ledger):
    s = state_mod.empty({})
    s["ledger"] = ledger
    body = "Run.\n\n" + state_mod.BEGIN + "\n```json\n" + json.dumps(s) + "\n```\n" + state_mod.END + "\n"
    (root / ".workflow/run").mkdir(parents=True, exist_ok=True)
    (root / ".workflow/run/body.md").write_text(body)


def _allowed(sha, **more):
    return {"what": "revert", "revert": sha, "at": "2026-11-01T00:00:00Z", "grant": "'yes, revert it' (chat 2026-11-01T00:00Z)", **more}


PLANNING = {k: v for k, v in NOT_TICKET.items() if k != "conductor"}


# ---------- a matched revert goes through ----------


@pytest.mark.parametrize("who", PLANNING)
def test_a_revert_of_a_merge_on_the_base_committed_and_pushed_goes_through(proj, monkeypatch, capsys, who):
    role, branch = PLANNING[who]
    merge = _merge_pr(proj)
    _feature(proj)
    _on(proj, branch)
    assert hook(monkeypatch, capsys, proj, f"git revert --no-edit -m 1 {merge}", role) == ("allow", "")  # it checks out content already committed
    assert _revert(proj, merge) == 0
    assert hook(monkeypatch, capsys, proj, f"git push origin {branch}", role) == ("allow", "")


def test_a_revert_after_a_later_change_two_lines_away_goes_through(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v7 = 7", "v7 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge) == 0
    assert (proj / CODE).read_text().count("'") == 2  # line 5 undone, line 7 kept
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_revert_of_a_plain_commit_on_the_base_goes_through(proj, monkeypatch, capsys):
    sha = _on_base(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'plain'"))
    _feature(proj)
    assert _revert(proj, sha) == 0
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_revert_in_progress_is_judged_by_the_revert_rule(proj, monkeypatch, capsys):
    """`git revert --no-commit` leaves `REVERT_HEAD`: finishing it is judged
    by the revert rule, the commit's own message aside."""
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v7 = 7", "v7 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    keeps = f"git commit -m 'Undo #12' -m 'This reverts commit {merge}.'"
    heredoc = f"git commit -m \"$(cat <<'EOF'\nUndo #12, which cost $5\n\nThis reverts commit {merge}.\nEOF\n)\""  # as Claude Code writes a message
    for command in ("git commit --no-edit", "git commit -a --no-edit", "git revert --continue", "cd src && git commit --no-edit", keeps, heredoc):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command
    git(proj, "commit", "-q", "-m", "Undo #12", "-m", f"This reverts commit {merge}.")
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


@pytest.mark.parametrize(
    "command, why",
    [
        ("git commit -m 'Undo #12'", 'leaves out the "This reverts commit'),
        ("git commit -m 'Undo' -m 'This reverts commit 0123456789abcdef0123456789abcdef01234567.'", 'leaves out the "This reverts commit'),
        ("git commit -F msg.txt", "`-F` takes its message from elsewhere, which the guard doesn't read"),
        ("git commit --amend --no-edit", "`--amend` folds it into the commit before it"),
        ("git commit --no-edit -- src/app.py", "a pathspec commits only part of it"),
        ("git add -A && git commit --no-edit", "the command also runs `git add -A`"),
        ("python3 -c 'pass'; git commit -a --no-edit", "the command also runs `python3 -c pass`"),
        ("git commit --no-edit && git checkout origin/main -- src/app.py", "the command also runs `git checkout origin/main -- src/app.py`"),
        ("git -c core.fsmonitor=./x.sh status && git commit --no-edit", "the command also runs `git -c core.fsmonitor=./x.sh status`"),
        ("git branch gone && git commit --no-edit", "the command also runs `git branch gone`"),
        ("git branch -uorigin/main && git commit --no-edit", "the command also runs `git branch -uorigin/main`"),
        ("sh x.sh git status && git commit --no-edit", "the command also runs `sh x.sh git status`"),
        ("git grep -Otrue -e v5 && git commit --no-edit", "the command also runs `git grep -Otrue -e v5`"),
        ("git --exec-path=/tmp status && git commit --no-edit", "the command also runs `git --exec-path=/tmp status`"),
        ("time -o src/app.py git status && git commit -a --no-edit", "the command also runs `git status`"),
        ("./git status && git commit --no-edit", "the command also runs `./git status`"),
        ("printf -v HOME /tmp/h && git commit --no-edit", "the command also runs `printf -v HOME /tmp/h`"),
        (": $((HOME=1)) && git commit --no-edit", "the command also runs `HOME=1`"),
        ("> docs/x.md; git commit --no-edit", "the command also runs `> docs/x.md`"),
        ('cd "$CLAUDE_PROJECT_DIR" <<< $[HOME=1]; git commit --no-edit', "the command also runs `cd"),
        ("GIT_LITERAL_PATHSPECS=$[HOME=1] git commit --no-edit", "it sets a value the shell expands for itself"),
        ('git commit --no-edit 2>"docs/log$[HOME=1]"', "it sets a value the shell expands for itself"),
        ("GIT_EDITOR=vim git commit --no-edit", "it sets `GIT_EDITOR` for itself"),
        ("env -u XDG_CONFIG_HOME git commit --no-edit", "it runs under `env`, which"),
        ("git commit -m 'This reverts commit x.' -m $(cat <<'EOF'\nUndo -a\nEOF\n)", "it sets a value the shell expands for itself"),
        ("git diff \"$(cat <<'EOF'\n--output=src/app.py\nEOF\n)\" && git commit -a --no-edit", "the command also runs `git diff"),
        ("echo <<EOF\n$[HOME=1]\nEOF\ngit commit --no-edit", "the command also runs `echo`"),
        ("cat <<EOF\n$[HOME=1]\nEOF\ngit commit --no-edit", "the command also runs `cat`"),  # `cat` may be a function the command defines
        ("cat() { :; }; cat <<EOF\n$[HOME=1]\nEOF\ngit commit --no-edit", "the command also runs"),
        ("git status <<< $[HOME=1]; git commit --no-edit", "the command also runs `git status`"),
        ('ls "docs/$[HOME=1]" && git commit --no-edit', "the command also runs `ls"),
        (": <<< $[HOME=1]; git commit --no-edit", "the command also runs `:`"),
        ("[ -v 'BASH_VERSINFO[HOME=1]' ] && git commit --no-edit", "the command also runs `[ -v BASH_VERSINFO[HOME=1] ]`"),
        ("git -c core.hooksPath=/tmp/h commit --no-edit", "it sets `-c` for itself"),
        ("git --config-env=core.hooksPath=H commit --no-edit", "it sets `--config-env=core.hooksPath=H` for itself"),
        ("git --exec-path=/tmp commit --no-edit", "it sets `--exec-path=/tmp` for itself"),
        ("git -c core.hooksPath=/tmp/h revert --continue", "it sets `-c` for itself"),
        ("HOME=/tmp/h git commit --no-edit", "it sets `HOME` for itself"),
        ("git commit -m Undo -m 'This reverts commit x.'$[HOME=1]", "it sets a value the shell expands for itself"),
    ],
)
def test_finishing_a_revert_other_than_as_it_stands_is_refused(proj, monkeypatch, capsys, command, why):
    """The revert is read from the index as it is, with the message `git
    revert` wrote: a push reads a revert by its "This reverts commit" line."""
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    d, msg = hook(monkeypatch, capsys, proj, command)
    assert d == "deny" and why in msg and f"it finishes a revert of {merge[:7]}, but not as it stands" in msg, msg
    assert "runs ``" not in msg, msg
    assert "`git revert --abort` cancels the revert" in msg, msg
    assert "**Revert** button" not in msg and "quick ticket" not in msg, msg  # the plain step is the way forward
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")


@pytest.mark.parametrize(
    "command",
    [
        "git status && git commit --no-edit", "echo ok && git commit --no-edit", "true; git commit --no-edit", "git diff --cached --stat; git commit --no-edit",
        "git branch --show-current && git commit --no-edit", "git log --oneline | head -3; git commit --no-edit", "ls src && git commit --no-edit",
        "git diff > /dev/null; git commit --no-edit", "git commit --no-edit; git status",
        'cd "$CLAUDE_PROJECT_DIR" && git commit --no-edit', 'cd "$(git rev-parse --show-toplevel)" && git commit --no-edit',
        "GIT_EDITOR=true git revert --continue", "EDITOR=: git commit --no-edit", "GIT_LITERAL_PATHSPECS=1 git commit --no-edit",
    ],
)  # fmt: skip
def test_reads_before_finishing_a_revert_change_nothing(proj, monkeypatch, capsys, command):
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    assert hook(monkeypatch, capsys, proj, command) == ("allow", "")


def test_a_revert_beside_other_commits_is_judged_with_them(proj, monkeypatch, capsys):
    """Only the revert is let through: a code commit sent with it still counts."""
    merge = _merge_pr(proj)
    _feature(proj)
    _commit(proj, lambda r: _change(r, "docs/branch.md", "# Branch\n"))
    assert _revert(proj, merge) == 0
    _commit(proj, lambda r: _change(r, "docs/more.md", "# More\n"))
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")
    # A code commit older than the revert, which `git log` lists after it, still counts.
    git(proj, "reset", "-q", "--hard", "HEAD~2")
    _commit(proj, lambda r: _change(r, "src/mine.py", "m = 1\n"))
    code = git(proj, "rev-parse", "--short", "HEAD").strip()
    assert _revert(proj, merge) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"commit {code}," in why and "src/mine.py" in why, why


# ---------- an unmatched revert is refused ----------


def _forged(root, sha, extra):
    """A commit that names `sha` as the commit it reverts but doesn't undo it
    exactly: the revert, then `extra` changed before it is committed."""
    assert _revert(root, sha, "--no-commit") == 0
    extra(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-edit")


def test_an_unmatched_revert_of_a_pull_request_offers_github_s_revert_button(proj, monkeypatch, capsys):
    merge = _merge_pr(proj, pr=12)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    sha = git(proj, "rev-parse", "--short", "HEAD").strip()
    for role in (None, "tikcet"):
        d, why = hook(monkeypatch, capsys, proj, PUSH, role)
        assert d == "deny", (role, why)
        assert f"commit {sha}" in why and "src/app.py" in why, why
        assert f"doesn't exactly undo {merge[:7]}" in why, why
        assert "GitHub's own **Revert** button on pull request #12" in why, why


def test_an_unmatched_revert_of_a_plain_commit_offers_a_quick_ticket(proj, monkeypatch, capsys):
    plain = _on_base(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'plain'"))
    _feature(proj)
    _forged(proj, plain, lambda r: _change(r, "src/new.py", "x = 1\n"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {plain[:7]}" in why, why
    assert "quick ticket" in why and "**Run it unattended**" in why, why
    assert "**Revert** button" not in why, why


def test_a_revert_resolved_after_a_later_change_to_the_same_lines_is_refused(proj, monkeypatch, capsys):
    """The base changed line 5 again after the pull request: the revert
    conflicts, and resolving it is writing code (answer 23)."""
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v5 = 'pr'", "v5 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge) != 0  # it conflicts: `REVERT_HEAD` is left
    _change(proj, CODE, LINES)
    git(proj, "add", CODE)
    for command in ("git commit --no-edit", "git revert --continue"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and f"doesn't exactly undo {merge[:7]}: undoing it conflicts in `src/app.py`" in why, (command, why)
        assert "**Revert** button" not in why and "quick ticket" in why, why  # GitHub's button would meet the same conflict
    git(proj, "commit", "-q", "--no-edit")
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}: undoing it conflicts" in why, why


def test_a_revert_stopped_on_a_docs_conflict_says_to_add_it(proj, monkeypatch, capsys):
    """Only the guide conflicts: the code is undone exactly, and the plain
    step is to `git add` the guide once resolved."""
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _change(r, DOC, "# Later\n"), "later")
    _feature(proj)
    assert _revert(proj, merge) != 0
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")
    assert d == "deny" and "`git add` them once resolved" in why and "**Revert** button" not in why, why
    _change(proj, DOC, "# Later\n")
    git(proj, "add", DOC)
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")


@pytest.mark.parametrize(
    "setting",
    [
        pytest.param(lambda r: _change(r, ".gitattributes", "src/app.py merge=union\n"), id="an attribute"),
        pytest.param(lambda r: _change(r, ".git/info/attributes", "*.py merge=union\n"), id="info/attributes"),
        pytest.param(lambda r: git(r, "config", "merge.default", "union"), id="merge.default"),
    ],
)
def test_a_merge_that_keeps_both_sides_lines_isn_t_git_s_own_revert(proj, monkeypatch, capsys, setting):
    """`union` keeps both sides' lines rather than marking a conflict, so the
    revert after a later change to the same line merges "cleanly". The guard
    merges with git's own text merge, whatever the repository says: a conflict."""
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v5 = 'pr'", "v5 = 'later'"), "later")
    _feature(proj)
    setting(proj)  # left uncommitted
    assert _revert(proj, merge) == 0
    assert "v5 = 'later'" in (proj / CODE).read_text() and "v5 = 5" in (proj / CODE).read_text()
    for command in (PUSH, "cd src && git push origin feature", "git -C src push origin feature"):
        for role in (None, "conductor"):
            d, why = hook(monkeypatch, capsys, proj, command, role)
            assert d == "deny" and "undoing it conflicts in `src/app.py`" in why, (command, role, why)


def test_a_merge_driver_in_git_s_config_is_never_run(proj, monkeypatch, capsys, tmp_path):
    """The guard merges in an empty repository of its own: the project's
    merge driver never runs, even where the merge isn't trivial (the base
    changed the file since), and git's own text merge decides."""
    ran = tmp_path / "ran"
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v8 = 8", "v8 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge) == 0
    git(proj, "config", "merge.mine.driver", f"touch {ran} && cp %B %A")
    _change(proj, ".git/info/attributes", "src/* merge=mine\n")
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")
    assert not ran.exists()


def test_the_session_s_own_git_settings_don_t_reach_the_guard_s_merge(proj, monkeypatch, capsys):
    """`GIT_CONFIG_PARAMETERS` in the session's environment, as `git -c`
    passes settings on: the guard's merge reads none of them."""
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v5 = 'pr'", "v5 = 'later'"), "later")
    _feature(proj)
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'merge.default'='union'")
    assert _revert(proj, merge) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "undoing it conflicts in `src/app.py`" in why, why


def test_with_no_remote_ref_of_the_base_it_says_to_fetch(proj, monkeypatch, capsys):
    """A push would send the base's own commits too: the commit rule's reading."""
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    git(proj, "update-ref", "-d", "refs/remotes/origin/main")
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")
    assert d == "ask" and "no remote ref of the base branch `main`" in why and "run `git fetch`" in why, why


def test_a_squash_merge_s_revert_button(proj, monkeypatch, capsys):
    squash = _on_base(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'squash'"), "Fix login (#17)")
    _feature(proj)
    _forged(proj, squash, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "GitHub's own **Revert** button on pull request #17" in why, why


def test_a_commit_inside_a_merged_pull_request_isn_t_taken_for_a_squash_merge(proj, monkeypatch, capsys):
    """A commit "… (#17)" inside a pull request merged with a merge commit
    names an issue, not a pull request GitHub can revert."""
    git(proj, "checkout", "-q", "-b", "pr-work", "origin/main")
    _commit(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'fix'"), "Fix login (#17)")
    inner = git(proj, "rev-parse", "HEAD").strip()
    git(proj, "checkout", "-q", "-B", "base-work", "origin/main")
    git(proj, "merge", "-q", "--no-ff", "-m", "Merge pull request #12 from acme/fix", "pr-work")
    git(proj, "push", "-q", "origin", "base-work:main")
    _feature(proj)
    _forged(proj, inner, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {inner[:7]}" in why and "**Revert** button" not in why, why


def test_a_revert_in_progress_with_more_code_staged_is_refused(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    _edit(proj, CODE, "v9 = 9", "v9 = 'extra'")
    d, why = hook(monkeypatch, capsys, proj, "git commit -a --no-edit")
    assert d == "deny" and "it would also take the working tree's change to `src/app.py`" in why, why
    git(proj, "add", CODE)
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why


def test_a_revert_that_differs_only_in_whitespace_is_refused(proj, monkeypatch, capsys):
    """Compared verbatim: indentation is code too."""
    merge = _merge_pr(proj)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v5 = 5", "    v5 = 5"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why


def _audits(root):
    """The base calls `audit()` after v2; pull request #41 adds another call
    after v8. Returns #41's merge commit."""
    _on_base(root, lambda r: _edit(r, CODE, "v2 = 2\n", "v2 = 2\naudit()\n"), "audit")
    return _on_base(root, lambda r: _edit(r, CODE, "v8 = 8\n", "v8 = 8\naudit()\n"), "audit v8 too", pr=41)


def test_a_revert_that_removes_another_identical_line_is_refused(proj, monkeypatch, capsys):
    """The revert must leave the code as `git revert` would: deleting the
    base's own `audit()` instead of #41's, the same line elsewhere, is refused."""
    merge = _audits(proj)
    _feature(proj)
    _change(proj, CODE, (proj / CODE).read_text().replace("v2 = 2\naudit()\n", "v2 = 2\n", 1))
    git(proj, "commit", "-qam", f"Revert #41\n\nThis reverts commit {merge}.")
    for role in (None, "conductor"):
        d, why = hook(monkeypatch, capsys, proj, PUSH, role)
        assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why and f"isn't as `git revert` of {merge[:7]} leaves it" in why, (role, why)


def test_lines_put_back_elsewhere_are_refused(proj, monkeypatch, capsys):
    """A revert of a commit that removed a line, putting the line back at
    the top rather than where it was."""
    sha = _on_base(proj, lambda r: _edit(r, CODE, "v4 = 4\n", ""))
    _feature(proj)
    assert _revert(proj, sha, "--no-commit") == 0
    _change(proj, CODE, "v4 = 4\n" + (proj / CODE).read_text().replace("v4 = 4\n", ""))
    d, why = hook(monkeypatch, capsys, proj, "git commit -a --no-edit")
    assert d == "deny" and "it would also take the working tree's change" in why, why
    git(proj, "add", CODE)
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")
    assert d == "deny" and f"isn't as `git revert` of {sha[:7]} leaves it" in why, why


def _binary(root):
    (root / "src/logo.bin").write_bytes(b"\x00\x01" * 50)


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(lambda r: _change(r, "src/new.py", "n = 1\n"), id="a new file"),
        pytest.param(lambda r: (r / "tests/test_app.py").unlink(), id="a file removed"),
        pytest.param(lambda r: (r / CODE).chmod(0o755), id="a mode"),
        pytest.param(_binary, id="a binary file"),
        pytest.param(lambda r: _change(r, "src/a b/ünï.py", "u = 1\n"), id="an odd name"),
    ],
)
def test_reverts_of_every_kind_of_change_go_through(proj, monkeypatch, capsys, change):
    sha = _on_base(proj, change)
    _feature(proj)
    assert _revert(proj, sha) == 0
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_revert_after_a_later_rename_goes_through(proj, monkeypatch, capsys):
    """git's revert follows a file the base moved since: so does the guard."""
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: (r / "src/core").mkdir() or git(r, "mv", CODE, "src/core/app.py"), "move")
    _feature(proj)
    assert _revert(proj, merge) == 0
    assert "v5 = 5" in (proj / "src/core/app.py").read_text()
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_revert_of_a_rename_edited_since_goes_through(proj, monkeypatch, capsys):
    merge = _on_base(proj, lambda r: git(r, "mv", CODE, "src/moved.py"), "rename", pr=30)
    _on_base(proj, lambda r: _edit(r, "src/moved.py", "v9 = 9", "v9 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge) == 0
    assert "v9 = 'later'" in (proj / CODE).read_text()
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_merge_reverted_against_its_second_parent_is_refused(proj, monkeypatch, capsys):
    """Both parents changed the code file: `-m 2` undoes the base's side."""
    git(proj, "checkout", "-q", "-b", "pr-work", "origin/main")
    _commit(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'pr'"))
    git(proj, "checkout", "-q", "-B", "base-work", "origin/main")
    _commit(proj, lambda r: _edit(r, CODE, "v8 = 8", "v8 = 'base'"))
    git(proj, "merge", "-q", "--no-ff", "-m", "Merge pull request #12 from acme/fix", "pr-work")
    merge = git(proj, "rev-parse", "HEAD").strip()
    git(proj, "push", "-q", "origin", "base-work:main")
    _feature(proj)
    assert subprocess.run(["git", "revert", "--no-commit", "-m", "2", merge], cwd=proj, capture_output=True).returncode == 0
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")  # in progress: read from `MERGE_MSG`
    assert d == "deny" and f"`git revert -m 1 {merge[:7]}`" in why, why
    git(proj, "commit", "-q", "--no-edit")
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"`git revert -m 1 {merge[:7]}`" in why, why


def test_a_file_git_doesn_t_diff_is_read_as_git_merges_it(proj, monkeypatch, capsys):
    """A code file marked `-diff` still merges as text: a revert after a later
    change elsewhere in it goes through."""
    _on_base(proj, lambda r: _change(r, ".gitattributes", "src/app.py -diff\n"), "attributes")
    merge = _merge_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v8 = 8", "v8 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge) == 0
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_revert_naming_its_commit_by_reference_goes_through(proj, monkeypatch, capsys):
    """`git revert --reference` names the commit by an abbreviated name."""
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--reference") == 0
    assert f"This reverts commit {merge[:7]}" in git(proj, "log", "-1", "--format=%B")
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")


def test_a_file_named_like_a_commit_header_hides_no_commit(proj, monkeypatch, capsys):
    """git's log of a push names each commit with a header line of the
    guard's own; a file named like one, beside code, changes nothing."""
    merge = _merge_pr(proj)
    git(proj, "checkout", "-q", "-b", "real", "origin/main")
    assert _revert(proj, merge) == 0
    real = git(proj, "rev-parse", "HEAD").strip()
    _feature(proj)
    _change(proj, "\x01\x02abcd\x03" + real, "x\n")
    _change(proj, "src/evil.py", "e = 1\n")
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "sneak")
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "src/evil.py" in why, why


def test_a_revert_of_a_commit_not_on_the_base_is_refused(proj, monkeypatch, capsys):
    """The commit it names must be on the base's remote ref: one on another
    branch only, pushed or not, isn't."""
    _feature(proj)
    git(proj, "checkout", "-q", "-b", "side")
    _commit(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'side'"))
    side = git(proj, "rev-parse", "HEAD").strip()
    git(proj, "push", "-q", "origin", "side")
    git(proj, "checkout", "-q", "feature")
    git(proj, "merge", "-q", "--ff-only", "side")  # `side` is in `feature`, but not on the base
    git(proj, "push", "-q", "origin", "feature")
    assert _revert(proj, side) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "src/app.py" in why and f"{side[:7]} isn't on `origin/main`" in why, why
    assert "run `git fetch`" in why and "**Revert** button" not in why, why


def test_a_revert_of_a_commit_merged_since_the_last_fetch_says_to_fetch(proj, monkeypatch, capsys, tmp_path):
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", git(proj, "remote", "get-url", "origin").strip(), str(other))
    _edit(other, CODE, "v5 = 5", "v5 = 'other'")
    git(other, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qam", "elsewhere")
    git(other, "push", "-q", "origin", "HEAD:main")
    sha = git(other, "rev-parse", "HEAD").strip()
    git(proj, "fetch", "-q", str(other), "main")  # the commit is here, but `origin/main` is as last fetched
    _feature(proj)
    git(proj, "merge", "-q", "--ff-only", sha)
    assert _revert(proj, sha) == 0
    d, why = hook(monkeypatch, capsys, proj, "git push origin HEAD:refs/heads/feature")
    assert d == "deny" and "run `git fetch` and try again" in why, why
    git(proj, "fetch", "-q", "origin")
    assert hook(monkeypatch, capsys, proj, "git push origin HEAD:refs/heads/feature") == ("allow", "")


def test_a_ref_named_like_a_commit_doesn_t_stand_in_for_it(proj, monkeypatch, capsys):
    """The push rule reads each commit by its full name: a branch named like
    a pushed commit's short name, pointing at an exact revert, changes nothing."""
    merge = _merge_pr(proj)
    git(proj, "checkout", "-q", "-b", "real", "origin/main")
    assert _revert(proj, merge) == 0
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    short = git(proj, "rev-parse", "--short", "HEAD").strip()
    git(proj, "branch", "-q", short, "real")
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why


def test_a_message_naming_no_commit_here_is_refused(proj, monkeypatch, capsys):
    _feature(proj)
    _commit(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'x'"), msg="Revert\n\nThis reverts commit " + "ab" * 20 + ".")
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "src/app.py" in why, why


# ---------- the conductor needs the owner's yes ----------


def test_the_conductor_s_matched_revert_needs_the_ledger_entry(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and f"reverts {merge[:7]} exactly" in why, why
    assert "ask the owner" in why and '{"what": "revert", "revert": "' + merge + '"' in why, why
    assert "`.workflow/run/body.md`" in why, why
    # An entry without a `revert` field, or for another commit, doesn't count.
    # Nor does an entry whose `what` isn't "revert", or that doesn't give the full SHA in lower case.
    unread = [{"what": "revert", "at": "2026-11-01T00:00:00Z", "grant": "yes"}], [_allowed("ab" * 20)], [{"what": "revert", "sha": merge, "at": "x", "grant": "y"}]
    for ledger in (*unread, [_allowed(merge, what="merge")], [_allowed(merge[:7])], [_allowed(merge.upper())]):
        _run_body(proj, ledger)
        d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
        assert d == "deny" and "ask the owner" in why, (ledger, why)
    _run_body(proj, [_allowed("ab" * 20), _allowed(merge)])
    assert hook(monkeypatch, capsys, proj, PUSH, "conductor") == ("allow", "")


def test_the_conductor_s_revert_in_progress_needs_the_ledger_entry(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit", "conductor")
    assert d == "deny" and "ask the owner" in why and merge in why, why
    _run_body(proj, [_allowed(merge)])
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit", "conductor") == ("allow", "")


def test_the_conductor_s_unmatched_revert_is_refused_even_when_allowed(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    _run_body(proj, [_allowed(merge)])
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why
    assert '"result": "not made: <why>"' in why and "**Revert** button on pull request #12" in why, why
    _run_body(proj, [])
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and "tell the owner" in why and "not made" not in why, why  # no entry to mark


def test_the_conductor_s_refusal_of_a_plain_commit_s_revert(proj, monkeypatch, capsys):
    plain = _on_base(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'plain'"))
    _feature(proj)
    _forged(proj, plain, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and "tell the owner, who can have it filed as a ticket" in why, why


def test_a_body_file_that_can_t_be_read_allows_nothing(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge) == 0
    (proj / ".workflow/run").mkdir(parents=True)
    (proj / ".workflow/run/body.md").write_text("Run.\n\n" + state_mod.BEGIN + "\n```json\n{not json\n```\n" + state_mod.END + "\n")
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and "ask the owner" in why, why


# ---------- when the guard can't tell ----------


def test_a_revert_it_can_t_read_is_asked(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    assert _revert(proj, merge) == 0
    monkeypatch.setattr(guard_mod, "_undone_by_git", lambda *a, **k: ("unsure", "`git merge-tree` took too long"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "ask" and "can't tell" in why and "took too long" in why, why
    assert "or only a revert that exactly undoes a commit on the base" in why, why
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and "can't tell" in why, why


def test_an_unread_revert_doesn_t_hide_a_code_commit(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    _commit(proj, lambda r: _change(r, "src/mine.py", "m = 1\n"))
    assert _revert(proj, merge) == 0
    monkeypatch.setattr(guard_mod, "_undone_by_git", lambda *a, **k: ("unsure", "`git merge-tree` took too long"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "src/mine.py" in why, why


def test_past_the_revert_cap_a_plain_code_commit_is_still_refused(proj, monkeypatch, capsys):
    monkeypatch.setattr(guard_mod, "_REVERT_CAP", 1)
    first = _on_base(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'one'"))
    second = _on_base(proj, lambda r: _edit(r, CODE, "v8 = 8", "v8 = 'two'"))
    _feature(proj)
    assert _revert(proj, second) == 0 and _revert(proj, first) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "ask" and "more than 1 reverts to read" in why, why
    git(proj, "reset", "-q", "--hard", "origin/main")
    _commit(proj, lambda r: _change(r, "src/mine.py", "m = 1\n"))
    assert _revert(proj, second) == 0 and _revert(proj, first) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and "src/mine.py" in why, why


# ---------- "any" and unanswered ----------


@pytest.mark.parametrize("code_writers", ["any", None])
def test_any_and_unanswered_decide_as_today(tmp_path, monkeypatch, capsys, code_writers):
    root = _clone(tmp_path, code_writers)
    _on_base(root, lambda r: _change(r, CODE, LINES))
    calls = []
    for name in ("_commit_code", "_push_code"):
        real = getattr(guard_mod, name)
        monkeypatch.setattr(guard_mod, name, lambda *a, _real=real, **k: calls.append(a) or _real(*a, **k))
    merge = _merge_pr(root)
    _feature(root)
    assert _revert(root, merge, "--no-commit") == 0
    _edit(root, CODE, "v9 = 9", "v9 = 'extra'")
    for role in (None, "conductor", "tikcet"):
        assert hook(monkeypatch, capsys, root, "git commit -a --no-edit", role) == ("allow", ""), role
    git(root, "commit", "-qa", "--no-edit")
    for role in (None, "conductor", "tikcet"):
        d, why = hook(monkeypatch, capsys, root, PUSH, role)
        assert "code path" not in why and "revert" not in why and "can't tell" not in why, (role, why)
    assert calls == []  # never judged: every decision is the rest of the guard's, as today


def test_a_ticket_session_s_revert_is_as_today(proj, monkeypatch, capsys):
    merge = _merge_pr(proj)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    git(proj, "checkout", "-q", "-b", "claude/build-7")
    assert hook(monkeypatch, capsys, proj, "git push origin claude/build-7", "ticket") == ("allow", "")


# ---------- docs ----------


def test_enforcement_doc_says_how_reverts_are_read():
    doc = (KIT / "docs/enforcement.md").read_text()
    section = doc[doc.index("**Who writes code**") :]
    for phrase in ("#392", "This reverts commit", "`git merge-tree`", "REVERT_HEAD", "**Revert** button", '"revert"'):
        assert phrase in section, phrase


def test_changelog_note():
    notes = since_0110()
    assert "(#392, part of #338)" in notes and "test_guard_code_reverts.py" in notes

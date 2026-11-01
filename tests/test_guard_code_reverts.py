"""#392 (spec #338, split from #341): under `code_writers = "ticket"`, a
revert that exactly undoes a commit already on the base goes through #389's
commit rule and #390's push rule in a planning session. A commit made by
`git revert` names the commit it reverts ("This reverts commit <sha>"); when
that commit is on the base's remote ref and the revert's code-path changes
are its inverse (for a merge, of its change against its first parent),
compared by patch id with no context lines, it is a revert, not code. While a
revert is in progress (`REVERT_HEAD`), its changes are judged by that rule.
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
from workflow import guard as guard_mod
from workflow import state as state_mod

pytestmark = pytest.mark.usefixtures("_no_user_git_config")

LINES = "".join(f"v{i} = {i}\n" for i in range(1, 11))
DOC = "docs/guide.md"
PUSH = "git push origin feature"


def _edit(root, path, old, new):
    p = root / path
    text = p.read_text()
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1))


def _commit(root, change, msg="x"):
    change(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)


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


def _merged_pr(root, pr=12):
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
    merge = _merged_pr(proj)
    _feature(proj)
    _on(proj, branch)
    assert _revert(proj, merge) == 0
    target = "feature" if branch == "feature" else branch
    assert hook(monkeypatch, capsys, proj, f"git push origin {target}", role) == ("allow", "")


def test_a_revert_after_a_later_change_two_lines_away_goes_through(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
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
    merge = _merged_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v7 = 7", "v7 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    for command in ("git commit --no-edit", "git commit -m 'Undo #12'", "git commit -a --no-edit", "git revert --continue"):
        assert hook(monkeypatch, capsys, proj, command) == ("allow", ""), command


def test_a_revert_beside_other_commits_is_judged_with_them(proj, monkeypatch, capsys):
    """Only the revert is let through: a code commit sent with it still counts."""
    merge = _merged_pr(proj)
    _feature(proj)
    _commit(proj, lambda r: _change(r, "docs/branch.md", "# Branch\n"))
    assert _revert(proj, merge) == 0
    _commit(proj, lambda r: _change(r, "docs/more.md", "# More\n"))
    assert hook(monkeypatch, capsys, proj, PUSH) == ("allow", "")
    _commit(proj, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'mine'"))
    code = git(proj, "rev-parse", "--short", "HEAD").strip()
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"commit {code}," in why and "src/app.py" in why, why


# ---------- an unmatched revert is refused ----------


def _forged(root, sha, extra):
    """A commit that names `sha` as the commit it reverts but doesn't undo it
    exactly: the revert, then `extra` changed before it is committed."""
    assert _revert(root, sha, "--no-commit") == 0
    extra(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-edit")


def test_an_unmatched_revert_of_a_pull_request_offers_github_s_revert_button(proj, monkeypatch, capsys):
    merge = _merged_pr(proj, pr=12)
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
    merge = _merged_pr(proj)
    _on_base(proj, lambda r: _edit(r, CODE, "v5 = 'pr'", "v5 = 'later'"), "later")
    _feature(proj)
    assert _revert(proj, merge) != 0  # it conflicts: `REVERT_HEAD` is left
    _change(proj, CODE, LINES)
    git(proj, "add", CODE)
    for command in ("git commit --no-edit", "git revert --continue"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "src/app.py" in why and f"doesn't exactly undo {merge[:7]}" in why, (command, why)
        assert "**Revert** button on pull request #12" in why, why
    git(proj, "commit", "-q", "--no-edit")
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why


def test_a_revert_in_progress_with_more_code_staged_is_refused(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    _edit(proj, CODE, "v9 = 9", "v9 = 'extra'")
    d, why = hook(monkeypatch, capsys, proj, "git commit -a --no-edit")
    assert d == "deny" and "src/app.py" in why and f"doesn't exactly undo {merge[:7]}" in why, why
    git(proj, "add", CODE)
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why


def test_a_revert_that_differs_only_in_whitespace_is_refused(proj, monkeypatch, capsys):
    """Compared verbatim: indentation is code too."""
    merge = _merged_pr(proj)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v5 = 5", "    v5 = 5"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why


@pytest.mark.parametrize("command", ["git commit --amend --no-edit", "git commit --no-edit -- src/app.py"])
def test_finishing_a_revert_as_only_part_of_a_commit_is_refused(proj, monkeypatch, capsys, command):
    """An `--amend` folds the revert into the commit before it, and a
    pathspec commits only part of it: neither is the revert as it stands."""
    merge = _merged_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    d, why = hook(monkeypatch, capsys, proj, command)
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")


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
    assert d == "deny" and "src/app.py" in why and f"{side[:7]}" in why and "isn't on" in why, why


def test_a_ref_named_like_a_commit_doesn_t_stand_in_for_it(proj, monkeypatch, capsys):
    """The push rule reads each commit by its full name: a branch named like
    a pushed commit's short name, pointing at an exact revert, changes nothing."""
    merge = _merged_pr(proj)
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
    merge = _merged_pr(proj)
    _feature(proj)
    assert _revert(proj, merge) == 0
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and f"reverts {merge[:7]} exactly" in why, why
    assert "ask the owner" in why and '{"what": "revert", "revert": "' + merge + '"' in why, why
    assert "`.workflow/run/body.md`" in why, why
    # An entry without a `revert` field, or for another commit, doesn't count.
    for ledger in ([{"what": "revert", "at": "2026-11-01T00:00:00Z", "grant": "yes"}], [_allowed("ab" * 20)], [{"what": "revert", "sha": merge, "at": "x", "grant": "y"}]):
        _run_body(proj, ledger)
        d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
        assert d == "deny" and "ask the owner" in why, (ledger, why)
    _run_body(proj, [_allowed("ab" * 20), _allowed(merge)])
    assert hook(monkeypatch, capsys, proj, PUSH, "conductor") == ("allow", "")


def test_the_conductor_s_revert_in_progress_needs_the_ledger_entry(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
    _feature(proj)
    assert _revert(proj, merge, "--no-commit") == 0
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit", "conductor")
    assert d == "deny" and "ask the owner" in why and merge in why, why
    _run_body(proj, [_allowed(merge)])
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit", "conductor") == ("allow", "")


def test_the_conductor_s_unmatched_revert_is_refused_even_when_allowed(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    _run_body(proj, [_allowed(merge)])
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and f"doesn't exactly undo {merge[:7]}" in why, why
    assert '"result": "not made: <why>"' in why and "**Revert** button on pull request #12" in why, why


def test_a_body_file_that_can_t_be_read_allows_nothing(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
    _feature(proj)
    assert _revert(proj, merge) == 0
    (proj / ".workflow/run").mkdir(parents=True)
    (proj / ".workflow/run/body.md").write_text("Run.\n\n" + state_mod.BEGIN + "\n```json\n{not json\n```\n" + state_mod.END + "\n")
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and "ask the owner" in why, why


# ---------- when the guard can't tell ----------


def test_a_revert_it_can_t_read_is_asked(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
    _feature(proj)
    assert _revert(proj, merge) == 0
    monkeypatch.setattr(guard_mod, "_patch_id", lambda *a, **k: (None, "`git patch-id` took too long"))
    d, why = hook(monkeypatch, capsys, proj, PUSH)
    assert d == "ask" and "can't tell" in why and "took too long" in why, why
    d, why = hook(monkeypatch, capsys, proj, PUSH, "conductor")
    assert d == "deny" and "can't tell" in why, why


def test_an_unread_revert_doesn_t_hide_a_code_commit(proj, monkeypatch, capsys):
    merge = _merged_pr(proj)
    _feature(proj)
    _commit(proj, lambda r: _change(r, "src/mine.py", "m = 1\n"))
    assert _revert(proj, merge) == 0
    monkeypatch.setattr(guard_mod, "_patch_id", lambda *a, **k: (None, "`git patch-id` took too long"))
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
    merge = _merged_pr(root)
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
    merge = _merged_pr(proj)
    _feature(proj)
    _forged(proj, merge, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'extra'"))
    git(proj, "checkout", "-q", "-b", "claude/build-7")
    assert hook(monkeypatch, capsys, proj, "git push origin claude/build-7", "ticket") == ("allow", "")


# ---------- docs ----------


def test_enforcement_doc_says_how_reverts_are_read():
    doc = (KIT / "docs/enforcement.md").read_text()
    section = doc[doc.index("**Who writes code**") :]
    for phrase in ("#392", "This reverts commit", "patch id", "REVERT_HEAD", "**Revert** button", '"revert"'):
        assert phrase in section, phrase


def test_changelog_note():
    notes = since_0110()
    assert "(#392, part of #338)" in notes and "test_guard_code_reverts.py" in notes

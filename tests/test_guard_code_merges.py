"""#391 (spec #338, split from #341): under `code_writers = "ticket"`, #389's
commit rule and #390's push rule judge a merge by its own changes, so
bringing a pull request up to date with its base goes through in a planning
session. For a merge commit, and a commit finishing a merge, only what the
merge itself changed counts, read line by line with no context lines
(`git diff-tree --cc -U0`): a line taken cleanly from one parent isn't
counted; a conflict resolved in a code path, or a change of the merge's
own, is. A cherry-pick in progress counts everything staged, and a pushed
cherry-pick's new commits are judged as any commit. Under `"any"` or with
`code_writers` absent, as today.

Through `workflow hook guard`, run as Claude Code runs it, in temporary git
repositories cloned from a bare remote (`…/acme/demo.git`). The commands are
data given to the hook; only the set-up runs."""

import subprocess

import pytest

from changelog_notes import since_0110
from conftest import KIT, git
from test_guard_code_commits import CODE, _change, _clone, hook
from workflow import guard as guard_mod

pytestmark = pytest.mark.usefixtures("_no_user_git_config")

LINES = "".join(f"v{i} = {i}\n" for i in range(1, 11))
DOC = "docs/guide.md"
ROLES = (None, "conductor")  # an attended (planning) session, and the conductor


def _edit(root, path, old, new):
    p = root / path
    text = p.read_text()
    assert old in text, (path, old)
    p.write_text(text.replace(old, new, 1))


def _merge(root, *args):
    """`git merge`, which exits 1 on a conflict: the set-up expects it."""
    p = subprocess.run(["git", "merge", "-q", "--no-edit", *args], cwd=root, capture_output=True, text=True)
    return p.returncode


def _on_base(root, change, msg="base"):
    """A commit on the remote's base branch (`main`), as if another pull
    request had merged: `origin/main` moves, `feature` stays."""
    here = git(root, "branch", "--show-current").strip()
    git(root, "checkout", "-q", "-B", "base-work", "origin/main")
    change(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)
    git(root, "push", "-q", "origin", "base-work:main")
    git(root, "checkout", "-q", here)
    git(root, "branch", "-q", "-D", "base-work")


def _commit(root, change, msg="x"):
    change(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg)


@pytest.fixture
def proj(tmp_path):
    """A clone on `feature`, from a base whose code file has ten lines."""
    root = _clone(tmp_path)
    _on_base(root, lambda r: _change(r, CODE, LINES))
    git(root, "checkout", "-q", "-B", "feature", "origin/main")
    return root


def _base_code(root):
    _on_base(root, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'base'"))


def _docs_conflict(root):
    """A merge of the base in progress: the base changed the code file and
    the guide, the branch the guide, so the guide conflicts and is resolved;
    the code comes cleanly from the base."""
    _on_base(root, lambda r: (_edit(r, CODE, "v5 = 5", "v5 = 'base'"), _change(r, DOC, "# Base\n")))
    _commit(root, lambda r: _change(r, DOC, "# Branch\n"))
    assert _merge(root, "origin/main") == 1
    _change(root, DOC, "# Both\n")
    git(root, "add", DOC)


def _code_conflict(root, resolved="v5 = 'both'\n"):
    """A merge of the base in progress, conflicting in the code file, which
    the branch changed too (pushed by a ticket session, so on the remote)."""
    _base_code(root)
    _commit(root, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'branch'"))
    git(root, "push", "-q", "origin", "feature")
    assert _merge(root, "origin/main") == 1
    text = "".join(l for l in LINES.splitlines(keepends=True) if not l.startswith("v5 ")).replace("v4 = 4\n", "v4 = 4\n" + resolved)
    _change(root, CODE, text)
    git(root, "add", CODE)


def _two_sided(root):
    """Both sides changed the code file two lines apart (the branch's change
    pushed already): git merges it cleanly, stopping before the commit."""
    _base_code(root)
    _commit(root, lambda r: _edit(r, CODE, "v3 = 3", "v3 = 'branch'"))
    git(root, "push", "-q", "origin", "feature")
    assert _merge(root, "--no-commit", "origin/main") == 0
    assert (root / CODE).read_text().count("'") == 4


FINISHING = ["git commit --no-edit", "git commit -m 'Merge main'", "git merge --continue", "git commit -a --no-edit", "git commit -am x"]


# ---------- finishing a merge: the commit rule ----------


@pytest.mark.parametrize("setup", [_docs_conflict, _two_sided])
def test_finishing_a_merge_of_the_base_goes_through(proj, monkeypatch, capsys, setup):
    """Code taken cleanly from either side isn't the merge's own change."""
    setup(proj)
    for command in FINISHING:
        for role in ROLES:
            assert hook(monkeypatch, capsys, proj, command, role) == ("allow", ""), (command, role)


def test_a_conflict_resolved_in_a_code_path_is_refused(proj, monkeypatch, capsys):
    _code_conflict(proj)
    for command in FINISHING:
        for role in ROLES:
            d, why = hook(monkeypatch, capsys, proj, command, role)
            assert d == "deny", (command, role, why)
            assert "merge" in why and "code path `src/app.py` (src/**)" in why, why
            assert "the merge itself" in why, why


def test_a_conflict_resolved_by_taking_one_side_is_the_side_s_change(proj, monkeypatch, capsys):
    """Taking the base's whole version changes nothing of the merge's own
    (`--cc` shows no hunk), so it goes through, as a clean merge does."""
    _code_conflict(proj, resolved="v5 = 'base'\n")
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")


def test_a_change_of_the_merge_s_own_in_a_code_path_is_refused(proj, monkeypatch, capsys):
    _docs_conflict(proj)
    _change(proj, "src/extra.py", "x = 1\n")
    git(proj, "add", "src/extra.py")
    for command in ("git commit --no-edit", "git merge --continue"):
        d, why = hook(monkeypatch, capsys, proj, command, "conductor")
        assert d == "deny" and "code path `src/extra.py` (src/**)" in why, (command, why)
    # A change to a line the base merged in cleanly: the result differs from both sides there.
    git(proj, "reset", "-q", "src/extra.py")
    (proj / "src/extra.py").unlink()
    _edit(proj, CODE, "v5 = 'base'", "v5 = 'mine'")
    git(proj, "add", CODE)
    d, why = hook(monkeypatch, capsys, proj, "git commit --no-edit")
    assert d == "deny" and "code path `src/app.py` (src/**)" in why, why


def test_a_code_change_left_unstaged_counts_only_when_the_commit_takes_it(proj, monkeypatch, capsys):
    _docs_conflict(proj)
    _edit(proj, CODE, "v9 = 9", "v9 = 'mine'")
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")
    for command in ("git commit -a --no-edit", "git commit -am x", "git commit -i -m x src/app.py"):
        d, why = hook(monkeypatch, capsys, proj, command)
        assert d == "deny" and "code path `src/app.py` (src/**)" in why, (command, why)


def test_an_octopus_merge_is_judged_by_its_own_changes(proj, monkeypatch, capsys):
    _on_base(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'base'"))
    git(proj, "checkout", "-q", "-b", "two", "origin/main")
    _commit(proj, lambda r: _edit(r, CODE, "v1 = 1", "v1 = 'two'"))
    git(proj, "push", "-q", "origin", "two")
    git(proj, "checkout", "-q", "feature")
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    assert _merge(proj, "--no-commit", "origin/main", "origin/two") == 0
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")
    _edit(proj, CODE, "v9 = 9", "v9 = 'mine'")
    git(proj, "add", CODE)
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit")[0] == "deny"


def test_a_merge_with_files_still_unmerged_counts_everything_staged(proj, monkeypatch, capsys):
    """git won't finish it (`git commit -a` would take the conflict markers):
    with no merge result to read, everything staged counts, as before."""
    _on_base(proj, lambda r: (_edit(r, CODE, "v5 = 5", "v5 = 'base'"), _change(r, DOC, "# Base\n")))
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    assert _merge(proj, "origin/main") == 1
    d, why = hook(monkeypatch, capsys, proj, "git commit -a --no-edit", "conductor")
    assert d == "deny" and "code path `src/app.py` (src/**)" in why, why


def test_the_guard_s_read_leaves_the_repository_as_it_was(proj, monkeypatch, capsys):
    """The merge result is written to a copy of the index and a temporary
    object store: the real index and objects are untouched."""
    _docs_conflict(proj)
    index = (proj / ".git/index").read_bytes()
    objects = sorted(p.name for p in (proj / ".git/objects").rglob("*"))
    assert hook(monkeypatch, capsys, proj, "git commit --no-edit") == ("allow", "")
    assert (proj / ".git/index").read_bytes() == index
    assert sorted(p.name for p in (proj / ".git/objects").rglob("*")) == objects
    git(proj, "commit", "-q", "--no-edit")
    git(proj, "fsck", "--no-progress")


# ---------- a cherry-pick in progress ----------


def test_a_cherry_pick_in_progress_counts_everything_staged(proj, monkeypatch, capsys):
    _on_base(proj, lambda r: (_edit(r, CODE, "v5 = 5", "v5 = 'base'"), _change(r, DOC, "# Base\n")))
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    p = subprocess.run(["git", "cherry-pick", "origin/main"], cwd=proj, capture_output=True, text=True)
    assert p.returncode != 0, p.stdout
    _change(proj, DOC, "# Both\n")
    git(proj, "add", DOC)
    for command in ("git cherry-pick --continue", "git commit --no-edit", "git commit -am x"):
        for role in ROLES:
            d, why = hook(monkeypatch, capsys, proj, command, role)
            assert d == "deny" and "code path `src/app.py` (src/**)" in why, (command, role, why)


def test_a_docs_only_cherry_pick_in_progress_goes_through(proj, monkeypatch, capsys):
    _on_base(proj, lambda r: _change(r, DOC, "# Base\n"))
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    p = subprocess.run(["git", "cherry-pick", "origin/main"], cwd=proj, capture_output=True, text=True)
    assert p.returncode != 0, p.stdout
    _change(proj, DOC, "# Both\n")
    git(proj, "add", DOC)
    for command in ("git cherry-pick --continue", "git commit --no-edit"):
        assert hook(monkeypatch, capsys, proj, command, "conductor") == ("allow", ""), command


# ---------- pushing a merge: the push rule ----------


def _finish(root):
    git(root, "commit", "-q", "--no-edit")


@pytest.mark.parametrize("setup", [_docs_conflict, _two_sided])
def test_a_push_of_a_merge_of_the_base_goes_through(proj, monkeypatch, capsys, setup):
    setup(proj)
    _finish(proj)
    for role in ROLES:
        for command in ("git push origin feature", "git push origin HEAD:refs/heads/feature", "git push -u origin HEAD"):
            assert hook(monkeypatch, capsys, proj, command, role) == ("allow", ""), (command, role)


def test_a_push_of_a_clean_merge_of_the_base_goes_through(proj, monkeypatch, capsys):
    _base_code(proj)
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    assert _merge(proj, "origin/main") == 0
    for role in ROLES:
        assert hook(monkeypatch, capsys, proj, "git push origin feature", role) == ("allow", ""), role
    # The pull request's own code still counts, merge or not.
    _commit(proj, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'mine'"))
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "src/app.py" in why, why


def test_a_push_after_a_conflict_resolved_in_a_code_path_is_refused(proj, monkeypatch, capsys):
    _code_conflict(proj)
    _finish(proj)
    sha = git(proj, "rev-parse", "--short", "HEAD").strip()
    for role in ROLES:
        d, why = hook(monkeypatch, capsys, proj, "git push origin feature", role)
        assert d == "deny", (role, why)
        assert f"merge commit {sha}" in why and "code path `src/app.py` (src/**)" in why, why
        assert "the merge itself" in why, why


def test_a_push_of_a_merge_with_a_change_of_its_own_is_refused(proj, monkeypatch, capsys):
    _base_code(proj)
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    assert _merge(proj, "--no-commit", "origin/main") == 0
    _change(proj, "src/new/mod.py", "x = 1\n")
    git(proj, "add", "-A")
    _finish(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and "code path `src/new/mod.py` (src/**)" in why, why


def test_a_merged_branch_not_on_the_remote_sends_its_own_code(proj, monkeypatch, capsys):
    """The merge itself is clean, but the merged branch's code commit isn't on
    the remote: the push sends it, and it is judged as any commit."""
    git(proj, "checkout", "-q", "-b", "side")
    _commit(proj, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'side'"))
    side = git(proj, "rev-parse", "--short", "HEAD").strip()
    git(proj, "checkout", "-q", "feature")
    git(proj, "merge", "-q", "--no-ff", "--no-edit", "side")
    git(proj, "branch", "-q", "-D", "side")
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and f"commit {side}," in why and "src/app.py" in why, why


def test_a_code_path_whose_name_git_quotes_is_read(proj, monkeypatch, capsys):
    """A merge's own change to `src/näme "x".py`, which git's patch
    header writes in quotes with octal escapes, is still that code path."""
    name = 'src/näme "x".py'
    _base_code(proj)
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))
    assert _merge(proj, "--no-commit", "origin/main") == 0
    _change(proj, name, "x = 1\n")
    git(proj, "add", "-A")
    _finish(proj)
    d, why = hook(monkeypatch, capsys, proj, "git push origin feature")
    assert d == "deny" and name in why and "(src/**)" in why, why


# ---------- a cherry-pick, pushed ----------


@pytest.mark.parametrize("where", ["on the base", "on another branch"])
def test_a_push_after_cherry_picking_a_code_commit_is_refused(proj, monkeypatch, capsys, where):
    _commit(proj, lambda r: _change(r, DOC, "# Branch\n"))  # else a pick of the base's next commit is that commit
    if where == "on the base":
        _base_code(proj)
        pick = "origin/main"
    else:
        git(proj, "checkout", "-q", "-b", "side")
        _commit(proj, lambda r: _edit(r, CODE, "v5 = 5", "v5 = 'side'"))
        git(proj, "checkout", "-q", "feature")
        pick = "side"
    git(proj, "cherry-pick", pick)
    for role in ROLES:
        d, why = hook(monkeypatch, capsys, proj, "git push origin feature", role)
        assert d == "deny" and "code path `src/app.py` (src/**)" in why, (role, why)


def test_a_push_after_cherry_picking_a_docs_commit_goes_through(proj, monkeypatch, capsys):
    _commit(proj, lambda r: _change(r, "README.md", "# Demo\n"))
    _on_base(proj, lambda r: _change(r, DOC, "# Base\n"))
    git(proj, "cherry-pick", "origin/main")
    for role in ROLES:
        assert hook(monkeypatch, capsys, proj, "git push origin feature", role) == ("allow", ""), role


# ---------- "any" and unanswered ----------


@pytest.mark.parametrize("code_writers", ["any", None])
def test_any_and_unanswered_decide_as_today(tmp_path, monkeypatch, capsys, code_writers):
    root = _clone(tmp_path, code_writers)
    _on_base(root, lambda r: _change(r, CODE, LINES))
    git(root, "checkout", "-q", "-B", "feature", "origin/main")
    calls = []
    for name in ("_commit_code", "_push_code"):
        real = getattr(guard_mod, name)
        monkeypatch.setattr(guard_mod, name, lambda *a, _real=real, **k: calls.append(a) or _real(*a, **k))
    _code_conflict(root)
    for command in [*FINISHING, "git cherry-pick --continue"]:
        for role in (None, "conductor", "tikcet"):
            assert hook(monkeypatch, capsys, root, command, role) == ("allow", ""), (command, role)
    _finish(root)
    git(root, "checkout", "-q", "-b", "side", "origin/main")
    _commit(root, lambda r: _edit(r, CODE, "v9 = 9", "v9 = 'side'"))
    git(root, "checkout", "-q", "feature")
    git(root, "cherry-pick", "side")
    for role in (None, "conductor", "tikcet"):
        d, why = hook(monkeypatch, capsys, root, "git push origin feature", role)
        assert "code path" not in why and "can't tell" not in why, (role, why)
    assert calls == []  # never judged: every decision is the rest of the guard's, as today


# ---------- docs ----------


def test_enforcement_doc_says_how_merges_are_read():
    doc = (KIT / "docs/enforcement.md").read_text()
    section = doc[doc.index("**Who writes code**") :]
    for phrase in ("#391", "--cc", "cherry-pick"):
        assert phrase in section, phrase


def test_changelog_note():
    notes = since_0110()
    assert "(#391, part of #338)" in notes and "test_guard_code_merges.py" in notes

"""#703: a background evidence run watches the working tree after each shard.

A tracked or staged file changed while the suites run (edited, written with the
same bytes, removed, renamed, staged or left in a merge conflict, in the
project or inside a submodule, even undone before the shard ends) never ends
in a report naming the commit without the dirty marker, and never leaves a
shard under `<sha>/` for a later run to reuse. Read-only git commands beside
the run change nothing.

The suite's runner (from `test_evidence_tree`) stands in for the session working
beside the run: after the shard holding a given file it carries out the action
written in `.workflow/act`, once, and logs each shard it runs to `.workflow/ran`."""

import re
import shutil
from pathlib import Path

import pytest
from conftest import git
from test_evidence_tree import _act, _evidence, _ran, _repo, _sha

from workflow import evidence

ROOT = Path(__file__).resolve().parents[1]


def _store(root, sha=None) -> Path:
    return root / ".workflow/evidence" / (sha or _sha(root))


def _kept(root, sha=None) -> list[str]:
    d = _store(root, sha)
    return sorted(p.name for p in d.glob("unit-*.json")) if d.is_dir() else []


def _dirty_kept(root, sha=None) -> list[str]:
    d = root / ".workflow/evidence" / ((sha or _sha(root)) + "-dirty")
    return sorted(p.name for p in d.glob("unit-*.json")) if d.is_dir() else []


def _headline(out: str) -> str:
    return out.splitlines()[0]


def _with_submodule(tmp_path) -> Path:
    """A project with a local submodule `lib` holding a tracked `lib.txt`."""
    sub = tmp_path / "libsrc"
    sub.mkdir()
    git(sub, "init", "-q", "-b", "main")
    git(sub, "config", "user.email", "t@e")
    git(sub, "config", "user.name", "t")
    (sub / "lib.txt").write_text("lib v1\n")
    git(sub, "add", ".")
    git(sub, "commit", "-qm", "lib")
    root = _repo(tmp_path / "proj")
    git(root, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "lib")
    git(root, "commit", "-qm", "add lib")
    git(root / "lib", "config", "user.email", "t@e")
    git(root / "lib", "config", "user.name", "t")
    return root


# ---------- 1. a tracked file changed mid-run ----------

CHANGES = {
    "an edit": "echo v2 > notes.txt",
    "an edit undone before the shard ends": "echo v2 > notes.txt && echo v1 > notes.txt",
    "a write with the same bytes": "printf 'v1\\n' > notes.txt",
    "a removal": "rm notes.txt",
    "a rename": "git mv notes.txt renamed.txt",
    "a staged new file": "echo new > staged.txt && git add staged.txt",
    "a staged edit undone in the tree": "echo v2 > notes.txt && git add notes.txt && git checkout HEAD -- notes.txt && git reset -q",
    "a merge left in conflict": "git merge -q other || true",
}


def _other_branch(root) -> None:
    """A branch `other` whose notes.txt conflicts with the head's."""
    sha = _sha(root)
    git(root, "checkout", "-q", "-b", "other")
    (root / "notes.txt").write_text("other\n")
    git(root, "commit", "-qam", "other")
    git(root, "checkout", "-q", "main")
    (root / "notes.txt").write_text("main\n")
    git(root, "commit", "-qam", "main")
    assert _sha(root) != sha


@pytest.mark.parametrize("cmd", CHANGES.values(), ids=CHANGES.keys())
def test_a_tracked_file_changed_mid_run_makes_a_dirty_report_and_keeps_nothing_under_the_sha(
    tmp_path, monkeypatch, capsys, cmd
):
    root = _repo(tmp_path)
    if "merge" in cmd:
        _other_branch(root)
    sha = _sha(root)
    _act(root, "tests/test_1.txt", cmd)
    _evidence(monkeypatch, root)
    out = capsys.readouterr().out
    assert _sha(root) == sha  # nothing here moves the head
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    # The shard before the change ran on the commit and is kept as its; the one
    # it ran beside, and every one after, is kept apart and never reused.
    assert _kept(root, sha) == ["unit-000.json"]
    assert _dirty_kept(root, sha) == ["unit-001.json", "unit-002.json"]
    assert _ran(root) == ["tests/test_0.txt", "tests/test_1.txt", "tests/test_2.txt"]  # it finished


def test_the_report_names_what_changed_and_says_its_content_may_be_the_same(tmp_path, monkeypatch, capsys):
    # A write with the same bytes can't be told from an edit undone: the report
    # says so, rather than sending the reader looking for a change that isn't there.
    root = _repo(tmp_path)
    _act(root, "tests/test_0.txt", "printf 'v1\\n' > notes.txt")
    _evidence(monkeypatch, root)
    out = capsys.readouterr().out
    note = next(l for l in out.splitlines() if "while it ran" in l)
    assert "`notes.txt`" in note
    assert "may be the same" in note
    assert "--allow-dirty" not in note
    assert "[repair]" in note  # the remedy when the run's own commands write it


def test_the_report_note_keeps_each_changed_name_whole(tmp_path, monkeypatch, capsys):
    # A line break or a backtick in a name never splits the note or breaks its code span.
    root = _repo(tmp_path)
    (root / "new\nline.txt").write_text("a\n")
    (root / "back`tick.txt").write_text("b\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "odd names")
    _act(root, "tests/test_1.txt", "echo x >> 'new\nline.txt' && echo x >> 'back`tick.txt'")
    _evidence(monkeypatch, root)
    lines = capsys.readouterr().out.splitlines()
    i = next(i for i, l in enumerate(lines) if "while it ran" in l)
    assert lines[i + 1] == ""  # the note is one line
    assert '`"new\\nline.txt"`' in lines[i]  # quoted as git quotes it
    assert "``back`tick.txt``" in lines[i]
    assert "`notes.txt`" not in lines[i]
    assert evidence._code("`a`") == "`` `a` ``"  # a name that starts or ends with a backtick is padded


def test_a_change_in_the_repair_window_makes_a_dirty_report(tmp_path, monkeypatch, capsys):
    # The repair runs again after a failing shard: what it writes then can't be
    # told from a change beside the run.
    root = _repo(tmp_path, repair="test ! -e .workflow/twice || echo v2 > notes.txt; touch .workflow/twice")
    (root / "tests/test_0.txt").write_text("fail")
    git(root, "commit", "-qam", "test_0 fails")
    sha = _sha(root)
    assert _evidence(monkeypatch, root) == 1
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, False, dirty=True)
    assert "2 passed, 1 failed" in out  # it finished
    assert _kept(root, sha) == ["unit-000.json"]


def test_a_project_in_a_folder_of_its_checkout_watches_the_whole_checkout(tmp_path, monkeypatch, capsys):
    # The start check (`git status`) covers the whole checkout, and so does the look after each shard.
    mono = tmp_path / "mono"
    root = _repo(mono / "proj")
    shutil.rmtree(root / ".git")
    (mono / "shared.txt").write_text("s1\n")
    git(mono, "init", "-q", "-b", "main")
    git(mono, "config", "user.email", "t@e")
    git(mono, "config", "user.name", "t")
    git(mono, "add", ".")
    git(mono, "commit", "-qm", "x")
    sha = _sha(root)
    _act(root, "tests/test_1.txt", "echo s2 > ../shared.txt")
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    assert "`shared.txt`" in next(l for l in out.splitlines() if "while it ran" in l)
    assert _kept(root, sha) == ["unit-000.json"]
    assert _dirty_kept(root, sha) == ["unit-001.json", "unit-002.json"]
    # The project's own .workflow/ is still left out, named from the checkout's top.
    (root / ".gitignore").write_text("")
    (root / "y.txt").write_text("y")
    assert evidence.tree_state(root).untracked == {"proj/y.txt"}


def test_a_suite_that_writes_a_tracked_file_still_finishes_with_a_dirty_report(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, run="python3 run_tests.py {files} && date > notes.txt")
    sha = _sha(root)
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    assert "3 passed" in out
    assert _kept(root, sha) == []


def test_a_suite_that_writes_untracked_files_stays_clean_and_kept(tmp_path, monkeypatch, capsys):
    # Untracked files that appear mid-run are #704's: this check leaves them be.
    root = _repo(tmp_path, run="python3 run_tests.py {files} && mkdir -p test-results && date > coverage.xml")
    sha = _sha(root)
    assert _evidence(monkeypatch, root) == 0
    assert _headline(capsys.readouterr().out) == evidence.headline(sha, True)
    assert _kept(root, sha) == ["unit-000.json", "unit-001.json", "unit-002.json"]


# ---------- 2. inside a submodule ----------

SUBMODULE_CHANGES = {
    "an edit in it": "echo v2 > lib/lib.txt",
    "an edit in it undone": "echo v2 > lib/lib.txt && echo 'lib v1' > lib/lib.txt",
    "a commit in it": "cd lib && git commit -q --allow-empty -m moved",
    "a staged file in it": "echo n > lib/n.txt && git -C lib add n.txt",
    "a removal in it": "rm lib/lib.txt",
}


@pytest.mark.parametrize("cmd", SUBMODULE_CHANGES.values(), ids=SUBMODULE_CHANGES.keys())
def test_a_change_inside_a_submodule_makes_a_dirty_report_and_keeps_nothing_under_the_sha(
    tmp_path, monkeypatch, capsys, cmd
):
    root = _with_submodule(tmp_path)
    sha = _sha(root)
    _act(root, "tests/test_1.txt", cmd)
    _evidence(monkeypatch, root)
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    assert "lib" in next(l for l in out.splitlines() if "while it ran" in l)
    assert _kept(root, sha) == ["unit-000.json"]
    # The start check refuses the same state, as it always did (an edit undone leaves none).
    if "'lib v1'" not in cmd:
        with pytest.raises(evidence.EvidenceError):
            evidence.require_clean(root)


def test_a_submodule_left_alone_keeps_the_run_clean(tmp_path, monkeypatch, capsys):
    root = _with_submodule(tmp_path)
    sha = _sha(root)
    _act(root, "tests/test_1.txt", "git status --porcelain >/dev/null && git -C lib status >/dev/null && git submodule status >/dev/null")
    assert _evidence(monkeypatch, root) == 0
    assert _headline(capsys.readouterr().out) == evidence.headline(sha, True)
    assert _kept(root, sha) == ["unit-000.json", "unit-001.json", "unit-002.json"]


# ---------- 3. read-only git commands beside the run ----------


@pytest.mark.parametrize("args", [[], ["--allow-dirty"]], ids=["plain", "allow-dirty"])
def test_read_only_git_commands_beside_the_run_keep_it_clean(tmp_path, monkeypatch, capsys, args):
    root = _repo(tmp_path / "proj")
    remote = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(root), str(remote))
    git(root, "remote", "add", "origin", str(remote))
    sha = _sha(root)
    _act(
        root,
        "tests/test_1.txt",
        "git status >/dev/null && git status --porcelain >/dev/null && git diff >/dev/null && git diff HEAD >/dev/null"
        " && git fetch -q origin && git update-index --refresh >/dev/null && git log -1 >/dev/null && cat notes.txt >/dev/null",
    )
    assert _evidence(monkeypatch, root, *args) == 0
    assert _headline(capsys.readouterr().out) == evidence.headline(sha, True)
    assert _kept(root, sha) == ["unit-000.json", "unit-001.json", "unit-002.json"]
    assert _dirty_kept(root, sha) == []


# ---------- 4. a shard a stop interrupted is never reused (moved from #671) ----------


def test_a_shard_run_beside_a_changed_tree_runs_again_once_the_tree_is_clean(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    sha = _sha(root)
    _act(root, "tests/test_1.txt", "echo v2 > notes.txt")
    _evidence(monkeypatch, root)
    assert evidence.DIRTY in _headline(capsys.readouterr().out)
    git(root, "checkout", "-q", "--", "notes.txt")  # the tree clean again, on the same commit
    assert _evidence(monkeypatch, root) == 0
    assert _headline(capsys.readouterr().out) == evidence.headline(sha, True)
    # The shard the change was beside, and the one after it, ran again; the one before was reused.
    assert _ran(root)[3:] == ["tests/test_1.txt", "tests/test_2.txt"]
    assert _kept(root, sha) == ["unit-000.json", "unit-001.json", "unit-002.json"]


# ---------- 5. --allow-dirty keeps the marker for a tree that changed mid-run (moved from #671) ----------


@pytest.mark.parametrize(
    "cmd",
    ["echo v2 > notes.txt", "echo extra > extra.txt", "echo v2 > lib/lib.txt", "echo extra > lib/extra.txt"],
    ids=["tracked", "untracked", "submodule", "untracked in a submodule"],
)
def test_allow_dirty_on_a_clean_tree_that_changes_mid_run_gives_the_dirty_marker(tmp_path, monkeypatch, capsys, cmd):
    root = _with_submodule(tmp_path)
    sha = _sha(root)
    _act(root, "tests/test_1.txt", cmd)
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    assert _kept(root, sha) == ["unit-000.json"]
    # The note names the file, inside the submodule too.
    assert f"`{cmd.split('> ')[1]}`" in next(l for l in out.splitlines() if "while it ran" in l)


def test_allow_dirty_on_a_clean_tree_sees_an_untracked_file_that_came_and_went(tmp_path, monkeypatch, capsys):
    # Like a tracked edit undone within a shard: the file is gone by the next look, its folder still shows it.
    root = _repo(tmp_path)
    sha = _sha(root)
    _act(root, "tests/test_1.txt", "echo pass > tests/test_9.txt && rm tests/test_9.txt")
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    assert "`tests/`" in next(l for l in out.splitlines() if "while it ran" in l)
    assert _kept(root, sha) == ["unit-000.json"]
    assert _dirty_kept(root, sha) == ["unit-001.json", "unit-002.json"]


def test_allow_dirty_on_a_clean_tree_with_no_workflow_folder_yet_is_a_clean_report(tmp_path, monkeypatch, capsys):
    # The run's own store, made in the project's folder, isn't a change beside it.
    root = _repo(tmp_path)
    shutil.rmtree(root / ".workflow")
    sha = _sha(root)
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    assert _headline(capsys.readouterr().out) == evidence.headline(sha, True)
    assert _kept(root, sha) == ["unit-000.json", "unit-001.json", "unit-002.json"]


def test_allow_dirty_on_a_dirty_tree_names_what_changed_mid_run_too(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    (root / "notes.txt").write_text("dirty\n")
    sha = _sha(root)
    _act(root, "tests/test_0.txt", "echo again > tests/test_2.txt.bak && echo pass > tests/test_2.txt")
    _evidence(monkeypatch, root, "--allow-dirty")
    out = capsys.readouterr().out
    assert _headline(out) == evidence.headline(sha, True, dirty=True)
    note = next(l for l in out.splitlines() if "while it ran" in l)
    assert "tests/test_2.txt" in note
    assert _kept(root, sha) == []


def test_allow_dirty_on_a_clean_tree_left_alone_is_a_clean_report(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    sha = _sha(root)
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    assert _headline(capsys.readouterr().out) == evidence.headline(sha, True)


# ---------- 6. the page lists the helper and says what each check does ----------


def _page() -> str:
    return (ROOT / "docs/architecture/scripts--workflow.md").read_text()


def test_the_tree_state_is_a_helper_listed_in_its_page(tmp_path):
    helpers = _page().split("\n## Helpers\n", 1)[1].split("\n## ", 1)[0]
    assert re.search(r"^- `tree_state`: ", helpers, re.M)
    root = _with_submodule(tmp_path)
    before = evidence.tree_state(root)
    assert before == evidence.tree_state(root)  # a second look at a tree left alone is the same
    (root / "lib/lib.txt").write_text("lib v1\n")  # the same bytes, written again
    after = evidence.tree_state(root)
    assert evidence.tree_changes(before, after) == ["lib/lib.txt"]
    (root / "x.txt").write_text("x")
    assert evidence.tree_changes(after, evidence.tree_state(root)) == []
    assert evidence.tree_changes(after, evidence.tree_state(root), untracked=True) == ["./", "x.txt"]  # and the folder it appeared in

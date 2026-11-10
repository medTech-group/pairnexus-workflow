"""#671: a background evidence run never reports a tree it didn't test.

The suite's runner below stands in for the session working beside the run: after
the shard holding a given file, it carries out an action written in
`.workflow/act` (git-ignored, like all of .workflow/), once. Each shard it runs
is logged to `.workflow/ran`, so a test sees which shards ran and which were
reused."""

import re
from pathlib import Path

import pytest
from conftest import git

from workflow import cli, evidence

ROOT = Path(__file__).resolve().parents[1]

RUNNER = (
    "import os, subprocess, sys\n"
    "p=f=0\n"
    "for a in sys.argv[1:]:\n"
    "    r=open(a).read().strip()\n"
    "    p+=r=='pass'; f+=r=='fail'\n"
    "open('.workflow/ran','a').write(' '.join(sys.argv[1:])+'\\n')\n"
    "act='.workflow/act'\n"
    "if os.path.exists(act):\n"
    "    when, cmd = open(act).read().split('\\n', 1)\n"
    "    if when in sys.argv[1:]:\n"
    "        os.remove(act)\n"
    "        subprocess.run(cmd, shell=True, check=True)\n"
    "print(f'{p} passed' + (f', {f} failed' if f else ''))\n"
    "sys.exit(1 if f else 0)\n"
)

TESTS = {"tests/test_0.txt": "pass", "tests/test_1.txt": "pass", "tests/test_2.txt": "pass"}


def _repo(tmp_path, run="python3 run_tests.py {files}", repair=""):
    for name, result in TESTS.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(result)
    (tmp_path / "run_tests.py").write_text(RUNNER)
    (tmp_path / "notes.txt").write_text("v1\n")
    (tmp_path / ".gitignore").write_text(".workflow/\n")
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "d"\nrepo = "a/d"\n'
        + (f"[repair]\ncommands = [{repair!r}]\n" if repair else "")
        + f'[[commands.suite]]\nname = "unit"\nrun = "{run}"\nfiles = "tests/test_*.txt"\ngroup = 1\n'
    )
    (tmp_path / ".workflow").mkdir()
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@e")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "x")
    return tmp_path


def _act(root, after: str, cmd: str) -> None:
    """After the shard holding `after`, run `cmd` in the checkout, once."""
    (root / ".workflow/act").write_text(f"{after}\n{cmd}")


def _ran(root) -> list[str]:
    f = root / ".workflow/ran"
    return f.read_text().splitlines() if f.exists() else []


def _evidence(monkeypatch, root, *args):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return cli.main(["evidence", *args])


def _store(root) -> Path:
    return root / ".workflow/evidence" / git(root, "rev-parse", "HEAD").strip()


# ---------- 1. a changed tree is never reported as the commit's ----------
#
# The run can't tell a tracked file its suites or repair commands wrote from one
# the session changed beside it, so it never stops for one (AC 3): from that
# shard on, what it runs is kept apart from the commit's, and its report is a
# dirty one, which merge-check never counts (AC 1).


def _sha(root) -> str:
    return git(root, "rev-parse", "HEAD").strip()


def test_a_tracked_file_changed_mid_run_makes_a_dirty_report(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _act(root, "tests/test_1.txt", "echo fail > tests/test_2.txt")
    assert _evidence(monkeypatch, root) == 1
    cap = capsys.readouterr()
    # Never a report that names the commit as tested: its first line says it isn't.
    assert cap.out.splitlines()[0] == evidence.headline(_sha(root), False, dirty=True)
    assert "tests/test_2.txt" in cap.out and "changed while it ran" in cap.out
    # The shard the change landed in isn't kept as the commit's; the one before it is.
    assert (_store(root) / "unit-000.json").exists()
    assert not (_store(root) / "unit-001.json").exists()
    assert not (_store(root) / "unit-002.json").exists()


def test_a_merge_left_in_conflict_mid_run_makes_a_dirty_report(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    git(root, "checkout", "-qb", "other")
    (root / "notes.txt").write_text("other\n")
    git(root, "commit", "-qam", "other")
    git(root, "checkout", "-q", "main")
    (root / "notes.txt").write_text("main\n")
    git(root, "commit", "-qam", "main")
    _act(root, "tests/test_0.txt", "git merge -q other || true")
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(evidence.DIRTY) and "notes.txt" in out
    assert not (_store(root) / "unit-000.json").exists()


def test_a_file_staged_mid_run_makes_a_dirty_report(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _act(root, "tests/test_0.txt", "echo pass > tests/test_9.txt && git add tests/test_9.txt")
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(evidence.DIRTY) and "tests/test_9.txt" in out


def test_an_untracked_file_that_appears_mid_run_is_named_in_the_report(tmp_path, monkeypatch, capsys):
    # The run can't tell a file the suite wrote from one the session added, so it
    # finishes (AC 3) and names the file; the session's own steps (build-ticket
    # §6 step 2) keep it from adding one while the run goes.
    root = _repo(tmp_path)
    _act(root, "tests/test_0.txt", "echo pass > tests/test_9.txt")
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert re.search(r"Files that appeared while it ran.*`tests/test_9\.txt`", out)
    assert "NOT A PROOF" not in out.splitlines()[0]


# ---------- 2. an interrupted shard is never reused ----------


def test_a_shard_run_on_a_changed_tree_runs_again_on_the_next_run(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _act(root, "tests/test_1.txt", "echo v2 > notes.txt")
    assert _evidence(monkeypatch, root) == 0
    assert capsys.readouterr().out.splitlines()[0].endswith(evidence.DIRTY)
    assert _ran(root) == ["tests/test_0.txt", "tests/test_1.txt", "tests/test_2.txt"]
    git(root, "checkout", "--", "notes.txt")  # the tree is clean again, on the same commit
    assert _evidence(monkeypatch, root) == 0
    # Shard 0 finished before the change and is reused; shard 1 and 2 run again.
    assert _ran(root)[3:] == ["tests/test_1.txt", "tests/test_2.txt"]
    out = capsys.readouterr().out
    assert out.splitlines()[0] == evidence.headline(_sha(root), True) and "3 passed" in out


def test_a_shard_the_head_moved_under_runs_again_on_that_commit(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    sha = git(root, "rev-parse", "HEAD").strip()
    _act(root, "tests/test_1.txt", "git commit -q --allow-empty -m moved")
    assert _evidence(monkeypatch, root) == 1
    assert "HEAD moved" in capsys.readouterr().err
    assert not (root / ".workflow/evidence" / sha / "unit-001.json").exists()
    git(root, "reset", "-q", "--hard", sha)  # back on the commit the run stopped on
    assert _evidence(monkeypatch, root) == 0
    assert _ran(root)[2:] == ["tests/test_1.txt", "tests/test_2.txt"]


def test_a_failing_shard_is_never_saved_as_passing_when_the_tree_changed(tmp_path, monkeypatch, capsys):
    # #670 round 2: a shard saved as ok before the stop made a restart report a
    # passing commit whose test fails. Here the session's edit makes the shard pass
    # (test_1 reads "pass" at the time it runs); the commit's own test_1 fails.
    root = _repo(tmp_path)
    (root / "tests/test_1.txt").write_text("fail")
    git(root, "commit", "-qam", "test_1 fails")
    _act(root, "tests/test_0.txt", "echo pass > tests/test_1.txt")
    assert _evidence(monkeypatch, root) == 0  # every shard passed, on a tree that wasn't the commit
    assert capsys.readouterr().out.splitlines()[0] == evidence.headline(_sha(root), True, dirty=True)
    git(root, "checkout", "--", "tests/test_1.txt")
    assert _evidence(monkeypatch, root) == 1
    assert capsys.readouterr().out.splitlines()[0] == evidence.headline(_sha(root), False)


# ---------- 3. files the run writes itself ----------


def test_a_suite_that_writes_a_tracked_file_finishes_with_a_dirty_report(tmp_path, monkeypatch, capsys):
    # It can't be told from the session's edit, so the report isn't the commit's;
    # the run still finishes, and says what to do (AC 3).
    root = _repo(tmp_path, run="python3 run_tests.py {files} && date >> notes.txt")
    assert _evidence(monkeypatch, root) == 0
    cap = capsys.readouterr()
    assert cap.out.splitlines()[0] == evidence.headline(_sha(root), True, dirty=True)
    assert "3 passed" in cap.out and "(notes.txt)" in cap.out
    assert "If the suites or the `[repair]` commands write them, make them write elsewhere" in cap.out
    assert not any(_store(root).glob("unit-*.json"))  # nothing kept as the commit's


def test_a_suite_that_writes_files_not_ignored_still_finishes(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, run="python3 run_tests.py {files} && mkdir -p test-results && touch coverage.xml test-results/r.xml")
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith("passed")
    assert "3 passed" in out


def test_a_repair_command_that_writes_files_not_ignored_still_finishes(tmp_path, monkeypatch, capsys):
    # The repair runs before the first shard and again after a failing one.
    root = _repo(tmp_path, repair="date >> repaired.log")
    (root / "tests/test_0.txt").write_text("fail")
    git(root, "commit", "-qam", "test_0 fails")
    assert _evidence(monkeypatch, root) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == evidence.headline(_sha(root), False)
    assert "2 passed, 1 failed" in out  # every shard ran: nothing stopped it
    assert "`repaired.log`" in out


def test_a_repair_command_that_writes_a_tracked_file_finishes_with_a_dirty_report(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, repair="date >> notes.txt")
    (root / "tests/test_0.txt").write_text("fail")
    git(root, "commit", "-qam", "test_0 fails")
    assert _evidence(monkeypatch, root) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == evidence.headline(_sha(root), False, dirty=True)
    assert "2 passed, 1 failed" in out and "(notes.txt)" in out


def test_a_tracked_file_changed_while_the_repair_ran_is_never_the_commits(tmp_path, monkeypatch, capsys):
    # The repair stands in for a slow `npm ci` during which the session edits a
    # test: the commit's test_1 fails, the edited one passes.
    root = _repo(tmp_path, repair="echo pass > tests/test_1.txt")
    (root / "tests/test_1.txt").write_text("fail")
    git(root, "commit", "-qam", "test_1 fails")
    assert _evidence(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == evidence.headline(_sha(root), True, dirty=True)
    assert "tests/test_1.txt" in out
    assert not any(_store(root).glob("unit-*.json"))


# ---------- 4. --allow-dirty keeps the marker ----------


def test_allow_dirty_on_a_clean_start_marks_a_tree_that_changed_mid_run(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _act(root, "tests/test_1.txt", "echo v2 > notes.txt")
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(evidence.DIRTY)
    assert "notes.txt" in out and "changed while it ran" in out
    # Nothing that ran on the changed tree is kept as the commit's own: a clean
    # run on the commit runs shards 1 and 2 again, and reuses shard 0.
    git(root, "checkout", "--", "notes.txt")
    capsys.readouterr()
    assert _evidence(monkeypatch, root) == 0
    assert _ran(root)[3:] == ["tests/test_1.txt", "tests/test_2.txt"]
    assert not capsys.readouterr().out.splitlines()[0].endswith(evidence.DIRTY)


def test_allow_dirty_marks_a_tracked_file_changed_while_the_repair_ran(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, repair="echo v2 > notes.txt")
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(evidence.DIRTY) and "(notes.txt)" in out
    assert not any(_store(root).glob("unit-*.json"))


def test_allow_dirty_marks_an_untracked_file_that_appeared_mid_run(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _act(root, "tests/test_0.txt", "echo pass > tests/test_9.txt")
    assert _evidence(monkeypatch, root, "--allow-dirty") == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(evidence.DIRTY)
    assert "tests/test_9.txt" in out


def test_allow_dirty_on_a_dirty_start_names_what_changed_mid_run(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    (root / "notes.txt").write_text("dirty at the start\n")
    _act(root, "tests/test_0.txt", "echo fail > tests/test_2.txt")
    assert _evidence(monkeypatch, root, "--allow-dirty") == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0].endswith(evidence.DIRTY)
    assert "tests/test_2.txt" in out and "changed while it ran" in out


# ---------- 5. the session's own steps ----------


def _section_6_step_2(text: str) -> str:
    s6 = text.split("## 6. Post the evidence and merge", 1)[1].split("\n## 7.", 1)[0]
    return s6.split("\n2. ", 1)[1].split("\n3. ", 1)[0]


@pytest.mark.parametrize("path", ["skills/build-ticket/SKILL.md"])
def test_build_ticket_stops_the_background_run_before_changing_the_checkout(path):
    step = _section_6_step_2((ROOT / path).read_text())
    rule = step.split("**While it runs,", 1)[1].split("\n   - ", 1)[0]
    # Before any change to the checkout it stops the run, which the run can't
    # always see itself (an untracked file it might have written).
    for word in ("edit", "merging the base in", "pull", "untracked", "stop it first", "TaskStop"):
        assert word in rule, word


# ---------- 6. the page's helpers (the overview's "Reuse, not copies") ----------


def _helpers() -> str:
    page = (ROOT / "docs/architecture/scripts--workflow.md").read_text()
    return page.split("\n## Helpers\n", 1)[1].split("\n## ", 1)[0] if "\n## Helpers\n" in page else ""


def test_the_path_list_is_one_helper_listed_in_its_page(tmp_path):
    assert re.search(r"^- `_paths`: ", _helpers(), re.M)
    names = [f"f{i}.txt" for i in range(7)]
    assert evidence._paths(names) == "f0.txt, f1.txt, f2.txt, f3.txt, f4.txt and 2 more"
    assert evidence._paths(names, code=True).startswith("`f0.txt`, `f1.txt`") and " and 2 more" in evidence._paths(names, code=True)
    # require_clean and the report's "appeared" line name paths the same way.
    root = _repo(tmp_path)
    for n in names:
        (root / n).write_text("x")
    with pytest.raises(evidence.EvidenceError, match=re.escape(evidence._paths(names))):
        evidence.require_clean(root)


def test_the_report_names_files_that_appeared_with_the_path_helper(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    names = [f"out{i}.txt" for i in range(7)]
    _act(root, "tests/test_2.txt", "touch " + " ".join(names))
    assert _evidence(monkeypatch, root) == 0
    assert evidence._paths(names, code=True) + "." in capsys.readouterr().out


def test_the_dirty_store_is_one_helper_listed_in_its_page(tmp_path):
    assert re.search(r"^- `_dirty_store`: ", _helpers(), re.M)
    old = tmp_path / ".workflow/evidence/abc-dirty"
    old.mkdir(parents=True)
    (old / "unit-000.json").write_text("{}")
    d = evidence._dirty_store(None, tmp_path, "abc")
    assert d == old and d.is_dir() and not any(d.iterdir())  # emptied: never reused
    assert evidence._dirty_store(tmp_path / "s", tmp_path, "abc") == tmp_path / "s/abc-dirty"

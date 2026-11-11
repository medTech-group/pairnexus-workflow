"""#671: a background evidence run never reports a tree it didn't test: a shard
the head moved under is never kept, and the session stops the run before
changing its checkout.

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


def _sha(root) -> str:
    return git(root, "rev-parse", "HEAD").strip()


# ---------- 1. a shard the head moved under is never reused ----------


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


# ---------- 2. files the run writes itself still let it finish ----------


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


# ---------- 3. the session's own steps ----------


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


# ---------- 4. the page's helpers (the overview's "Reuse, not copies") ----------


def _helpers() -> str:
    page = (ROOT / "docs/architecture/scripts--workflow.md").read_text()
    return page.split("\n## Helpers\n", 1)[1].split("\n## ", 1)[0] if "\n## Helpers\n" in page else ""


def test_the_path_list_is_one_helper_listed_in_its_page(tmp_path):
    assert re.search(r"^- `_paths`: ", _helpers(), re.M)
    names = [f"f{i}.txt" for i in range(7)]
    assert evidence._paths(names) == "f0.txt, f1.txt, f2.txt, f3.txt, f4.txt and 2 more"
    # require_clean names its paths with it.
    root = _repo(tmp_path)
    for n in names:
        (root / n).write_text("x")
    with pytest.raises(evidence.EvidenceError, match=re.escape(evidence._paths(names))):
        evidence.require_clean(root)


def test_the_dirty_store_is_one_helper_listed_in_its_page(tmp_path):
    assert re.search(r"^- `_dirty_store`: ", _helpers(), re.M)
    old = tmp_path / ".workflow/evidence/abc-dirty"
    old.mkdir(parents=True)
    (old / "unit-000.json").write_text("{}")
    d = evidence._dirty_store(None, tmp_path, "abc")
    assert d == old and d.is_dir() and not any(d.iterdir())  # emptied: never reused
    assert evidence._dirty_store(tmp_path / "s", tmp_path, "abc") == tmp_path / "s/abc-dirty"


def test_the_pages_rule_says_what_each_check_does():
    page = (ROOT / "docs/architecture/scripts--workflow.md").read_text()
    rule = page.split("\n## Rules\n", 1)[1]
    # True for the code: HEAD is checked before a shard's result is kept, and
    # the working tree only at the start.
    for words in ("only after checking", "HEAD", "nothing kept for that shard", "only at its start"):
        assert words in rule, words
    assert "untracked" not in rule and "changed tree" not in rule

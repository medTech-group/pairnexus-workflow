"""Evidence: the base ref, counts from the runner's summary, and logs per attempt."""

import json
from pathlib import Path

import pytest
from conftest import git

from workflow import cli, evidence
from workflow.profile import parse

RUNNER = (
    "import sys\n"
    "p=f=0\n"
    "for a in sys.argv[1:]:\n"
    "    r=open(a).read().strip()\n"
    "    p+=r=='pass'; f+=r=='fail'\n"
    "print(f'{p} passed' + (f', {f} failed' if f else ''))\n"
    "sys.exit(1 if f else 0)\n"
)


def _suite(**kw):
    return parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [{"name": "u", "run": "x", **kw}]}}, Path(".")).suites[0]


def _repo(tmp_path, tests: dict[str, str], setup: str = "", run: str = "python3 run_tests.py {files}", extra_suites=()):
    """A committed repo with a profile, the runner and the given test files."""
    for name, result in tests.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(result)
    (tmp_path / "run_tests.py").write_text(RUNNER)
    (tmp_path / ".gitignore").write_text(".workflow/\n")
    suites = [f'[[commands.suite]]\nname = "unit"\nrun = "{run}"\nfiles = "tests/test_*.txt"\n']
    suites += list(extra_suites)
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        f'[project]\nname = "d"\nrepo = "a/d"\n[commands]\nsetup = "{setup}"\n' + "\n".join(suites)
    )
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@e")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "x")
    return tmp_path


def _evidence(monkeypatch, root, *args):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return cli.main(["evidence", *args])


# ---------- 1. --base-ref ----------


def test_a_bad_base_ref_fails_before_anything_runs(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {"tests/test_0.txt": "pass"})
    assert _evidence(monkeypatch, root, "--base-ref", "no-such-branch") == 1
    assert "not a commit here" in capsys.readouterr().err
    assert not (root / ".workflow/evidence").exists()  # nothing ran


def test_the_base_worktree_runs_setup_first_and_nothing_else(tmp_path, monkeypatch, capsys):
    # The suite needs what setup makes; setup's output isn't ignored, and the base still runs.
    root = _repo(
        tmp_path,
        {"tests/test_0.txt": "pass", "tests/test_1.txt": "pass"},
        setup="touch built",
        run="test -f built && python3 run_tests.py {files}",
    )
    (root / "built").write_text("")  # the head's own setup, done by hand
    (root / ".gitignore").write_text(".workflow/\nbuilt\n")
    git(root, "commit", "-qam", "ignore built")
    git(root, "branch", "base", "HEAD~1")
    assert _evidence(monkeypatch, root, "--base-ref", "base") == 0
    out = capsys.readouterr().out
    assert "Base branch (`base` at" in out and "2 passed; this commit: 2" in out
    b = evidence.base_count_from_ref(parse_profile(root), root, "base")
    assert b.count == 2 and not b.problem
    # Nothing of the head's is copied in: without setup the base has no `built`.
    prof = parse_profile(root)
    prof.setup = ""
    b = evidence.base_count_from_ref(prof, root, "base", fresh=True)
    assert b.count is None and "unit shard 0 didn't pass there" in b.problem


def parse_profile(root):
    from workflow.profile import load

    return load(root)


def test_a_failing_base_run_is_reported_not_compared(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {"tests/test_0.txt": "fail", "tests/test_1.txt": "pass"})
    git(root, "branch", "base")
    (root / "tests/test_0.txt").write_text("pass")
    git(root, "commit", "-qam", "fix")
    # The commit's own result stands; the report says the count wasn't compared.
    assert _evidence(monkeypatch, root, "--base-ref", "base") == 0
    out = capsys.readouterr().out
    assert "no usable base count from base: unit shard 0 didn't pass there" in out.lower()
    assert "Not compared with the base branch" in out and "FAILED" not in out.splitlines()[0]


def test_setup_failing_on_the_base_is_no_usable_count(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, {"tests/test_0.txt": "pass"}, setup="exit 3")
    git(root, "branch", "base")
    prof = parse_profile(root)
    b = evidence.base_count_from_ref(prof, root, "base")
    assert b.count is None and "commands.setup (`exit 3`) exited 3" in b.problem
    sha, res = evidence.collect(prof, root)
    ok, md = evidence.report(sha, prof, res, b.count, base_problem=f"no usable base count from base: {b.problem}")
    assert ok and "Not compared with the base branch:" in md and "no usable base count from base: commands.setup" in md


def test_a_suite_with_no_files_on_the_base_counts_zero_with_a_note(tmp_path, monkeypatch, capsys):
    web = '[[commands.suite]]\nname = "web"\nrun = "python3 run_tests.py {files}"\nfiles = "web/test_*.txt"\n'
    root = _repo(tmp_path, {"tests/test_0.txt": "pass"}, extra_suites=[web])
    # The base has no web/ yet: only the head adds it. (The profile names it on both.)
    (root / "web").mkdir()
    (root / "web/test_a.txt").write_text("pass")
    git(root, "branch", "base")
    git(root, "add", ".")
    git(root, "commit", "-qm", "add web tests")
    b = evidence.base_count_from_ref(parse_profile(root), root, "base")
    assert b.count == 1 and not b.problem
    assert b.notes == ["suite web: no files match 'web/test_*.txt' here, so it counts 0"]
    assert _evidence(monkeypatch, root, "--base-ref", "base") == 0
    out = capsys.readouterr().out
    assert "- Base branch: suite web: no files match" in out and "1 passed; this commit: 2" in out


# ---------- 2. gotestsum's total ----------


def test_total_regex_works_out_passed():
    s = _suite(total=r"DONE (\d+) tests", failed=r"(\d+) failures?", skipped=r"(\d+) skipped")
    c = evidence.counts(s, "ok pkg\nDONE 42 tests, 1 skipped, 2 failures in 3.2s\n", "")
    assert c == {"passed": 39, "failed": 2, "skipped": 1, "errors": 0}
    assert evidence.counts(s, "DONE 5 tests in 1.0s\n", "")["passed"] == 5


def test_the_template_documents_total():
    text = (Path(__file__).resolve().parents[1] / "templates/profile.toml").read_text()
    assert "total = 'DONE (\\d+) tests'" in text and "passed = total - skipped - failed - errors" in text


# ---------- 3. counts from the summary ----------


def test_pytest_counts_only_its_summary_line():
    s = _suite(run="python -m pytest {files} -q")
    out = (
        "FAILED tests/test_x.py::test_a - AssertionError: assert 'all 3 passed' == ''\n"
        "E   3 passed\n"
        "==================== 1 failed, 2 passed in 0.50s ====================\n"
    )
    assert evidence.counts(s, out, "") == {"passed": 2, "failed": 1, "skipped": 0, "errors": 0}
    quiet = "F..\nE   AssertionError: 3 passed\nFAILED tests/test_x.py::test_a - 3 passed\n1 failed, 2 passed in 0.12s\n"
    assert evidence.counts(s, quiet, "")["passed"] == 2


def test_other_runners_read_the_last_lines_without_hints_or_colours():
    s = _suite(run="npx playwright test")
    out = "\n".join(
        ["  3 passed"] + [f"  ok {i}" for i in range(6)] + ["", "  \x1b[32m10 passed\x1b[39m (30s)", "\x1b[0m", "", "To open last HTML report run:", "", "  npx playwright show-report", ""]
    )
    assert evidence.counts(s, out, "")["passed"] == 10


def test_a_shard_of_only_skipped_tests_counts_zero(tmp_path):
    (tmp_path / "x").write_text("")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@e")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "x")
    prof = parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [{"name": "s", "run": "echo '4 skipped'"}]}}, tmp_path)
    sha, res = evidence.collect(prof, tmp_path)
    assert res[0].ok and res[0].problem == "" and res[0].counted == 0 and res[0].skipped == 4
    ok, md = evidence.report(sha, prof, res)
    assert ok and "every test was skipped" in md and evidence.NO_COUNTS not in md


# ---------- 4. a log per attempt ----------


def test_each_attempt_keeps_its_log(tmp_path):
    root = _repo(tmp_path, {"tests/test_0.txt": "pass"})
    prof = parse_profile(root)
    prof.suites[0].run = "test -f .workflow/ok && python3 run_tests.py {files}"
    (root / ".workflow").mkdir()
    sha, res = evidence.collect(prof, root)
    assert not res[0].ok and res[0].log.endswith("unit-000.1.log")
    (root / ".workflow/ok").write_text("")
    sha, res = evidence.collect(prof, root)
    assert res[0].ok and res[0].log.endswith("unit-000.2.log")
    prev = res[0].previous_failures[0]["log"]
    assert prev.endswith("unit-000.1.log") and "# exit: 1" in (root / prev).read_text()
    assert "1 passed" in (root / res[0].log).read_text()
    saved = json.loads((root / f".workflow/evidence/{sha}/unit-000.json").read_text())
    assert saved["previous_failures"][0]["log"] == prev

"""Evidence: only the suites a pull request's changed files need (`commands.select_suites`)."""

from pathlib import Path

import pytest
from conftest import git

from workflow import cli, evidence
from workflow.profile import ProfileError, load, parse, summary

RUNNER = (
    "import sys\n"
    "p=f=0\n"
    "for a in sys.argv[1:]:\n"
    "    r=open(a).read().strip()\n"
    "    p+=r=='pass'; f+=r=='fail'\n"
    "print(f'{p} passed' + (f', {f} failed' if f else ''))\n"
    "sys.exit(1 if f else 0)\n"
)

# The project's own rules, kept apart from the selector as a real one might:
# web/ needs the web suite, src/ the unit suite, markdown and tests/ nothing
# (the kit adds a suite whose test files changed), anything else both.
RULES = "RULES = {'web/': ['web'], 'src/': ['unit'], 'tests/': []}\n"
SELECTOR = (
    "import sys\n"
    "from rules import RULES\n"
    "out = set()\n"
    "for p in sys.stdin.read().splitlines():\n"
    "    hit = [v for k, v in RULES.items() if p.startswith(k)]\n"
    "    if p.endswith('.md'): continue\n"
    "    if hit: out.update(hit[0])\n"
    "    else: out.update(['unit', 'web'])\n"
    "print('\\n'.join(sorted(out)) or 'none')\n"
)

SUITES = (
    '[[commands.suite]]\nname = "unit"\nrun = "python3 run_tests.py {files}"\nfiles = "tests/test_*.txt"\n'
    '[[commands.suite]]\nname = "web"\nrun = "python3 run_tests.py {files}"\nfiles = "web/test_*.txt"\n'
)
BASE = "origin/main"


def _repo(tmp_path, select: str | None = "python3 select_suites.py", ci: str = "") -> Path:
    """A committed repo with two suites and the selector, `main` pushed to a bare
    `origin`, and a `feature` branch checked out."""
    root = tmp_path / "proj"
    for path, text in {
        "tests/test_0.txt": "pass",
        "web/test_0.txt": "pass",
        "web/test_1.txt": "pass",
        "src/a.txt": "a",
        "run_tests.py": RUNNER,
        "select_suites.py": SELECTOR,
        "rules.py": RULES,
        ".gitignore": ".workflow/\n__pycache__/\n",
    }.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    commands = "[commands]\n" + (f'select_suites = "{select}"\n' if select is not None else "")
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(f'[project]\nname = "d"\nrepo = "a/d"\n{ci}{commands}{SUITES}')
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@e")
    git(root, "config", "user.name", "t")
    git(root, "add", ".")
    git(root, "commit", "-qm", "x")
    git(tmp_path, "init", "-q", "--bare", "origin.git")
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    git(root, "checkout", "-qb", "feature")
    return root


def _change(root: Path, path: str, text: str = "changed") -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)
    git(root, "add", path)
    git(root, "commit", "-qm", f"change {path}")


def _evidence(monkeypatch, root, *args):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    return cli.main(["evidence", *args])


def _ran(root: Path, sha: str) -> set[str]:
    """The suites with a shard result kept for this commit."""
    d = root / ".workflow/evidence" / sha
    return {f.name.rsplit("-", 1)[0] for f in d.glob("*.json")} if d.is_dir() else set()


def _sha(root, ref="HEAD"):
    return git(root, "rev-parse", ref).strip()


def _select(root):
    return evidence.select(load(root), root, BASE, _sha(root, BASE))


# ---------- the profile ----------


def test_select_suites_is_a_string_and_shows_in_the_summary():
    base = {"project": {"name": "d", "repo": "a/d"}}
    prof = parse({**base, "commands": {"select_suites": "python3 x.py"}}, Path("."))
    assert prof.select_suites == "python3 x.py" and summary(prof)["select_suites"] == "python3 x.py"
    assert parse(base, Path(".")).select_suites == "" and summary(parse(base, Path(".")))["select_suites"] is None
    with pytest.raises(ProfileError, match="commands.select_suites"):
        parse({**base, "commands": {"select_suites": ["python3", "x.py"]}}, Path("."))


def test_no_suite_may_be_named_none_beside_select_suites():
    none = {"name": "none", "run": "x"}
    with pytest.raises(ProfileError, match='named "none"'):
        parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"select_suites": "x", "suite": [none]}}, Path("."))
    parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [none]}}, Path("."))


# ---------- only what the files need ----------


def test_only_the_needed_suites_run_on_the_branch_and_the_base(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _change(root, "web/page.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    head = _sha(root)
    assert _ran(root, head) == {"web"}
    assert _ran(root, _sha(root, BASE)) == {"web"}  # the base ran the same suites
    first = out.splitlines()[0]
    assert first == f"**Local suites its files need on `{head}`**: passed"
    assert evidence.read_headline(first) == (head, True, False) and not evidence.is_full(first)
    assert (
        "- **Only the suites this PR's files need** (`python3 select_suites.py`, given the files changed since "
        "`origin/main`): ran web; not needed: unit."
    ) in out
    assert "**web**" in out and "**unit**" not in out
    assert "Base branch (`origin/main` at" in out and "2 passed; this commit: 2" in out
    assert not (root / f".workflow/select-{_sha(root, BASE)}").exists()
    assert len(git(root, "worktree", "list").splitlines()) == 1


def test_every_suite_needed_keeps_the_full_suite_headline(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _change(root, "web/page.txt")
    _change(root, "src/a.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"**Local full suite on `{_sha(root)}`**: passed")
    assert _ran(root, _sha(root)) == {"unit", "web"}
    assert "Every suite was needed for the files changed since `origin/main` (`python3 select_suites.py`)." in out


def test_a_failure_in_a_needed_suite_still_fails(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _change(root, "web/test_1.txt", "fail")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 1
    assert capsys.readouterr().out.startswith(f"**Local suites its files need on `{_sha(root)}`**: FAILED")


def test_no_suite_needed_runs_nothing_and_passes(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _change(root, "README.md")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    head = _sha(root)
    assert out.splitlines()[0] == f"**Local suites its files need on `{head}`**: passed"
    assert not _ran(root, head) and not _ran(root, _sha(root, BASE))
    assert "- **No suite needed** for the files changed since `origin/main` (`python3 select_suites.py`): unit and web didn't run." in out
    assert "No base-branch count given" not in out


def test_no_suite_needed_still_refuses_a_dirty_tree(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _change(root, "README.md")
    (root / "notes.txt").write_text("untracked")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 1
    assert "untracked" in capsys.readouterr().err
    assert _evidence(monkeypatch, root, "--base-ref", BASE, "--allow-dirty") == 0
    first = capsys.readouterr().out.splitlines()[0]
    assert first == f"**Local suites its files need on `{_sha(root)}`**: passed{evidence.DIRTY}"
    assert evidence.read_headline(first) == (_sha(root), True, True)


@pytest.mark.parametrize("how", ["added", "deleted"])
def test_a_changed_test_file_always_runs_its_suite(tmp_path, how):
    root = _repo(tmp_path)
    if how == "added":
        _change(root, "tests/test_9.txt", "pass")  # the rules say tests/ needs nothing
    else:  # so the base comparison sees the test gone
        git(root, "rm", "-q", "tests/test_0.txt")
        git(root, "commit", "-qm", "drop a test")
    sel = _select(root)
    assert sel.names == ["unit"] and sel.skipped == ["web"]


def test_the_base_branchs_selector_decides_not_the_branchs(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    # The branch rewrites a module the selector reads, so by its own rules nothing would run.
    _change(root, "rules.py", "RULES = {'rules.py': [], 'web/': [], 'src/': [], 'tests/': []}\n")
    _change(root, "web/page.txt")
    sel = _select(root)
    # The base's rules don't know rules.py, so both: web/page.txt's web and the fallback's unit.
    assert sel.names == ["unit", "web"] and sel.skipped == []


# ---------- every suite, when the selection can't be trusted ----------


@pytest.mark.parametrize(
    "path, why",
    [
        (".github/workflows/ci.yml", "`.github/workflows/ci.yml` changed, and a change there can change what runs"),
        (".claude/workflow/profile.toml", "`.claude/workflow/profile.toml` changed, and a change there can change what runs"),
        (".claude/workflow/bin/workflow/evidence.py", "`.claude/workflow/bin/workflow/evidence.py` changed, and a change there can change what runs"),
        ("select_suites.py", "`select_suites.py`, which commands.select_suites runs, changed"),
    ],
)
def test_a_change_to_what_decides_runs_every_suite(tmp_path, monkeypatch, capsys, path, why):
    root = _repo(tmp_path)
    _change(root, "web/page.txt")
    text = (root / path).read_text() + "\n# changed\n" if (root / path).exists() else "# new\n"
    _change(root, path, text)
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"**Local full suite on `{_sha(root)}`**: passed")
    assert _ran(root, _sha(root)) == {"unit", "web"} and _ran(root, _sha(root, BASE)) == {"unit", "web"}
    assert f"- **Every suite ran:** {why}." in out


@pytest.mark.parametrize(
    "select, why",
    [
        ("exit 3", "`exit 3` exited 3"),
        ("echo mobile", "`echo mobile` named 'mobile', which isn't a suite of the profile"),
        ("echo none; echo web", "`echo none; echo web` named 'none', which isn't a suite of the profile"),
        # A selector that crashed in a pipeline may exit 0 with nothing printed: never "no suite needed".
        ("cat > /dev/null", "`cat > /dev/null` printed no suite (it prints `none` when none is needed)"),
        ("python3 -c 'import time; time.sleep(5)'", "didn't finish in 1 seconds"),
    ],
)
def test_a_selector_that_fails_or_names_no_suite_runs_every_suite(tmp_path, monkeypatch, capsys, select, why):
    monkeypatch.setattr(evidence, "SELECT_TIMEOUT", 1)
    root = _repo(tmp_path, select=select.replace('"', '\\"'))
    _change(root, "web/page.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert _ran(root, _sha(root)) == {"unit", "web"}
    assert "- **Every suite ran:** " in out and why in out


@pytest.mark.parametrize("ref", ["HEAD~1", "feature-start"])
def test_a_base_ref_that_isnt_the_fetched_base_branch_runs_every_suite(tmp_path, monkeypatch, capsys, ref):
    root = _repo(tmp_path)
    _change(root, "src/a.txt")
    git(root, "branch", "feature-start")
    _change(root, "README.md")  # the last commit alone needs no suite
    assert _evidence(monkeypatch, root, "--base-ref", ref) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"**Local full suite on `{_sha(root)}`**: passed") and _ran(root, _sha(root)) == {"unit", "web"}
    assert f"- **Every suite ran:** `{ref}` isn't `origin/main` as fetched here" in out


def test_ci_none_runs_every_suite(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, ci="[ci]\nnone = true\n")
    _change(root, "web/page.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert _ran(root, _sha(root)) == {"unit", "web"}
    assert "- **Every suite ran:** the profile says `ci.none`, so this report is the only proof of the commit." in out


def test_a_diff_that_cant_be_read_runs_every_suite(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    git(root, "checkout", "-q", "--orphan", "unrelated")
    git(root, "commit", "-qm", "no common history")
    git(root, "push", "-q", "-f", "origin", "unrelated:main")
    git(root, "fetch", "-q", "origin")
    git(root, "checkout", "-q", "feature")
    _change(root, "web/page.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert _ran(root, _sha(root)) == {"unit", "web"}
    assert "- **Every suite ran:** couldn't list the files changed since `origin/main`" in out


def test_a_path_with_a_line_break_runs_every_suite(tmp_path):
    root = _repo(tmp_path)
    _change(root, "web/a\nb.md")
    sel = _select(root)
    assert sel.names is None and "a changed path has a line break in it" in sel.why


def test_no_change_since_the_base_runs_every_suite(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert _ran(root, _sha(root)) == {"unit", "web"}
    assert "- **Every suite ran:** no file changed since `origin/main`." in out


# ---------- when no selection is made ----------


def test_without_the_setting_every_suite_runs_as_before(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, select=None)
    _change(root, "web/page.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE) == 0
    out = capsys.readouterr().out
    assert _ran(root, _sha(root)) == {"unit", "web"} and out.startswith("**Local full suite on")
    assert "Every suite" not in out and "Only the suites" not in out


def test_all_and_suite_and_base_count_skip_the_selection(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path)
    _change(root, "web/page.txt")
    assert _evidence(monkeypatch, root, "--base-ref", BASE, "--all") == 0
    out = capsys.readouterr().out
    assert out.startswith("**Local full suite on") and _ran(root, _sha(root)) == {"unit", "web"}
    assert "Only the suites" not in out and "Every suite ran" not in out
    # --suite runs only what it names, so its report isn't the full suite's either.
    assert _evidence(monkeypatch, root, "--base-ref", BASE, "--suite", "unit", "--fresh") == 0
    out = capsys.readouterr().out
    assert out.startswith(f"**Local suites its files need on `{_sha(root)}`**") and "Only the suites" not in out
    assert _evidence(monkeypatch, root, "--base-count", "3") == 0
    assert "Only the suites" not in capsys.readouterr().out
    assert _evidence(monkeypatch, root, "--base-ref", BASE, "--all", "--suite", "unit") == 2
    assert "--all or --suite, not both" in capsys.readouterr().err


def test_select_reads_the_paths_on_stdin_one_a_line(tmp_path):
    root = _repo(tmp_path, select="cat > ../seen && echo web")
    _change(root, "web/a b.txt")  # a space stays inside its line
    _change(root, "src/a.txt")
    git(root, "mv", "src/a.txt", "src/renamed.txt")
    git(root, "commit", "-qm", "rename")
    sel = _select(root)
    assert sel.names == ["web"] and sel.skipped == ["unit"]
    # Run in the base's worktree (.workflow/select-<sha>), so ../seen is in .workflow/.
    # A rename is its old path and its new one, so a rule for either applies.
    assert (root / ".workflow/seen").read_text().splitlines() == ["src/a.txt", "src/renamed.txt", "web/a b.txt"]

"""The hashes of a pull request's own changes on review records (#258, from
#255's seam 2): `workflow review-record` writes `diff=` and `lines=` on round
and pass records, computed from `--commit` against the merge base of
`origin/<base>`, in temporary repositories whose `origin` is a local bare
repository, never the network.
"""

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from changelog_notes import since_0110
from workflow import cli, own_changes, reviews
from workflow.small import Change

KIT = Path(__file__).resolve().parents[1]
PROFILE = '[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n'
APP = "".join(f"line {i}\n" for i in range(1, 31))
EMPTY_BLOB = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "-c", "core.autocrlf=false", *args], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def commit_all(root, message="change"):
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def edit(root, rel, old, new):
    path = root / rel
    path.write_text(path.read_text().replace(old, new))


@pytest.fixture(autouse=True)
def _no_user_git_config(monkeypatch, tmp_path):
    """The developer's global and system git configuration, and their own
    git files (`~/.config/git/ignore` and `attributes`), never reach these
    repositories."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A checkout whose `origin` is a local bare repository, on a branch whose
    change has a file with two hunks, a rename with a change, a rename alone,
    a binary file, an empty file, a change of mode alone, a removed file, a
    path with a space and an accent, and a copy of a changed file (found as
    added: copies are never detected)."""
    origin, root = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(root))
    git(root, "checkout", "-q", "-b", "main")
    (root / ".claude/workflow").mkdir(parents=True)
    (root / ".claude/workflow/profile.toml").write_text(PROFILE)
    for rel, text in {"src/app.py": APP, "docs/old.md": "".join(f"Note {i}.\n" for i in range(1, 11)),
                      "docs/same.md": "Unchanged.\n", "bin/run.sh": "echo hi\n", "data/gone.txt": "a\nb\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    commit_all(root, "base")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-q", "-b", "claude/build-1")
    edit(root, "src/app.py", "line 10\n", "line ten\n")
    edit(root, "src/app.py", "line 20\n", "line twenty\n")
    git(root, "mv", "docs/old.md", "docs/new.md")
    edit(root, "docs/new.md", "Note 5.", "Note five.")
    git(root, "mv", "docs/same.md", "docs/moved.md")
    (root / "assets").mkdir()
    (root / "assets/logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00binary")
    (root / "src/__init__.py").write_text("")
    (root / "bin/run.sh").chmod(0o755)
    (root / "data/gone.txt").unlink()
    (root / "docs/café notes.md").write_text("Ça va.\n")
    (root / "src/app_copy.py").write_text(APP)
    commit_all(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.chdir(root)
    return root


def run(capsys, *args):
    code = cli.main(["review-record", *args])
    out, err = capsys.readouterr()
    return code, out, err


def recorded(capsys, commit, *extra, kind="round"):
    """The record's hashes for `commit`, checking standard output is the record alone."""
    reviewers = "correctness" if kind == "pass" else "standards,spec,correctness"
    code, out, err = run(capsys, "--kind", kind, "--round", "1", "--commit", commit, "--reviewers", reviewers, "--clean", *extra)
    assert code == 0, err
    lines = out.splitlines()
    assert len(lines) == 3 and lines[2] == "<!-- workflow:agent -->", out
    (r,) = reviews.records_in(out)
    return r.diff, r.lines


def head():
    return git(Path.cwd(), "rev-parse", "HEAD")


def base_clone(root):
    """A second clone of `origin`'s main, to move the base on."""
    base = root.parent / "base"
    if not base.exists():
        git(root.parent, "clone", "-q", "-b", "main", str(root.parent / "origin.git"), str(base))
    return base


def move_base(root, rel, old, new):
    base = base_clone(root)
    git(base, "pull", "-q")
    edit(base, rel, old, new)
    commit_all(base, "base moves on")
    git(base, "push", "-q", "origin", "main")


def merge_base_in(root):
    git(root, "fetch", "-q", "origin")
    git(root, "merge", "-q", "--no-edit", "origin/main")
    return git(root, "rev-parse", "HEAD")


# ---------- the record's fields ----------


@pytest.mark.parametrize("kind", ["round", "pass"])
def test_round_and_pass_records_carry_both_hashes(checkout, capsys, kind):
    diff, lines = recorded(capsys, head(), kind=kind)
    assert len(diff) == 64 and len(lines) == 64 and diff != lines
    code, out, _ = run(capsys, "--kind", kind, "--round", "1", "--commit", head(), "--reviewers", "correctness", "--clean")
    assert f"reviewers=correctness diff={diff} lines={lines} result=clean -->" in out.splitlines()[1]


def test_a_spec_record_never_carries_them(checkout, capsys, tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("## Problem Statement\n\nNotes are lost.\n")
    code, out, err = run(capsys, "--kind", "spec", "--round", "1", "--body", str(spec), "--reviewers", "spec", "--clean")
    assert code == 0 and "diff=" not in out and "lines=" not in out and err == ""
    with pytest.raises(reviews.RecordError, match="spec record names no hashes"):
        reviews.record(kind="spec", round=1, body="x", reviewers="spec", clean=True, diff="unknown", lines="unknown")


def test_the_reader_takes_records_with_and_without_them():
    sha, h = "a" * 40, "b" * 64
    old = f"<!-- workflow:review kind=round round=1 commit={sha} reviewers=correctness result=clean -->"
    new = f"<!-- workflow:review kind=pass round=1 commit={sha} reviewers=correctness diff={h} lines=unknown result=clean -->"
    (a,), (b,) = reviews.records_in(old), reviews.records_in(new)
    assert (a.diff, a.lines) == (None, None)
    assert (b.kind, b.diff, b.lines, b.clean) == ("pass", h, "unknown", True)
    assert b.line() == new and a.line() == old
    # The writer's records without them (as test fixtures build them) are as before.
    assert reviews.record(kind="round", round=1, commit=sha, reviewers="correctness", clean=True).splitlines()[1] == old


@pytest.mark.parametrize("fields", [
    "diff={h} result=clean",  # one without the other
    "lines={h} result=clean",
    "lines={h} diff={h} result=clean",  # out of order
    "result=clean diff={h} lines={h}",
    "diff={short} lines={h} result=clean",
    "diff=UNKNOWN lines={h} result=clean",
    "diff={upper} lines={h} result=clean",
    "diff= lines={h} result=clean",
])
def test_malformed_hash_fields_yield_no_record(fields):
    h = "c" * 64
    tail = fields.format(h=h, short=h[:40], upper=h.upper())
    line = f"<!-- workflow:review kind=round round=1 commit={'a' * 40} reviewers=correctness {tail} -->"
    assert reviews.records_in(line) == []


def test_the_python_writer_refuses_one_hash_alone_or_a_malformed_one():
    sha = "a" * 40
    with pytest.raises(reviews.RecordError, match="both hashes"):
        reviews.record(kind="round", round=1, commit=sha, reviewers="spec", clean=True, diff="unknown")
    with pytest.raises(reviews.RecordError, match="64 hex characters or `unknown`"):
        reviews.record(kind="round", round=1, commit=sha, reviewers="spec", clean=True, diff="abc", lines="unknown")


# ---------- where the hashes come from ----------


def test_the_hashes_come_from_commit_with_the_head_moved_past_it(checkout, capsys):
    reviewed = head()
    before = recorded(capsys, reviewed)
    edit(checkout, "src/app.py", "line 25\n", "line twenty-five\n")
    commit_all(checkout, "a fix")
    assert recorded(capsys, reviewed) == before
    after = recorded(capsys, head())
    assert after[0] != before[0] and after[1] != before[1]


def test_the_same_changes_hash_the_same_when_a_base_change_lands_elsewhere_in_the_file(checkout, capsys):
    before = recorded(capsys, head())
    move_base(checkout, "src/app.py", "line 1\n", "line one\n")  # far from the hunks at lines 10 and 20
    assert recorded(capsys, merge_base_in(checkout)) == before


def test_a_base_change_within_3_lines_of_a_hunk_changes_diff_and_not_lines(checkout, capsys):
    before = recorded(capsys, head())
    move_base(checkout, "src/app.py", "line 13\n", "line thirteen\n")  # in the context of line 10's hunk
    diff, lines = recorded(capsys, merge_base_in(checkout))
    assert diff != before[0] and lines == before[1]


def test_a_changed_line_changes_both(checkout, capsys):
    before = recorded(capsys, head())
    edit(checkout, "src/app.py", "line ten\n", "line 10!\n")
    diff, lines = recorded(capsys, commit_all(checkout))
    assert diff != before[0] and lines != before[1]


def test_the_same_lines_moved_change_diff_and_not_lines(checkout, capsys):
    git(checkout, "checkout", "-q", "-b", "early", "origin/main")
    edit(checkout, "src/app.py", "line 3\n", "line 3\nadded\n")
    early = recorded(capsys, commit_all(checkout))
    git(checkout, "checkout", "-q", "-b", "late", "origin/main")
    edit(checkout, "src/app.py", "line 27\n", "line 27\nadded\n")
    late = recorded(capsys, commit_all(checkout))
    assert early[0] != late[0] and early[1] == late[1]


def test_a_removed_line_instead_of_an_added_one_changes_lines():
    added = Change("a.txt", status="modified", patch="@@ -1,2 +1,3 @@\n one\n+two\n three")
    removed = Change("a.txt", status="modified", patch="@@ -1,3 +1,2 @@\n one\n-two\n three")
    assert own_changes.of_files([added]).lines != own_changes.of_files([removed]).lines


def test_the_base_is_an_option(checkout, capsys):
    # `release` holds the branch's change already, so against it there is nothing of its own.
    git(checkout, "push", "-q", "origin", "HEAD:release")
    git(checkout, "update-ref", "-d", "refs/remotes/origin/release")  # so only a fetch brings it back
    nothing = hashlib.sha256(b"").hexdigest()
    assert recorded(capsys, head(), "--base", "release") == (nothing, nothing)
    assert git(checkout, "rev-parse", "origin/release") == head()


def test_the_configuration_and_the_environment_dont_change_them(checkout, capsys, monkeypatch):
    before = recorded(capsys, head())
    for key, value in [("diff.algorithm", "patience"), ("diff.context", "8"), ("diff.interHunkContext", "20"),
                       ("diff.suppressBlankEmpty", "true"), ("diff.renames", "copies"), ("diff.indentHeuristic", "false"),
                       ("diff.noprefix", "true"), ("diff.mnemonicPrefix", "true"), ("core.quotePath", "true"),
                       ("diff.external", "false"), ("diff.renameLimit", "1"), ("core.bigFileThreshold", "10"),
                       ("color.ui", "always"), ("diff.orderFile", "/dev/null")]:
        git(checkout, "config", key, value)
    monkeypatch.setenv("GIT_DIFF_OPTS", "--unified=0")
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", "false")
    assert recorded(capsys, head()) == before


def test_the_attributes_are_the_commits_own(checkout, capsys):
    reviewed = head()
    before = recorded(capsys, reviewed)
    (checkout / ".gitattributes").write_text("*.py -diff\n")
    commit_all(checkout, "attributes after the review")
    git(checkout, "config", "core.attributesFile", str(checkout / ".gitattributes"))
    # Before git 2.40, git ignores GIT_ATTR_SOURCE and reads the working tree's (the changelog says so).
    if tuple(int(n) for n in re.findall(r"\d+", git(checkout, "version"))[:2]) >= (2, 40):
        assert recorded(capsys, reviewed) == before
    # The commit's own attributes do count, as GitHub reads them.
    files = {c.path: c for c in own_changes.local_files(checkout, head(), "refs/remotes/origin/main")}
    assert files["src/app.py"].patch is None and files["src/app.py"].sha == git(checkout, "rev-parse", "HEAD:src/app.py")


def test_a_rename_to_a_path_git_quotes_is_hashed(checkout, capsys):
    git(checkout, "checkout", "-q", "-b", "quoted", "origin/main")
    git(checkout, "mv", "src/app.py", 'src/"app".py')
    edit(checkout, 'src/"app".py', "line 10\n", "line ten\n")
    commit_all(checkout)
    (c,) = own_changes.local_files(checkout, head(), "refs/remotes/origin/main")
    assert (c.path, c.previous, c.status) == ('src/"app".py', "src/app.py", "renamed") and c.patch.startswith("@@ -7,7 +7,7 @@")
    assert "unknown" not in recorded(capsys, head())


def test_a_type_change_is_one_changed_file_with_both_hunks(checkout, capsys):
    git(checkout, "checkout", "-q", "-b", "link", "origin/main")
    (checkout / "data/gone.txt").unlink()
    os.symlink("../src/app.py", checkout / "data/gone.txt")
    commit_all(checkout)
    (c,) = own_changes.local_files(checkout, head(), "refs/remotes/origin/main")
    assert (c.path, c.status, c.sha) == ("data/gone.txt", "changed", git(checkout, "rev-parse", "HEAD:data/gone.txt"))
    assert c.patch == "@@ -1,2 +0,0 @@\n-a\n-b\n@@ -0,0 +1 @@\n+../src/app.py\n\\ No newline at end of file\n"
    assert "unknown" not in recorded(capsys, head())


def test_a_submodule_is_its_commit_lines_whatever_the_configuration(checkout, capsys, tmp_path):
    lib = tmp_path / "lib"
    git(tmp_path, "init", "-q", "-b", "main", str(lib))
    (lib / "x.txt").write_text("1\n")
    old = commit_all(lib, "one")
    git(checkout, "checkout", "-q", "-b", "sub", "origin/main")
    git(checkout, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(lib), "libs/lib")
    commit_all(checkout, "the submodule")
    git(checkout, "push", "-q", "origin", "HEAD:main")
    (lib / "x.txt").write_text("2\n")
    new = commit_all(lib, "two")
    git(checkout / "libs/lib", "-c", "protocol.file.allow=always", "pull", "-q", "origin", "main")
    commit_all(checkout, "bump")
    (c,) = own_changes.local_files(checkout, head(), "refs/remotes/origin/main")
    assert (c.path, c.status, c.sha) == ("libs/lib", "modified", new)
    assert c.patch == f"@@ -1 +1 @@\n-Subproject commit {old}\n+Subproject commit {new}\n"
    before = recorded(capsys, head())
    for key, value in [("diff.submodule", "log"), ("diff.ignoreSubmodules", "all"), ("submodule.libs/lib.ignore", "all")]:
        git(checkout, "config", key, value)
        assert recorded(capsys, head()) == before, key
    git(checkout, "config", "diff.submodule", "diff")
    assert recorded(capsys, head()) == before


# ---------- the definition ----------


def _spelled_out(files):
    """The definition written out by hand, independently of `own_changes`."""
    diff, lines = b"", b""
    for path, previous, status, sha, patch in sorted(files):
        head = f"file\0{path}\0{previous}\0{status}\0".encode()
        if patch is None:
            tail = b"" if status == "removed" else f"blob\0{sha}\0".encode()
            diff, lines = diff + head + tail, lines + head + tail
            continue
        body = patch.split("\n")
        diff += head + b"".join(b"@@\n" if ln.startswith("@@") else ln.encode() + b"\n" for ln in body)
        lines += head + b"".join(ln.encode() + b"\n" for ln in body if ln[:1] in "+-" and ln)
    return hashlib.sha256(diff).hexdigest(), hashlib.sha256(lines).hexdigest()


def rest_files(root):
    """The checkout's change as GitHub's REST list would give its files, written
    out by hand: (path, old path, status, blob SHA, patch), as `_spelled_out`
    takes them. Shared with `test_merge_check_carry_over.py`'s test of both sides."""
    blob = lambda rel: git(root, "rev-parse", f"HEAD:{rel}")  # noqa: E731
    return [
        ("assets/logo.png", "", "added", blob("assets/logo.png"), None),
        ("bin/run.sh", "", "changed", blob("bin/run.sh"), None),
        ("data/gone.txt", "", "removed", None, "@@ -1,2 +0,0 @@\n-a\n-b"),
        ("docs/moved.md", "docs/same.md", "renamed", blob("docs/moved.md"), None),
        ("docs/new.md", "docs/old.md", "renamed", blob("docs/new.md"),
         "@@ -2,7 +2,7 @@ Note 1.\n Note 2.\n Note 3.\n Note 4.\n-Note 5.\n+Note five.\n Note 6.\n Note 7.\n Note 8."),
        ("src/__init__.py", "", "added", EMPTY_BLOB, None),
        ("docs/café notes.md", "", "added", blob("docs/café notes.md"), "@@ -0,0 +1 @@\n+Ça va."),
        ("src/app_copy.py", "", "added", blob("src/app_copy.py"), "@@ -0,0 +1,30 @@\n" + "\n".join("+" + ln for ln in APP.splitlines())),
        ("src/app.py", "", "modified", blob("src/app.py"),
         "@@ -7,7 +7,7 @@\n line 7\n line 8\n line 9\n-line 10\n+line ten\n line 11\n line 12\n line 13\n"
         "@@ -17,7 +17,7 @@ line 16\n line 17\n line 18\n line 19\n-line 20\n+line twenty\n line 21\n line 22\n line 23"),
    ]


def test_binary_renamed_empty_and_mode_only_files_hash_as_defined(checkout, capsys):
    root = checkout
    files = {c.path: c for c in own_changes.local_files(root, head(), "refs/remotes/origin/main")}
    blob = lambda rel: git(root, "rev-parse", f"HEAD:{rel}")  # noqa: E731
    assert {p: (c.previous, c.status) for p, c in files.items()} == {
        "assets/logo.png": (None, "added"), "bin/run.sh": (None, "changed"), "data/gone.txt": (None, "removed"), "docs/moved.md": ("docs/same.md", "renamed"), "docs/new.md": ("docs/old.md", "renamed"),
        "src/__init__.py": (None, "added"), "src/app.py": (None, "modified"), "docs/café notes.md": (None, "added"),
        "src/app_copy.py": (None, "added"),
    }
    # No hunks: binary, empty, a rename alone, a mode change alone.
    for rel in ("assets/logo.png", "src/__init__.py", "docs/moved.md", "bin/run.sh"):
        assert files[rel].patch is None, rel
    assert files["assets/logo.png"].sha == blob("assets/logo.png")
    assert files["src/__init__.py"].sha == EMPTY_BLOB
    assert files["bin/run.sh"].sha == blob("bin/run.sh")
    assert files["data/gone.txt"].sha is None
    # Hunks as GitHub's `patch` gives them: from the first `@@`, two for app.py.
    assert files["src/app.py"].patch.count("\n@@ ") == 1 and files["src/app.py"].patch.startswith("@@ -7,7 +7,7 @@")
    assert files["data/gone.txt"].patch == "@@ -1,2 +0,0 @@\n-a\n-b\n"
    # REST-shaped, as GitHub would list these files: the same hashes as the record's.
    rest = rest_files(root) + [("data/empty.txt", "", "removed", None, None)]  # as GitHub lists an empty file removed: no blob
    as_github = own_changes.of_files([Change(p, prev or None, s, sha=sha, patch=patch) for p, prev, s, sha, patch in rest])
    assert as_github == own_changes.Hashes(*_spelled_out(rest))
    # The record's, without the empty file removed (git pairs two empty files as a rename).
    rest.remove(("data/empty.txt", "", "removed", None, None))
    as_github = own_changes.of_files([Change(p, prev or None, s, sha=sha, patch=patch) for p, prev, s, sha, patch in rest])
    assert recorded(capsys, head()) == (as_github.diff, as_github.lines)


def test_a_hunks_header_numbers_and_function_name_are_left_out():
    one = Change("a.py", status="modified", patch="@@ -1,2 +1,2 @@ def f():\n x\n-y\n+z")
    other = Change("a.py", status="modified", patch="@@ -40,2 +41,2 @@ class G:\n x\n-y\n+z")
    assert own_changes.of_files([one]) == own_changes.of_files([other])
    split = Change("a.py", status="modified", patch="@@ -1,2 +1,2 @@\n x\n@@ -9 +9 @@\n-y\n+z")
    assert own_changes.of_files([split]).diff != own_changes.of_files([one]).diff
    assert own_changes.of_files([split]).lines == own_changes.of_files([one]).lines


def test_crlf_and_no_newline_at_end_of_file_are_kept(checkout):
    lf = Change("a.txt", status="modified", patch="@@ -1 +1 @@\n-x\n+y")
    crlf = Change("a.txt", status="modified", patch="@@ -1 +1 @@\n-x\r\n+y\r")
    eof = Change("a.txt", status="modified", patch="@@ -1 +1 @@\n-x\n+y\n\\ No newline at end of file")
    assert len({own_changes.of_files([c]).diff for c in (lf, crlf, eof)}) == 3
    assert own_changes.of_files([crlf]).lines != own_changes.of_files([lf]).lines
    assert own_changes.of_files([eof]).lines == own_changes.of_files([lf]).lines
    # Locally, git's `\r` and its note reach the patch as they are.
    (checkout / "src/dos.txt").write_bytes(b"one\r\ntwo")
    commit_all(checkout)
    files = {c.path: c for c in own_changes.local_files(checkout, head(), "refs/remotes/origin/main")}
    assert files["src/dos.txt"].patch == "@@ -0,0 +1,2 @@\n+one\r\n+two\n\\ No newline at end of file\n"


def test_a_file_with_changed_lines_but_no_patch_cant_be_hashed():
    with pytest.raises(own_changes.CantHash, match="no patch"):
        own_changes.of_files([Change("big.sql", status="modified", additions=5000, deletions=0, sha="d" * 40)])
    with pytest.raises(own_changes.CantHash, match="no status"):
        own_changes.of_files([Change("a.txt", patch="@@ -1 +1 @@\n-x\n+y")])


# ---------- when they can't be computed ----------


def test_a_commit_missing_from_the_repository_gives_unknown_and_the_record_alone(checkout, capsys):
    git(checkout, "remote", "set-url", "origin", str(checkout.parent / "gone.git"))  # never fetched for it
    code, out, err = run(capsys, "--kind", "round", "--round", "2", "--commit", "d" * 40, "--reviewers", "correctness", "--not-clean")
    assert code == 0
    assert out.splitlines() == [
        "Review round 2 on `ddddddd`: not clean. Reviewers: Correctness.",
        f"<!-- workflow:review kind=round round=2 commit={'d' * 40} reviewers=correctness diff=unknown lines=unknown result=not-clean -->",
        "<!-- workflow:agent -->",
    ]
    assert "ddddddd isn't a commit in this repository" in err and "unknown for diff and lines" in err
    assert "fetch" not in err


def test_no_repository_gives_unknown(tmp_path, capsys, monkeypatch):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(PROFILE)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    monkeypatch.chdir(tmp_path)
    code, out, err = run(capsys, "--kind", "pass", "--round", "1", "--commit", "e" * 40, "--reviewers", "correctness", "--clean")
    assert code == 0 and "diff=unknown lines=unknown" in out and out.count("\n") == 3
    assert "no git repository" in err


def test_a_failed_fetch_uses_the_origin_base_already_here_with_a_note(checkout, capsys):
    before = recorded(capsys, head())
    git(checkout, "remote", "set-url", "origin", str(checkout.parent / "gone.git"))
    code, out, err = run(capsys, "--kind", "round", "--round", "1", "--commit", head(), "--reviewers", "correctness", "--clean")
    assert code == 0 and f"diff={before[0]} lines={before[1]}" in out and out.count("\n") == 3
    assert "couldn't fetch origin/main (fatal: " in err and "already here" in err


def test_with_no_origin_base_both_are_unknown(checkout, capsys):
    git(checkout, "remote", "set-url", "origin", str(checkout.parent / "gone.git"))
    git(checkout, "update-ref", "-d", "refs/remotes/origin/main")
    assert recorded(capsys, head()) == ("unknown", "unknown")
    _, _, err = run(capsys, "--kind", "round", "--round", "1", "--commit", head(), "--reviewers", "correctness", "--clean")
    assert "no origin/main" in err and "unknown for diff and lines" in err


def test_an_unreadable_profile_without_base_gives_unknown_and_with_base_hashes(checkout, capsys):
    before = recorded(capsys, head())
    (checkout / ".claude/workflow/profile.toml").write_text("[project\n")
    assert recorded(capsys, head()) == ("unknown", "unknown")
    assert recorded(capsys, head(), "--base", "main") == before
    _, out, err = run(capsys, "--kind", "round", "--round", "1", "--commit", head(), "--reviewers", "correctness", "--clean", "--base", "")
    assert "diff=unknown lines=unknown" in out and "isn't a branch's name (--base)" in err


def test_a_shallow_clone_without_the_merge_base_says_so(checkout, capsys, tmp_path, monkeypatch):
    git(checkout, "push", "-q", "origin", "HEAD")
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "-q", "--depth", "1", "--no-single-branch", "-b", "claude/build-1", f"file://{tmp_path / 'origin.git'}", str(shallow))
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(shallow))
    monkeypatch.chdir(shallow)
    _, out, err = run(capsys, "--kind", "round", "--round", "1", "--commit", head(), "--reviewers", "correctness", "--clean")
    assert "diff=unknown lines=unknown" in out and "no merge base with origin/main in this shallow clone's history" in err


def test_base_given_twice_is_refused(checkout, capsys):
    code, out, err = run(capsys, "--kind", "round", "--round", "1", "--commit", head(), "--reviewers", "correctness", "--clean",
                         "--base", "nosuch", "--base", "main")
    assert code == 2 and out == "" and "give --base once" in err


def test_a_refused_record_runs_no_git(checkout, capsys, monkeypatch):
    monkeypatch.setattr(own_changes, "local", lambda *a, **k: pytest.fail("hashed a refused record"))
    code, out, err = run(capsys, "--kind", "round", "--round", "0", "--commit", head(), "--reviewers", "correctness", "--clean")
    assert code == 2 and out == ""


# ---------- the skill and the changelog ----------


def test_the_review_panel_gives_the_base_where_it_isnt_the_profiles():
    text = (KIT / "skills/review-panel/SKILL.md").read_text(encoding="utf-8")
    assert "When the pull request's base branch isn't the profile's `project.base_branch`, add `--base <branch>` to the command." in text
    # The diff the reviewers read is against the same base.
    assert "The base is the pull request's base branch (the profile's `project.base_branch` unless it targets another)" in text


def test_the_changelog_has_the_note():
    notes = since_0110((KIT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert "#258" in notes and "`diff=`" in notes and "`lines=`" in notes
    assert "older" in notes and "unreviewed" in notes

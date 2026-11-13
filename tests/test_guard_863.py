"""#863: a security problem in the guard.

A missing profile still reads as "not set up"; the profile read as a whole
follows `profile.missing`.

Seams: `workflow hook guard` through the entry point on this Python (the kit's
path) and through the old-Python fallback's own entry, each in a subprocess
with a `timeout`; and the readers in-process."""

import errno
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_guard_833 import GIT, LS, PUSH, _argv
from test_guard_no_python import _kit_at
from workflow import _old_python, cli, vendor
from workflow.profile import ProfileError, load

KIT = Path(__file__).resolve().parents[1]
PROFILE = Path(".claude/workflow/profile.toml")
SECONDS = 20
PATHS = ["kit", "old-python"]
VALID = '[project]\nrepo = "o/r"\nbase_branch = "main"\n\n[run]\nticket_branch = "claude/build-*"\n'


def _as_anyone(argv):
    """`argv` run as an ordinary user would run it."""
    return (["unshare", "-U"] + argv) if os.geteuid() == 0 else argv


def _project(tmp_path, branch, profile=VALID, kit=False):
    """A git project on `branch`, with `profile` as its profile (None: no
    `.claude` at all) and with `kit` the kit's CLI too."""
    root = tmp_path / "proj"
    subprocess.run(GIT + ["init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(GIT + ["-C", str(root), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    if branch != "main":
        subprocess.run(GIT + ["-C", str(root), "checkout", "-q", "-b", branch], check=True)
    if kit:
        _kit_at(root / vendor.HOOK_TAG)
    if profile is not None:
        (root / PROFILE).parent.mkdir(parents=True, exist_ok=True)
        (root / PROFILE).write_text(profile, encoding="utf-8")
    return root


@pytest.fixture
def shape(tmp_path):
    """A project in the shape the tests below need, put back after the test."""
    made = []

    def make(branch, folder=PROFILE.parent, mode=0, **project):
        root = _project(tmp_path, branch, **project)
        os.chmod(root / folder, mode)
        made.append(root / folder)
        return root

    yield make
    for folder in made:
        os.chmod(folder, 0o755)


def _guard(path, root, event):
    """The hook's (exit code, decision or None), WORKFLOW_ROLE unset."""
    env = {"PATH": os.environ["PATH"], "HOME": str(root), "CLAUDE_PROJECT_DIR": str(root)}
    p = subprocess.run(
        _as_anyone(_argv(path) + ["hook", "guard"]), input=json.dumps(dict(event, cwd=str(root))),
        capture_output=True, text=True, env=env, cwd=root, timeout=SECONDS,
    )
    if not p.stdout.strip():
        return p.returncode, None
    return p.returncode, json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


# ---------- the guard: the shape ----------


@pytest.mark.parametrize("path", PATHS)
def test_on_a_ticket_branch_every_tool_is_refused(shape, path):
    """The kit is set up, so the default `run.ticket_branch` decides (#833)."""
    root = shape("claude/build-1")
    for event in (PUSH, LS):
        assert _guard(path, root, event) == (0, "deny"), event


@pytest.mark.parametrize("path", PATHS)
def test_off_a_ticket_branch_a_push_is_asked(shape, path):
    root = shape("main")
    assert _guard(path, root, PUSH) == (0, "ask")
    assert _guard(path, root, LS) == (0, None)


# ---------- the guard: a missing profile is still "not set up" ----------


def _absent(root):
    (root / PROFILE).unlink()


def _folder_a_file(root):
    (root / PROFILE).unlink()
    (root / PROFILE.parent).rmdir()
    (root / PROFILE.parent).write_text("", encoding="utf-8")


def _loop(root):
    (root / PROFILE).unlink()
    os.symlink(PROFILE.name, root / PROFILE)


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("make", [_absent, _folder_a_file, _loop])
def test_a_missing_profile_is_not_a_ticket_session(tmp_path, path, make):
    """Left alone by the kit; the old-Python path asks a push, as it always
    has where the kit isn't set up."""
    root = _project(tmp_path, "claude/build-1")
    make(root)
    assert _guard(path, root, LS) == (0, None)
    assert _guard(path, root, PUSH) == (0, None if path == "kit" else "ask")


# ---------- the readers ----------


def _second_shape(tmp_path):
    """A project root in the second shape: asking about a path in it fails
    with an error other than "not found"."""
    return tmp_path / ("x" * 300)


def test_load_refuses_the_second_shape_in_one_line(tmp_path):
    with pytest.raises(ProfileError) as e:
        load(_second_shape(tmp_path), required=False)
    assert str(e.value) == ".claude/workflow/profile.toml can't be read (OSError)"


def test_load_refuses_the_shape_in_one_line(shape):
    root = shape("main")
    code = "import sys; sys.path.insert(0, sys.argv[1]); from workflow.profile import load, ProfileError\n" \
        "try:\n    load(__import__('pathlib').Path(sys.argv[2]), required=False)\nexcept ProfileError as e:\n    print(e)"
    p = subprocess.run(
        _as_anyone([sys.executable, "-B", "-c", code, str(KIT / "scripts"), str(root)]),
        capture_output=True, text=True, timeout=SECONDS,
    )
    assert (p.returncode, p.stdout.strip()) == (0, ".claude/workflow/profile.toml can't be read (PermissionError)"), p.stderr


def test_load_still_reads_a_missing_profile_as_none(tmp_path):
    assert load(tmp_path, required=False) is None
    (tmp_path / ".claude").write_text("", encoding="utf-8")
    assert load(tmp_path, required=False) is None


def test_the_old_python_reader_reads_the_second_shape_as_unreadable(tmp_path):
    root = str(_second_shape(tmp_path))
    assert _old_python._profile_text(root) == ""
    assert _old_python._ticket_branch(root) == _old_python.DEFAULT_TICKET_BRANCH


def test_the_old_python_reader_still_reads_a_missing_profile_as_none(tmp_path):
    assert _old_python._profile_text(str(tmp_path)) is None
    (tmp_path / ".claude").write_text("", encoding="utf-8")
    assert _old_python._profile_text(str(tmp_path)) is None


def test_the_cant_decide_fallback_asks_a_push_in_the_second_shape(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "project_root", lambda: _second_shape(tmp_path))
    assert cli._cant_decide({"tool_name": "Bash", "tool_input": {"command": "git push origin x"}}, "why") == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_the_cant_decide_fallback_leaves_a_missing_profile_alone(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    assert cli._cant_decide({"tool_name": "Bash", "tool_input": {"command": "git push origin x"}}, "why") == 0
    assert capsys.readouterr().out == ""


def test_the_readers_ask_whether_the_profile_is_there_through_one_check(tmp_path, monkeypatch):
    """`profile` gives on `_old_python`'s check, and `_profile_text` asks
    through it: one copy of the check, read the same way on both paths."""
    from workflow import profile

    assert profile.missing is _old_python.missing
    assert profile.NOT_FOUND is _old_python.NOT_FOUND

    def refused(path):
        raise OSError(errno.EACCES, "refused")

    (tmp_path / PROFILE).parent.mkdir(parents=True)
    (tmp_path / PROFILE).write_text(VALID, encoding="utf-8")
    assert _old_python._profile_text(str(tmp_path)) == VALID
    monkeypatch.setattr(_old_python, "missing", refused)
    assert _old_python._profile_text(str(tmp_path)) == ""


def test_the_check_reads_a_path_that_names_no_file_as_missing_and_raises_any_other_error(tmp_path):
    """Both sides of the check: a path that is there, one that isn't, one that
    can't name a file, and an error other than "not found"."""
    from workflow.profile import missing

    (tmp_path / "here").write_text("", encoding="utf-8")
    assert missing(tmp_path / "here") is False
    assert missing(tmp_path / "gone") is True
    assert missing(tmp_path / "a\x00b") is True
    assert _old_python.missing(str(tmp_path / "a\x00b")) is True
    with pytest.raises(OSError):
        missing(_second_shape(tmp_path) / PROFILE)


def test_the_second_shape_is_an_error_other_than_not_found(tmp_path):
    """The readers' tests above rest on this."""
    with pytest.raises(OSError) as e:
        os.stat(_second_shape(tmp_path) / PROFILE)
    assert e.value.errno not in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP)


# ---------- the wording ----------


def test_the_guards_own_lines_name_it_by_its_area_only():
    """The code and the page's lines for the readers state what they do, with
    no ticket number on them."""
    import inspect

    from workflow import profile

    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8").splitlines()
    for name in ("missing", "unreadable", "_load", "_profile_text"):
        (line,) = [line for line in page if line.startswith(f"- `{name}`:")]
        assert "#863" not in line, name
    for fn in (_old_python.missing, _old_python._profile_text, profile.load, profile.unreadable, cli._load, cli._cant_decide):
        assert "#863" not in inspect.getsource(fn), fn.__name__


# ---------- the changelog ----------


def test_changelog_notes_it_under_unreleased():
    (line,) = [line for line in since_0110().splitlines() if "(#863" in line]
    assert line.lower().startswith("**a security problem in the guard"), line

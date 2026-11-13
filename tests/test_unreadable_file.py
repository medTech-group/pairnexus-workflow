"""#836 (and #847's cases): one helper words a file the kit can't read.

`profile.file_problem` holds the check (a directory or a pipe isn't a file,
and is never opened; an error asking is `can't be read (<the error's type>)`),
`profile.read_file` reads through it (`isn't UTF-8 text`), and
`profile.cant_be_read` holds the words for an error. `profile.load`,
`doctor._file` and `doctor._read_text` all read through them, and no other
copy of the check or its wording stays in `profile.py` or `doctor.py`.
`workflow doctor`'s and `workflow status`'s lines stay as they were for each
shape of the files they read. Seams: the helper, its three callers, and each
command as a session runs it."""

import ast
import json
import os
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_doctor import _lines, _project, _report
from test_status_local_gaps import _status
from workflow import doctor, profile
from workflow.profile import PROFILE_PATH, ProfileError

KIT = Path(__file__).resolve().parents[1]
LOCK = ".claude/workflow/lock.json"
GOOD_PROFILE = b'[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n'
GOOD_LOCK = json.dumps({"kit_version": "0.1.11", "files": {}, "mattpocock_skills": "vendored"}).encode()
BOM = b"\xef\xbb\xbf"


# ---------- the helper ----------


def _denied(monkeypatch, target, method="read_text"):
    """`Path.<method>` raises PermissionError for `target` alone."""
    was = getattr(Path, method)

    def denied(self, *a, **kw):
        if os.path.abspath(self) == os.path.abspath(target):
            raise PermissionError(13, "Permission denied", str(self))
        return was(self, *a, **kw)

    monkeypatch.setattr(Path, method, denied)


def test_read_file_words_each_shape(tmp_path, monkeypatch):
    f = tmp_path / "f"
    assert profile.read_file(f) == (None, None)  # missing
    f.mkdir()
    assert profile.read_file(f) == (None, "isn't a file")
    assert profile.file_problem(f) == "isn't a file"
    f.rmdir()
    os.mkfifo(f)  # opened, it would block the read
    assert profile.read_file(f) == (None, "isn't a file")
    f.unlink()
    f.write_bytes(b"caf\xe9\n")
    assert profile.read_file(f) == (None, "isn't UTF-8 text")
    assert profile.file_problem(f) is None
    f.write_bytes(BOM + b"text\n")
    assert profile.read_file(f) == ("﻿text\n", None)  # the mark is the caller's to judge
    _denied(monkeypatch, f)
    assert profile.read_file(f) == (None, "can't be read (PermissionError)")


def test_file_problem_words_an_error_asking(tmp_path, monkeypatch):
    f = tmp_path / "f"
    f.write_text("x")
    _denied(monkeypatch, f, "is_file")
    assert profile.file_problem(f) == "can't be read (PermissionError)"
    assert profile.read_file(f) == (None, "can't be read (PermissionError)")


def test_cant_be_read_names_the_type_never_the_message():
    e = PermissionError(13, "Permission denied", "/home/someone/secret")
    assert profile.cant_be_read(e) == "can't be read (PermissionError)"
    assert str(profile.unreadable(e)) == f"{PROFILE_PATH} can't be read (PermissionError)"


# ---------- its three callers read through it ----------


def _spy(monkeypatch, name, value):
    """`profile.<name>` answers `value` and records the paths it was asked about."""
    asked = []

    def spy(path):
        asked.append(Path(path))
        return value

    monkeypatch.setattr(profile, name, spy)
    return asked


@pytest.mark.parametrize("required", [True, False])
def test_load_reads_through_the_helper(tmp_path, monkeypatch, required):
    (tmp_path / PROFILE_PATH).parent.mkdir(parents=True)
    (tmp_path / PROFILE_PATH).write_bytes(GOOD_PROFILE)
    asked = _spy(monkeypatch, "file_problem", "is spied on")
    with pytest.raises(ProfileError) as e:
        profile.load(tmp_path, required=required)
    assert str(e.value) == f"{PROFILE_PATH} is spied on"
    assert asked == [tmp_path / PROFILE_PATH]
    monkeypatch.undo()
    _spy(monkeypatch, "read_file", (None, "is read by a spy"))
    with pytest.raises(ProfileError) as e:
        profile.load(tmp_path, required=required)
    assert str(e.value) == f"{PROFILE_PATH} is read by a spy"


def test_doctors_file_reads_through_the_helper(tmp_path, monkeypatch):
    asked = _spy(monkeypatch, "file_problem", "is spied on")
    assert doctor._file(tmp_path, "VERSION") == (tmp_path / "VERSION", "it is spied on")
    assert doctor._file(tmp_path, tmp_path / "x") == (tmp_path / "x", "it is spied on")  # an absolute path as it is
    assert asked == [tmp_path / "VERSION", tmp_path / "x"]
    monkeypatch.undo()
    _spy(monkeypatch, "file_problem", None)
    assert doctor._file(tmp_path, "VERSION") == (tmp_path / "VERSION", None)


def test_doctors_read_text_reads_through_the_helper(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text("{}")
    asked = _spy(monkeypatch, "file_problem", "is spied on")
    assert doctor._read_text(tmp_path, "a.json") == (None, "it is spied on")
    assert asked == [tmp_path / "a.json"]
    monkeypatch.undo()
    _spy(monkeypatch, "read_file", ("﻿{}", None))
    assert doctor._read_text(tmp_path, "a.json") == ("{}", None)  # doctor leaves the mark out
    _spy(monkeypatch, "read_file", (None, None))
    assert doctor._read_text(tmp_path, "a.json") == (None, None)


# ---------- no other copy stays ----------


def _code_strings(source):
    """Each string constant in `source` with its line, docstrings and
    comments left out, and each f-string's pieces joined around a
    placeholder: `type(<name>).__name__` as `{TYPE}`, anything else as `{}`."""
    tree = ast.parse(source)
    docs = {id(n.body[0].value) for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and id(n) not in inner:
            yield n.lineno, n.value
        elif isinstance(n, ast.JoinedStr):
            parts = []
            for v in n.values:
                if isinstance(v, ast.Constant):
                    parts.append(v.value)
                elif ast.unparse(v.value).startswith("type(") and ast.unparse(v.value).endswith(").__name__"):
                    parts.append("{TYPE}")
                else:
                    parts.append("{}")
            yield n.lineno, "".join(parts)


def _where(text, source):
    return [line for line, s in _code_strings(source) if text in s]


@pytest.mark.parametrize("name", ["profile.py", "doctor.py"])
def test_no_other_copy_of_the_wording(name):
    source = (KIT / "scripts/workflow" / name).read_text(encoding="utf-8")
    own = source if name == "profile.py" else ""
    for words in ("isn't a file", "isn't UTF-8 text"):
        assert len(_where(words, source)) == (1 if own else 0), (name, words, _where(words, source))
    # The error's words, `can't be read (<the error's type>)`, only in `cant_be_read`.
    assert len(_where("can't be read ({TYPE})", source)) == (1 if own else 0), _where("can't be read ({TYPE})", source)


def test_no_other_copy_of_the_check():
    """`exists() and not is_file()` only in `file_problem`."""
    for name in ("profile.py", "doctor.py"):
        tree = ast.parse((KIT / "scripts/workflow" / name).read_text(encoding="utf-8"))
        found = []
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                for n in ast.walk(fn):
                    if isinstance(n, ast.BoolOp) and "exists()" in ast.unparse(n) and "not" in ast.unparse(n) and "is_file()" in ast.unparse(n):
                        found.append(fn.name)
        assert found == (["file_problem"] if name == "profile.py" else []), (name, found)


# ---------- doctor's and status's lines, for each shape of a file they read ----------

MISTAKE = f"The kit's profile ({PROFILE_PATH}, its settings for this project) has a mistake, so the kit can't use it: "
PROFILE_LINES = {
    "missing": f"The kit isn't set up in this project yet: it has no profile ({PROFILE_PATH}).",
    "a-directory": MISTAKE + f"{PROFILE_PATH} isn't a file.",
    "a-pipe": MISTAKE + f"{PROFILE_PATH} isn't a file.",
    "not-utf8": MISTAKE + f"{PROFILE_PATH} isn't UTF-8 text.",
    # `load` keeps the byte-order mark, which TOML refuses, as before.
    "a-byte-order-mark": MISTAKE + f"{PROFILE_PATH}: Invalid statement (at line 1, column 1).",
    "cant-be-read": MISTAKE + f"{PROFILE_PATH} can't be read (PermissionError).",
}
LOCK_LINES = {
    "missing": f"This project has the kit's copy or its hooks, but the record of that copy ({LOCK}) is gone, so the copy can't be checked or updated.",
    "a-directory": f"The record of the kit's copy ({LOCK}) can't be read (it isn't a file), so the copy can't be checked.",
    "a-pipe": f"The record of the kit's copy ({LOCK}) can't be read (it isn't a file), so the copy can't be checked.",
    "not-utf8": f"The record of the kit's copy ({LOCK}) can't be read (it isn't UTF-8 text), so the copy can't be checked.",
    # Doctor leaves the byte-order mark out: the lock reads as it should.
    "a-byte-order-mark": None,
    "cant-be-read": f"The record of the kit's copy ({LOCK}) can't be read (it can't be read (PermissionError)), so the copy can't be checked.",
}
FILES = {str(PROFILE_PATH): ("kit.profile", GOOD_PROFILE, PROFILE_LINES), LOCK: ("kit.vendor", GOOD_LOCK, LOCK_LINES)}

# `Path.read_text` refuses one path in the command's own process, as a file
# the user can't read does (the sandbox runs as root, where mode 000 doesn't).
SITECUSTOMIZE = '''
import os, pathlib
_target = os.environ["WORKFLOW_TEST_UNREADABLE"]
_was = pathlib.Path.read_text
def _read_text(self, *a, **kw):
    if os.path.abspath(self) == _target:
        raise PermissionError(13, "Permission denied", str(self))
    return _was(self, *a, **kw)
pathlib.Path.read_text = _read_text
'''


def _shaped(tmp_path, rel, shape):
    """A project whose `rel` has `shape`, and the environment its command runs with."""
    root = _project(tmp_path)
    path = root / rel
    path.unlink()
    env = {}
    if shape == "a-directory":
        path.mkdir()
    elif shape == "a-pipe":
        os.mkfifo(path)
    elif shape == "not-utf8":
        path.write_bytes(FILES[rel][1].replace(b"demo", b"d\xffmo").replace(b"0.1.11", b"0.1.\xff1"))
    elif shape == "a-byte-order-mark":
        path.write_bytes(BOM + FILES[rel][1])
    elif shape == "cant-be-read":
        path.write_bytes(FILES[rel][1])
        site = tmp_path / "site"
        site.mkdir()
        (site / "sitecustomize.py").write_text(SITECUSTOMIZE)
        env = {"PYTHONPATH": str(site), "WORKFLOW_TEST_UNREADABLE": os.path.abspath(path)}
    return root, env


SHAPES = list(PROFILE_LINES)
CASES = [pytest.param(rel, shape, id=f"{FILES[rel][0]}-{shape}") for rel in FILES for shape in SHAPES]


@pytest.mark.parametrize("rel, shape", CASES)
def test_doctors_line_for_each_shape(tmp_path, rel, shape):
    id_, _, said = FILES[rel]
    root, env = _shaped(tmp_path, rel, shape)
    line = _lines(_report(tmp_path, root, env=env))[id_]
    if said[shape] is None:
        assert line["status"] == "fine", line
    else:
        assert (line["status"], line["message"]) == ("gap", said[shape])
    assert str(root) not in line["message"]


# `workflow status` with a lock.json that is a pipe blocks before its report
# (`updates.installed` opens the lock unchecked, on the base too): filed as
# its own ticket, outside the three readers this one moves.
STATUS_CASES = [c for c in CASES if c.values != (LOCK, "a-pipe")]


@pytest.mark.parametrize("rel, shape", STATUS_CASES)
def test_statuss_line_for_each_shape(tmp_path, rel, shape):
    id_, _, said = FILES[rel]
    root, env = _shaped(tmp_path, rel, shape)
    report = json.loads(_status(tmp_path, root, "--json", env=env))
    gaps = {g["id"]: g["message"] for g in report["local_gaps"]}
    assert gaps.get(id_) == said[shape]
    assert report["profile_error"] is (id_ == "kit.profile" and shape not in ("missing",))


# ---------- the notes ----------


def test_changelog_notes_it_under_unreleased():
    assert "#836" in since_0110()


def test_the_page_lists_the_helper_and_names_its_users():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    lines = {line.split("`")[1]: line for line in page.splitlines() if line.startswith("- `")}
    for name in ("file_problem", "read_file", "cant_be_read"):
        assert name in lines, name
        assert "profile.py" in lines[name]
    for user in ("`load`", "`doctor._file`", "`doctor._read_text`"):
        assert user in lines["file_problem"], user
    assert "doctor" in lines["cant_be_read"]

"""#61: `workflow doctor`'s short report on a `python3` older than 3.11, from
the kit's old-Python path (`_old_python`, Python 3.7 syntax, the standard
library only). Seam 2 of #34: run on a real Python 3.9 as 0.1.8's tests do,
and in-process with a made-up old version. A test on the supported Python
compares its lines with the full doctor's, so a line added there can't be
missed here."""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import threading

import pytest

from changelog_notes import since_0110
from conftest import KIT
from test_doctor import HEALTHY, _bin, _project, _report
from test_kit_018 import _old_python_binary
from workflow import _old_python, doctor, vendor

CLI = KIT / "scripts/workflow.py"
UNTIL = "until `python3` is 3.11 or newer"
STRICT_FAIL = 1
LINE_KEYS = {"group", "id", "status", "message", "fix", "offer"}
PLUGIN_ON = {"enabledPlugins": {vendor.PLUGIN_KEY: True}}
# The lines the full doctor gives only when something is wrong (each beside
# the line that is always there), which the short report can't tell.
ONLY_WHEN_WRONG = {
    "kit.settings",  # a settings file Claude Code can't read
    "kit.hooks_off",  # disableAllHooks
    "github.protection.active", "github.protection.base", "github.protection.bypass",  # each missing protection
    "github.protection.deletions", "github.protection.force_pushes", "github.protection.pull_requests",
    "github.profile_checks",  # a check the ruleset requires that the profile doesn't list (#69)
}


@pytest.fixture(autouse=True)
def _wide(monkeypatch):
    """The in-process report wraps to COLUMNS (else the real terminal's width)."""
    monkeypatch.setenv("COLUMNS", "100")


def _old(root, *args, env=None, version="3.9.6"):
    """The old-Python path's doctor, in-process, as a `python3` of `version`
    runs it: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    e = {"CLAUDE_PROJECT_DIR": str(root), **(env or {})}
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _old_python.main(["doctor", *args], stdin_text="", env=e, version=version, cwd=root)
    return code, out.getvalue(), err.getvalue()


def _old_report(root, *args, **kw):
    code, out, err = _old(root, "--json", *args, **kw)
    assert code == 0, err
    return json.loads(out)


def _pairs(report):
    return sorted((ln["group"], ln["id"]) for ln in report["lines"])


# The short report


def test_your_computer_shows_python3s_version_as_a_gap_and_every_other_line_cant_check(tmp_path):
    root = _project(tmp_path)
    r = _old_report(root)
    first = r["lines"][0]
    assert (first["group"], first["id"], first["status"]) == ("Your computer", "computer.python3", "gap")
    assert "3.9.6" in first["message"] and "3.11" in first["message"]
    assert "3.11" in first["fix"]
    for ln in r["lines"][1:]:
        assert ln["status"] == "cant_check", ln
        assert UNTIL in ln["message"], ln
        assert ln["fix"], ln
    groups = [ln["group"] for ln in r["lines"]]
    assert groups[:2] == ["Your computer"] * 2  # the gap's group first, then GROUPS order
    assert [g for k, g in enumerate(groups) if g not in groups[:k]] == ["Your computer", "The kit", "GitHub", "Cloud"]


def test_the_json_is_in_the_full_doctors_shape(tmp_path):
    root = _project(tmp_path)
    r = _old_report(root)
    full = _report(tmp_path, root)
    assert list(r) == list(full)  # experience, wording, counts, strict_ok, lines
    assert list(r["experience"]) == list(full["experience"])
    assert list(r["counts"]) == list(full["counts"])
    for ln in r["lines"]:
        assert list(ln) == list(full["lines"][0])
        assert set(ln) == LINE_KEYS and ln["offer"] is None
    n = len(r["lines"])
    assert r["counts"] == {"gap": 1, "cant_check": n - 1, "note": 0, "fine": 0}
    assert r["strict_ok"] is False
    assert len({ln["id"] for ln in r["lines"]}) == n  # no id twice


def test_the_text_report_groups_the_lines_with_their_fixes(tmp_path):
    root = _project(tmp_path)
    code, out, _ = _old(root)
    assert code == 0
    head, *rest = out.splitlines()
    n = len(_old_report(root)["lines"])
    assert head == "Workflow doctor: 1 gap, {} can't check".format(n - 1)
    assert rest[0] == "" and rest[1] == "Your computer"
    assert rest[2].startswith("  [gap] ") and "3.9.6" in rest[2]
    assert any(ln.startswith("      Fix: ") for ln in rest)
    for group in ("The kit", "GitHub", "Cloud"):
        assert group in rest
    assert out.count("[can't check]") == n - 1
    assert out.count("[gap]") == 1
    assert " ".join(out.split()).count(UNTIL) == n - 1  # wrapped lines joined


def test_the_text_report_wraps_to_the_terminal(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setenv("COLUMNS", "50")
    code, out, _ = _old(root)
    assert code == 0
    assert max(len(ln) for ln in out.splitlines()) <= 50


@pytest.mark.parametrize("args", [(), ("--json",)])
def test_exit_0_without_strict_and_non_zero_with_it(tmp_path, args):
    root = _project(tmp_path)
    assert _old(root, *args)[0] == 0
    code, out, _ = _old(root, "--strict", *args)
    assert code == STRICT_FAIL and out  # the report is still printed


def test_the_files_a_session_hands_in_are_taken_and_ignored(tmp_path):
    root = _project(tmp_path)
    given = tmp_path / "given.json"
    given.write_text("{}")
    args = ("--rulesets", str(given), "--repo", str(given), "--environments", str(given), "--runs", "-",
            "--claude-version", "2.1.300", "--repo=" + str(given))
    assert _old_report(root, *args) == _old_report(root)


@pytest.mark.parametrize("args,needle", [
    (("--bogus",), "--bogus"),
    (("extra",), "extra"),
    (("--rulesets",), "--rulesets"),
    (("--claude-version", "--strict"), "--claude-version"),
    (("--rulesets", "--json"), "--rulesets"),
    (("--repo", "-", "--runs", "-"), "only one of"),
    (("--repo=-", "--environments", "-"), "only one of"),
])
def test_arguments_the_full_doctor_refuses_exit_2(tmp_path, args, needle):
    root = _project(tmp_path)
    code, out, err = _old(root, *args)
    assert code == 2 and out == "" and needle in err


@pytest.mark.parametrize("args,code,as_json", [
    (("--jso",), 0, True),
    (("--str",), STRICT_FAIL, False),
    (("--rulesets", "-", "--rulesets", "-"), 0, False),  # the last value counts: one standard input
    (("--repo", "-", "--repo", "x", "--runs", "-"), 0, False),
])
def test_arguments_the_full_doctor_takes_are_taken(tmp_path, args, code, as_json):
    root = _project(tmp_path)
    got, out, err = _old(root, *args)
    assert got == code, err
    assert out.startswith("{") if as_json else out.startswith("Workflow doctor: ")


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_says_its_the_short_report(tmp_path, flag):
    code, out, _ = _old(_project(tmp_path), flag)
    assert code == 0 and "doctor" in out and "--strict" in out and "3.11" in out


# Wording by experience


@pytest.mark.parametrize("env,level,source", [
    ({}, None, "unknown"),
    ({"WORKFLOW_EXPERIENCE": "developer"}, "developer", "environment"),
    ({"WORKFLOW_EXPERIENCE": " New "}, "new", "environment"),
    ({"WORKFLOW_EXPERIENCE": "\ufeffdeveloper"}, "developer", "environment"),
    ({"WORKFLOW_EXPERIENCE": "expert"}, None, "unknown"),
    ({"WORKFLOW_EXPERIENCE": "  "}, None, "unknown"),
])
def test_experience_comes_from_the_environment(tmp_path, env, level, source):
    root = _project(tmp_path)
    r = _old_report(root, env=env)
    assert r["experience"] == {"level": level, "source": source, "default": None}
    assert r["wording"] == (level or "new")


def test_experience_comes_from_the_local_file_and_the_environment_wins(tmp_path):
    root = _project(tmp_path)
    (root / ".workflow").mkdir()
    (root / ".workflow/experience").write_text("developer\n")
    r = _old_report(root)
    assert (r["experience"]["level"], r["experience"]["source"], r["wording"]) == ("developer", "local file", "developer")
    r = _old_report(root, env={"WORKFLOW_EXPERIENCE": "new"})
    assert (r["experience"]["source"], r["wording"]) == ("environment", "new")
    r = _old_report(root, env={"WORKFLOW_EXPERIENCE": "expert"})  # skipped: the file is next
    assert (r["experience"]["source"], r["wording"]) == ("local file", "developer")


@pytest.mark.parametrize("body", ["expert\n", "new\ndeveloper\n", "x" * 300, "", b"\xff\xfe"])
def test_an_unreadable_local_file_reads_as_unknown(tmp_path, body):
    root = _project(tmp_path)
    (root / ".workflow").mkdir()
    f = root / ".workflow/experience"
    f.write_bytes(body) if isinstance(body, bytes) else f.write_text(body)
    r = _old_report(root)
    assert (r["experience"]["level"], r["experience"]["source"], r["wording"]) == (None, "unknown", "new")


@pytest.mark.parametrize("body", ["developer\n", " new \n", "\ufeffdeveloper", "DEVELOPER\r\n", "expert\n", "x" * 300, ""])
def test_the_local_file_is_read_as_the_full_doctor_reads_it(tmp_path, body):
    root = _project(tmp_path)
    (root / ".workflow").mkdir()
    (root / ".workflow/experience").write_bytes(body.encode("utf-8"))
    full = _report(tmp_path, root)["experience"]
    old = _old_report(root)["experience"]
    if full["source"] == "profile":  # the full doctor goes on to the profile's default
        full = {"level": None, "source": "unknown"}
    assert (old["level"], old["source"]) == (full["level"], full["source"])


def test_the_profiles_default_isnt_read_on_old_python(tmp_path):
    root = _project(tmp_path)  # its profile says experience = "new"
    prof = root / ".claude/workflow/profile.toml"
    prof.write_text(prof.read_text().replace('experience = "new"', 'experience = "developer"'))
    r = _old_report(root)
    assert r["experience"] == {"level": None, "source": "unknown", "default": None} and r["wording"] == "new"


def test_each_message_and_fix_differs_by_experience_while_every_status_is_the_same(tmp_path):
    root = _project(tmp_path)
    new = _old_report(root, env={"WORKFLOW_EXPERIENCE": "new"})
    dev = _old_report(root, env={"WORKFLOW_EXPERIENCE": "developer"})
    assert [(ln["id"], ln["status"]) for ln in new["lines"]] == [(ln["id"], ln["status"]) for ln in dev["lines"]]
    for a, b in zip(new["lines"], dev["lines"]):
        assert a["message"] != b["message"], a["id"]
        assert a["fix"] != b["fix"], a["id"]
        if a["status"] == "cant_check":
            assert UNTIL in a["message"] and UNTIL in b["message"]


def test_the_text_report_is_worded_by_experience(tmp_path):
    root = _project(tmp_path)
    new = _old(root, env={"WORKFLOW_EXPERIENCE": "new"})[1]
    dev = _old(root, env={"WORKFLOW_EXPERIENCE": "developer"})[1]
    assert "brew install python" in new and "brew install python" not in dev


# The same lines as the full doctor's


@pytest.mark.parametrize("vendored", [True, False])
@pytest.mark.parametrize("gh", [None, False])
def test_the_ids_and_groups_match_the_full_doctors(tmp_path, vendored, gh):
    """The full doctor on the same checkout, with GitHub answering (every
    line fine) or not (`gh` missing): the same groups and ids, in vendored and
    plugin mode."""
    root = _project(tmp_path, profile=HEALTHY, vendored=vendored, settings=None if vendored else PLUGIN_ON)
    full = _report(tmp_path, root, path=_bin(tmp_path, gh=gh))
    assert _pairs(_old_report(root)) == _pairs(full)


def test_every_line_the_full_doctor_names_is_in_the_short_report_or_said_only_when_wrong(tmp_path):
    """Every id doctor.py writes. A new one fails here until it is added to
    `_old_python`'s short report (`_DOCTOR_LINES`), or to ONLY_WHEN_WRONG
    above as a line said only when something is wrong."""
    source = (KIT / "scripts/workflow/doctor.py").read_text()
    named = set(re.findall(r'"((?:computer|kit|github|cloud|previews)\.[a-z_.]+)"', source))
    short = {ln["id"] for ln in _old_report(_project(tmp_path / "v"))["lines"]}
    short |= {ln["id"] for ln in _old_report(_project(tmp_path / "p", vendored=False))["lines"]}
    assert named - short - ONLY_WHEN_WRONG == set()
    assert ONLY_WHEN_WRONG & short == set()
    lines = {(g, i) for g, i, *_ in _old_python._DOCTOR_LINES} | {("Your computer", "computer.python3")}
    assert {(c.group, c.id) for c in doctor.CHECKS} <= lines  # each check's main line


def test_the_groups_and_statuses_are_the_full_doctors():
    assert _old_python._DOCTOR_GROUPS == doctor.GROUPS
    assert _old_python._DOCTOR_STATUSES == doctor.STATUSES
    assert _old_python._DOCTOR_LABELS == doctor.LABELS


# It never raises, and changes nothing


def _boom(*a, **k):
    raise RuntimeError("boom")


def test_a_report_that_fails_still_gives_the_gap(tmp_path, monkeypatch):
    monkeypatch.setattr(_old_python, "_doctor_root", _boom)
    r = _old_report(_project(tmp_path))
    assert r["lines"][0]["id"] == "computer.python3" and r["lines"][0]["status"] == "gap"
    assert {ln["status"] for ln in r["lines"][1:]} == {"cant_check"}
    assert _old(_project(tmp_path / "s"), "--strict")[0] == STRICT_FAIL


def test_a_deleted_current_folder_still_gives_the_report(tmp_path, monkeypatch):
    def gone():
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(os, "getcwd", gone)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _old_python.main(["doctor", "--json"], stdin_text="", env={"WORKFLOW_EXPERIENCE": "developer"}, version="3.9.6")
    assert code == 0, err.getvalue()
    r = json.loads(out.getvalue())
    assert r["lines"][0]["id"] == "computer.python3"
    assert (r["wording"], r["experience"]["source"]) == ("developer", "environment")  # still read


class _Closed(io.StringIO):
    """A stdout whose reader has gone."""

    def write(self, text):
        raise BrokenPipeError(32, "Broken pipe")


@pytest.mark.parametrize("args,code", [((), 0), (("--json",), 0), (("--strict",), STRICT_FAIL)])
def test_output_that_cant_be_written_exits_as_strict_says(tmp_path, args, code):
    err = io.StringIO()
    env = {"CLAUDE_PROJECT_DIR": str(_project(tmp_path))}
    with contextlib.redirect_stdout(_Closed()), contextlib.redirect_stderr(err):
        got = _old_python.main(["doctor", *args], stdin_text="", env=env, version="3.9.6")
    assert got == code
    assert "couldn't write the report" in err.getvalue() and "needs Python" not in err.getvalue()


def test_no_stderr_either_never_raises(tmp_path, monkeypatch):
    dup2 = []
    with monkeypatch.context() as m:  # undone before pytest's own capture moves descriptors again
        m.setattr(os, "dup2", lambda *a: dup2.append(a))
        m.setattr(sys, "stderr", None)
        with contextlib.redirect_stdout(_Closed()):
            bogus = _old_python.main(["doctor", "--bogus"], stdin_text="", env={}, version="3.9.6", cwd=tmp_path)
            plain = _old_python.main(["doctor"], stdin_text="", env={}, version="3.9.6", cwd=tmp_path)
    assert (bogus, plain) == (2, 0)
    assert dup2 == []  # no stream has nothing to flush: no descriptor is touched


@pytest.mark.parametrize("where", ["missing", "file", "empty"])
def test_an_odd_project_folder_still_gives_the_report(tmp_path, where):
    root = tmp_path / "proj"
    if where == "file":
        root.write_text("x")
    elif where == "empty":
        root.mkdir()
    r = _old_report(root)
    assert r["lines"][0]["id"] == "computer.python3" and r["lines"][0]["status"] == "gap"


def test_the_experience_file_as_a_pipe_or_a_directory_reads_as_unknown(tmp_path):
    root = _project(tmp_path)
    (root / ".workflow").mkdir()
    os.mkfifo(str(root / ".workflow/experience"))  # nobody writes to it: a blocking read would wait for ever
    got = []
    t = threading.Thread(target=lambda: got.append(_old_python._experience(str(root), {})), daemon=True)
    t.start()
    t.join(10)
    assert got == [(None, "unknown")], "reading .workflow/experience as a pipe waited"
    assert _old_report(root)["experience"]["source"] == "unknown"
    (root / ".workflow/experience").unlink()
    (root / ".workflow/experience").mkdir()
    assert _old_report(root)["experience"]["source"] == "unknown"


def test_nothing_in_the_checkout_changes_after_a_run(tmp_path):
    root = _project(tmp_path)
    before = sorted((p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*"))
    _old(root)
    _old(root, "--json", "--strict")
    assert sorted((p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*")) == before


def test_other_commands_still_say_what_they_need(tmp_path):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        code = _old_python.main(["status"], stdin_text="", env={}, version="3.9.6", cwd=tmp_path)
    assert code == 1 and "3.11" in err.getvalue()


# On a real Python 3.9 (in CI always; elsewhere when there is one, else the
# entry point run with an old version made up, so the test runs everywhere)

# The entry point with sys.version_info made old, for a machine with no 3.9.
_AS_OLD = (
    "import runpy, sys; sys.version_info = (3, 9, 6, 'final', 0); "
    "sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
)


# A child that waits on standard input, or never ends, fails its test rather than the run.
_BOUNDED = {"stdin": subprocess.DEVNULL, "timeout": 60}


def _old_entry_point():
    """The command that runs the entry point on an old Python, and the
    version it reports."""
    py = _old_python_binary()
    if py:
        return [py, "-B"], "3.9."
    assert not os.environ.get("CI"), "set OLD_PYTHON to a Python 3.9"
    return [sys.executable, "-B", "-c", _AS_OLD], "3.9.6"


def test_doctor_on_a_real_python_3_9(tmp_path):
    py, version = _old_entry_point()
    root = _project(tmp_path, compiled=False)  # no bytecode, so the end shows none was written
    (root / ".workflow").mkdir()
    (root / ".workflow/experience").write_text("developer\n")
    copy = root / ".claude/workflow/bin/workflow.py"
    for cli in (CLI, copy):
        for level, wording, source in (("developer", "developer", "environment"), ("new", "new", "environment"),
                                       ("", "developer", "local file")):
            env = {"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(root), "WORKFLOW_EXPERIENCE": level}
            p = subprocess.run([*py, str(cli), "doctor", "--json"], capture_output=True, text=True, env=env, cwd=root, **_BOUNDED)
            assert p.returncode == 0, p.stderr
            r = json.loads(p.stdout)
            first = r["lines"][0]
            assert (first["id"], first["status"]) == ("computer.python3", "gap") and version in first["message"]
            assert all(ln["status"] == "cant_check" and UNTIL in ln["message"] for ln in r["lines"][1:])
            assert (r["wording"], r["experience"]["source"]) == (wording, source)
            assert _pairs(r) == _pairs(_old_report(root))
        p = subprocess.run([*py, str(cli), "doctor", "--strict"], capture_output=True, text=True, env=env, cwd=root, **_BOUNDED)
        assert p.returncode == STRICT_FAIL and "[gap]" in p.stdout and UNTIL in " ".join(p.stdout.split()), p.stderr
        p = subprocess.run([*py, str(cli), "doctor"], capture_output=True, text=True, env=env, cwd=root, **_BOUNDED)
        assert p.returncode == 0 and p.stdout.startswith("Workflow doctor: 1 gap, "), p.stderr
        p = subprocess.run([*py, str(cli), "doctor", "--help"], capture_output=True, text=True, env=env, cwd=root, **_BOUNDED)
        assert p.returncode == 0 and "--strict" in p.stdout, p.stderr
        p = subprocess.run([*py, str(cli), "doctor", "--json", "--bogus"], capture_output=True, text=True, env=env, cwd=root, **_BOUNDED)
        assert (p.returncode, p.stdout) == (2, "") and "unrecognized arguments: --bogus" in p.stderr
    assert not list(root.rglob("__pycache__"))


def _with_a_closed_pipe(tmp_path, args, stream):
    """The old-Python entry point with `stream` ("stdout" or "stderr") a pipe
    whose reader is gone before it starts, the other one captured."""
    py, _ = _old_entry_point()
    root = _project(tmp_path)
    r, w = os.pipe()
    os.close(r)
    try:
        return subprocess.run([*py, str(CLI), "doctor", *args], text=True, cwd=root, **_BOUNDED,
                              env={"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(root)},
                              **{stream: w, ("stderr" if stream == "stdout" else "stdout"): subprocess.PIPE})
    finally:
        os.close(w)


@pytest.mark.parametrize("args,code", [((), 0), (("--json",), 0), (("--strict",), STRICT_FAIL), (("--help",), 0)])
def test_a_closed_stdout_on_an_old_python_exits_as_strict_says(tmp_path, args, code):
    """Nothing left to flush at exit, which would exit 120."""
    p = _with_a_closed_pipe(tmp_path, args, "stdout")
    assert p.returncode == code, p.stderr
    assert "Exception ignored" not in p.stderr and "Traceback" not in p.stderr


def test_a_closed_stderr_on_an_old_python_still_refuses_with_2(tmp_path):
    p = _with_a_closed_pipe(tmp_path, ("--json", "--bogus"), "stderr")
    assert (p.returncode, p.stdout) == (2, "")


# Docs and the changelog


def test_enforcement_md_names_the_short_report():
    text = (KIT / "docs/enforcement.md").read_text()
    section = text[text.index("**When something is wrong it fails closed**"):text.index("**When the guard's hook itself fails")]
    assert "workflow doctor" in section and "short report" in section and UNTIL in section


def test_the_readme_names_the_short_report():
    text = (KIT / "README.md").read_text()
    section = text[text.index("### When something goes wrong"):]
    section = section[:section.index("\n#", 1)]
    assert "workflow doctor" in section and "short report" in section


def test_the_changelog_has_a_note_under_unreleased():
    notes = since_0110()
    assert "#61" in notes and "short report" in notes

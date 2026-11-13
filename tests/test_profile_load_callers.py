"""#832: the commands that read the profile give `load`'s words for a profile
file they can't read, never their own.

Since #829, `profile.load` refuses a profile file it can't read with a
`ProfileError` in its own words (`… isn't UTF-8 text`, `… isn't a file`,
`… can't be read (<error>)`). Its callers in `cli.py` pass those words on,
with their own context after them where they keep one: a charter change
(`state put`), `preview --fetch`, `research`, `merge-check`, `review-record`,
`status` and `doctor`. Those read the profile through `cli._load`, which
refuses the `OSError` `load` still lets through (#837) in the same words.
Seams: each command through `cli.main` (`review-record`'s hashes and
`_read_profile` called directly), `cli.py`'s source for the handlers around
`load`, and the architecture page's lines."""

import argparse
import ast
import json
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import since_0110
from test_profile_unreadable import NOT_UTF8, _not_utf8, _page_line
from workflow import charter, cli, state
from workflow.profile import PROFILE_PATH

KIT = Path(__file__).resolve().parents[1]

# `load` still asks whether the profile exists before its own error handling
# (#837), so a path the system refuses (here a folder name too long) gives an
# `OSError` there: refused in `load`'s words all the same.
CANT_READ = f"{PROFILE_PATH} can't be read (OSError)"


def _a_profile_not_utf8(tmp_path):
    _not_utf8(tmp_path, b'[sensitive]\npatterns = ["secret-[0-9]+"]\n')
    return tmp_path


def _a_path_too_long(tmp_path):
    (tmp_path / "long").mkdir()
    return tmp_path / "long" / ("a" * 300)


SHAPES = [(_a_profile_not_utf8, NOT_UTF8), (_a_path_too_long, CANT_READ)]


@pytest.fixture(params=SHAPES, ids=["not-utf8", "path-too-long"])
def said(request, tmp_path, monkeypatch, capsys):
    """The project, in each shape of a profile `load` can't read, and its words for it."""
    make, words = request.param
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(make(tmp_path)))
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    return words


def _charter():
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    return c


def test_a_charter_change_gives_loads_words_then_its_context(tmp_path, capsys, said):
    s = state.empty(_charter())
    s["run_id"] = "2026-11-13-unreadable"
    (tmp_path / "body.md").write_text(state.put("## Run\n", s), encoding="utf-8")
    changed = json.loads(json.dumps(s))
    changed["charter"]["limits"]["ends_at"] = "2099-10-14T03:30:00Z"
    assert charter.validate(changed["charter"]) == []
    (tmp_path / "state.json").write_text(json.dumps(changed), encoding="utf-8")
    capsys.readouterr()
    rc = cli.main(["state", "put", "--body", str(tmp_path / "body.md"), "--state", str(tmp_path / "state.json"), "--out", str(tmp_path / "new.md")])
    out, err = capsys.readouterr()
    assert rc == 1
    assert out == ""
    assert err == f"workflow: {said}, so the charter change can't be checked\n"
    assert "Traceback" not in err and str(tmp_path) not in err
    assert not (tmp_path / "new.md").exists()


def test_preview_fetch_gives_loads_words(tmp_path, monkeypatch, capsys, said):
    gh = fake_gh.install(tmp_path, monkeypatch, {})
    rc = cli.main(["preview", "--fetch", "12"])
    out, err = capsys.readouterr()
    assert rc == 2
    assert out == ""
    assert f"the profile can't be read ({said}): " in err
    assert err.startswith("workflow preview: --fetch needs the profile's project.repo, and ")
    assert "Traceback" not in err and str(tmp_path) not in err
    assert gh.calls() == []


def test_research_gives_loads_words_then_its_context(tmp_path, capsys, said):
    (tmp_path / "page.txt").write_text("A paragraph naming secret-123.\n", encoding="utf-8")
    rc = cli.main(["research", "fingerprint", "https://example.com/page", "--page", str(tmp_path / "page.txt")])
    out, err = capsys.readouterr()
    assert rc == 1
    assert out == ""
    assert err == f"workflow: {said}, so [sensitive].patterns can't be left out\n"
    assert "Traceback" not in err and str(tmp_path) not in err


# ---------- no caller words it itself ----------


def _functions():
    tree = ast.parse((KIT / "scripts/workflow/cli.py").read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _calls_load(node):
    return any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in ("load", "_load") for c in ast.walk(node))


def _caught(handler):
    t = handler.type
    names = t.elts if isinstance(t, ast.Tuple) else [t] if t is not None else []
    return {n.id for n in names if isinstance(n, ast.Name)}


def _tries_around_load():
    """Every `try` in `cli.py` whose body calls `load` (or `_load`), with its function's name."""
    return [(name, t) for name, fn in _functions().items() for t in ast.walk(fn) if isinstance(t, ast.Try) and any(_calls_load(s) for s in t.body)]


# What catches the `OSError` a read can raise, as `except` names it.
READ_ERRORS = {"OSError", "IOError", "EnvironmentError", "Exception", "BaseException"}


def test_the_walk_finds_every_caller_that_refuses_a_profile_it_cant_read():
    assert {"_load", "_read_profile", "_page_profile", "_charter_change_problems", "cmd_merge_check", "cmd_preview", "_research_patterns", "_own_hashes", "_measure"} <= {n for n, _ in _tries_around_load()}


def test_no_handler_around_load_catches_the_read_errors_load_words():
    """`load` refuses a profile file it can't read with a `ProfileError` in its
    own words, and `_load` refuses the `OSError` it still lets through in the
    same words: any other caller in `cli.py` that catches `UnicodeDecodeError`
    or `OSError` around them keeps a second wording of its own. `_page_profile`
    words nothing: it renders the page without a profile."""
    for name, t in _tries_around_load():
        for h in t.handlers:
            caught = _caught(h) if h.type is not None else {"BaseException"}
            assert "UnicodeDecodeError" not in caught, (name, h.lineno, caught)
            assert not caught & READ_ERRORS or name in ("_load", "_page_profile"), (name, h.lineno, caught)


def test_load_wrapper_refuses_an_oserror_in_loads_words_and_page_profile_words_none():
    [(_, t)] = [(n, t) for n, t in _tries_around_load() if n == "_load"]
    [h] = t.handlers
    assert _caught(h) == {"OSError"}
    assert [ast.unparse(s) for s in h.body] == ["raise unreadable(e) from None"]
    [(_, t)] = [(n, t) for n, t in _tries_around_load() if n == "_page_profile"]
    [h] = t.handlers
    assert [ast.unparse(s) for s in h.body] == ["return None"]


def test_merge_check_gives_loads_words_as_its_reason(monkeypatch, capsys, said):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    assert cli.main(["merge-check", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    [reason] = [r for r in got["reasons"] if r.get("input") == "profile"]
    assert reason["message"] == f"Not yet: couldn't read the profile: {said}."


def test_review_record_measure_gives_loads_words(tmp_path, capsys, said):
    assert cli.main(["review-record", "--measure", "--commit", "0" * 40]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"workflow review-record: can't measure: couldn't read the profile: {said}\n"
    assert str(tmp_path) not in err


def test_review_records_hashes_note_gives_loads_words(tmp_path, capsys, said):
    from workflow import own_changes

    assert cli._own_hashes(argparse.Namespace(base=None), "0" * 40) == own_changes.UNKNOWN_HASHES
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"workflow review-record: couldn't read the profile for the base branch ({said}): {own_changes.UNKNOWN} for diff and lines\n"
    assert str(tmp_path) not in err


def test_status_and_doctor_read_it_in_loads_words(said):
    from workflow.profile import project_root

    assert cli._read_profile(project_root()) == (None, said)


# `tomllib` refuses an integer longer than Python's limit on digits (4300)
# with a plain `ValueError`, not a `TOMLDecodeError`: `load` lets it through,
# and status and doctor still name it as they did before #832.
HUGE_INTEGER = '[project]\nname = "demo"\nrepo = "acme/demo"\n[run]\nmax_parallel = ' + "1" * 4301 + "\n"
CANT_READ_VALUE = f"{PROFILE_PATH} can't be read (ValueError)"


def test_status_and_doctor_name_a_profile_tomllib_refuses_with_a_value_error(tmp_path):
    from test_doctor import _line, _project
    from test_status_local_gaps import _status

    root = _project(tmp_path, profile=HUGE_INTEGER)
    assert cli._read_profile(root) == (None, CANT_READ_VALUE)
    gap = f"The kit's profile ({PROFILE_PATH}, its settings for this project) has a mistake, so the kit can't use it: {CANT_READ_VALUE}."
    line = _line(tmp_path, root, "kit.profile")
    assert (line["status"], line["message"]) == ("gap", gap)
    report = json.loads(_status(tmp_path, root, "--json"))
    assert report["profile_error"] is True
    assert {g["id"]: g for g in report["local_gaps"]}["kit.profile"]["message"] == gap
    assert "Kit: set up, but its profile has an error (kit.profile)" in _status(tmp_path, root)


# Each caller that reads the profile through `_load`, as the page's `_load` line names it.
THROUGH_LOAD = {
    "_charter_change_problems": "a charter change",
    "cmd_preview": "`preview --fetch`",
    "_research_patterns": "`research`",
    "cmd_merge_check": "`merge-check`",
    "_own_hashes": "`review-record`",
    "_measure": "`review-record`",
    "_read_profile": "`cli._read_profile` (`status`, `doctor`)",
}


def test_the_page_names_the_callers_that_read_it_through_the_wrapper():
    """The page's `load` line says no other caller in `cli.py` words the read's
    errors its own way (the walk above holds it to that); its `_load` line
    names each caller that reads the profile through `_load`."""
    callers = {n for n, fn in _functions().items() if n != "_load" and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "_load" for c in ast.walk(fn))}
    assert callers == set(THROUGH_LOAD)
    line = _page_line("_load")
    for said in THROUGH_LOAD.values():
        assert said in line, said
    assert "never catch the read's errors to word them their own way" in _page_line("load")
    assert "`load` and `cli._load` both give them" in _page_line("unreadable")


def test_page_profiles_comment_no_longer_says_a_file_that_isnt_utf8_is_a_value_error():
    src = ast.get_source_segment((KIT / "scripts/workflow/cli.py").read_text(encoding="utf-8"), _functions()["_page_profile"])
    assert "so is a file that isn't UTF-8" not in src


def test_changelog_notes_it_under_unreleased():
    assert "#832" in since_0110()

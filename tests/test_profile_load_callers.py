"""#832: the commands that read the profile give `load`'s words for a profile
file they can't read, never their own.

Since #829, `profile.load` refuses a profile file it can't read with a
`ProfileError` in its own words (`… isn't UTF-8 text`, `… isn't a file`,
`… can't be read (<error>)`). Its callers in `cli.py` pass those words on,
with their own context after them where they keep one: a charter change
(`state put`), `preview --fetch` and `research`. Seams: each command through
`cli.main`, and `cli.py`'s source for the handlers around `load`."""

import ast
import json
from pathlib import Path

import pytest

import fake_gh
from changelog_notes import since_0110
from test_profile_unreadable import NOT_UTF8, _not_utf8
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


@pytest.mark.parametrize("name", ["_charter_change_problems", "cmd_preview", "_research_patterns", "_page_profile"])
def test_no_handler_around_load_catches_the_read_errors_load_words(name):
    """`load` turns a file it can't decode into a `ProfileError`: a caller
    that catches `UnicodeDecodeError` (or `OSError` beside it, wording it)
    around `load` keeps a second wording of its own."""
    fn = _functions()[name]
    tries = [t for t in ast.walk(fn) if isinstance(t, ast.Try) and any(_calls_load(s) for s in t.body)]
    assert tries, f"{name} no longer calls load inside a try"
    for t in tries:
        for h in t.handlers:
            caught = _caught(h)
            assert "UnicodeDecodeError" not in caught, (name, caught)
            assert "OSError" not in caught or name == "_page_profile", (name, caught)


def test_page_profiles_comment_no_longer_says_a_file_that_isnt_utf8_is_a_value_error():
    src = ast.get_source_segment((KIT / "scripts/workflow/cli.py").read_text(encoding="utf-8"), _functions()["_page_profile"])
    assert "so is a file that isn't UTF-8" not in src


def test_changelog_notes_it_under_unreleased():
    assert "#832" in since_0110()

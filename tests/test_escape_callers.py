"""#805: one escape of what can't be printed, in `issues.py`.

`merge._clean` and `doctor._printable` kept their own lists beside the shared
`issues.escape_controls`. Both now call `issues.escape_unprintable`, which
escapes everything `escape_controls` does, written the same way, and every
other character `str.isprintable()` rejects (a format character such as an
emoji's joiner, a no-break space, a lone surrogate), since merge-check and
doctor show names that must be told apart. `protection.printable` builds on
`escape_controls` line by line, so its JSON keeps its lines.
"""

import json
import sys

import pytest

from changelog_notes import KIT, entry
from test_doctor_cloud import NAMED, NEW, _doctor, _env_file, _no_gh, _project
from test_merge_check import check, inputs, project  # noqa: F401  (the fixture)
from test_protection_requests import cli as protection_cli, inp, put, recorded_ruleset  # noqa: F401  (the fixture)
from workflow import doctor as doctor_mod
from workflow import issues as issues_mod
from workflow import merge as merge_mod
from workflow import protection


# ---------- the helper ----------


def test_escape_unprintable_escapes_exactly_what_cant_be_printed():
    wrong = [hex(cp) for cp in range(sys.maxunicode + 1) if (issues_mod.escape_unprintable(chr(cp)) != chr(cp)) == chr(cp).isprintable()]
    assert wrong == []


def test_escape_unprintable_writes_each_control_as_escape_controls_does():
    """One way of writing an escape: what `escape_controls` escapes,
    `escape_unprintable` escapes the same, so only one list is kept."""
    wrong = [hex(cp) for cp in range(sys.maxunicode + 1)
             if issues_mod.escape_controls(chr(cp)) != chr(cp) and issues_mod.escape_unprintable(chr(cp)) != issues_mod.escape_controls(chr(cp))]
    assert wrong == []


@pytest.mark.parametrize("text,shown", [
    ("a\nb", "a\\nb"),
    ("a\x1b[31mb", "a\\u001b[31mb"),
    ("a‍b", "a\\u200db"),
    ("a b", "a\\u00a0b"),
    ("a\ud800b", "a\\ud800b"),
    ("é 😀 中文 ü", "é 😀 中文 ü"),
])
def test_escape_unprintable_examples(text, shown):
    assert issues_mod.escape_unprintable(text) == shown


# ---------- the callers keep no list of their own ----------


@pytest.mark.parametrize("call", [merge_mod._clean, doctor_mod._shown, doctor_mod._named, doctor_mod._printable])
def test_merge_and_doctor_call_the_shared_helper(monkeypatch, call):
    """With the shared helper told to escape nothing, a zero-width space (which
    json.dumps, behind `_named`, leaves as it is) gets through: neither caller
    has another copy behind it."""
    assert "\u200b" not in call("a\u200bb")
    monkeypatch.setattr(issues_mod, "escape_unprintable", lambda text: text)
    assert "\u200b" in call("a\u200bb")


def test_protection_printable_calls_the_shared_helper(monkeypatch):
    monkeypatch.setattr(issues_mod, "escape_controls", lambda text: text)
    assert "\x9b" in protection.printable('"a\x9bb"')


# ---------- through each command's text ----------


def test_merge_check_text_escapes_a_line_break_and_an_escape_code(project, capsys):
    data = inputs()
    data["files"] = [{"filename": ".claude/a\nb\x1b[31m.md", "status": "modified"}]
    out, _ = check(project, capsys, data, as_json=False)
    assert "Needs the owner's review" in out, out
    assert "- `.claude/a\\nb\\u001b[31m.md`" in out, out
    assert "\x1b" not in out


@pytest.mark.parametrize("name,shown", [
    (".claude/é😀中文.md", ".claude/é😀中文.md"),
    (".claude/a‍b.md", ".claude/a\\u200db.md"),
    (".claude/a b.md", ".claude/a\\u00a0b.md"),
])
def test_merge_check_text_outside_ascii(project, capsys, name, shown):
    """Text outside ASCII prints as it is; a format character escaped as
    before; a no-break space now escaped too (the changelog says why)."""
    data = inputs()
    data["files"] = [{"filename": name, "status": "modified"}]
    out, _ = check(project, capsys, data, as_json=False)
    assert f"- `{shown}`" in out, out


def test_doctor_text_escapes_a_line_break_and_an_escape_code(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    args = _env_file(tmp_path, json.dumps({"environments": [{"name": "workflow-ticket\n\x1b[31m"}, {"name": "workflow-conductor"}]}))
    p = _doctor(tmp_path, root, *args, environments=None, path=_no_gh(tmp_path), env={**NEW, "PYTHONIOENCODING": "utf-8"})
    assert p.returncode == 0, p.stderr
    assert "workflow-ticket\\n\\u001b[31m" in p.stdout and "\x1b" not in p.stdout, p.stdout


def test_doctor_text_outside_ascii_prints_as_it_is(tmp_path):
    root = _project(tmp_path, profile=NAMED)
    args = _env_file(tmp_path, json.dumps({"environments": [{"name": "workflow-ticket-é😀"}, {"name": "workflow-conductor"}]}, ensure_ascii=False))
    p = _doctor(tmp_path, root, *args, environments=None, path=_no_gh(tmp_path), env={**NEW, "PYTHONIOENCODING": "utf-8"})
    assert p.returncode == 0, p.stderr
    assert "workflow-ticket-é😀" in p.stdout, p.stdout


@pytest.mark.parametrize("raw,shown", [("\x9b", "\\u009b"), ("\x7f", "\\u007f"), ("‮", "\\u202e")])
def test_protection_text_escapes_a_c1_code_del_and_a_bidi_override(repo, inp, raw, shown):
    """json.dumps leaves these as they are; the shared helper escapes them,
    and the JSON keeps its lines."""
    rs = recorded_ruleset()
    rs["name"] = f"bad{raw}[31m é😀"
    p = protection_cli(repo, "--require-checks", put(inp, "ruleset.json", json.dumps(rs)), "--check", "tests")
    assert p.returncode == 0, p.stderr
    assert raw not in p.stdout and f"bad{shown}[31m é😀" in p.stdout, p.stdout


def test_protection_printable_keeps_the_json_s_lines():
    dumped = json.dumps({"name": "a\x9bb", "x": [1]}, indent=2, ensure_ascii=False)
    shown = protection.printable(dumped)
    assert shown.count("\n") == dumped.count("\n")
    assert json.loads(shown) == {"name": "a\x9bb", "x": [1]}


# ---------- the architecture page ----------


def test_the_architecture_page_names_the_callers():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `escape_unprintable`: in `issues.py`"))
    assert "`merge._clean`" in line and "`doctor._shown`" in line and "`doctor._named`" in line
    controls = next(l for l in page.splitlines() if l.startswith("- `escape_controls`: in `issues.py`"))
    assert "`protection.printable`" in controls


def test_the_changelog_note():
    note = entry("#805, found in the review of #776's pull request")
    assert "`issues.escape_unprintable`" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_escape_callers.py" in note

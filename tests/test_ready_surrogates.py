"""`workflow ready --issues F --prs G`'s text gives no traceback on a title, an
`Area:` line, a `note:` line or a reason it can't print (#785): a lone
surrogate, written in the JSON as an escape (`"bad \\ud800 title"`), is shown
as that escape, through `issues.escape_surrogates` (#774). `--json` is
unchanged. Run through `cli.main`.
"""

import json
from pathlib import Path

from changelog_notes import entry, released
from workflow import cli

KIT = Path(__file__).resolve().parents[1]


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _ready(monkeypatch, capsys, tmp_path, issues_json: str, *extra, profile: str | None = None) -> str:
    """The files written as given, so the escapes are the JSON's own."""
    _env(monkeypatch, tmp_path)
    if profile is not None:
        (tmp_path / ".claude/workflow").mkdir(parents=True)
        (tmp_path / ".claude/workflow/profile.toml").write_text(profile, encoding="utf-8")
    (tmp_path / "issues.json").write_text(issues_json, encoding="utf-8")
    (tmp_path / "prs.json").write_text("[]", encoding="utf-8")
    code = cli.main(["ready", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    # The text as a terminal gets it: it encodes as UTF-8.
    out.out.encode("utf-8")
    return out.out


def _ticket(number: int, title: str, body: str, state: str = "open", labels: str = '[{"name": "ready-for-agent"}]') -> str:
    """One issue as JSON, `title` and `body` given as JSON string contents, escapes and all."""
    return f'{{"number": {number}, "title": "{title}", "state": "{state}", "labels": {labels}, "body": "{body}"}}'


TITLE = "[" + _ticket(1, "bad \\ud800 title", "Area: x") + "]"


def test_a_title_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    out = _ready(monkeypatch, capsys, tmp_path, TITLE)
    assert "READY #1 [x] bad \\ud800 title" in out.splitlines()
    assert "start now: #1" in out.splitlines()


def test_an_area_line_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    """An area is one word, so the lone surrogate never reaches the area
    itself: it reaches the note saying how the `Area:` line was read."""
    out = _ready(monkeypatch, capsys, tmp_path, "[" + _ticket(2, "Notes list", "Area: do\\ud800ctor") + "]").splitlines()
    assert "READY #2 [do-ctor] Notes list" in out
    assert any(l.startswith("      note: Area should be one word") and "do\\ud800ctor" in l for l in out), out


def test_a_note_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    """The protected-path note names the path as the ticket's body writes it."""
    profile = '[project]\nname = "p"\nrepo = "o/r"\n\n[guard]\nprotected_paths = [".claude/**"]\n'
    issues = "[" + _ticket(3, "Notes list", "Area: notes\\nChange `.claude/x\\ud800y.md` please") + "]"
    out = _ready(monkeypatch, capsys, tmp_path, issues, profile=profile).splitlines()
    assert any(l.startswith("READY #3 [notes] Notes list") for l in out), out
    assert "      note: names protected path .claude/x\\ud800y.md (.claude/**): check it isn't an owner task" in out


def test_a_reason_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    """A waiting ticket's reasons, on its own line, are escaped too."""
    issues = (
        "["
        + _ticket(4, "Notes list", "Area: notes\\n\\n## Blocked by\\n\\n#5\\n")
        + ", "
        + _ticket(5, "Old", "", state="closed", labels="[]").replace('"body"', '"state_reason": "not\\udc80planned", "body"')
        + "]"
    )
    out = _ready(monkeypatch, capsys, tmp_path, issues).splitlines()
    assert "wait  #4 [notes] Notes list — blocker #5 closed as not\\udc80planned, not completed" in out


def test_printable_text_is_unchanged(monkeypatch, capsys, tmp_path):
    """Only lone surrogates change here: an emoji (a surrogate pair in the
    JSON) and an accent are left as they were. A tab is a control character,
    shown as `\\t` (#797's `tests/test_ready_control_chars.py`)."""
    out = _ready(monkeypatch, capsys, tmp_path, "[" + _ticket(6, "caf\\u00e9 \\ud83d\\ude00 tab\\there", "Area: x") + "]")
    assert "READY #6 [x] café \U0001F600 tab\\there" in out.splitlines()


def test_json_output_is_unchanged(monkeypatch, capsys, tmp_path):
    out = json.loads(_ready(monkeypatch, capsys, tmp_path, TITLE, "--json"))
    assert out["ready"][0]["title"] == "bad \ud800 title"
    assert out["start_now"] == [1]


def test_the_changelog_notes_it_and_version_is_not_bumped():
    note = entry("#785, found in the review of #774's pull request")
    assert "`VERSION` is unchanged" in note
    assert "tests/test_ready_surrogates.py" in note
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()


def test_the_architecture_page_names_ready_as_a_caller():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `escape_surrogates`: in `issues.py`"))
    assert "`workflow ready`" in line

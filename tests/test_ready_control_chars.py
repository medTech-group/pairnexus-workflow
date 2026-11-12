"""`workflow ready --issues F --prs G`'s text shows the control characters in
a ticket's title, area, `note:` lines and reasons as escapes, never as they
are (#797), through `issues.escape_controls` (#776): a line break keeps each
ticket on its one line, and an escape code reaches the terminal as text.
Plain and non-ASCII titles, and `--json`, are unchanged. Run through
`cli.main`.
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


def _ready(monkeypatch, capsys, tmp_path, issues, *extra, profile: str | None = None) -> str:
    _env(monkeypatch, tmp_path)
    if profile is not None:
        (tmp_path / ".claude/workflow").mkdir(parents=True)
        (tmp_path / ".claude/workflow/profile.toml").write_text(profile, encoding="utf-8")
    text = issues if isinstance(issues, str) else json.dumps(issues)
    (tmp_path / "issues.json").write_text(text, encoding="utf-8")
    (tmp_path / "prs.json").write_text("[]", encoding="utf-8")
    code = cli.main(["ready", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    return out.out


def _ticket(n, title, body="Area: notes", state="open", labels=("ready-for-agent",), **more):
    return {"number": n, "title": title, "state": state, "labels": [{"name": l} for l in labels], "body": body, **more}


FAKE = "READY #99 [x] fake"


def _lines_starting(out: str, start: str) -> list[str]:
    return [l for l in out.splitlines() if l.startswith(start)]


def test_a_title_with_a_line_break_stays_on_its_one_line(monkeypatch, capsys, tmp_path):
    issues = [_ticket(1, "line1\n" + FAKE, body="Area: notes\n\n## Blocked by\n\n#5")]
    out = _ready(monkeypatch, capsys, tmp_path, issues)
    lines = out.splitlines()
    assert "wait  #1 [notes] line1\\n" + FAKE + " — blocker #5 unknown" in lines[0]
    assert not _lines_starting(out, "READY")
    assert len(lines) == 2 and lines[1] == "start now: nothing"


def test_each_line_break_a_terminal_reads_as_one_is_escaped(monkeypatch, capsys, tmp_path):
    title = "a\rb\x0bc\x0cd\x1ce\x1df\x1eg\x85h\u2028i\u2029j"
    out = _ready(monkeypatch, capsys, tmp_path, [_ticket(1, title)])
    lines = out.splitlines()
    assert "READY #1 [notes] a\\rb\\u000bc\\u000cd\\u001ce\\u001df\\u001eg\\u0085h\\u2028i\\u2029j" in lines
    assert len(lines) == out.count("\n") == 2


def test_an_escape_code_in_a_title_is_shown_escaped(monkeypatch, capsys, tmp_path):
    out = _ready(monkeypatch, capsys, tmp_path, [_ticket(1, "\x1b[31mred\x1b[0m and \x9b2J")])
    assert "READY #1 [notes] \\u001b[31mred\\u001b[0m and \\u009b2J" in out.splitlines()
    assert "\x1b" not in out and "\x9b" not in out


def test_other_control_characters_and_bidirectional_overrides_are_escaped(monkeypatch, capsys, tmp_path):
    out = _ready(monkeypatch, capsys, tmp_path, [_ticket(1, "nul\x00 bell\x07 del\x7f tab\t a\u202eb\u2066c")])
    assert "READY #1 [notes] nul\\u0000 bell\\u0007 del\\u007f tab\\t a\\u202eb\\u2066c" in out.splitlines()


def test_a_note_line_is_escaped(monkeypatch, capsys, tmp_path):
    """A `note:` line quoting a path from the ticket's body shows its escape code as text."""
    profile = '[project]\nname = "p"\nrepo = "o/r"\n\n[guard]\nprotected_paths = [".claude/**"]\n'
    body = "Area: notes\nChange `.claude/x\x1by.md` please"
    out = _ready(monkeypatch, capsys, tmp_path, [_ticket(1, "Plain", body=body)], profile=profile)
    assert "      note: names protected path .claude/x\\u001by.md (.claude/**): check it isn't an owner task" in out.splitlines()
    assert "\x1b" not in out


def test_a_reason_is_escaped(monkeypatch, capsys, tmp_path):
    """A waiting ticket's reason quoting a blocker's `state_reason` stays on its line."""
    issues = [
        _ticket(4, "Notes list", body="Area: notes\n\n## Blocked by\n\n#5"),
        _ticket(5, "Blocker", state="closed", labels=(), state_reason="not\n" + FAKE),
    ]
    out = _ready(monkeypatch, capsys, tmp_path, issues)
    assert "wait  #4 [notes] Notes list — blocker #5 closed as not\\n" + FAKE + ", not completed" in out.splitlines()
    assert not _lines_starting(out, "READY")


def test_the_area_is_shown_as_read(monkeypatch, capsys, tmp_path):
    """An area is one word, so a control character never reaches it: the
    `Area:` line's words are joined as its slug."""
    out = _ready(monkeypatch, capsys, tmp_path, [_ticket(2, "Notes list", body="Area: do\x1b[2Jctor")])
    assert "READY #2 [do-2jctor] Notes list" in out.splitlines()
    assert "\x1b" not in out


def test_plain_and_non_ascii_titles_are_unchanged(monkeypatch, capsys, tmp_path):
    titles = [
        "Notes list shows the newest first",
        "Café — naïve façade “quoted” …",
        "日本語のタイトル 😀 👩‍💻 🇫🇷",
        "עברית RTL title with \u200f mark",
        "Path C:\\Users\\me and a \\n written out",
    ]
    out = _ready(monkeypatch, capsys, tmp_path, [_ticket(i + 1, t) for i, t in enumerate(titles)]).splitlines()
    for i, t in enumerate(titles):
        assert f"READY #{i + 1} [notes] {t}" in out


def test_a_lone_surrogate_is_still_escaped_beside_a_control_character(monkeypatch, capsys, tmp_path):
    issues = '[{"number": 1, "title": "bad \\ud800\\n title", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: x"}]'
    out = _ready(monkeypatch, capsys, tmp_path, issues)
    out.encode("utf-8")
    assert "READY #1 [x] bad \\ud800\\n title" in out.splitlines()


def test_json_output_is_unchanged(monkeypatch, capsys, tmp_path):
    title = "line1\n" + FAKE + " \x1b[31m\u2028"
    out = json.loads(_ready(monkeypatch, capsys, tmp_path, [_ticket(1, title)], "--json"))
    assert out["ready"][0]["title"] == title
    assert out["start_now"] == [1]


def test_the_changelog_notes_it_and_version_is_not_bumped():
    note = entry("#797")
    assert "`workflow ready`" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_ready_control_chars.py" in note
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()


def test_the_architecture_page_names_ready_as_a_caller():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    line = next(l for l in page.splitlines() if l.startswith("- `escape_controls`: in `issues.py`"))
    assert "`workflow ready`" in line

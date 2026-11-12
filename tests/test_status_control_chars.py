"""`workflow status --issues F --prs G`'s text shows the control characters in
an issue's or pull request's title, detail or branch as escapes, never as
they are (#776): a line break can't add a line of its own, and an escape code
reaches the terminal as text. Plain and non-ASCII titles, and `--json`, are
unchanged. Run through `cli.main`.
"""

import json
from pathlib import Path

from workflow import cli, issues as issues_mod

KIT = Path(__file__).resolve().parents[1]


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _status(monkeypatch, capsys, tmp_path, issues, prs, *extra) -> str:
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(json.dumps(issues), encoding="utf-8")
    (tmp_path / "prs.json").write_text(json.dumps(prs), encoding="utf-8")
    code = cli.main(["status", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    return out.out


def _issue(n, title, labels=(), body=""):
    return {"number": n, "title": title, "state": "open", "labels": [{"name": l} for l in labels], "body": body}


def _pr(n, title, ref):
    return {"number": n, "title": title, "state": "open", "head": {"ref": ref}}


FAKE = "Kit update pull request open: #99 (offer it, not another update)"


def test_a_title_with_a_line_break_stays_on_its_own_line(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, [_issue(1, "Line one\n" + FAKE)], []).splitlines()
    assert "- #1 Line one\\n" + FAKE in out
    assert not any(line.startswith("Kit update pull request open") for line in out)


def test_each_line_break_the_status_text_reads_as_one_is_escaped(monkeypatch, capsys, tmp_path):
    """`\\r`, NEL, the line and paragraph separators and the other characters
    `str.splitlines` breaks at all stay in the title's one line."""
    title = "a\rb\x0bc\x0cd\x1ce\x1df\x1eg\x85h\u2028i\u2029j"
    out = _status(monkeypatch, capsys, tmp_path, [_issue(1, title)], [])
    lines = out.splitlines()
    want = "- #1 a\\rb\\u000bc\\u000cd\\u001ce\\u001df\\u001eg\\u0085h\\u2028i\\u2029j"
    assert want in lines
    assert len(lines) == out.count("\n")


def test_an_escape_code_in_a_title_is_shown_escaped(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, [_issue(1, "\x1b[31mred\x1b[0m and \x9b2J")], [])
    assert "- #1 \\u001b[31mred\\u001b[0m and \\u009b2J" in out.splitlines()
    assert "\x1b" not in out and "\x9b" not in out


def test_other_control_characters_are_escaped(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, [_issue(1, "nul\x00 bell\x07 back\x08 del\x7f tab\t")], [])
    assert "- #1 nul\\u0000 bell\\u0007 back\\u0008 del\\u007f tab\\t" in out.splitlines()


def test_bidirectional_overrides_are_escaped(monkeypatch, capsys, tmp_path):
    """Characters that reorder what a terminal shows are made visible too."""
    out = _status(monkeypatch, capsys, tmp_path, [_issue(1, "a\u202eb\u2066c\u2069d\u202ae")], [])
    assert "- #1 a\\u202eb\\u2066c\\u2069d\\u202ae" in out.splitlines()


def test_a_pull_requests_title_and_branch_are_escaped(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, [], [_pr(5, "Notes\n" + FAKE, "x\x1b[2Jy\nz")]).splitlines()
    assert "- #5 Notes\\n" + FAKE + " [x\\u001b[2Jy\\nz]" in out
    assert not any(line.startswith("Kit update pull request open") for line in out)


def test_every_sections_title_and_detail_are_escaped():
    """Each item's title and detail, in every section `status.text` prints, go
    through the escape, whatever the section."""
    from workflow import status as status_mod

    st = status_mod.Status(set_up=True, brand_new=False, own_files=3, issues_read=True)
    for i, (key, _) in enumerate(status_mod._SECTIONS):
        getattr(st, key).append(status_mod.Item(100 + i, f"T{i}\n" + FAKE, f"d{i}\x1b[1m"))
    lines = status_mod.text(st).splitlines()
    for i, _ in enumerate(status_mod._SECTIONS):
        assert f"- #{100 + i} T{i}\\n{FAKE} [d{i}\\u001b[1m]" in lines
    assert not any(line.startswith("Kit update pull request open") for line in lines)


def test_plain_and_non_ascii_titles_are_unchanged(monkeypatch, capsys, tmp_path):
    titles = [
        "Notes list shows the newest first",
        "Café — naïve façade “quoted” …",
        "日本語のタイトル 😀 👩‍💻 🇫🇷",
        "עברית RTL title with \u200f mark",
        "Path C:\\Users\\me and a \\n written out",
    ]
    issues = [_issue(i + 1, t) for i, t in enumerate(titles)]
    out = _status(monkeypatch, capsys, tmp_path, issues, [_pr(20, "Plain PR", "claude/build-20")]).splitlines()
    for i, t in enumerate(titles):
        assert f"- #{i + 1} {t}" in out
    assert "- #20 Plain PR [claude/build-20]" in out


def test_a_lone_surrogate_is_still_escaped_beside_a_control_character(monkeypatch, capsys, tmp_path):
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(
        '[{"number": 1, "title": "bad \\ud800\\n title", "state": "open", "labels": []}]', encoding="utf-8"
    )
    (tmp_path / "prs.json").write_text("[]", encoding="utf-8")
    assert cli.main(["status", "--issues", "issues.json", "--prs", "prs.json"]) == 0
    out = capsys.readouterr().out
    assert "- #1 bad \\ud800\\n title" in out.splitlines()


def test_json_output_is_unchanged(monkeypatch, capsys, tmp_path):
    title = "Line one\n" + FAKE + " \x1b[31m\u2028"
    out = json.loads(_status(monkeypatch, capsys, tmp_path, [_issue(1, title)], [_pr(5, "t\x07", "b\nr")], "--json"))
    assert out["to_triage"][0]["title"] == title
    assert out["prs"][0]["title"] == "t\x07"
    assert out["prs"][0]["detail"] == "b\nr"
    assert out["kit_update_pr"] is None


def test_a_real_kit_update_pull_request_is_still_named(monkeypatch, capsys, tmp_path):
    from workflow import status as status_mod

    pr = _pr(42, status_mod.KIT_UPDATE_TITLE + " 1.2.3", "workflow/update")
    out = _status(monkeypatch, capsys, tmp_path, [], [pr]).splitlines()
    assert "Kit update pull request open: #42 (offer it, not another update)" in out


def test_escape_controls():
    esc = issues_mod.escape_controls
    assert esc("") == ""
    assert esc("plain text") == "plain text"
    assert esc("a\nb\rc\td") == "a\\nb\\rc\\td"
    assert esc("\x1b[31m") == "\\u001b[31m"
    assert esc("\x00\x1f\x7f\x80\x9f") == "\\u0000\\u001f\\u007f\\u0080\\u009f"
    assert esc("\u2028\u2029") == "\\u2028\\u2029"
    assert esc("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069") == (
        "\\u202a\\u202b\\u202c\\u202d\\u202e\\u2066\\u2067\\u2068\\u2069"
    )
    # Left as they are: text outside ASCII, the joiner inside an emoji, the
    # marks inside right-to-left text, a lone surrogate (`escape_surrogates`'s).
    for s in ("café", "👩‍💻", "a\u200fb\u200e", "\u00a0nbsp", "\ud800"):
        assert esc(s) == s
    # Nothing it writes is a character it escapes, so escaping twice changes no more.
    assert esc(esc("a\n\x1b")) == esc("a\n\x1b")


def test_the_architecture_page_lists_the_helper():
    page = (KIT / "docs" / "architecture" / "scripts--workflow.md").read_text(encoding="utf-8")
    helpers = page.split("## Helpers", 1)[1].split("\n## ", 1)[0]
    assert "- `escape_controls`: in `issues.py`" in helpers

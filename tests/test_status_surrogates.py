"""`workflow status --issues F --prs G`'s text gives no traceback on a title or
a branch it can't print (#774): a lone surrogate, written in the JSON as an
escape (`"bad \\ud800 title"`), is shown as that escape. Run through
`cli.main`.
"""

import json
from pathlib import Path

from changelog_notes import entry, released
from workflow import cli, issues as issues_mod, protection

KIT = Path(__file__).resolve().parents[1]


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _status(monkeypatch, capsys, tmp_path, issues_json: str, prs_json: str, *extra) -> str:
    """The files written as given, so the escapes are the JSON's own."""
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(issues_json, encoding="utf-8")
    (tmp_path / "prs.json").write_text(prs_json, encoding="utf-8")
    code = cli.main(["status", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert code == 0, out.err
    # The text as a terminal gets it: it encodes as UTF-8.
    out.out.encode("utf-8")
    return out.out


ISSUE = '[{"number": 1, "title": "bad \\ud800 title", "state": "open", "labels": []}]'
PR = '[{"number": 5, "title": "Notes list", "state": "open", "head": {"ref": "x\\udfff"}}]'


def test_an_issue_title_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, ISSUE, "[]")
    assert "- #1 bad \\ud800 title" in out.splitlines()


def test_a_pull_requests_branch_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, "[]", PR)
    assert "- #5 Notes list [x\\udfff]" in out.splitlines()


def test_both_at_once(monkeypatch, capsys, tmp_path):
    out = _status(monkeypatch, capsys, tmp_path, ISSUE, PR).splitlines()
    assert "- #1 bad \\ud800 title" in out
    assert "- #5 Notes list [x\\udfff]" in out


def test_a_pull_requests_title_with_a_lone_surrogate_is_listed(monkeypatch, capsys, tmp_path):
    prs = '[{"number": 6, "title": "Notes \\udc80list", "state": "open", "head": {"ref": "claude/build-6"}}]'
    out = _status(monkeypatch, capsys, tmp_path, "[]", prs)
    assert "- #6 Notes \\udc80list [claude/build-6]" in out.splitlines()


def test_printable_text_is_unchanged(monkeypatch, capsys, tmp_path):
    """Only lone surrogates change: other text, an emoji (a surrogate pair in
    the JSON) and a control character among it, is left as it was (#776 owns
    the rest of this output's handling)."""
    issues = '[{"number": 1, "title": "caf\\u00e9 \\ud83d\\ude00 tab\\there", "state": "open", "labels": []}]'
    out = _status(monkeypatch, capsys, tmp_path, issues, "[]")
    assert "- #1 café \U0001F600 tab\there" in out.splitlines()


def test_json_output_is_unchanged(monkeypatch, capsys, tmp_path):
    out = json.loads(_status(monkeypatch, capsys, tmp_path, ISSUE, PR, "--json"))
    assert out["to_triage"][0]["title"] == "bad \ud800 title"
    assert out["prs"][0]["detail"] == "x\udfff"


def test_escape_surrogates():
    esc = issues_mod.escape_surrogates
    assert esc("bad \ud800 title") == "bad \\ud800 title"
    assert esc("x\udfff") == "x\\udfff"
    # Two halves in the wrong order are two lone surrogates.
    assert esc("\ude00\ud83d") == "\\ude00\\ud83d"
    assert esc("café \U0001F600 \t\x1b") == "café \U0001F600 \t\x1b"
    assert esc("") == ""


def test_protection_printable_still_escapes_them_through_the_shared_helper():
    assert protection.printable('"a\ud800b "') == '"a\\ud800b\\u2028"'


def test_no_copy_of_the_surrogate_range_is_left_in_scripts():
    """`issues.escape_surrogates` is the one escape: a copy of its range
    elsewhere in the kit's scripts should call it instead."""
    copies = [
        p.relative_to(KIT).as_posix()
        for p in sorted((KIT / "scripts/workflow").glob("*.py"))
        if p.name != "issues.py" and "\\ud800-\\udfff" in p.read_text(encoding="utf-8")
    ]
    assert copies == []


def test_the_changelog_notes_it_and_version_is_not_bumped():
    note = entry("#774, found in the review of #770's pull request")
    assert "`VERSION` is unchanged" in note
    assert "tests/test_status_surrogates.py" in note
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()


def test_the_architecture_page_lists_the_helper():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    assert any(l.startswith("- `escape_surrogates`: in `issues.py`") for l in page.splitlines())

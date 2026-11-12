"""`workflow status`'s and `workflow protection`'s text give no traceback on a
standard output whose encoding can't take a character (#786): the character is
written as Python's backslash escape (`\\U0001f600`), the rest as it was. Run
through `cli.main` with such a standard output.
"""

import io
import json
import sys
from pathlib import Path

from changelog_notes import entry, released
from workflow import cli

KIT = Path(__file__).resolve().parents[1]

EMOJI = '[{"number": 3, "title": "emoji \\ud83d\\ude00 ok", "state": "open", "labels": []}]'


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _run(monkeypatch, capsys, encoding: str, argv: list[str]) -> tuple[int, str]:
    """`cli.main(argv)` with a standard output in `encoding` that refuses what
    it can't encode (errors="strict"), as a piped one on Windows does; its
    exit code and what it wrote, decoded."""
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding=encoding, errors="strict", newline="\n")
    monkeypatch.setattr(sys, "stdout", out)
    code = cli.main(argv)
    out.flush()
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "UnicodeEncodeError" not in err
    return code, raw.getvalue().decode(encoding)


def _status(monkeypatch, capsys, tmp_path, encoding: str, issues_json: str, *extra) -> tuple[int, str]:
    _env(monkeypatch, tmp_path)
    (tmp_path / "issues.json").write_text(issues_json, encoding="utf-8")
    (tmp_path / "prs.json").write_text("[]", encoding="utf-8")
    return _run(monkeypatch, capsys, encoding, ["status", "--issues", "issues.json", "--prs", "prs.json", *extra])


def test_status_lists_a_title_cp1252_cant_take_escaped(monkeypatch, capsys, tmp_path):
    code, out = _status(monkeypatch, capsys, tmp_path, "cp1252", EMOJI)
    assert code == 0
    assert "- #3 emoji \\U0001f600 ok" in out.splitlines()
    assert out.splitlines()[-1].startswith("Kit version:")


def test_status_keeps_what_cp1252_can_take(monkeypatch, capsys, tmp_path):
    """Only the characters the encoding can't take are escaped: `é` is in
    cp1252, and is written as itself."""
    issues = '[{"number": 3, "title": "caf\\u00e9 \\ud83d\\ude00", "state": "open", "labels": []}]'
    code, out = _status(monkeypatch, capsys, tmp_path, "cp1252", issues)
    assert code == 0
    assert "- #3 café \\U0001f600" in out.splitlines()


def test_status_and_n_more_under_ascii(monkeypatch, capsys, tmp_path):
    """Nine untriaged issues: the section lists eight and its own `… and 1
    more` line, whose `…` ASCII can't take, with plain titles."""
    issues = json.dumps([{"number": n, "title": f"Plain {n}", "state": "open", "labels": []} for n in range(1, 10)])
    code, out = _status(monkeypatch, capsys, tmp_path, "ascii", issues)
    assert code == 0
    lines = out.splitlines()
    assert "- #1 Plain 1" in lines
    assert "- \\u2026 and 1 more" in lines


def test_status_a_lone_surrogate_is_still_its_escape_under_ascii(monkeypatch, capsys, tmp_path):
    issues = '[{"number": 1, "title": "bad \\ud800 title", "state": "open", "labels": []}]'
    code, out = _status(monkeypatch, capsys, tmp_path, "ascii", issues)
    assert code == 0
    assert "- #1 bad \\ud800 title" in out.splitlines()


def test_status_utf8_output_is_unchanged(monkeypatch, capsys, tmp_path):
    code, out = _status(monkeypatch, capsys, tmp_path, "utf-8", EMOJI)
    assert code == 0
    assert "- #3 emoji \U0001F600 ok" in out.splitlines()


def test_status_json_is_unchanged(monkeypatch, capsys, tmp_path):
    code, cp = _status(monkeypatch, capsys, tmp_path, "cp1252", EMOJI, "--json")
    assert code == 0
    _, utf8 = _status(monkeypatch, capsys, tmp_path, "utf-8", EMOJI, "--json")
    assert cp == utf8
    assert json.loads(cp)["to_triage"][0]["title"] == "emoji \U0001F600 ok"


def _protection(monkeypatch, capsys, tmp_path, encoding: str, base: str, *extra) -> tuple[int, str]:
    _env(monkeypatch, tmp_path)
    (tmp_path / "rulesets.json").write_text("[]", encoding="utf-8")
    return _run(monkeypatch, capsys, encoding, ["protection", "--rulesets", "rulesets.json", "--base", base, *extra])


def test_protection_names_a_branch_cp1252_cant_take_escaped(monkeypatch, capsys, tmp_path):
    code, out = _protection(monkeypatch, capsys, tmp_path, "cp1252", "main\U0001F600")
    assert code == 0
    assert out.splitlines()[0] == "main\\U0001f600 is not protected:"


def test_protection_under_ascii(monkeypatch, capsys, tmp_path):
    code, out = _protection(monkeypatch, capsys, tmp_path, "ascii", "mäin")
    assert code == 0
    assert out.splitlines()[0] == "m\\xe4in is not protected:"


def test_protection_requests_under_ascii(monkeypatch, capsys, tmp_path):
    """`--protect`'s text goes through the same print."""
    _env(monkeypatch, tmp_path)
    (tmp_path / "repo.json").write_text(json.dumps({"full_name": "acme/notes", "default_branch": "main"}), encoding="utf-8")
    argv = ["protection", "--protect", "--repo", "repo.json", "--base", "mäin"]
    code, out = _run(monkeypatch, capsys, "ascii", argv)
    assert code == 0
    assert "m\\xe4in" in out
    _, utf8 = _run(monkeypatch, capsys, "utf-8", argv)
    assert out == utf8.replace("ä", "\\xe4")


def test_protection_utf8_and_json_are_unchanged(monkeypatch, capsys, tmp_path):
    code, out = _protection(monkeypatch, capsys, tmp_path, "utf-8", "main\U0001F600")
    assert code == 0
    assert out.splitlines()[0] == "main\U0001F600 is not protected:"
    code, cp = _protection(monkeypatch, capsys, tmp_path, "cp1252", "main\U0001F600", "--json")
    assert code == 0
    _, utf8 = _protection(monkeypatch, capsys, tmp_path, "utf-8", "main\U0001F600", "--json")
    assert cp == utf8
    assert json.loads(cp)["base_branch"] == "main\U0001F600"


def test_print_text_on_a_stream_without_an_encoding(capsys):
    """A stream that names no encoding (a `StringIO`) takes the text as it is."""
    buf = io.StringIO()
    cli._print_text("emoji \U0001F600 …", file=buf)
    assert buf.getvalue() == "emoji \U0001F600 …\n"


def test_the_changelog_notes_it_and_version_is_not_bumped():
    note = entry("#786, found in the review of #774's pull request")
    assert "`VERSION` is unchanged" in note
    assert "tests/test_text_output_encoding.py" in note
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()


def test_the_architecture_page_lists_the_helper():
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    assert any(l.startswith("- `_print_text`: in `cli.py`") for l in page.splitlines())

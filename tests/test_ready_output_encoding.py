"""`workflow ready --issues F --prs G`'s text gives no traceback on a standard
output whose encoding can't take a character (#802): each ticket's line and
each `note:` line go through `cli._print_text` (#786), so the character is
written as Python's backslash escape (`\\u2014`, `\\U0001f600`) and the rest as
it was. Run through `cli.main` with such a standard output, and as a
subprocess with the environments the ticket names.
"""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from changelog_notes import entry, released
from workflow import cli

KIT = Path(__file__).resolve().parents[1]

WAITING = "Area: notes\n\n## Blocked by\n\n#5"
UNKNOWN = "blocker #5 unknown (not in the issue list; for a PR, list it with the issues API's pull requests)"


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _ticket(n, title, body="Area: notes", labels=("ready-for-agent",)):
    return {"number": n, "title": title, "state": "open", "labels": [{"name": l} for l in labels], "body": body}


def _files(root: Path, issues, profile: str | None = None) -> None:
    if profile is not None:
        (root / ".claude/workflow").mkdir(parents=True)
        (root / ".claude/workflow/profile.toml").write_text(profile, encoding="utf-8")
    text = issues if isinstance(issues, str) else json.dumps(issues)
    (root / "issues.json").write_text(text, encoding="utf-8")
    (root / "prs.json").write_text("[]", encoding="utf-8")


def _ready(monkeypatch, capsys, tmp_path, encoding: str, issues, *extra, profile: str | None = None) -> tuple[int, str]:
    """`cli.main(["ready", ...])` with a standard output in `encoding` that
    refuses what it can't encode (errors="strict"); its exit code and what it
    wrote, decoded."""
    _env(monkeypatch, tmp_path)
    _files(tmp_path, issues, profile)
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding=encoding, errors="strict", newline="\n")
    monkeypatch.setattr(sys, "stdout", out)
    code = cli.main(["ready", "--issues", "issues.json", "--prs", "prs.json", *extra])
    out.flush()
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "UnicodeEncodeError" not in err
    return code, raw.getvalue().decode(encoding)


def _subprocess(tmp_path, issues, env: dict) -> subprocess.CompletedProcess:
    _files(tmp_path, issues)
    full = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8", "LC_ALL", "LANG", "LC_CTYPE", "WORKFLOW_ROLE")}
    full.update({"CLAUDE_PROJECT_DIR": str(tmp_path), "WORKFLOW_UPDATE_CHECK": "off", **env})
    return subprocess.run(
        [sys.executable, str(KIT / "scripts/workflow.py"), "ready", "--issues", "issues.json", "--prs", "prs.json"],
        cwd=tmp_path, env=full, capture_output=True, timeout=60,
    )


def test_a_waiting_ticket_under_ascii(monkeypatch, capsys, tmp_path):
    """The kit's own ` — ` before a waiting ticket's reasons is escaped."""
    code, out = _ready(monkeypatch, capsys, tmp_path, "ascii", [_ticket(1, "Notes list", body=WAITING)])
    assert code == 0
    assert out.splitlines() == ["wait  #1 [notes] Notes list \\u2014 " + UNKNOWN, "start now: nothing"]


def test_a_waiting_ticket_under_pythonioencoding_ascii_as_a_subprocess(tmp_path):
    r = _subprocess(tmp_path, [_ticket(1, "Notes list", body=WAITING)], {"PYTHONIOENCODING": "ascii"})
    assert b"Traceback" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode("ascii").splitlines() == ["wait  #1 [notes] Notes list \\u2014 " + UNKNOWN, "start now: nothing"]


def test_a_waiting_ticket_under_latin_1(monkeypatch, capsys, tmp_path):
    code, out = _ready(monkeypatch, capsys, tmp_path, "latin-1", [_ticket(1, "Café", body=WAITING)])
    assert code == 0
    assert "wait  #1 [notes] Café \\u2014 " + UNKNOWN in out.splitlines()


def test_an_emoji_title_under_cp1252(monkeypatch, capsys, tmp_path):
    code, out = _ready(monkeypatch, capsys, tmp_path, "cp1252", [_ticket(3, "emoji \U0001F600 ok")])
    assert code == 0
    assert out.splitlines() == ["READY #3 [notes] emoji \\U0001f600 ok", "start now: #3"]


def test_an_emoji_title_under_the_c_locale_as_a_subprocess(tmp_path):
    env = {"LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    r = _subprocess(tmp_path, [_ticket(3, "emoji \U0001F600 ok")], env)
    assert b"Traceback" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr
    assert "READY #3 [notes] emoji \\U0001f600 ok" in r.stdout.decode("ascii").splitlines()


def test_a_note_line_under_ascii(monkeypatch, capsys, tmp_path):
    """A `note:` line quoting a path from the ticket's body goes through the same print."""
    profile = '[project]\nname = "p"\nrepo = "o/r"\n\n[guard]\nprotected_paths = [".claude/**"]\n'
    body = "Area: notes\nChange `.claude/café\U0001F600.md` please"
    code, out = _ready(monkeypatch, capsys, tmp_path, "ascii", [_ticket(1, "Plain", body=body)], profile=profile)
    assert code == 0
    assert "      note: names protected path .claude/caf\\xe9\\U0001f600.md (.claude/**): check it isn't an owner task" in out.splitlines()


def test_a_lone_surrogate_is_still_its_escape_under_ascii(monkeypatch, capsys, tmp_path):
    issues = '[{"number": 1, "title": "bad \\ud800 title", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: x"}]'
    code, out = _ready(monkeypatch, capsys, tmp_path, "ascii", issues)
    assert code == 0
    assert "READY #1 [x] bad \\ud800 title" in out.splitlines()


def test_what_the_output_can_take_is_unchanged(monkeypatch, capsys, tmp_path):
    """Under UTF-8, every character is printed as itself; under cp1252, only
    the emoji is escaped, `é` and `—` written as themselves."""
    issues = [_ticket(1, "Café \U0001F600", body=WAITING)]
    code, out = _ready(monkeypatch, capsys, tmp_path, "utf-8", issues)
    assert code == 0
    assert "wait  #1 [notes] Café \U0001F600 — " + UNKNOWN in out.splitlines()
    code, out = _ready(monkeypatch, capsys, tmp_path, "cp1252", issues)
    assert code == 0
    assert "wait  #1 [notes] Café \\U0001f600 — " + UNKNOWN in out.splitlines()


def test_json_is_unchanged(monkeypatch, capsys, tmp_path):
    issues = [_ticket(1, "emoji \U0001F600 ok", body=WAITING), _ticket(2, "Café")]
    code, cp = _ready(monkeypatch, capsys, tmp_path, "ascii", issues, "--json")
    assert code == 0
    _, utf8 = _ready(monkeypatch, capsys, tmp_path, "utf-8", issues, "--json")
    assert cp == utf8
    data = json.loads(cp)
    assert data["not_ready"][0]["title"] == "emoji \U0001F600 ok"
    assert data["start_now"] == [2]


def test_the_changelog_notes_it_and_version_is_not_bumped():
    note = entry("#802, found in the review of #785's pull request")
    assert "`workflow ready --issues F --prs G`" in note
    assert "`cli._print_text`" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_ready_output_encoding.py" in note
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()

"""A file a command can't read is refused in one `workflow:` line, never a
traceback (#687, and #727: the same bug, with a folder given as the path).

`workflow briefing verify --file <path>` is the first command a ticket
session runs, and its output is quoted in the session's first comment. The
commands that read their input through `_read` in `scripts/workflow/cli.py`
(`_json` among them) refuse the same way, through the CLI.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from changelog_notes import entry

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def _cli(tmp_path, *args, close_stdin=False):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=tmp_path,
        env=env,
        preexec_fn=(lambda: os.close(0)) if close_stdin else None,
    )


def _one_refusal(p, *words):
    """The command refused in one `workflow:` line on standard error, naming
    the file and saying it can't be read, with nothing on standard output."""
    assert p.returncode != 0, p
    assert "Traceback" not in p.stderr, p.stderr
    lines = p.stderr.strip().splitlines()
    assert len(lines) == 1, p.stderr
    assert lines[0].startswith("workflow: can't read "), lines[0]
    for w in words:
        assert w in lines[0], lines[0]
    assert p.stdout == ""
    return lines[0]


def test_briefing_verify_refuses_a_missing_file_in_one_line(tmp_path):
    line = _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", ".workflow/briefing.md"))
    assert line == "workflow: can't read `.workflow/briefing.md`: No such file or directory"


def test_briefing_verify_refuses_an_absolute_path_that_doesnt_exist(tmp_path):
    _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", "/nonexistent.md"), "`/nonexistent.md`", "No such file or directory")


def test_briefing_verify_refuses_a_folder_given_as_the_file(tmp_path):
    """#727's case: a folder given as --file."""
    (tmp_path / "briefings").mkdir()
    line = _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", "briefings"))
    assert line == "workflow: can't read `briefings`: Is a directory"


def test_briefing_verify_refuses_a_file_that_isnt_utf8(tmp_path):
    (tmp_path / "briefing.md").write_bytes(b"Hello \xff\xfe\n\nBriefing 0123456789ab\n")
    line = _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", "briefing.md"))
    assert line == "workflow: can't read `briefing.md`: it isn't UTF-8 text"


def test_briefing_verify_refuses_closed_standard_input(tmp_path):
    line = _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", "-", close_stdin=True))
    assert line == "workflow: can't read standard input (-): it is closed"


def test_the_closed_standard_input_check_is_reads_alone():
    """`_read` checks for a closed standard input, and `_json_inputs` reads
    through it with no copy of that check (the architecture's "Reuse, not
    copies")."""
    import inspect

    from workflow import cli

    assert "sys.stdin is None" in inspect.getsource(cli._read)
    assert "sys.stdin" not in inspect.getsource(cli._json_inputs)


def _merge_check_why(p, flag):
    import json

    assert p.returncode == 0, p.stderr
    reasons = json.loads(p.stdout)["reasons"]
    return next(r["wording"]["developer"]["message"] for r in reasons if r["id"] == "couldnt_read" and r["input"] == flag)


def test_merge_check_words_a_closed_standard_input_as_before(tmp_path):
    p = _cli(tmp_path, "merge-check", "--json", "--pr", "-", close_stdin=True)
    assert _merge_check_why(p, "pr") == "Not yet: couldn't read the pull request (--pr): standard input (-) is closed."


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("charter", "estimate", "-", "--tickets", "3"), id="charter estimate"),
        pytest.param(("charter", "splice", "--body", "-", "--charter", "{c}"), id="charter splice --body"),
        pytest.param(("charter", "markdown", "{c}", "--estimate", "-"), id="charter markdown --estimate"),
    ],
)
def test_a_command_with_its_own_wording_says_standard_input_is_closed_plainly(tmp_path, args):
    """A command that words what `_read` raises itself (`str(e)`) says standard
    input is closed in plain words, never `[Errno None] ...`."""
    import json

    c = json.loads(_cli(tmp_path, "charter", "defaults").stdout)
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    (tmp_path / "charter.json").write_text(json.dumps(c))
    p = _cli(tmp_path, *(a.format(c="charter.json") for a in args), close_stdin=True)
    assert p.returncode == 1
    assert p.stderr == f"workflow charter {args[1]}: standard input (-) is closed\n", p.stderr


def test_a_path_with_a_line_break_stays_on_one_line(tmp_path):
    _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", "brief\ning.md"), "`brief\\ning.md`")


def test_a_path_with_a_backtick_is_quoted_escaped(tmp_path):
    _one_refusal(_cli(tmp_path, "briefing", "verify", "--file", "a`b.md"), "`a\\`b.md`")


def test_a_readable_briefing_still_verifies(tmp_path):
    from workflow import render

    (tmp_path / "briefing.md").write_text(render.seal("You are one ticket session."))
    p = _cli(tmp_path, "briefing", "verify", "--file", "briefing.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("Briefing ") and p.stdout.strip().endswith(" intact")


# The other commands that read a file through `_read` (or `_json`) without
# catching what it raises: each refuses the same way.
OTHERS = [
    pytest.param(("comments", "--owner", "someone", "--file", "{f}"), id="comments --file"),
    pytest.param(("charter", "validate", "{f}"), id="charter validate"),
    pytest.param(("charter", "reuse", "{f}"), id="charter reuse"),
    pytest.param(("state", "get", "--body", "{f}"), id="state get --body"),
    pytest.param(("ready", "--issues", "{f}", "--prs", "{f}"), id="ready --issues"),
    pytest.param(("status", "--issues", "{f}", "--prs", "{f}"), id="status --issues"),
]


@pytest.mark.parametrize("args", OTHERS)
@pytest.mark.parametrize("kind", ["missing", "folder"])
def test_other_commands_refuse_an_unreadable_file_the_same_way(tmp_path, args, kind):
    name = "input.json"
    if kind == "folder":
        (tmp_path / name).mkdir()
    p = _cli(tmp_path, *(a.format(f=name) for a in args))
    _one_refusal(p, f"`{name}`", "No such file or directory" if kind == "missing" else "Is a directory")


@pytest.mark.parametrize("kind", ["missing", "folder"])
def test_render_refuses_an_unreadable_ticket_file_the_same_way(tmp_path, kind):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n')
    for name in ("template.md", "charter.json", "slots.json"):
        (tmp_path / name).write_text("{}")
    if kind == "folder":
        (tmp_path / "ticket.json").mkdir()
    p = _cli(tmp_path, "render", "--template", "template.md", "--ticket", "ticket.json", "--charter", "charter.json", "--slots", "slots.json", "--tracking", "9")
    _one_refusal(p, "`ticket.json`", "No such file or directory" if kind == "missing" else "Is a directory")


def test_other_commands_refuse_a_file_that_isnt_utf8(tmp_path):
    (tmp_path / "charter.json").write_bytes(b'{"preset": "\xff"}')
    line = _one_refusal(_cli(tmp_path, "charter", "validate", "charter.json"))
    assert line == "workflow: can't read `charter.json`: it isn't UTF-8 text"


def test_a_command_with_its_own_wording_keeps_it(tmp_path):
    """`protection` words a file it can't read itself; what `_read` raises
    still gives it the reason it gave before."""
    p = _cli(tmp_path, "protection", "--rulesets", "missing.json", "--repo", "a/b", "--base", "main")
    assert p.returncode != 0
    assert p.stderr.strip() == "workflow protection: can't read the rulesets file missing.json: No such file or directory", p.stderr


def test_changelog_note_names_each_charter_file_that_keeps_its_own_wording():
    """`charter estimate`'s files, `charter markdown`'s --estimate and `charter
    splice`'s --body and --estimate word a file they can't read themselves:
    the note lists them with the commands that word it as before, never
    `charter` whole among those refused in one line."""
    note = entry("#687")
    opening, rest = note.split("\n\n", 1)
    assert "`charter`" not in opening, opening
    as_before = rest[rest.index("A command that already worded"):].split("\n")[0]
    for words in ("`charter estimate`", "`charter markdown`'s `--estimate`", "`charter splice`'s `--body` and `--estimate`"):
        assert words in as_before, as_before


def test_changelog_note_without_bumping_version():
    note = entry("#687")
    assert "#727" in note
    assert "briefing verify" in note
    text = (KIT / "CHANGELOG.md").read_text()
    released = text.split("\n## ")[2].split()[0].lstrip("v")
    assert (KIT / "VERSION").read_text().strip() == released

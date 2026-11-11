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

from changelog_notes import entry, released

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


def test_briefing_verify_refuses_standard_input_that_isnt_utf8(tmp_path):
    p = subprocess.run(
        [sys.executable, str(CLI), "briefing", "verify", "--file", "-"],
        input=b"Hi \xff there\n\nBriefing 0123456789ab\n",
        capture_output=True,
        cwd=tmp_path,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    line = _one_refusal(subprocess.CompletedProcess(p.args, p.returncode, p.stdout.decode(), p.stderr.decode()))
    assert line == "workflow: can't read standard input (-): it isn't UTF-8 text"


def test_standard_input_in_utf8_still_verifies(tmp_path):
    from workflow import render

    p = subprocess.run(
        [sys.executable, str(CLI), "briefing", "verify", "--file", "-"],
        input=render.seal("You are one ticket session, café.").encode("utf-8"),
        capture_output=True,
        cwd=tmp_path,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )
    assert p.returncode == 0, p.stderr
    assert p.stdout.decode().strip().endswith(" intact")


@pytest.mark.parametrize(
    "args",
    [
        pytest.param(("briefing", "verify", "--file", ""), id="briefing verify"),
        pytest.param(("comments", "--owner", "someone", "--file", ""), id="comments"),
    ],
)
def test_an_empty_path_is_refused_as_no_path_given(tmp_path, args):
    """An empty path is no file at all (`Path("")` is the folder `.`): it is
    refused before anything is read."""
    line = _one_refusal(_cli(tmp_path, *args))
    assert line == "workflow: can't read the file: no path was given"


def test_an_empty_path_in_a_command_with_its_own_wording(tmp_path):
    """merge-check words a file it can't read itself (`str(e)`): an empty path
    is no path given there too. (`charter` refuses an empty path before
    reading.)"""
    p = _cli(tmp_path, "merge-check", "--json", "--pr", "")
    assert _merge_check_why(p, "pr") == "Not yet: couldn't read the pull request (--pr): no path was given."


@pytest.mark.parametrize("flag, what", [("--rulesets", "rulesets"), ("--repo", "repository's settings")])
def test_protection_words_an_empty_path_from_reads_own_check(tmp_path, flag, what):
    """`protection` refuses an empty path in one line naming which file, in
    `_read`'s words: `_read`'s check is the only one (the architecture's
    "Reuse, not copies")."""
    import inspect

    from workflow import cli

    (tmp_path / "rulesets.json").write_text("[]")
    args = {"--rulesets": "rulesets.json", "--repo": "settings.json", flag: ""}
    p = _cli(tmp_path, "protection", *[x for k, v in args.items() for x in (k, v)], "--base", "main")
    assert p.returncode != 0 and p.stdout == ""
    assert p.stderr == f"workflow protection: can't read the {what} file: no path was given\n", p.stderr
    assert "not path" not in inspect.getsource(cli.cmd_protection)


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


@pytest.mark.parametrize("role", ["ticket", "conductor", "attended"])
def test_merge_check_words_a_charter_it_cant_read_as_the_note_says(tmp_path, monkeypatch, role):
    """`merge-check --charter` gives no `couldnt_read` reason: a `charter_refused`
    note in a ticket or conductor session, and the charter ignored in any other."""
    import json

    _fixtures(tmp_path)
    monkeypatch.setenv("WORKFLOW_ROLE", role)
    p = _cli(tmp_path, "merge-check", "--json", "--charter", "missing.json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert not [r for r in out["reasons"] if r.get("input") == "charter"], out["reasons"]
    notes = {n["id"]: n["message"] for n in out["notes"]}
    if role == "attended":
        assert "charter_refused" not in notes and "charter_ignored" in notes, notes
    else:
        assert notes["charter_refused"] == "The charter wasn't used, so no check is waived: couldn't read it: can't open missing.json: No such file or directory.", notes
    assert "`merge-check` (a `couldnt_read` reason; for `--charter`, a `charter_refused` note in a ticket or conductor session, the charter ignored in any other)" in entry(NOTE)


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



# The changelog note (#736, split out of #687): it names, for each file a
# command reads through `_read` (`_json` and `_json_inputs` among its readers),
# whether it now gives the one line or words the failure itself, as before.
NOTE = "#736, split out of #687"
COMMANDS = ("briefing", "comments", "render", "status", "ready", "charter", "state", "protection", "merge-check", "preview", "research")
ONE_LINE, OWN_WORDS = "one line", "own words"
# Each place `cli.py` calls a reader, by (function, the `a.action` it is under,
# reader, its argument): how it words a file it can't read, and the files the
# note names for it.
READS = {
    ("briefing", "cmd_briefing", None, "_read", "a.file"): (ONE_LINE, ["briefing verify"]),
    ("comments", "cmd_comments", None, "_read", "a.file"): (ONE_LINE, ["comments"]),
    ("render ticket", "cmd_render", None, "_json", "a.ticket"): (ONE_LINE, ["render"]),
    ("render charter", "cmd_render", None, "_json", "a.charter"): (ONE_LINE, ["render"]),
    ("render slots", "cmd_render", None, "_json", "a.slots"): (ONE_LINE, ["render"]),
    ("render template", "cmd_render", None, "_read", "a.template"): (ONE_LINE, ["render"]),
    ("status issues", "_status", None, "_json", "a.issues"): (ONE_LINE, ["status"]),
    ("status prs", "_status", None, "_json", "a.prs"): (ONE_LINE, ["status"]),
    ("ready issues", "cmd_ready", None, "_json", "a.issues"): (ONE_LINE, ["ready --issues"]),
    ("ready prs", "cmd_ready", None, "_json", "a.prs"): (ONE_LINE, ["ready --prs"]),
    ("ready permissions", "_note_unreviewed_specs", None, "_json_inputs", "argparse.Namespace(permissions=permissions_file)"): (OWN_WORDS, ["ready --permissions"]),
    ("charter reuse", "cmd_charter", "reuse", "_json", "a.file"): (ONE_LINE, ["charter reuse"]),
    ("charter pin-plan", "cmd_charter", "pin-plan", "_json", "a.file"): (ONE_LINE, ["charter pin-plan"]),
    ("charter validate", "cmd_charter", "validate", "_json", "a.file"): (ONE_LINE, ["charter validate"]),
    ("charter markdown file", "cmd_charter", "markdown", "_json", "a.file"): (ONE_LINE, ["charter markdown <file>"]),
    ("charter markdown estimate", "cmd_charter", "markdown", "_json", "a.estimate"): (OWN_WORDS, ["charter markdown --estimate"]),
    ("charter splice charter", "cmd_charter", "splice", "_json", "a.charter"): (ONE_LINE, ["charter splice --charter"]),
    ("charter splice estimate", "cmd_charter", "splice", "_json", "a.estimate"): (OWN_WORDS, ["charter splice --estimate"]),
    ("charter splice body", "cmd_charter", "splice", "_read", "a.body"): (OWN_WORDS, ["charter splice --body"]),
    ("charter diff old", "cmd_charter", "diff", "_json", "a.file"): (ONE_LINE, ["charter diff"]),
    ("charter diff new", "cmd_charter", "diff", "_json", "a.other"): (ONE_LINE, ["charter diff"]),
    ("charter estimate file", "_charter_estimate", None, "_json", "a.file"): (OWN_WORDS, ["charter estimate"]),
    ("charter estimate runs", "_charter_estimate", None, "_json", "a.runs"): (OWN_WORDS, ["charter estimate"]),
    ("state init charter", "cmd_state", "init", "_json", "a.charter"): (ONE_LINE, ["state init --charter"]),
    ("state body", "cmd_state", None, "_read", "a.body"): (ONE_LINE, ["state <action> --body"]),
    ("state put state", "cmd_state", "put", "_json", "a.state"): (ONE_LINE, ["state put --state"]),
    ("state patch patch", "cmd_state", None, "_json", "a.patch"): (ONE_LINE, ["state patch --patch"]),
    ("state join", "_state_join", None, "_json_inputs", "a"): (OWN_WORDS, ["state join --issues", "state join --permissions"]),
    ("protection", "cmd_protection", None, "_read", "path"): (OWN_WORDS, ["protection"]),
    ("merge-check", "cmd_merge_check", None, "_json_inputs", "a"): (OWN_WORDS, ["merge-check"]),
    ("preview", "cmd_preview", None, "_json_inputs", "a"): (OWN_WORDS, ["preview"]),
    ("research", "_research_records", None, "_json_inputs", "a"): (OWN_WORDS, ["research stakes", "research estimate"]),
}


def _reads_in_cli():
    """Each call of `_read`, `_json` or `_json_inputs` in `cli.py` outside the
    readers themselves: (function, `a.action`, reader, argument) -> whether a
    `try` around it in its function catches `OSError`."""
    import ast

    from workflow import cli

    readers = {"_read", "_json", "_json_inputs"}
    found = {}

    def catches(t: ast.Try) -> bool:
        for h in t.handlers:
            names = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
            if h.type is None or any(isinstance(n, ast.Name) and n.id in ("OSError", "Exception", "BaseException") for n in names):
                return True
        return False

    def action(test) -> str | None:
        if isinstance(test, ast.Compare) and ast.unparse(test.left) == "a.action" and isinstance(test.ops[0], ast.Eq):
            return test.comparators[0].value
        return None

    def walk(node, fn, act, caught):
        for child in ast.iter_child_nodes(node):
            a, c = act, caught
            if isinstance(node, ast.Try) and child in node.body:
                c = caught or catches(node)
            if isinstance(node, ast.If) and child in node.body and action(node.test):
                a = action(node.test)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id in readers:
                key = (fn, a, child.func.id, ast.unparse(child.args[0]))
                assert key not in found or found[key] == c, key
                found[key] = c
            walk(child, fn, a, c)

    tree = ast.parse(Path(cli.__file__).read_text())
    for f in tree.body:
        if isinstance(f, ast.FunctionDef) and f.name not in readers:
            walk(f, f.name, None, False)
    return found


def _note_lists():
    """The files the note lists under its one line and under their own words:
    the backticked items in each bullet that start with a command."""
    import re

    note = entry(NOTE)
    lists = {}
    for kind, start in ((ONE_LINE, "- **One line now:**"), (OWN_WORDS, "- **Their own words, as before:**")):
        line = next(l for l in note.splitlines() if l.startswith(start))
        spans = [s.strip() for _, s in re.findall(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", line)]  # Markdown's code spans
        lists[kind] = {w for w in spans if w.split()[0] in COMMANDS}
    return lists


def test_every_read_in_the_cli_is_in_the_notes_table():
    """A new place reading a file through `_read` fails here until the table,
    and so the note, says how it words a file it can't read."""
    found = _reads_in_cli()
    table = {k[1:]: kind for k, (kind, _) in READS.items()}
    assert set(found) == set(table), (set(found) ^ set(table))
    for key, caught in found.items():
        # `_json_inputs` words what it can't read itself, as the commands' own reasons.
        own = caught or key[2] == "_json_inputs"
        assert table[key] == (OWN_WORDS if own else ONE_LINE), key


def test_the_changelog_note_lists_each_file_where_it_belongs():
    """The note's two lists are exactly the table's: each file under how it
    words a file it can't read, and no command listed whole where some of its
    files word it the other way."""
    lists = _note_lists()
    for kind in (ONE_LINE, OWN_WORDS):
        want = {w for k, names in READS.values() if k == kind for w in names}
        assert lists[kind] == want, (kind, lists[kind] ^ want)
    assert not lists[ONE_LINE] & lists[OWN_WORDS]


def _fixtures(tmp_path):
    import json

    from workflow import state

    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n')
    c = json.loads(_cli(tmp_path, "charter", "defaults").stdout)
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    (tmp_path / "charter.json").write_text(json.dumps(c))
    (tmp_path / "empty.json").write_text("{}")
    (tmp_path / "list.json").write_text("[]")
    (tmp_path / "body.md").write_text("body\n")
    (tmp_path / "state.md").write_text(state.put("body\n", state.empty(c)))
    (tmp_path / "template.md").write_text("{{ briefing }}\n")


# Each file the note lists, run with a missing file (`M`): what it prints.
RUNS = {
    "briefing verify": ("briefing", "verify", "--file", "M"),
    "comments": ("comments", "--owner", "someone", "--file", "M"),
    "render": ("render", "--template", "template.md", "--ticket", "M", "--charter", "charter.json", "--slots", "empty.json", "--tracking", "9"),
    "status": ("status", "--issues", "M", "--prs", "list.json"),
    "ready --issues": ("ready", "--issues", "M", "--prs", "list.json"),
    "ready --prs": ("ready", "--issues", "list.json", "--prs", "M"),
    "charter reuse": ("charter", "reuse", "M"),
    "charter pin-plan": ("charter", "pin-plan", "M"),
    "charter validate": ("charter", "validate", "M"),
    "charter markdown <file>": ("charter", "markdown", "M"),
    "charter markdown --estimate": ("charter", "markdown", "charter.json", "--estimate", "M"),
    "charter splice --charter": ("charter", "splice", "--body", "body.md", "--charter", "M"),
    "charter splice --estimate": ("charter", "splice", "--body", "body.md", "--charter", "charter.json", "--estimate", "M"),
    "charter splice --body": ("charter", "splice", "--body", "M", "--charter", "charter.json"),
    "charter diff": ("charter", "diff", "charter.json", "M"),
    "charter estimate": ("charter", "estimate", "charter.json", "--tickets", "3", "--runs", "M"),
    "state init --charter": ("state", "init", "--charter", "M", "--run-id", "r"),
    "state <action> --body": ("state", "get", "--body", "M"),
    "state put --state": ("state", "put", "--body", "body.md", "--state", "M"),
    "state patch --patch": ("state", "patch", "--body", "state.md", "--patch", "M"),
    "state join --issues": ("state", "join", "--body", "state.md", "--out", "out.md", "--issues", "M", "--permissions", "empty.json"),
    "state join --permissions": ("state", "join", "--body", "state.md", "--out", "out.md", "--issues", "list.json", "--permissions", "M"),
    "protection": ("protection", "--base", "main", "--rulesets", "M"),
    "merge-check": ("merge-check", "--json", "--pr", "M"),
    "preview": ("preview", "--sha", "a" * 40, "--checks", "list.json", "--comments", "M"),
    "research stakes": ("research", "stakes", "--comments", "M", "--permissions", "empty.json"),
    "research estimate": ("research", "estimate", "--comments", "list.json", "--permissions", "M"),
    # `ready --permissions` is read only for a spec it must check: tests/test_ready_spec_note.py words it.
}


@pytest.mark.parametrize("name", sorted(RUNS))
def test_each_file_the_note_lists_words_a_missing_file_as_the_note_says(tmp_path, name):
    _fixtures(tmp_path)
    p = _cli(tmp_path, *(a.replace("M", "missing.json") if a == "M" else a for a in RUNS[name]))
    said = p.stderr + p.stdout
    assert "Traceback" not in said, said
    if name in _note_lists()[ONE_LINE]:
        _one_refusal(p, "`missing.json`", "No such file or directory")
    else:
        assert name in _note_lists()[OWN_WORDS], name
        assert "missing.json" in said and "No such file or directory" in said, said
        assert "can't read `missing.json`" not in said, said


def test_every_file_the_note_lists_is_run_but_ready_permissions():
    lists = _note_lists()
    assert set(RUNS) == (lists[ONE_LINE] | lists[OWN_WORDS]) - {"ready --permissions"}


def _stdin_cli(tmp_path, *args, data=None, closed=False):
    if closed:
        return _cli(tmp_path, *args, close_stdin=True)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        input=data,
        capture_output=True,
        cwd=tmp_path,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )


def _err(p) -> str:
    err = p.stderr.decode() if isinstance(p.stderr, bytes) else p.stderr
    return err.strip()


def test_the_note_says_what_the_one_line_gives_for_no_path_and_standard_input(tmp_path):
    note = entry(NOTE)
    for args in (("briefing", "verify", "--file"), ("comments", "--owner", "someone", "--file")):
        assert _err(_cli(tmp_path, *args, "")) == "workflow: can't read the file: no path was given"
        assert _err(_stdin_cli(tmp_path, *args, "-", closed=True)) == "workflow: can't read standard input (-): it is closed"
        assert _err(_stdin_cli(tmp_path, *args, "-", data=b"\xff\xfe")) == "workflow: can't read standard input (-): it isn't UTF-8 text"
    for line in ("workflow: can't read the file: no path was given", "workflow: can't read standard input (-): it is closed", "workflow: can't read standard input (-): it isn't UTF-8 text"):
        assert f"`{line}`" in note, line


@pytest.mark.parametrize(
    "args",
    [
        ("ready", "--prs", "list.json", "--issues"),
        ("status", "--prs", "list.json", "--issues"),
        ("charter", "validate"),
        ("charter", "splice", "--charter", "charter.json", "--body"),
        ("state", "get", "--body"),
        ("state", "join", "--body", "state.md", "--out", "out.md", "--permissions", "empty.json", "--issues"),
    ],
)
def test_the_commands_the_note_says_ask_for_an_empty_path_do(tmp_path, args):
    """The note: only `briefing verify`, `comments` and `render` read an empty
    path to refuse it; `ready`, `charter` and `state` ask for the file first
    (`state join` among them), and `status` asks when the other file is given."""
    _fixtures(tmp_path)
    p = _cli(tmp_path, *args, "")
    assert p.returncode != 0 and "no path was given" not in p.stderr and "Traceback" not in p.stderr, p.stderr
    note = entry(NOTE)
    assert "(`briefing verify`, `comments` and `render`; `ready`, `charter` and `state` ask for the file before reading it" in note
    assert "`status` counts an empty `--issues` or `--prs` as not given, asking for both only when the other is given)" in note


@pytest.mark.parametrize("args", [("status", "--issues", ""), ("status", "--issues", "", "--prs", "")])
def test_status_counts_an_empty_path_as_not_given_as_the_note_says(tmp_path, args):
    """With no other file given, `status` reads no file and asks for none."""
    p = _cli(tmp_path, *args)
    assert p.returncode == 0, p.stderr
    assert "Issues: not read" in p.stdout and p.stderr == "", p
    assert "`status` counts an empty `--issues` or `--prs` as not given" in entry(NOTE)


@pytest.mark.parametrize(
    "args, said",
    [
        (("ready", "--fetch", "--issues", ""), "--fetch needs a profile (project.repo)"),
        (("state", "join", "--body", "state.md", "--out", "out.md", "--fetch", "--issues", "", "--permissions", ""), "workflow: no profile at "),
    ],
)
def test_with_fetch_an_empty_path_counts_as_not_given_as_the_note_says(tmp_path, args, said):
    """With `--fetch`, `ready` and `state join` go to the fetch (here refused,
    as no profile names the repository), never asking for the empty file."""
    _fixtures(tmp_path)
    (tmp_path / ".claude/workflow/profile.toml").unlink()
    p = _cli(tmp_path, *args)
    assert p.returncode != 0 and p.stderr.startswith(said), p.stderr
    note = entry(NOTE)
    assert "except that `ready --fetch` reads neither `--issues` nor `--prs`" in note
    assert "`state join` asks for an empty `--issues` or `--permissions` before reading it, or with `--fetch` counts it as not given" in note


def test_the_note_says_what_protection_gives_for_no_path_and_standard_input(tmp_path):
    note = entry(NOTE)
    base = ("protection", "--base", "main", "--rulesets")
    said = {
        "empty": _err(_cli(tmp_path, *base, "")),
        "closed": _err(_stdin_cli(tmp_path, *base, "-", closed=True)),
        "binary": _err(_stdin_cli(tmp_path, *base, "-", data=b"\xff\xfe")),
    }
    assert said["empty"] == "workflow protection: can't read the rulesets file: no path was given"
    assert said["closed"] == "workflow protection: the rulesets file is standard input (-), and standard input is closed"
    assert said["binary"].startswith("workflow protection: the rulesets file - isn't JSON ('utf-8' codec can't decode"), said["binary"]
    for words in ("`workflow protection: can't read the <what> file: no path was given`", "`workflow protection: the <what> file is standard input (-), and standard input is closed`", "`workflow protection: the <what> file - isn't JSON (<the decode error>)`"):
        assert words in note, words


@pytest.mark.parametrize(
    "args",
    [
        ("charter", "estimate", "charter.json", "--tickets", "3", "--runs"),
        ("charter", "markdown", "charter.json", "--estimate"),
        ("charter", "splice", "--charter", "charter.json", "--body", "body.md", "--estimate"),
        ("charter", "splice", "--charter", "charter.json", "--body"),
    ],
)
def test_the_note_says_what_the_charter_files_with_their_own_words_give(tmp_path, args):
    _fixtures(tmp_path)
    action = args[1]
    closed = _err(_stdin_cli(tmp_path, *args, "-", closed=True))
    binary = _err(_stdin_cli(tmp_path, *args, "-", data=b"\xff\xfe"))
    assert closed == f"workflow charter {action}: standard input (-) is closed", closed
    assert binary.startswith(f"workflow charter {action}: 'utf-8' codec can't decode"), binary
    empty = _cli(tmp_path, *args, "")
    assert "no path was given" not in empty.stderr and "Traceback" not in empty.stderr, empty.stderr
    note = entry(NOTE)
    for words in ("`workflow charter <action>: standard input (-) is closed`", "`workflow charter <action>: 'utf-8' codec can't decode byte …`", "an empty `--estimate` or `--runs` counts as not given"):
        assert words in note, words


@pytest.mark.parametrize(
    "args, shown",
    [
        (("research", "stakes", "--permissions", "empty.json", "--comments"), "workflow research stakes: --comments: {}"),
        (("preview", "--sha", "a" * 40, "--checks", "list.json", "--comments"), "workflow preview: couldn't read --comments: {}"),
        (("state", "join", "--body", "state.md", "--out", "out.md", "--permissions", "empty.json", "--issues"), "workflow: --issues: {}"),
    ],
)
def test_the_note_says_what_the_json_inputs_files_give(tmp_path, args, shown):
    _fixtures(tmp_path)
    assert _err(_stdin_cli(tmp_path, *args, "-", closed=True)) == shown.format("standard input (-) is closed")
    assert _err(_stdin_cli(tmp_path, *args, "-", data=b"\xff\xfe")) == shown.format("- isn't UTF-8 text")
    if args[0] != "state":
        assert _err(_cli(tmp_path, *args, "")) == shown.format("no path was given")
    note = entry(NOTE)
    for words in ("`no path was given`", "`standard input (-) is closed`", "`- isn't UTF-8 text`", "`--permissions was given no file`"):
        assert words in note, words


def test_changelog_note_without_bumping_version():
    note = entry(NOTE)
    assert "#727" in note and "briefing verify" in note
    assert (KIT / "VERSION").read_text().strip() == released()


def test_the_released_version_comes_from_the_shared_helper():
    """The version under `## Unreleased` is read by `released` in
    `changelog_notes.py`, listed on its architecture page, never copied here
    (the architecture's "Reuse, not copies")."""
    import inspect

    import changelog_notes

    assert changelog_notes.released("# Changelog\n\n## Unreleased\n\nA note.\n\n## v0.2.0\n\nOne.\n\n## 0.1.9\n") == "0.2.0"
    source = inspect.getsource(test_changelog_note_without_bumping_version)
    assert "released()" in source and ".split(" not in source, source
    assert "- `released`: in `changelog_notes.py`" in (KIT / "docs/architecture/tests.md").read_text()

"""`workflow ready` and `workflow status` with `--issues -` and `--prs -`
both: standard input can be read only once, so the second flag is refused in
one line saying standard input (-) is already `--issues`'s, never "it is
empty" (#794), the words `ready` gives `--permissions` (#757). A single `-`,
for `--issues` or for `--prs`, still reads standard input. Run through
`cli.main`.
"""

import argparse
import io
import json
from pathlib import Path

import pytest

from changelog_notes import entry
from workflow import cli
from workflow import issues as issues_mod

ISSUES = [
    {"number": 10, "title": "Notes 10", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: notes"},
    {"number": 11, "title": "Notes 11", "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Area: shop"},
]
PRS = [{"number": 30, "title": "Notes list", "state": "open", "body": "Closes #11", "head": {"ref": "claude/build-11"}}]


def _env(monkeypatch, root):
    monkeypatch.chdir(root)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)
    (root / "issues.json").write_text(json.dumps(ISSUES), encoding="utf-8")
    (root / "prs.json").write_text(json.dumps(PRS), encoding="utf-8")


def _stdin(monkeypatch, text: str) -> io.TextIOWrapper:
    stdin = io.TextIOWrapper(io.BytesIO(text.encode("utf-8")), encoding="utf-8")
    monkeypatch.setattr("sys.stdin", stdin)
    return stdin


def _run(capsys, *args):
    code = cli.main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


# ---------- both `-`: refused ----------


@pytest.mark.parametrize("cmd", ["ready", "status"])
@pytest.mark.parametrize("extra", [(), ("--json",)])
def test_issues_and_prs_both_standard_input_is_refused_in_one_line(monkeypatch, capsys, tmp_path, cmd, extra):
    _env(monkeypatch, tmp_path)
    stdin = _stdin(monkeypatch, json.dumps(ISSUES))
    code, out, err = _run(capsys, cmd, "--issues", "-", "--prs", "-", *extra)
    assert code == 1
    assert out == ""
    assert "Traceback" not in err and "empty" not in err, err
    assert err.strip().splitlines() == [f"workflow {cmd}: --prs: standard input (-) is already --issues's: only one file can be read from it"]
    assert stdin.read() == json.dumps(ISSUES)  # refused before any of it is read


def test_ready_with_permissions_on_standard_input_too_is_refused_the_same_way(monkeypatch, capsys, tmp_path):
    _env(monkeypatch, tmp_path)
    _stdin(monkeypatch, json.dumps(ISSUES))
    code, out, err = _run(capsys, "ready", "--issues", "-", "--prs", "-", "--permissions", "-", "--json")
    assert (code, out) == (1, "")
    assert err.strip().splitlines() == ["workflow ready: --prs: standard input (-) is already --issues's: only one file can be read from it"]


# ---------- a single `-`: read as today ----------


@pytest.mark.parametrize("cmd", ["ready", "status"])
@pytest.mark.parametrize("flags", [("--issues", "-", "--prs", "prs.json"), ("--issues", "issues.json", "--prs", "-")])
def test_a_single_standard_input_is_read_as_its_file_is(monkeypatch, capsys, tmp_path, cmd, flags):
    _env(monkeypatch, tmp_path)
    from_files = _run(capsys, cmd, "--issues", "issues.json", "--prs", "prs.json", "--json")
    assert from_files[0] == 0, from_files[2]
    _stdin(monkeypatch, json.dumps(ISSUES if flags[1] == "-" else PRS))
    assert _run(capsys, cmd, *flags, "--json") == from_files


def test_ready_reads_the_tickets_from_standard_input(monkeypatch, capsys, tmp_path):
    """Not only alike: standard input's tickets are there."""
    _env(monkeypatch, tmp_path)
    _stdin(monkeypatch, json.dumps(ISSUES))
    code, out, err = _run(capsys, "ready", "--issues", "-", "--prs", "prs.json", "--json")
    assert code == 0, err
    got = json.loads(out)
    assert [v["number"] for v in got["ready"]] == [10]
    assert [v["number"] for v in got["not_ready"]] == [11]


# ---------- one helper words it ----------

TAKEN = "standard input (-) is already --issues's: only one file can be read from it"


def test_one_helper_gives_the_words_with_the_flag_or_without():
    assert cli._stdin_taken("prs", "issues") == f"--prs: {TAKEN}"
    assert cli._stdin_taken(None, "comments") == TAKEN.replace("--issues's", "--comments's")


def test_the_words_are_written_once_in_cli():
    source = Path(cli.__file__).read_text(encoding="utf-8")
    assert source.count("only one file can be read from it") == 1


def test_each_refusal_of_a_second_standard_input_words_it_through_the_helper(monkeypatch):
    """`ready` and `status`'s line, `_json_inputs`' reason (merge-check and
    the rest) and `ready`'s `--permissions` note: a rewording of the helper
    reaches all three."""
    monkeypatch.setattr(cli, "_stdin_taken", lambda flag, owner: f"taken {flag} {owner}")
    assert cli._stdin_taken_line("ready", "-", "-") == "workflow ready: taken prs issues"
    _stdin(monkeypatch, "[]")
    inputs = cli._json_inputs(argparse.Namespace(comments="-", checks="-"), ["comments", "checks"])
    assert inputs["checks"] == (None, "taken None comments")
    told = []

    def note(verdicts, issues, repo, comments, permissions, pull_numbers):
        with pytest.raises(issues_mod.SpecReviewsUnread) as e:
            permissions(["owner"])
        told.append(str(e.value))

    monkeypatch.setattr(cli.issues_mod, "note_unreviewed_specs", note)
    cli._note_unreviewed_specs([], [], [], "acme/demo", "-", "prs")
    assert told == ["taken permissions prs"]


# ---------- the changelog note ----------


def test_the_changelog_note_gives_the_refusal_and_keeps_version():
    note = entry("#794, found in the review of #779's pull request")
    assert "standard input (-) is already --issues's: only one file can be read from it" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_issues_prs_one_stdin.py" in note

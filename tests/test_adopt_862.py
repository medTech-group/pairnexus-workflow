"""#862: a security problem in terminal output. Its details stay with the
owner; ordinary output reads as before.

Seam: the command through the CLI in a subprocess, on a copy of the starter
built with Python."""

import os
import subprocess
import sys
from pathlib import Path

from changelog_notes import entry, released, since_0110
from test_adopt import CLI, _run, _starter

KIT = Path(__file__).resolve().parents[1]


def _adopt(root: Path):
    return subprocess.run(
        [sys.executable, "-B", str(CLI), "adopt", "--owner=ada", "--repo=ada/my-notes", "--name=My Notes!", f"--project={root}"],
        capture_output=True, text=True, cwd=root.parent, env={**os.environ, "CLAUDE_PROJECT_DIR": str(root.parent)},
    )


def test_case_one_is_one_escaped_line(tmp_path):
    root = tmp_path / "p\x1b[31m\nX"
    root.mkdir()
    p = _adopt(root)
    assert p.returncode == 1
    assert "\x1b" not in p.stderr and p.stderr.count("\n") == 1
    assert p.stderr.startswith("workflow adopt: no profile at ")
    assert "p\\u001b[31m\\nX/.claude/workflow/profile.toml" in p.stderr


def test_case_one_reads_as_before_for_an_ordinary_project(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    p = _adopt(root)
    assert p.returncode == 1
    assert p.stderr == f"workflow adopt: no profile at {root.resolve()}/.claude/workflow/profile.toml: run this in a copy of the starter\n"


def test_case_two_is_one_escaped_line(tmp_path):
    copy = _starter(tmp_path / "copy")
    (copy / "wrangler.toml").write_text('name = """old‮"""\n', encoding="utf-8")
    p = _run(copy)
    assert p.returncode == 1 and "can't rewrite line by line" in p.stderr
    assert "‮" not in p.stderr and "old\\u202e" in p.stderr and p.stderr.count("\n") == 1


def test_the_note_and_this_file_name_the_area_only():
    note = entry("#862, found in the review of #824's pull request")
    for text in (note, __doc__):
        assert "workflow adopt" not in text and "whatever" not in text


def test_the_area_only_test_reads_the_note_with_the_shared_helper():
    """The overview's "Reuse, not copies": the test above finds #862's note
    with `changelog_notes.entry`, not a copy of its lookup."""
    import inspect

    src = inspect.getsource(test_the_note_and_this_file_name_the_area_only)
    assert "entry(" in src and ".index(" not in src


def test_changelog_notes_it_under_unreleased():
    (line,) = [line for line in since_0110().splitlines() if "(#862" in line]
    assert line.startswith("**A security problem in terminal output")
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()

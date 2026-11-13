"""#859: a security problem in the guard.

Where python3 is missing or failing, the guard's shell fallback (`fallback.sh`)
reads the profile only when it is a file, else as an empty profile; an
ordinary profile reads as before.

Seam: the guard's hook command (`vendor.hook_command`) run by `sh`, an event
on stdin, each run in a subprocess with a `timeout`."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_guard_no_python import _kit_at, _path
from workflow import vendor

KIT = Path(__file__).resolve().parents[1]
PROFILE = Path(".claude/workflow/profile.toml")
SECONDS = 20

LS = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
PUSH = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git push origin x"}}


def _shape_1(proj, tmp_path):
    os.mkfifo(proj / PROFILE)


def _shape_2(proj, tmp_path):
    target = tmp_path / "elsewhere"
    os.mkfifo(target)
    os.symlink(target, proj / PROFILE)


def _shape_3(proj, tmp_path):
    (proj / PROFILE).mkdir()


def _shape_4(proj, tmp_path):
    os.symlink(os.devnull, proj / PROFILE)


MAKES = [
    pytest.param(_shape_1, id="shape-1"), pytest.param(_shape_2, id="shape-2"),
    pytest.param(_shape_3, id="shape-3"), pytest.param(_shape_4, id="shape-4"),
]
KINDS = ("missing", "failing")


class Project:
    def __init__(self, tmp_path, kind, layout="vendored"):
        self.layout = layout
        self.proj = tmp_path / "proj"
        (self.proj / PROFILE).parent.mkdir(parents=True)
        self.plugin = tmp_path / "plugin"
        if layout == "vendored":
            _kit_at(self.proj / vendor.HOOK_TAG)
        else:
            _kit_at(self.plugin / "scripts/workflow.py")
        self.path = _path(tmp_path, kind)

    def guard(self, event, role=None):
        """The hook's decision, or None when it prints nothing."""
        env = {"PATH": self.path, "CLAUDE_PROJECT_DIR": str(self.proj), "CLAUDE_PLUGIN_ROOT": str(self.plugin)}
        if role is not None:
            env["WORKFLOW_ROLE"] = role
        p = subprocess.run(
            [shutil.which("sh"), "-c", vendor.hook_command("guard", plugin=self.layout == "plugin")],
            input=json.dumps(event), capture_output=True, text=True, env=env, cwd=self.proj, timeout=SECONDS,
        )
        assert p.returncode == 0, (p.returncode, p.stderr)
        if not p.stdout.strip():
            return None
        out = json.loads(p.stdout)["hookSpecificOutput"]
        assert out["permissionDecisionReason"]
        return out["permissionDecision"]


# ---------- a profile that isn't a regular file ----------


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("layout", ["vendored", "plugin"])
@pytest.mark.parametrize("make", MAKES)
def test_an_attended_push_is_asked(tmp_path, make, layout, kind):
    p = Project(tmp_path, kind, layout)
    make(p.proj, tmp_path)
    for role in (None, "attended"):
        assert p.guard(PUSH, role) == "ask", role
        assert p.guard(LS, role) is None, role


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("make", MAKES)
def test_a_role_the_kit_doesnt_know_is_refused_every_tool(tmp_path, make, kind):
    """Refused as with no profile."""
    p = Project(tmp_path, kind)
    make(p.proj, tmp_path)
    for event in (LS, PUSH):
        assert p.guard(event, "tickte") == "deny", event


# ---------- an ordinary profile ----------


@pytest.mark.parametrize("kind", KINDS)
def test_an_ordinary_profile_still_decides_as_before(tmp_path, kind):
    p = Project(tmp_path, kind)
    (p.proj / PROFILE).write_text("[repo]\nruleset = false\n", encoding="utf-8")
    assert p.guard(PUSH) == "deny"
    assert p.guard(LS, "tickte") == "deny"
    (p.proj / PROFILE).write_text('[repo]\nruleset = true\n\n[guard]\ncode_writers = "ticket"\n', encoding="utf-8")
    assert p.guard(PUSH) == "ask"
    assert p.guard(PUSH, "tickte") == "ask"
    assert p.guard(LS, "tickte") is None


@pytest.mark.parametrize("kind", KINDS)
def test_a_symlink_to_an_ordinary_profile_reads_as_before(tmp_path, kind):
    p = Project(tmp_path, kind)
    real = tmp_path / "real.toml"
    real.write_text('[repo]\nruleset = false\n\n[guard]\ncode_writers = "ticket"\n', encoding="utf-8")
    os.symlink(real, p.proj / PROFILE)
    assert p.guard(PUSH) == "deny"
    assert p.guard(LS, "tickte") is None
    assert p.guard(PUSH, "tickte") == "deny"


# ---------- the notes ----------

WHAT_IT_DOES = "only when it is a file, else as an empty profile"


def _words(text):
    """`text` on one line: comment marks and line breaks left out."""
    return " ".join(" ".join(line.strip().lstrip("#").split()) for line in text.splitlines()).strip()


def test_the_notes_say_what_the_fix_does():
    """The fallback's comment on the fix, its line on the architecture page and
    this file's docstring say what the fix does, in `_open_file`'s words."""
    page = (KIT / "docs/architecture/scripts--workflow.md").read_text(encoding="utf-8")
    (line,) = [line for line in page.splitlines() if line.startswith("- `fallback.sh`:")]
    script = (KIT / "scripts/workflow/fallback.sh").read_text(encoding="utf-8").splitlines()
    at = script.index('[ -f "$PROFILE_TOML" ] || PROFILE_TOML=/dev/null')
    start = at
    while script[start - 1].startswith("#"):
        start -= 1
    comment = "\n".join(script[start:at])
    for text in (line, comment, __doc__):
        assert WHAT_IT_DOES in _words(text), text


# ---------- the changelog ----------


def test_changelog_notes_it_under_unreleased():
    (line,) = [line for line in since_0110().splitlines() if "(#859" in line]
    assert line.lower().startswith("**a security problem in the guard"), line

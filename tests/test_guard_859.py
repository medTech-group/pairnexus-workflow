"""#859: a security problem in the guard.

Where python3 is missing or failing, the guard's shell fallback (`fallback.sh`)
reads the profile only when it is a file, else as an empty profile; an
ordinary profile reads as before.

Seam: the guard's hook command run by `sh` (`test_guard_no_python.Setup`), an
event on stdin, each run in a subprocess with a `timeout`."""

import os
from pathlib import Path

import pytest

from changelog_notes import since_0110
from test_guard_833 import MAKES
from test_guard_no_python import Setup, _bash, _decision

KIT = Path(__file__).resolve().parents[1]
PROFILE = Path(".claude/workflow/profile.toml")
SECONDS = 20

LS = _bash("ls")
PUSH = _bash("git push origin x")
KINDS = ("missing", "failing")


def _setup(tmp_path, kind, layout="vendored"):
    """`Setup`'s project with its profile's folder, and no role set."""
    s = Setup(tmp_path, layout, kind)
    (s.proj / PROFILE).parent.mkdir(parents=True, exist_ok=True)
    del s.env["WORKFLOW_ROLE"]
    return s


def _guard(s, event, role=None):
    """The hook's decision, or None when it prints nothing; no role set when `role` is None."""
    return _decision(s.run("guard", event, timeout=SECONDS, **({} if role is None else {"WORKFLOW_ROLE": role})))


# ---------- a profile that isn't a regular file ----------


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("layout", ["vendored", "plugin"])
@pytest.mark.parametrize("make", MAKES)
def test_an_attended_push_is_asked(tmp_path, make, layout, kind):
    p = _setup(tmp_path, kind, layout)
    make(p.proj, tmp_path)
    for role in (None, "attended"):
        assert _guard(p, PUSH, role) == "ask", role
        assert _guard(p, LS, role) is None, role


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("make", MAKES)
def test_a_role_the_kit_doesnt_know_is_refused_every_tool(tmp_path, make, kind):
    """Refused as with no profile."""
    p = _setup(tmp_path, kind)
    make(p.proj, tmp_path)
    for event in (LS, PUSH):
        assert _guard(p, event, "tickte") == "deny", event


# ---------- an ordinary profile ----------


@pytest.mark.parametrize("kind", KINDS)
def test_an_ordinary_profile_still_decides_as_before(tmp_path, kind):
    p = _setup(tmp_path, kind)
    (p.proj / PROFILE).write_text("[repo]\nruleset = false\n", encoding="utf-8")
    assert _guard(p, PUSH) == "deny"
    assert _guard(p, LS, "tickte") == "deny"
    (p.proj / PROFILE).write_text('[repo]\nruleset = true\n\n[guard]\ncode_writers = "ticket"\n', encoding="utf-8")
    assert _guard(p, PUSH) == "ask"
    assert _guard(p, PUSH, "tickte") == "ask"
    assert _guard(p, LS, "tickte") is None


@pytest.mark.parametrize("kind", KINDS)
def test_a_symlink_to_an_ordinary_profile_reads_as_before(tmp_path, kind):
    p = _setup(tmp_path, kind)
    real = tmp_path / "real.toml"
    real.write_text('[repo]\nruleset = false\n\n[guard]\ncode_writers = "ticket"\n', encoding="utf-8")
    os.symlink(real, p.proj / PROFILE)
    assert _guard(p, PUSH) == "deny"
    assert _guard(p, LS, "tickte") is None
    assert _guard(p, PUSH, "tickte") == "deny"


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

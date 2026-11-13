"""#856: a security problem in terminal output. Its details stay with the owner.

Seam: the command through `cli.main`."""

import json

import pytest

from workflow import cli
from workflow.profile import PROFILE_PATH

ESC, NL = chr(0x1B), chr(0x0A)
ODD_TOML = "u\\u001b[31m\\nNEXT"
ODD_SHOWN = "u\\u001b[31m\\nNEXT"
ODD = f"u{ESC}[31m{NL}NEXT"
HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "someone"\n'


def _check(root, monkeypatch, capsys, more):
    (root / PROFILE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / PROFILE_PATH).write_text(HEAD + more, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    capsys.readouterr()
    assert cli.main(["profile", "check"]) == 0
    return capsys.readouterr()


def _warnings(err):
    lines = err.splitlines()
    assert all(ln.startswith("warning: ") for ln in lines), lines
    return [ln[len("warning: "):] for ln in lines]


@pytest.mark.parametrize(
    "more, said",
    [
        pytest.param(
            f'[[commands.suite]]\nname = "{ODD_TOML}"\nrun = "true {{files}}"\nfiles = "nomatch/*.py"\n',
            f"commands.suite {ODD_SHOWN}: files glob 'nomatch/*.py' matches no file (globs are relative to the project root)",
            id="suite",
        ),
        pytest.param(
            f'[[commands.package]]\nname = "{ODD_TOML}"\npath = "nomatch/**"\ntypecheck = "true"\n',
            f"commands.package {ODD_SHOWN}: path 'nomatch/**' matches no file (relative to the project root)",
            id="package",
        ),
        pytest.param(
            f'[areas]\n"{ODD_TOML}" = ["nomatch/**"]\n',
            f"areas.{ODD_SHOWN}: glob 'nomatch/**' matches no file",
            id="area",
        ),
        pytest.param(
            f'flow_addendum = "{ODD_TOML}"\n',
            f"project.flow_addendum: {ODD_SHOWN} doesn't exist",
            id="flow-addendum",
        ),
        pytest.param(
            f'rules = ["{ODD_TOML}"]\n',
            f"project.rules: {ODD_SHOWN} doesn't exist (from {ODD!r})",
            id="rules",
        ),
    ],
)
def test_a_warning_from_the_profiles_text_stays_on_one_line(tmp_path, monkeypatch, capsys, more, said):
    out, err = _check(tmp_path, monkeypatch, capsys, more)
    assert ESC not in err
    assert said in _warnings(err)
    assert all(c.isprintable() for w in _warnings(err) for c in w)
    assert ESC not in out
    assert said.replace(ODD_SHOWN, ODD) in json.loads(out)["warnings"]


def test_ordinary_warnings_are_unchanged(tmp_path, monkeypatch, capsys):
    more = '[[commands.suite]]\nname = "unit"\nrun = "true {files}"\nfiles = "nomatch/*.py"\n'
    out, err = _check(tmp_path, monkeypatch, capsys, more)
    warned = _warnings(err)
    assert "commands.suite unit: files glob 'nomatch/*.py' matches no file (globs are relative to the project root)" in warned
    assert warned == json.loads(out)["warnings"]

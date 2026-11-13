"""#824: a profile error shows the profile's own text escaped.

A `ProfileError` can quote text from `.claude/workflow/profile.toml` (a
table's name, a suite's or a package's name). It holds its message with
every character `issues.escape_unprintable` escapes written as JSON escapes
it (`\\n`, `\\u001b`), so `workflow profile check`, `workflow ready --fetch`
and `workflow doctor` each show such a name on the one line they give it.
Seams: `profile.parse` and `ProfileError`, each command through `cli.main`,
and doctor's `kit.profile` line."""

import json
import tomllib

import pytest

from changelog_notes import released, since_0110
from test_doctor import _doctor, _entries, _line, _project
from test_status_local_gaps import _status
from workflow import cli, issues, profile
from workflow.profile import PROFILE_PATH, ProfileError

from pathlib import Path

KIT = Path(__file__).resolve().parents[1]

ESC, NL = chr(0x1B), chr(0x0A)
# The table's name as TOML writes it, and as the message shows it.
ODD_TOML = '"a\\nb\\u001b[31mred"'
ODD_SHOWN = "a\\nb\\u001b[31mred"
ALLOWED = "allowed: [areas], [ci], [commands], [guard], [previews], [project], [release], [repair], [run], [sensitive], [ui]"
HEAD = '[project]\nname = "demo"\nrepo = "acme/demo"\n'


def _profile(root, more):
    (root / PROFILE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / PROFILE_PATH).write_text(HEAD + more, encoding="utf-8")


def _odd(root):
    _profile(root, f"\n[{ODD_TOML}]\nx = 1\n")


def _parse(text, tmp_path):
    return profile.parse(tomllib.loads(text), tmp_path)


def _plain(text):
    """No character a terminal would act on, or that couldn't be told apart."""
    return all(c.isprintable() or c == NL for c in text) and ESC not in text


# ---------- profile.parse and ProfileError ----------


def test_an_unknown_tables_name_is_shown_escaped(tmp_path):
    with pytest.raises(ProfileError) as e:
        _parse(HEAD + f"\n[{ODD_TOML}]\nx = 1\n", tmp_path)
    assert str(e.value) == f"unknown table [{ODD_SHOWN}]; {ALLOWED}"
    assert e.value.args == (str(e.value),)


def test_an_ordinary_unknown_tables_line_is_unchanged(tmp_path):
    with pytest.raises(ProfileError) as e:
        _parse(HEAD + "\n[area]\nx = 1\n", tmp_path)
    assert str(e.value) == f"unknown table [area]; {ALLOWED}"


@pytest.mark.parametrize(
    "more, said",
    [
        pytest.param(
            '[[commands.suite]]\nname = "u\\u001bx"\nrun = "pytest"\nfiles = "tests/*.py"\n',
            "commands.suite[0] (u\\u001bx): files is set but run has no {files}",
            id="suite-name",
        ),
        pytest.param(
            '[[commands.package]]\nname = "w\\u202eb"\npath = "web/**"\n',
            "commands.package[0] (w\\u202eb): give typecheck, test_file or both",
            id="package-name",
        ),
    ],
)
def test_other_names_from_the_profile_are_shown_escaped(tmp_path, more, said):
    with pytest.raises(ProfileError) as e:
        _parse(HEAD + more, tmp_path)
    assert str(e.value).startswith(said)
    assert _plain(str(e.value)) and NL not in str(e.value)


def test_any_message_is_held_through_the_kits_escape():
    text = f"x{NL}y{ESC}[0m{chr(0x200B)}z {chr(0xE9)}"
    assert str(ProfileError(text)) == issues.escape_unprintable(text) == "x\\ny\\u001b[0m\\u200bz " + chr(0xE9)


def test_escaping_again_changes_nothing():
    """A caller that passes an error's words on with its own context after
    them (`…, so the charter change can't be checked`) keeps them as they were."""
    first = ProfileError(f"unknown table [a{NL}b]")
    assert str(ProfileError(f"{first}, so it can't be checked")) == "unknown table [a\\nb], so it can't be checked"


# ---------- the commands, through cli.main ----------


@pytest.mark.parametrize("argv", [["profile", "check"], ["ready", "--fetch"], ["ready", "--fetch", "--json"]])
def test_each_command_gives_one_line_with_the_name_escaped(tmp_path, monkeypatch, capsys, argv):
    _odd(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "_fetch", lambda *a, **kw: pytest.fail("read GitHub with a profile that has an error"))
    capsys.readouterr()
    assert cli.main(argv) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"workflow: unknown table [{ODD_SHOWN}]; {ALLOWED}\n"


def test_profile_check_keeps_an_ordinary_unknown_tables_line(tmp_path, monkeypatch, capsys):
    _profile(tmp_path, "\n[area]\nx = 1\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    capsys.readouterr()
    assert cli.main(["profile", "check"]) == 1
    assert capsys.readouterr().err == f"workflow: unknown table [area]; {ALLOWED}\n"


# ---------- doctor and status ----------


def test_doctors_profile_line_shows_the_name_escaped(tmp_path):
    root = _project(tmp_path, profile=None)
    _odd(root)
    line = _line(tmp_path, root, "kit.profile")
    assert line["status"] == "gap"
    assert line["message"] == (
        f"The kit's profile ({PROFILE_PATH}, its settings for this project) has a mistake, "
        f"so the kit can't use it: unknown table [{ODD_SHOWN}]; {ALLOWED}."
    )


def test_doctors_text_shows_the_name_escaped(tmp_path):
    root = _project(tmp_path, profile=None)
    _odd(root)
    p = _doctor(tmp_path, root)
    assert p.returncode == 0, p.stderr
    assert _plain(p.stdout)
    entry = next(e for e in _entries(p.stdout) if "unknown table" in e)
    assert f"unknown table [{ODD_SHOWN}];" in entry


def test_status_shows_the_name_escaped(tmp_path):
    root = _project(tmp_path, profile=None)
    _odd(root)
    text = _status(tmp_path, root, "--json")
    assert _plain(text)
    gaps = {g["id"]: g for g in json.loads(text)["local_gaps"]}
    assert f"unknown table [{ODD_SHOWN}];" in gaps["kit.profile"]["message"]


# ---------- the changelog ----------


def test_the_changelog_notes_it_under_unreleased_and_version_is_kept():
    assert "(#824, " in since_0110()
    assert (KIT / "VERSION").read_text(encoding="utf-8").strip() == released()

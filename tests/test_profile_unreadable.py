"""#829: a profile that isn't UTF-8, or isn't a file, is refused in one line.

`profile.load` turns a `.claude/workflow/profile.toml` holding a byte that
isn't UTF-8, or one that is a directory, into a `ProfileError` with the
wording `cli._read_profile` already gives `workflow status` and `workflow
doctor`. So `workflow profile check`, `workflow ready --fetch` and `workflow
state join --fetch` print one `workflow: …` line and exit 1, never a
traceback. Seams: `profile.load`, and each command through `cli.main`."""

import json

import pytest

from changelog_notes import since_0110
from test_doctor import _line, _project
from test_status_local_gaps import _status
from workflow import charter, cli, profile, state
from workflow.profile import PROFILE_PATH, ProfileError

NOT_UTF8 = f"{PROFILE_PATH} isn't UTF-8 text"
NOT_A_FILE = f"{PROFILE_PATH} isn't a file"


def _not_utf8(root):
    (root / PROFILE_PATH).parent.mkdir(parents=True, exist_ok=True)
    (root / PROFILE_PATH).write_bytes(b'[project]\nname = "demo"\nrepo = "acme/d\xffmo"\nbase_branch = "main"\n')


def _a_directory(root):
    (root / PROFILE_PATH).mkdir(parents=True)


CASES = [pytest.param(_not_utf8, NOT_UTF8, id="not-utf8"), pytest.param(_a_directory, NOT_A_FILE, id="a-directory")]


# ---------- profile.load ----------


@pytest.mark.parametrize("make, said", CASES)
@pytest.mark.parametrize("required", [True, False])
def test_load_refuses_it_with_read_profiles_wording(tmp_path, make, said, required):
    make(tmp_path)
    with pytest.raises(ProfileError) as e:
        profile.load(tmp_path, required=required)
    assert str(e.value) == said
    assert str(tmp_path) not in str(e.value)


def test_load_refuses_a_profile_it_cant_open(tmp_path, monkeypatch):
    _not_utf8(tmp_path)

    def denied(self, *a, **kw):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(type(tmp_path), "read_text", denied)
    with pytest.raises(ProfileError) as e:
        profile.load(tmp_path)
    assert str(e.value) == f"{PROFILE_PATH} can't be read (PermissionError)"


def test_load_still_reads_a_good_profile_and_reports_a_missing_one(tmp_path):
    assert profile.load(tmp_path, required=False) is None
    with pytest.raises(ProfileError, match="no profile at"):
        profile.load(tmp_path)
    (tmp_path / PROFILE_PATH).parent.mkdir(parents=True)
    (tmp_path / PROFILE_PATH).write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nbase_branch = "main"\n', encoding="utf-8")
    assert profile.load(tmp_path).repo == "acme/demo"


# ---------- the commands, through cli.main ----------


def _state_body(root):
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-13-unreadable"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    (root / "body.md").write_text(state.put("## Run\n", s), encoding="utf-8")
    return str(root / "body.md")


COMMANDS = [
    pytest.param(lambda root: ["profile", "check"], id="profile-check"),
    pytest.param(lambda root: ["ready", "--fetch"], id="ready-fetch"),
    pytest.param(lambda root: ["ready", "--fetch", "--json"], id="ready-fetch-json"),
    pytest.param(lambda root: ["state", "join", "--body", _state_body(root), "--fetch", "--out", str(root / "new.md")], id="state-join-fetch"),
]


@pytest.mark.parametrize("make, said", CASES)
@pytest.mark.parametrize("argv", COMMANDS)
def test_each_command_refuses_in_one_line(tmp_path, monkeypatch, capsys, make, said, argv):
    make(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "_fetch", lambda *a, **kw: pytest.fail("read GitHub with a profile it can't read"))
    args = argv(tmp_path)
    capsys.readouterr()
    assert cli.main(args) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err == f"workflow: {said}\n"
    assert "Traceback" not in err and str(tmp_path) not in err
    assert not (tmp_path / "new.md").exists()


# ---------- status and doctor keep their lines ----------


@pytest.mark.parametrize("make, said", CASES)
def test_doctor_keeps_its_profile_line(tmp_path, make, said):
    root = _project(tmp_path, profile=None)
    make(root)
    line = _line(tmp_path, root, "kit.profile")
    assert line["status"] == "gap"
    assert line["message"] == (
        f"The kit's profile ({PROFILE_PATH}, its settings for this project) has a mistake, so the kit can't use it: {said}."
    )


@pytest.mark.parametrize("make, said", CASES)
def test_status_keeps_its_profile_line(tmp_path, make, said):
    root = _project(tmp_path, profile=None)
    make(root)
    report = json.loads(_status(tmp_path, root, "--json"))
    assert report["profile_error"] is True
    gaps = {g["id"]: g for g in report["local_gaps"]}
    assert gaps["kit.profile"]["message"] == (
        f"The kit's profile ({PROFILE_PATH}, its settings for this project) has a mistake, so the kit can't use it: {said}."
    )
    assert "Kit: set up, but its profile has an error (kit.profile)" in _status(tmp_path, root)


# ---------- the changelog ----------


def test_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "#829" in notes

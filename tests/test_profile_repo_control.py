"""#821: the profile refuses a `project.repo` holding a NUL or any other
control character, in one line worded like "project.repo must be owner/repo",
so no command reaches `gh` with it (a NUL ended `workflow status --fetch` in
`ValueError: embedded null byte`). Through `cli.main`: `workflow profile
check` and `workflow status --fetch`, with the fake `gh` on the PATH.

The rest of #327's `owner/name` rule is #327's, not this ticket's.
"""

import pytest

import fake_gh
from changelog_notes import entry
from workflow import charter, cli, state
from workflow import profile as profile_mod

REFUSAL = "workflow: project.repo must be owner/repo, without control characters"

CONTROLS = pytest.mark.parametrize(
    "repo_toml",
    [
        '"acme/de\\u0000mo"',
        '"acme/de\\nmo"',
        '"acme/de\\rmo"',
        '"acme/de\\tmo"',
        '"acme/de\\u001bmo"',
        '"acme/de\\u007fmo"',
        '"acme/de\\u0085mo"',
        '"\\u0000acme/demo"',
    ],
    ids=["nul", "newline", "carriage-return", "tab", "escape", "delete", "c1-next-line", "nul-in-owner"],
)


def _project(monkeypatch, tmp_path, repo_toml: str = '"acme/demo"'):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(f'[project]\nname = "demo"\nrepo = {repo_toml}\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR", "WORKFLOW_ROLE"):
        monkeypatch.delenv(k, raising=False)


def _refused(capsys, *args) -> list[str]:
    """The command's refusal: exit non-zero, its lines on standard error,
    nothing on standard output, no traceback."""
    code = cli.main(list(args))
    out = capsys.readouterr()
    assert code != 0
    assert out.out == ""
    assert "Traceback" not in out.err
    return out.err.splitlines()


# ---------- the ticket's cases ----------


def _status_fetch(capsys) -> list[str]:
    """`workflow status --fetch` with any other profile error: it reads no
    issues, says why in one line on standard error and still prints its
    report, exit 0 (`test_status_local_gaps`'s
    `test_a_profile_error_with_fetch_reads_no_issues_and_says_why`)."""
    assert cli.main(["status", "--fetch"]) == 0
    out = capsys.readouterr()
    assert "Traceback" not in out.err
    assert "Kit: set up, but its profile has an error (kit.profile)" in out.out
    return out.err.splitlines()


def test_a_nul_in_the_repo_stops_status_fetch_in_one_line_before_gh(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path, '"acme/de\\u0000mo"')
    gh = fake_gh.install(tmp_path, monkeypatch, {})
    assert _refused(capsys, "status", "--fetch") == [REFUSAL]
    assert gh.calls() == []


def test_another_profile_error_still_lets_status_fetch_print_its_report(monkeypatch, capsys, tmp_path):
    """Only the control-character refusal stops `status --fetch`: a repo
    without its `/` is still a profile error the report shows, exit 0."""
    _project(monkeypatch, tmp_path, '"acme"')
    gh = fake_gh.install(tmp_path, monkeypatch, {})
    lines = _status_fetch(capsys)
    assert len(lines) == 1 and lines[0].startswith("workflow status: the kit's profile has an error")
    assert gh.calls() == []


@CONTROLS
def test_profile_check_names_the_same_problem(monkeypatch, capsys, tmp_path, repo_toml):
    _project(monkeypatch, tmp_path, repo_toml)
    assert _refused(capsys, "profile", "check") == [REFUSAL]


@CONTROLS
def test_status_fetch_never_reaches_gh_with_a_control_character(monkeypatch, capsys, tmp_path, repo_toml):
    _project(monkeypatch, tmp_path, repo_toml)
    gh = fake_gh.install(tmp_path, monkeypatch, {})
    assert _refused(capsys, "status", "--fetch") == [REFUSAL]
    assert gh.calls() == []


@CONTROLS
@pytest.mark.parametrize("command", [["ready", "--fetch"], ["state", "join", "--body", "body.md", "--fetch", "--out", "new.md"]], ids=["ready", "state-join"])
def test_the_other_fetches_refuse_before_gh(monkeypatch, capsys, tmp_path, repo_toml, command):
    _project(monkeypatch, tmp_path, repo_toml)
    gh = fake_gh.install(tmp_path, monkeypatch, {})
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    s = state.empty(c)
    s["run_id"] = "2026-11-13-join"
    s["tickets"] = {"378": {"status": "running", "attempts": 1}}
    (tmp_path / "body.md").write_text(state.put("## Run\n", s), encoding="utf-8")
    assert _refused(capsys, *command) == [REFUSAL]
    assert gh.calls() == []
    assert not (tmp_path / "new.md").exists()


@CONTROLS
def test_the_refusal_is_the_profile_s_own(repo_toml, tmp_path):
    import tomllib

    data = tomllib.loads(f'[project]\nname = "demo"\nrepo = {repo_toml}\n')
    with pytest.raises(profile_mod.ProfileError) as e:
        profile_mod.parse(data, tmp_path)
    assert str(e.value) == REFUSAL.removeprefix("workflow: ")


# ---------- what is still taken ----------


@pytest.mark.parametrize(
    "repo_toml",
    ['"acme/demo"', '"medTech-group/pairnexus-workflow"', '"acme/de`mo"', '"acme/de\\u202Emo"', '"acme/démo"'],
    ids=["ordinary", "this-kit", "backtick", "right-to-left-override", "accented"],
)
def test_a_repo_without_control_characters_is_still_taken(monkeypatch, capsys, tmp_path, repo_toml):
    """An ordinary repo passes; so do the characters that aren't control
    characters (#792's backtick and U+202E, shown escaped when `gh` fails):
    the rest of the `owner/name` rule is #327's."""
    _project(monkeypatch, tmp_path, repo_toml)
    assert cli.main(["profile", "check"]) == 0
    out = capsys.readouterr()
    assert '"ok": true' in out.out


def test_one_slash_is_still_required(monkeypatch, capsys, tmp_path):
    _project(monkeypatch, tmp_path, '"acme"')
    assert _refused(capsys, "profile", "check") == ["workflow: project.repo must be owner/repo"]


# ---------- the changelog ----------


def test_the_changelog_says_what_changed():
    note = entry("#821, found in the review of #792's pull request")
    assert "project.repo" in note
    assert "control character" in note
    assert "`VERSION` is unchanged" in note
    assert "tests/test_profile_repo_control.py" in note

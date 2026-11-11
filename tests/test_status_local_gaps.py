"""#62: `workflow status` reports doctor's local gaps, with no network calls.
Seam 3 of #34: `workflow status`'s report, through the CLI, with a temporary
checkout and profile (as the doctor tests build them), a fake `python3` on the
PATH, and a `gh` that records being run."""

import json
import os
import subprocess
import sys

import pytest

import fake_gh
from changelog_notes import since_0110
from conftest import KIT
from test_doctor import CLI, _bin, _ctrl_c, _fake, _gone, _lines, _prof, _project, _report
from workflow import cli, profile, vendor

# What `status --json` gave before #62; the report only adds to it.
FIELDS = {"set_up", "brand_new", "own_files", "issues_read", "solo_mode", "experience", "run", "in_progress", "prs", "planned", "maps",
          "specs", "ready", "waiting", "to_triage", "kit_update_pr", "kit"}
ADDED = {"local_gap", "local_gaps", "profile_error"}
# Added since by #339: who writes code.
CODE_WRITERS = {"code_writers", "writes_code"}
# Added since by #376: the carry-on tickets.
CARRY_ON = {"carry_on"}
# Added since by #514: research under way, and items held by an open owner task.
RESEARCH_HELD = {"research", "held"}


def _trap(bin_dir):
    """A `gh` that fails, and leaves a file behind, if it's ever run."""
    (bin_dir / "gh").write_text(f"#!/bin/sh\ntouch '{bin_dir / 'gh-was-run'}'\nexit 1\n")
    (bin_dir / "gh").chmod(0o755)
    return bin_dir / "gh-was-run"


def _env(tmp_path, root, path=None, env=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    e = {k: v for k, v in os.environ.items() if k not in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR")}
    e.update({"CLAUDE_PROJECT_DIR": str(root), "HOME": str(home), "PATH": str(path or _bin(tmp_path, gh=False)),
              "WORKFLOW_UPDATE_CHECK": "off", **(env or {})})
    return e


def _run(tmp_path, root, *args, path=None, env=None, own=False):
    """`workflow status` from the kit's source, or with `own` from the
    project's own copy of the CLI, as a session runs it. Only the hooks line
    needs the copy (doctor compares the hooks only from it), and the source
    starts in half the time, since its bytecode is already cached: CI runs
    the whole suite close to its time limit."""
    cli_ = root / ".claude/workflow/bin/workflow.py" if own else CLI
    return subprocess.run([sys.executable, "-B", str(cli_), "status", *args], cwd=root if root.is_dir() else tmp_path,
                          env=_env(tmp_path, root, path, env), capture_output=True, text=True)


def _status(tmp_path, root, *args, **kw):
    p = _run(tmp_path, root, *args, **kw)
    assert p.returncode == 0, p.stderr
    return p.stdout


def _online(tmp_path):
    """The update check left on, with nothing cached: whatever would reach
    the network gets as far as running `gh`."""
    empty = tmp_path / "empty-tmp"
    empty.mkdir(exist_ok=True)
    return {"WORKFLOW_UPDATE_CHECK": "", "TMPDIR": str(empty)}


def _json(tmp_path, root, *args, **kw):
    return json.loads(_status(tmp_path, root, "--json", *args, **kw))


def _gap_line(out):
    lines = [ln for ln in out.splitlines() if ln.startswith("Local gaps:")]
    assert len(lines) == 1, out
    return lines[0]


# No gap


def test_every_local_check_fine_is_no_local_gap(tmp_path):
    root = _project(tmp_path)
    r = _json(tmp_path, root)
    assert r["local_gap"] is False and r["local_gaps"] == []
    assert _gap_line(_status(tmp_path, root)) == "Local gaps: none"


# Each local check failing


def _old_python(tmp_path):
    return _project(tmp_path), {"path": _bin(tmp_path, python="3.9.6", gh=False)}


def _hand_edited_hooks(tmp_path):
    settings = vendor.merge_hooks({})
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 15
    return _project(tmp_path, settings=settings), {"own": True}


def _profile_error(tmp_path):
    return _project(tmp_path, profile="[project\nname = 'demo'\n"), {}


def _vendor_verify_failing(tmp_path):
    return _project(tmp_path, lock_files={".claude/skills/gone/SKILL.md": "0" * 64}), {}


def _unreadable_settings(tmp_path):
    root = _project(tmp_path)
    (root / ".claude/settings.json").write_text("{nope")
    return root, {}


def _hooks_off(tmp_path):
    return _project(tmp_path, settings={**vendor.merge_hooks({}), "disableAllHooks": True}), {}


def _plugin_too(tmp_path):
    return _project(tmp_path, local={"enabledPlugins": {vendor.PLUGIN_KEY: True}}), {}


@pytest.mark.parametrize("make, id_", [
    (_old_python, "computer.python3"),
    (_hand_edited_hooks, "kit.hooks"),
    (_profile_error, "kit.profile"),
    (_vendor_verify_failing, "kit.vendor"),
    (_unreadable_settings, "kit.settings"),
    (_hooks_off, "kit.hooks_off"),
    (_plugin_too, "kit.plugin"),
])
def test_each_local_check_failing_is_a_local_gap_with_doctors_id(tmp_path, make, id_):
    root, kw = make(tmp_path)
    r = _json(tmp_path, root, **kw)
    assert r["local_gap"] is True
    assert [ln["id"] for ln in r["local_gaps"]] == [id_]
    ln = r["local_gaps"][0]
    assert set(ln) == {"group", "id", "status", "message", "fix", "offer"}  # doctor's shape
    assert ln["status"] == "gap" and ln["message"] and ln["fix"]
    line = _gap_line(_status(tmp_path, root, **kw))
    assert line.startswith("Local gaps: 1 (") and id_ in line and "workflow doctor" in line


def test_the_gap_lines_are_doctors_own(tmp_path):
    """The same line doctor gives for the same checkout: reused, not copied."""
    root, kw = _old_python(tmp_path)
    mine = _json(tmp_path, root, **kw)["local_gaps"]
    assert mine == [_lines(_report(tmp_path, root, cli=CLI, **kw))["computer.python3"]]


def test_every_gap_is_named_most_serious_first(tmp_path):
    settings = vendor.merge_hooks({})
    del settings["hooks"]["SessionStart"]
    root = _project(tmp_path, settings=settings, lock_files={".claude/skills/gone/SKILL.md": "0" * 64})
    path = _bin(tmp_path, python=None, gh=False)
    r = _json(tmp_path, root, path=path, own=True)
    ids = [ln["id"] for ln in r["local_gaps"]]
    assert ids == ["computer.python3", "kit.hooks", "kit.vendor"]
    assert _gap_line(_status(tmp_path, root, path=path, own=True)).startswith("Local gaps: 3 (computer.python3, kit.hooks, kit.vendor)")


def test_the_gap_lines_are_worded_for_the_persons_experience(tmp_path):
    root, kw = _old_python(tmp_path)
    new = _json(tmp_path, root, env={"WORKFLOW_EXPERIENCE": "new"}, **kw)["local_gaps"][0]
    dev = _json(tmp_path, root, env={"WORKFLOW_EXPERIENCE": "developer"}, **kw)["local_gaps"][0]
    assert new["id"] == dev["id"] and new["status"] == dev["status"] == "gap"
    assert new["message"] != dev["message"] and new["fix"] != dev["fix"]


def test_a_profile_error_is_reported_not_raised(tmp_path):
    root, _ = _profile_error(tmp_path)
    r = _json(tmp_path, root)
    assert r["set_up"] is True and r["profile_error"] is True and r["solo_mode"] is None
    out = _status(tmp_path, root)
    assert "Kit: set up, but its profile has an error (kit.profile)" in out
    assert "Solo mode: unknown (the profile has an error)" in out
    assert "profile.toml" in r["local_gaps"][0]["message"]
    assert str(tmp_path) not in json.dumps(r)  # doctor's line shows the profile's path from the project


def test_a_profile_error_with_fetch_reads_no_issues_and_says_why(tmp_path):
    root, _ = _profile_error(tmp_path)
    path = _bin(tmp_path, gh=False)
    ran = _trap(path)
    p = _run(tmp_path, root, "--fetch", path=path)
    assert p.returncode == 0, p.stderr
    assert "profile has an error" in p.stderr and "kit.profile" in p.stdout
    assert not ran.exists()


# Solo mode isn't a gap here


@pytest.mark.parametrize("ruleset", ["ruleset = false\n", ""])
def test_solo_mode_and_no_ruleset_setting_arent_local_gaps(tmp_path, ruleset):
    root = _project(tmp_path, profile=_prof(ruleset))
    r = _json(tmp_path, root)
    assert r["local_gap"] is False and r["local_gaps"] == []
    out = _status(tmp_path, root)
    assert _gap_line(out) == "Local gaps: none"
    assert ("Solo mode: yes" if ruleset else "Solo mode: not set (as before)") in out


# No network


@pytest.mark.parametrize("args", [(), ("--json",)])
def test_without_fetch_gh_is_never_run(tmp_path, args):
    root = _project(tmp_path)
    path = _bin(tmp_path, gh=False)
    ran = _trap(path)
    _status(tmp_path, root, *args, path=path, env=_online(tmp_path))
    assert not ran.exists()


def test_without_fetch_gh_is_never_run_even_with_gaps(tmp_path):
    root = _project(tmp_path, profile=_prof(""), lock_files={".claude/skills/gone/SKILL.md": "0" * 64})
    path = _bin(tmp_path, python="3.9.6", gh=False)
    ran = _trap(path)
    assert _json(tmp_path, root, path=path, env=_online(tmp_path))["local_gap"] is True
    assert not ran.exists()


def test_without_fetch_gh_is_never_run_in_plugin_mode_or_unset_up(tmp_path):
    for name, make in (("plugin", lambda d: _project(d, vendored=False)), ("bare", lambda d: _project(d, profile=None, vendored=False))):
        d = tmp_path / name
        root = make(d)
        path = _bin(d, gh=False)
        ran = _trap(path)
        _json(d, root, path=path, env=_online(d))
        assert not ran.exists(), name


def test_with_fetch_only_issues_and_pull_requests_are_read(tmp_path):
    """`--fetch` reads issues and pull requests as before, never doctor's
    GitHub or Cloud reads (rulesets, the repository's settings, runs)."""
    root = _project(tmp_path)
    path = _bin(tmp_path, gh={"repos/acme/demo/issues": fake_gh.pages([]), "repos/acme/demo/pulls": fake_gh.pages([])})
    r = _json(tmp_path, root, "--fetch", path=path)
    assert r["issues_read"] is True and r["local_gap"] is False
    gh = fake_gh.FakeGh(path)
    assert sorted(p.split("?")[0] for p in gh.paths()) == ["repos/acme/demo/issues", "repos/acme/demo/pulls"], gh.calls()
    assert all(c[:1] == ["api"] for c in gh.calls()), gh.calls()  # no `gh auth status` either


# The rest of the report is unchanged


def test_the_json_only_adds_the_local_gap_fields(tmp_path):
    root = _project(tmp_path)
    assert set(_json(tmp_path, root)) == FIELDS | ADDED | CODE_WRITERS | CARRY_ON | RESEARCH_HELD


def test_the_text_only_adds_one_line(tmp_path):
    root = _project(tmp_path)
    out = _status(tmp_path, root).splitlines()
    assert [ln.split(":")[0] for ln in out] == ["Kit", "Project", "Solo mode", "Experience", "Local gaps", "Issues", "Kit version"]


def test_the_changelog_notes_it_under_unreleased_without_a_version_bump():
    log = (KIT / "CHANGELOG.md").read_text()
    start = log.index("## Unreleased\n")
    end = log.index("\n## ", start + 1)
    assert "#62" in since_0110(log) and "local gap" in since_0110(log)
    released = log[end + 4:].split("\n", 1)[0].strip()
    assert (KIT / "VERSION").read_text().strip() == released


# What a project without the kit, or without its folder, gets


def test_a_project_without_the_kit_has_doctors_profile_gap(tmp_path):
    """Doctor's own verdict, kept: no profile is the gap kit.profile (and, in
    plugin mode without the plugin, kit.plugin), beside `Kit: NOT set up`."""
    root = _project(tmp_path, profile=None, vendored=False)
    r = _json(tmp_path, root)
    assert r["set_up"] is False and r["profile_error"] is False
    assert [ln["id"] for ln in r["local_gaps"]] == ["kit.profile", "kit.plugin"]
    out = _status(tmp_path, root)
    assert "Kit: NOT set up here" in out and _gap_line(out).startswith("Local gaps: 2 (kit.profile, kit.plugin)")


def test_plugin_mode_with_the_plugin_on_has_no_local_gap(tmp_path):
    root = _project(tmp_path, vendored=False, settings={"enabledPlugins": {vendor.PLUGIN_KEY: True}})
    assert _json(tmp_path, root)["local_gaps"] == []


def test_a_missing_project_folder_is_doctors_profile_gap(tmp_path):
    r = json.loads(_status(tmp_path, tmp_path / "home/gone", "--json"))
    assert [ln["id"] for ln in r["local_gaps"]] == ["kit.profile"]
    assert "~/gone" in r["local_gaps"][0]["message"] and str(tmp_path) not in json.dumps(r["local_gaps"])


# What status leaves out, and stopping it


def test_status_skips_profile_checks_warnings(tmp_path, monkeypatch, capsys):
    """Its warnings are only ever notes, and their globs can walk a whole
    tree: `status` asks for gaps only, so it never runs them; doctor does."""
    root = _project(tmp_path)
    for k in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(k, raising=False)
    for k, v in _env(tmp_path, root).items():
        monkeypatch.setenv(k, v)
    calls = []
    monkeypatch.setattr(profile, "check", lambda prof: calls.append(prof) or [])
    assert cli.main(["status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["local_gap"] is False and calls == []
    assert cli.main(["doctor", "--json"]) == 0
    capsys.readouterr()
    assert len(calls) == 1


def test_ctrl_c_stops_status_quietly_with_nothing_left_running(tmp_path):
    import shutil

    root = _project(tmp_path)
    path = _bin(tmp_path, python=None, gh=False)
    marker = tmp_path / "child.pid"
    _fake(path, "python3", f"{shutil.which('sleep')} 30 & echo $! > {marker}; wait")
    # SIGINT as a terminal sends it, even where pytest was started ignoring it,
    # and only once the fake has started, however long that takes (#684).
    code, err = _ctrl_c(CLI, ["status"], root, _env(tmp_path, root, path), marker)
    assert code == 130 and "workflow status: stopped" in err and "Traceback" not in err
    assert _gone(int(marker.read_text()))


# #689: a Ctrl-C during status's own `git` calls (its tracked files, then the
# base's profile read for who writes code) stops it quietly, and kills what
# that `git` started, as doctor's `_run` does.
STATUS_GIT = ["ls-files -z", "check-ref-format refs/remotes/origin/main", "rev-parse --verify --quiet refs/remotes/origin/main^{commit}",
              "show refs/remotes/origin/main:.claude/workflow/profile.toml"]


def _git_project(tmp_path):
    """A checkout with a commit and `origin/main`, so status reads the base's profile."""
    import shutil

    root, git = _project(tmp_path), shutil.which("git")
    ident = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], [*ident, "commit", "-qm", "x"], ["update-ref", "refs/remotes/origin/main", "HEAD"]):
        subprocess.run([git, *args], cwd=root, check=True, capture_output=True)
    return root


def _counting_git(bin_dir, tmp_path, hang_at=None, delay=0):
    """A `git` on the PATH that logs each call's arguments and runs the real
    one, except its `hang_at`-th call, which first sleeps `delay` seconds (a
    busy machine), then starts a `sleep`, writes its pid to the marker and
    waits. Give the log and the marker."""
    import shutil

    log, count, marker = tmp_path / "git.log", tmp_path / "git.count", tmp_path / "child.pid"
    for f in (log, count, marker):
        f.unlink(missing_ok=True)
    slow = f'{shutil.which("sleep")} {delay}; ' if delay else ""
    hang = (f'if [ "$n" = {hang_at} ]; then {slow}{shutil.which("sleep")} 30 & echo $! > {marker}; wait; exit 1; fi\n'
            if hang_at else "")
    # Only the fakes are on the PATH: `cat` and the real `git` by their full paths.
    _fake(bin_dir, "git", f'n=$({shutil.which("cat")} {count} 2>/dev/null || echo 0); n=$((n+1)); echo $n > {count}\n'
                          f'printf "%s\\n" "$*" >> {log}\n{hang}exec {shutil.which("git")} "$@"')
    return log, marker


def _ctrl_c_at_status_git_call(tmp_path, call, delay=0):
    root = _git_project(tmp_path)
    path = _bin(tmp_path, gh=False)
    log, _ = _counting_git(path, tmp_path)
    p = _run(tmp_path, root, path=path)
    assert p.returncode == 0, p.stderr
    calls = log.read_text().splitlines()
    assert call in calls, calls
    # Status's own call comes after doctor's: the last one with these arguments.
    at = len(calls) - calls[::-1].index(call)
    _, marker = _counting_git(path, tmp_path, hang_at=at, delay=delay)
    code, err = _ctrl_c(CLI, ["status"], root, _env(tmp_path, root, path), marker)
    assert code == 130 and "workflow status: stopped" in err and "Traceback" not in err, err
    assert _gone(int(marker.read_text())), "what status's git started is still running"


@pytest.mark.parametrize("call", STATUS_GIT)
def test_ctrl_c_during_status_own_git_calls_stops_quietly_with_nothing_left_running(tmp_path, call):
    _ctrl_c_at_status_git_call(tmp_path, call)


# A slow `git` (a busy machine) at each of status's own timeouts: the test's
# launcher sets them far past its wait, as it does doctor's, so the Ctrl-C
# still finds the command running.
@pytest.mark.parametrize("call, delay", [(STATUS_GIT[0], 21), (STATUS_GIT[1], 6)])
def test_a_slow_status_git_call_is_still_running_when_the_ctrl_c_comes(tmp_path, call, delay):
    _ctrl_c_at_status_git_call(tmp_path, call, delay)


def test_the_changelog_notes_status_own_git_calls_ctrl_c():
    notes = since_0110()
    assert "#689" in notes and "workflow status" in notes


def test_status_s_quiet_stop_is_never_claimed_for_a_ctrl_c_anywhere():
    # A Ctrl-C while the CLI is still loading its modules gives a traceback
    # (#697), so neither the note nor `cmd_status` says "anywhere".
    notes = since_0110()
    start = notes.index("(#689).")
    entry = notes[start:notes.index("\n\n**", start)]
    assert "- **For projects updating:**" in entry and "Ctrl-C anywhere" not in entry
    assert "anywhere" not in cli.cmd_status.__doc__

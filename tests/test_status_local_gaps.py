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
from conftest import KIT
from test_doctor import CLI, _bin, _fake, _gone, _lines, _prof, _project, _report
from workflow import cli, profile, vendor

# What `status --json` gave before #62; the report only adds to it.
FIELDS = {"set_up", "brand_new", "own_files", "issues_read", "solo_mode", "experience", "run", "in_progress", "prs", "planned", "maps",
          "specs", "ready", "waiting", "to_triage", "kit_update_pr", "kit"}
ADDED = {"local_gap", "local_gaps", "profile_error"}


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


def _run(tmp_path, root, *args, path=None, env=None):
    """`workflow status` from the project's own copy of the CLI when it has
    one, as a session runs it, else from the kit's source (plugin mode)."""
    copy = root / ".claude/workflow/bin/workflow.py"
    return subprocess.run([sys.executable, "-B", str(copy if copy.is_file() else CLI), "status", *args], cwd=root if root.is_dir() else tmp_path,
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
    return _project(tmp_path, settings=settings), {}


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
    assert mine == [_lines(_report(tmp_path, root, **kw))["computer.python3"]]


def test_every_gap_is_named_most_serious_first(tmp_path):
    settings = vendor.merge_hooks({})
    del settings["hooks"]["SessionStart"]
    root = _project(tmp_path, settings=settings, lock_files={".claude/skills/gone/SKILL.md": "0" * 64})
    path = _bin(tmp_path, python=None, gh=False)
    r = _json(tmp_path, root, path=path)
    ids = [ln["id"] for ln in r["local_gaps"]]
    assert ids == ["computer.python3", "kit.hooks", "kit.vendor"]
    assert _gap_line(_status(tmp_path, root, path=path)).startswith("Local gaps: 3 (computer.python3, kit.hooks, kit.vendor)")


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
    assert set(_json(tmp_path, root)) == FIELDS | ADDED


def test_the_text_only_adds_one_line(tmp_path):
    root = _project(tmp_path)
    out = _status(tmp_path, root).splitlines()
    assert [ln.split(":")[0] for ln in out] == ["Kit", "Project", "Solo mode", "Experience", "Local gaps", "Issues", "Kit version"]


def test_the_changelog_notes_it_under_unreleased():
    text = (KIT / "CHANGELOG.md").read_text()
    start = text.index("## Unreleased\n")
    notes = text[start:text.index("\n## ", start + 1)]
    assert "#62" in notes and "local gap" in notes
    assert not (KIT / "VERSION").read_text().strip() in notes  # no VERSION bump under Unreleased


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
    import signal
    import time

    root = _project(tmp_path)
    path = _bin(tmp_path, python=None, gh=False)
    marker = tmp_path / "child.pid"
    _fake(path, "python3", f"{shutil.which('sleep')} 30 & echo $! > {marker}; wait")
    p = subprocess.Popen([sys.executable, "-B", str(root / ".claude/workflow/bin/workflow.py"), "status"], cwd=root,
                         env=_env(tmp_path, root, path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(100):
        if marker.exists() and marker.read_text().strip():
            break
        time.sleep(0.1)
    p.send_signal(signal.SIGINT)
    out, err = p.communicate(timeout=20)
    assert p.returncode == 130 and "workflow status: stopped" in err and "Traceback" not in err
    assert _gone(int(marker.read_text()))

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
from test_doctor import _bin, _prof, _project
from workflow import doctor, vendor

# What `status --json` gave before #62; the report only adds to it.
FIELDS = {"set_up", "brand_new", "own_files", "issues_read", "solo_mode", "experience", "run", "in_progress", "prs", "planned", "maps",
          "specs", "ready", "waiting", "to_triage", "kit_update_pr", "kit"}
ADDED = {"local_gap", "local_gaps", "profile_error"}
LOCAL_IDS = {"computer.python3", "kit.settings", "kit.hooks_off", "kit.hooks", "kit.plugin", "kit.vendor", "kit.profile", "kit.ruleset"}


def _trap(bin_dir):
    """A `gh` that fails, and leaves a file behind, if it's ever run."""
    (bin_dir / "gh").write_text(f"#!/bin/sh\ntouch '{bin_dir / 'gh-was-run'}'\nexit 1\n")
    (bin_dir / "gh").chmod(0o755)
    return bin_dir / "gh-was-run"


def _status(tmp_path, root, *args, path=None, env=None):
    """`workflow status` from the project's own copy of the CLI, as a session
    runs it."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    e = {k: v for k, v in os.environ.items() if k not in ("WORKFLOW_EXPERIENCE", "CLAUDE_CONFIG_DIR")}
    e.update({"CLAUDE_PROJECT_DIR": str(root), "HOME": str(home), "PATH": str(path or _bin(tmp_path, gh=False)),
              "WORKFLOW_UPDATE_CHECK": "off", **(env or {})})
    cli = root / ".claude/workflow/bin/workflow.py"
    p = subprocess.run([sys.executable, "-B", str(cli), "status", *args], cwd=root, env=e, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


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


@pytest.mark.parametrize("make, id_", [
    (_old_python, "computer.python3"),
    (_hand_edited_hooks, "kit.hooks"),
    (_profile_error, "kit.profile"),
    (_vendor_verify_failing, "kit.vendor"),
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
    e = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "HOME": str(tmp_path / "home"), "PATH": str(kw["path"])}
    e.pop("WORKFLOW_EXPERIENCE", None)
    p = subprocess.run([sys.executable, "-B", str(root / ".claude/workflow/bin/workflow.py"), "doctor", "--json"], cwd=root, env=e,
                       capture_output=True, text=True)
    theirs = [ln for ln in json.loads(p.stdout)["lines"] if ln["id"] == "computer.python3"]
    assert mine == theirs


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
    assert str(tmp_path) not in out  # doctor's line shows the profile's path from the project


def test_a_profile_error_with_fetch_reads_no_issues_and_says_why(tmp_path):
    root, _ = _profile_error(tmp_path)
    path = _bin(tmp_path, gh=False)
    ran = _trap(path)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    e = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "HOME": str(home), "PATH": str(path), "WORKFLOW_UPDATE_CHECK": "off"}
    p = subprocess.run([sys.executable, "-B", str(root / ".claude/workflow/bin/workflow.py"), "status", "--fetch"], cwd=root, env=e,
                       capture_output=True, text=True)
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
    _status(tmp_path, root, *args, path=path)
    assert not ran.exists()


def test_without_fetch_gh_is_never_run_even_with_gaps(tmp_path):
    root = _project(tmp_path, profile=_prof(""), lock_files={".claude/skills/gone/SKILL.md": "0" * 64})
    path = _bin(tmp_path, python="3.9.6", gh=False)
    ran = _trap(path)
    assert _json(tmp_path, root, path=path)["local_gap"] is True
    assert not ran.exists()


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


def test_status_runs_only_doctors_local_checks():
    """The local checks are doctor's own functions, none of the GitHub or Cloud
    ones, and not Claude Code's version (it isn't one #34 names for status)."""
    assert all(c in doctor.CHECKS for c in doctor.LOCAL_CHECKS)
    assert {c.__name__ for c in doctor.LOCAL_CHECKS} == {"check_python", "check_install", "check_profile", "check_vendor", "check_ruleset"}
    assert all(c.group in ("Your computer", "The kit") for c in doctor.LOCAL_CHECKS)


def test_the_changelog_notes_it_under_unreleased():
    notes = since_0110()
    assert "#62" in notes and "local gap" in notes
    assert (KIT / "VERSION").read_text().strip() in (KIT / "CHANGELOG.md").read_text().split("## Unreleased", 1)[1]

"""Kit 0.1.5: releases, and the update check (each session, the conductor, the weekly issue)."""

import importlib.util
import json
import os
import subprocess
import sys
import time

from conftest import KIT
from test_hooks_cli import CLI, run_hook
from workflow import updates


def _release():
    spec = importlib.util.spec_from_file_location("release", KIT / ".github/scripts/release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Releases --------------------------------------------------------------------


def test_each_version_is_released_at_its_last_commit():
    release = _release()
    commits = [("a", ""), ("b", "0.1.0"), ("c", "0.1.0"), ("d", "0.1.1"), ("e", "0.1.2"), ("f", "0.1.2"), ("g", "unknown")]
    assert release.release_points(commits) == {"0.1.0": "c", "0.1.1": "d", "0.1.2": "f"}


def test_release_notes_are_the_changelog_entry():
    release = _release()
    log = "# Changelog\n\n## 0.1.5\n\n- new\n\n## 0.1.4\n\n- old\n"
    assert release.notes(log, "0.1.5") == "- new"
    assert release.notes(log, "0.1.4") == "- old"
    assert release.notes(log, "0.1.3") is None
    assert release.notes("## 0.1.0 (first)\n\n- first\n", "0.1.0") == "- first"
    assert release.notes("## 0.1.10\n\n- ten\n", "0.1.1") is None


def test_the_release_workflow_runs_on_main_and_may_tag():
    wf = (KIT / ".github/workflows/release.yml").read_text()
    assert "branches: [main]" in wf and "contents: write" in wf and ".github/scripts/release.py" in wf
    assert "fetch-depth: 0" in wf


# The check -------------------------------------------------------------------


def test_versions_compare_as_numbers():
    assert updates.newer("0.1.10", "0.1.9")
    assert updates.newer("v0.2.0", "0.1.9")
    assert not updates.newer("0.1.5", "0.1.5")
    assert not updates.newer(None, "0.1.5") and not updates.newer("0.1.5", None)
    assert not updates.newer("latest", "0.1.5")


def test_installed_is_the_lock_s_version_or_the_kit_s(tmp_path):
    (tmp_path / "kit").mkdir()
    (tmp_path / "kit/VERSION").write_text("0.1.5\n")
    assert updates.installed(tmp_path, tmp_path / "kit") == "0.1.5"
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/lock.json").write_text(json.dumps({"kit_version": "0.1.3"}))
    assert updates.installed(tmp_path, tmp_path / "kit") == "0.1.3"


def test_latest_is_remembered_and_a_miss_is_too(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "on")
    asked = []

    def fetch():
        asked.append(1)
        return "v0.1.6"

    assert updates.latest(fetch=fetch) == "0.1.6"
    assert updates.latest(fetch=fetch) == "0.1.6" and len(asked) == 1  # from the cache
    assert updates.latest(fresh=True, fetch=fetch) == "0.1.6" and len(asked) == 2
    # A failed lookup isn't tried again for an hour.
    assert updates.latest(fresh=True, fetch=lambda: None) is None
    assert updates.latest(fetch=fetch) is None and len(asked) == 2
    cache = tmp_path / "workflow-kit-latest.json"
    cache.write_text(json.dumps({"at": time.time() - updates.MISS_FOR - 1, "latest": None}))
    assert updates.latest(fetch=fetch) == "0.1.6"


def test_the_check_can_be_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "off")
    assert updates.latest(fetch=lambda: "v9.9.9") is None


def test_the_notice_names_both_versions():
    assert updates.notice({"installed": "0.1.4", "latest": "0.1.4", "update_available": False}) is None
    note = updates.notice({"installed": "0.1.4", "latest": "0.1.5", "update_available": True})
    assert "0.1.5 is out" in note and "0.1.4" in note and "update-workflow" in note


def _cached(tmp_path, version="9.9.9"):
    (tmp_path / "workflow-kit-latest.json").write_text(json.dumps({"at": time.time(), "latest": version}))
    return {"TMPDIR": str(tmp_path), "WORKFLOW_UPDATE_CHECK": "on"}


def test_session_start_offers_a_newer_kit_except_to_ticket_sessions(repo, tmp_path):
    env = _cached(tmp_path)
    _, out, _ = run_hook("repair", {}, repo, env)
    assert "Workflow kit 9.9.9 is out" in out["hookSpecificOutput"]["additionalContext"]
    _, out, _ = run_hook("repair", {}, repo, {**env, "WORKFLOW_ROLE": "conductor"})
    assert "9.9.9 is out" in out["hookSpecificOutput"]["additionalContext"]
    _, out, _ = run_hook("repair", {}, repo, {**env, "WORKFLOW_ROLE": "ticket"})
    assert "is out" not in out["hookSpecificOutput"]["additionalContext"]


def test_session_start_says_nothing_when_up_to_date(repo, tmp_path):
    env = _cached(tmp_path, (KIT / "VERSION").read_text().strip())
    _, out, _ = run_hook("repair", {}, repo, env)
    assert "is out" not in out["hookSpecificOutput"]["additionalContext"]


def test_version_command(repo, tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo), **_cached(tmp_path)}
    p = subprocess.run([sys.executable, str(CLI), "version", "--json"], cwd=repo, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["latest"] == "9.9.9" and out["update_available"] is True


# The skills and templates ----------------------------------------------------


def test_the_weekly_check_opens_an_issue_never_a_pull_request():
    wf = (KIT / "templates/github/workflow-kit-update.yml").read_text()
    assert "schedule:" in wf and "workflow_dispatch:" in wf
    assert "issues: write" in wf and "pull-requests: write" not in wf and "contents: write" not in wf
    assert "kit_version" in wf and "releases/latest" in wf and "Workflow kit update:" in wf
    assert "gh issue close" in wf and "--label owner-task" in wf


def test_the_skills_offer_and_take_releases():
    start = (KIT / "skills/start/SKILL.md").read_text()
    assert "Update the workflow kit to <version> (Recommended)" in start and "git checkout v<version>" in start
    upd = (KIT / "skills/update-workflow/SKILL.md").read_text()
    assert "never `main` between releases" in upd and "workflow-kit-update.yml" in upd
    cond = (KIT / "skills/conductor/SKILL.md").read_text()
    assert "WF version --fresh" in cond and "never updates mid-run" in cond
    setup = (KIT / "skills/setup-workflow/SKILL.md").read_text()
    assert "workflow-kit-update.yml" in setup

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
    assert "gh label create owner-task" in wf and "NOT_PLANNED" in wf and "/compare/v$have...v$latest" in wf
    assert "cat notes.md" not in wf  # links, not notes that cross-link the project's own issues


def test_the_weekly_check_s_script_is_valid_shell():
    wf = (KIT / "templates/github/workflow-kit-update.yml").read_text()
    script = wf.split("        run: |\n", 1)[1]
    script = "\n".join(line[10:] for line in script.splitlines())
    p = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_the_skills_offer_and_take_releases():
    start = (KIT / "skills/start/SKILL.md").read_text()
    assert "Update the workflow kit to <version> (Recommended)" in start and "update-workflow/SKILL.md" in start
    assert "/plugin update pairnexus-workflow@pairnexus" in start and "kit_update_pr" in start
    upd = (KIT / "skills/update-workflow/SKILL.md").read_text()
    assert "never `main` between releases" in upd and "workflow-kit-update.yml" in upd
    assert "mktemp -d" in upd and "git ls-remote --tags" in upd and "Update the workflow kit to <version>" in upd
    assert "--branch v<version>" in upd and "version --repo" in upd  # the release, from the kit's home (0.1.7)
    cond = (KIT / "skills/conductor/SKILL.md").read_text()
    assert "WF version --fresh" in cond and "never updates mid-run" in cond
    setup = (KIT / "skills/setup-workflow/SKILL.md").read_text()
    assert "workflow-kit-update.yml" in setup


# The review's fixes ----------------------------------------------------------


def test_parse_takes_only_strings():
    for bad in (["a"], 5, None, {"v": 1}, 1.5):
        assert updates.parse(bad) is None


def test_a_bad_lock_is_no_version(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    for body in ("[1, 2]", '{"kit_version": 5}', '{"kit_version": "unknown"}', "not json"):
        (tmp_path / ".claude/workflow/lock.json").write_text(body)
        assert updates.installed(tmp_path, tmp_path) is None


def test_a_bad_cache_is_asked_again(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "on")
    cache = tmp_path / "workflow-kit-latest.json"
    for body in ('{"at": 0, "latest": ["a"]}', '{"at": 0, "latest": 5}', '{"at": 1e400, "latest": "0.1.0"}',
                 json.dumps({"at": time.time() + 3600, "latest": "0.1.0"}), "[]", '"x"'):
        cache.write_text(body)
        assert updates.latest(fetch=lambda: "v0.1.7") == "0.1.7", body


def test_a_hanging_lookup_never_holds_the_session_start(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_UPDATE_CHECK", "on")
    monkeypatch.setattr(updates, "_from_gh", lambda: time.sleep(5) or None)
    started = time.monotonic()
    assert updates.check_within(tmp_path, KIT, seconds=0.3) is None
    assert time.monotonic() - started < 2


def test_a_broken_check_is_no_notice(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(updates, "check", boom)
    assert updates.check_within(tmp_path, KIT) is None
    assert updates.notice(None) is None


def test_the_notice_fits_the_role_and_the_mode():
    vendored = {"installed": "0.1.4", "latest": "0.1.5", "update_available": True, "mode": "vendored"}
    assert "update-workflow" in updates.notice(vendored)
    assert "kick-off" in updates.notice(vendored, "conductor") and "never mid-run" in updates.notice(vendored, "conductor")
    plugin = {**vendored, "mode": "plugin"}
    assert "/plugin update pairnexus-workflow@pairnexus" in updates.notice(plugin)


def test_the_kit_line_says_each_case(repo, tmp_path):
    from workflow.cli import _kit_line

    assert "unknown" in _kit_line({"installed": None, "latest": "0.1.5"}) and "latest release is 0.1.5" in _kit_line({"installed": None, "latest": "0.1.5"})
    assert "ahead of the latest release (0.1.5)" in _kit_line({"installed": "0.1.6", "latest": "0.1.5", "ahead": True, "checked": True})
    assert "check is off" in _kit_line({"installed": "0.1.5", "latest": None, "checked": False})
    assert "(the latest)" in _kit_line({"installed": "0.1.5", "latest": "0.1.5", "checked": True})
    assert "couldn't read" in _kit_line({"installed": "0.1.5", "latest": None, "checked": True})
    assert "/plugin update" in _kit_line({"installed": "0.1.4", "latest": "0.1.5", "update_available": True, "mode": "plugin", "checked": True})


def test_a_session_start_survives_a_corrupt_cache(repo, tmp_path):
    (tmp_path / "workflow-kit-latest.json").write_text('{"at": 0, "latest": ["a"]}')
    code, out, _ = run_hook("repair", {}, repo, {"TMPDIR": str(tmp_path), "WORKFLOW_UPDATE_CHECK": "on", "GH_HOST": "invalid.invalid"})
    assert code == 0 and "Workflow role of this session" in out["hookSpecificOutput"]["additionalContext"]


def test_status_notices_an_open_kit_update(repo):
    from workflow import status

    prs = [{"number": 9, "title": "Update the workflow kit to 0.1.5", "state": "open", "head": {"ref": "claude/kit-0.1.5"}}]
    st = status.snapshot(repo, True, [], prs)
    assert st.kit_update_pr == 9 and "Kit update pull request open: #9" in status.text(st)


def test_every_changelog_entry_parses():
    import re

    release = _release()
    log = (KIT / "CHANGELOG.md").read_text()
    versions = re.findall(r"^## (\d+\.\d+\.\d+)", log, re.M)
    assert "0.1.0" in versions and (KIT / "VERSION").read_text().strip() in versions
    for v in versions:
        assert release.notes(log, v), v


def test_released_means_a_release_not_just_a_tag():
    release = _release()
    points = {"0.1.0": "a", "0.1.1": "b", "0.1.2": "c"}
    log = "## 0.1.2\n\n- c\n\n## 0.1.1\n\n- b\n\n## 0.1.0\n\n- a\n"
    steps = release.plan(points, {"v0.1.0"}, {"v0.1.0", "v0.1.1"}, log)
    assert [s["tag"] for s in steps] == ["v0.1.1", "v0.1.2"]
    assert steps[0]["target"] is None and "--verify-tag" in release.command(steps[0], "n.md")
    assert steps[1]["target"] == "c" and steps[1]["latest"] and "--latest=true" in release.command(steps[1], "n.md")


def test_one_failed_release_doesn_t_stop_the_others(tmp_path, monkeypatch):
    from conftest import git

    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    for v in ("0.1.0", "0.1.1"):
        (tmp_path / "VERSION").write_text(v + "\n")
        (tmp_path / "CHANGELOG.md").write_text("## 0.1.1\n\n- b\n\n## 0.1.0\n\n- a\n")
        git(tmp_path, "add", ".")
        git(tmp_path, "commit", "-qm", v)
    monkeypatch.chdir(tmp_path)
    calls = []

    class Done:
        def __init__(self, code, out=""):
            self.returncode, self.stdout, self.stderr = code, out, ""

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["gh", "release", "list"]:
            return Done(0, "[]")
        return Done(1 if "v0.1.0" in cmd else 0)

    assert _release().main(run=run) == 1
    created = [c[3] for c in calls if c[:3] == ["gh", "release", "create"]]
    assert created == ["v0.1.0", "v0.1.1"]


def test_the_release_job_runs_only_on_main():
    wf = (KIT / ".github/workflows/release.yml").read_text()
    assert "if: github.ref == 'refs/heads/main'" in wf

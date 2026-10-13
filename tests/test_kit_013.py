"""Kit 0.1.3: the project's own setup at session start, and the environment's setup script."""

import json

from test_hooks_cli import CLI, run_hook  # noqa: F401
from workflow import repair, vendor
from workflow.profile import parse

from conftest import BASE_PROFILE, KIT


CLOUD = {"CLAUDE_CODE_REMOTE": "true"}


def test_a_laptop_session_start_installs_nothing(repo, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    _with_commands(repo, "touch installed", "false")
    _, out, _ = run_hook("repair", {}, repo)
    assert not (repo / "installed").exists()
    assert "Project setup" not in out["hookSpecificOutput"]["additionalContext"]


def _with_commands(repo, setup, check):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text() + f"\n[commands]\nsetup = {json.dumps(setup)}\nsetup_check = {json.dumps(check)}\n")


def test_setup_runs_at_session_start_when_its_check_fails(repo):
    _with_commands(repo, "mkdir -p .deps && touch .deps/ready", "test -f .deps/ready")
    _, out, _ = run_hook("repair", {}, repo, CLOUD)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "Project setup (commands.setup) ran" in ctx and "ok:" in ctx
    assert (repo / ".deps/ready").exists()
    # The next session start finds it in place and says nothing about setup.
    _, out, _ = run_hook("repair", {}, repo, CLOUD)
    assert "Project setup" not in out["hookSpecificOutput"]["additionalContext"]


def test_a_failed_setup_is_reported_not_hidden(repo):
    _with_commands(repo, "echo no requirements file; exit 3", "false")
    _, out, _ = run_hook("repair", {}, repo, CLOUD)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "Project setup (commands.setup) FAILED, exit 3" in ctx and "no requirements file" in ctx


def test_no_check_means_no_setup_at_session_start(tmp_path):
    marker = tmp_path / "ran"
    assert repair.setup(f"touch {marker}", "", tmp_path, 10) is None
    assert not marker.exists()


def test_setup_is_bounded_by_its_budget(tmp_path):
    c, code, tail = repair.setup("sleep 5", "false", tmp_path, 1)
    assert code == 124 and "timed out" in tail


def test_workflow_repair_runs_setup_and_fails_when_it_fails(repo):
    import os
    import subprocess
    import sys

    _with_commands(repo, "exit 2", "false")
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    p = subprocess.run([sys.executable, str(CLI), "repair"], cwd=repo, env=env, capture_output=True, text=True)
    assert p.returncode == 1 and "FAILED, exit 2" in p.stdout


def test_the_session_start_hook_has_room_for_setup():
    assert vendor.KIT_HOOKS["SessionStart"][0]["hooks"][0]["timeout"] == 600
    hooks = json.loads((KIT / "hooks/hooks.json").read_text())
    assert hooks["hooks"]["SessionStart"][0]["hooks"][0]["timeout"] == 600
    assert repair.HOOK_BUDGET < 600


def test_profile_takes_setup_check_and_environment_setup(tmp_path):
    data = json.loads(json.dumps(BASE_PROFILE))
    data["commands"]["setup"] = "npm ci"
    data["commands"]["setup_check"] = "test -d node_modules"
    data["run"] = {"environment_setup": "apt-get install -y shellcheck"}
    prof = parse(data, tmp_path)
    assert prof.setup_check == "test -d node_modules"
    assert prof.environment_setup == "apt-get install -y shellcheck"

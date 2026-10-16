"""The guard sees `Monitor` and `PowerShell` (#55).

`Monitor` runs a shell command as Bash does, so its `command` is checked as a
Bash command, in every role. The guard can't read PowerShell: ticket and
conductor sessions are refused it, and an attended session gets the
can't-decide rule (#53) on its text.

Every command here is data passed to `decide`, the hook or the fallbacks; none is run.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import fallback, vendor
from workflow.guard import POWERSHELL_REFUSAL, decide
from workflow.profile import load

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
ROLES = ("attended", "ticket", "conductor")
ASKING = (None, "default", "acceptEdits", "auto", "plan")
NEVER = ("bypassPermissions", "dontAsk", "turbo")
PUSH = "git push origin main"
MERGE = "gh pr merge 12 --merge"


def _toml(ruleset):
    line = "" if ruleset is None else f"ruleset = {'true' if ruleset else 'false'}\n"
    return f"""
[project]
name = "demo"
repo = "acme/demo"
base_branch = "main"
{line}
[guard]
deploy_commands = ["scripts/deploy.sh"]
"""


def on_disk(root: Path, ruleset=None):
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(_toml(ruleset))
    return load(root)


@pytest.fixture(autouse=True)
def _session_env(monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture
def prof(tmp_path):
    return on_disk(tmp_path)


@pytest.fixture
def solo(tmp_path):
    return on_disk(tmp_path, False)


def tool(name, mode=None, **inp):
    ev = {"tool_name": name, "tool_input": inp}
    if mode is not None:
        ev["permission_mode"] = mode
    return ev


def branch_for(role):
    return "claude/build-7" if role == "ticket" else "feature"


def act(profile, event, role):
    return decide(event, profile, role, profile.root, branch_for(role))


# ---------- Monitor: checked exactly as Bash ----------

MONITOR_CASES = {
    "base-branch push": PUSH,
    "deploy command": "scripts/deploy.sh staging",
    "protected-path write": "echo x > .claude/settings.json",
    "allowed command": "ls -la",
    "run watch": "gh run watch 123",
    "checks watch": "gh pr checks 5 --watch",
    "merge": MERGE,
}


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("what", list(MONITOR_CASES))
@pytest.mark.parametrize("mode", (None, "bypassPermissions"))
def test_monitor_gets_the_same_decision_as_bash(prof, role, what, mode):
    cmd = MONITOR_CASES[what]
    as_bash = act(prof, tool("Bash", mode, command=cmd), role)
    as_monitor = act(prof, tool("Monitor", mode, command=cmd, description="watch"), role)
    assert (as_monitor.action, as_monitor.reason) == (as_bash.action, as_bash.reason)


def test_monitor_refuses_or_asks_what_bash_does(prof):
    # Not only the same as Bash: actually checked (a Monitor left alone would allow all of these).
    for cmd in (PUSH, "scripts/deploy.sh staging", "echo x > .claude/settings.json"):
        assert act(prof, tool("Monitor", command=cmd), "ticket").action == "deny", cmd
    for cmd in (PUSH, "scripts/deploy.sh staging"):
        assert act(prof, tool("Monitor", command=cmd), "attended").action == "ask", cmd
    assert act(prof, tool("Monitor", command=PUSH), "conductor").action == "deny"


def test_a_ticket_session_may_watch_ci_through_monitor(prof):
    for cmd in ("gh run watch 123", "gh pr checks 5 --watch"):
        assert act(prof, tool("Monitor", command=cmd), "ticket").action == "allow", cmd


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("mode", ASKING + NEVER)
def test_a_websocket_monitor_is_allowed(prof, role, mode):
    d = act(prof, tool("Monitor", mode, ws="wss://example.test/feed", description="feed"), role)
    assert d.action == "allow"


# ---------- PowerShell ----------


@pytest.mark.parametrize("role", ("ticket", "conductor"))
@pytest.mark.parametrize("cmd", ["Get-ChildItem", PUSH, MERGE, "", "Remove-Item -Recurse .claude"])
def test_powershell_is_refused_in_a_run(prof, role, cmd):
    d = act(prof, tool("PowerShell", command=cmd), role)
    assert d.action == "deny"
    assert "the guard can't read PowerShell; use Bash" in d.reason
    assert d.reason == POWERSHELL_REFUSAL


@pytest.mark.parametrize("cmd", [PUSH, MERGE, "cd repo; git push", "gh pr view 3 | Out-Null\ngh pr merge 3"])
@pytest.mark.parametrize("mode", ASKING)
def test_attended_powershell_push_or_merge_is_asked(prof, cmd, mode):
    d = act(prof, tool("PowerShell", mode, command=cmd), "attended")
    assert d.action == "ask"
    assert "PowerShell" in d.reason


@pytest.mark.parametrize("cmd", [PUSH, MERGE])
@pytest.mark.parametrize("mode", NEVER)
def test_attended_powershell_push_or_merge_is_refused_where_nobody_is_asked(prof, cmd, mode):
    d = act(prof, tool("PowerShell", mode, command=cmd), "attended")
    assert d.action == "deny"
    assert "would have asked" in d.reason


@pytest.mark.parametrize("cmd", [PUSH, MERGE])
@pytest.mark.parametrize("mode", ASKING)
def test_attended_powershell_push_or_merge_is_refused_in_solo_mode(solo, cmd, mode):
    d = act(solo, tool("PowerShell", mode, command=cmd), "attended")
    assert d.action == "deny"
    assert "PowerShell" in d.reason
    assert f"`{cmd}`" in d.reason


@pytest.mark.parametrize("cmd", ["Get-ChildItem", "Write-Output 'git'", "", "gh pr view 3"])
@pytest.mark.parametrize("mode", ASKING + NEVER)
def test_attended_powershell_anything_else_is_left_alone(prof, solo, cmd, mode):
    for p in (prof, solo):
        d = act(p, tool("PowerShell", mode, command=cmd), "attended")
        assert (d.action, d.reason) == ("allow", "")


def test_attended_powershell_backtick_continuation_is_one_line(prof):
    d = act(prof, tool("PowerShell", command="git `\npush origin main"), "attended")
    assert d.action == "ask"


# ---------- the hand command where nobody is asked ----------


@pytest.mark.parametrize("name", ["Monitor", "PowerShell"])
@pytest.mark.parametrize("cmd", [PUSH, MERGE])
def test_the_hand_command_is_the_command_itself(prof, name, cmd):
    if name == "Monitor" and cmd == MERGE:
        cmd = "gh pr merge 12 --admin"  # a plain merge isn't asked through Bash either
    d = act(prof, tool(name, "bypassPermissions", command=cmd), "attended")
    assert d.action == "deny"
    assert f"Or run it yourself in your own terminal: `{cmd}`" in d.reason


def test_a_powershell_hand_command_with_sensitive_text_is_not_repeated(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(_toml(None).replace(
        "[guard]", '[sensitive]\npatterns = ["PATIENT-\\\\d+"]\n\n[guard]'))
    p = load(tmp_path)
    cmd = "git commit -m PATIENT-1234; git push origin main"
    d = act(p, tool("PowerShell", "bypassPermissions", command=cmd), "attended")
    assert d.action == "deny"
    assert "PATIENT-1234" not in d.reason


# ---------- through the hook ----------


def run_hook(event, cwd, role):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd), "WORKFLOW_ROLE": role}
    env.pop("WORKFLOW_EXPERIENCE", None)
    return subprocess.run([sys.executable, str(CLI), "hook", "guard"], input=json.dumps(event),
                          capture_output=True, text=True, cwd=cwd, env=env)


def test_hook_prints_nothing_for_an_attended_get_childitem(prof):
    p = run_hook(tool("PowerShell", command="Get-ChildItem"), prof.root, "attended")
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == ""


def test_hook_refuses_powershell_in_a_ticket_session(prof):
    p = run_hook(tool("PowerShell", command="Get-ChildItem"), prof.root, "ticket")
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "the guard can't read PowerShell; use Bash" in out["permissionDecisionReason"]


# ---------- the can't-decide fallbacks read the command too ----------


@pytest.mark.parametrize("name", ["Monitor", "PowerShell"])
def test_fallback_py_reads_a_monitor_or_powershell_command(name):
    assert fallback.push_or_merge(tool(name, command=PUSH)) == "push"
    assert fallback.push_or_merge(tool(name, command=MERGE)) == "merge"
    assert fallback.push_or_merge(tool(name, command="ls")) is None
    assert fallback.push_or_merge(tool(name, ws="wss://x")) is None
    assert fallback.push_or_merge(tool("Read", command=PUSH)) is None


def _shell_decision(event_text, project):
    p = subprocess.run(["sh", str(KIT / "scripts/workflow/fallback.sh")], input=event_text, capture_output=True,
                       text=True, env={"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(project)})
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None


@pytest.mark.parametrize("name", ["Bash", "Monitor", "PowerShell", "Read"])
@pytest.mark.parametrize("cmd", [PUSH, MERGE, "ls", "git `\npush", "git \\\npush", "Get-ChildItem"])
@pytest.mark.parametrize("mode", [None, "default", "dontAsk"])
def test_the_shell_fallback_reads_them_as_fallback_py_does(tmp_path, name, cmd, mode):
    event = tool(name, mode, command=cmd)
    want = fallback.decide(event, False, "why")
    assert _shell_decision(json.dumps(event), tmp_path) == (want[0] if want else None)


@pytest.mark.parametrize("name", ["Monitor", "PowerShell"])
def test_the_fallbacks_never_repeat_the_command(tmp_path, name):
    event = tool(name, "dontAsk", command=PUSH)
    reason = fallback.decide(event, False, "why")[1]
    assert PUSH not in reason and "run it yourself in your own terminal" in reason


# ---------- what set-up installs ----------

SEEN = ("Bash", "Monitor", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit",
        "mcp__github__push_files", "mcp__GitHub__merge_pull_request")


def _guard_matchers(hooks):
    return [e["matcher"] for e in hooks["PreToolUse"] if "hook guard" in json.dumps(e)]


def test_the_matcher_sees_monitor_and_powershell_alongside_the_rest():
    for name in SEEN:
        assert re.fullmatch(vendor.GUARD_MATCHER, name), name
    for name in ("Read", "Grep", "WebFetch", "mcp__notion__search"):
        assert not re.fullmatch(vendor.GUARD_MATCHER, name), name


def test_vendored_settings_and_the_plugins_hooks_file_carry_the_matcher():
    settings = vendor.merge_hooks({})
    on_disk_file = json.loads((KIT / "hooks/hooks.json").read_text())
    for hooks in (settings["hooks"], vendor.plugin_hooks()["hooks"], on_disk_file["hooks"]):
        (matcher,) = _guard_matchers(hooks)
        assert matcher == vendor.GUARD_MATCHER
        assert {"Monitor", "PowerShell"} <= set(matcher.split("|"))


# ---------- docs ----------


def _doc():
    return (KIT / "docs/enforcement.md").read_text()


def test_enforcement_md_lists_exactly_the_tools_the_guard_sees():
    (line,) = [l for l in _doc().splitlines() if l.startswith("**The tools the guard sees:**")]
    listed = line.split(". ")[0]  # the list itself, before what it is
    named = set(re.findall(r"`([^`]+)`", listed))
    assert named == {"Bash", "Monitor", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit", "mcp__…github…"}
    plain = {n for n in named if "…" not in n}
    assert plain == {t for t in vendor.GUARD_MATCHER.split("|") if t.isalpha()}


def test_enforcement_md_records_the_release_gate_step_for_item_10():
    (line,) = [l for l in _doc().splitlines() if l.startswith("**Release gate (item 10):**")]
    assert "tools reference" in line
    assert "finding" in line
    assert "runs commands" in line
    assert "#36" in line

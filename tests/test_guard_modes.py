"""Modes that never ask (#52): in an attended session, the guard's asks become
denies when the event's `permission_mode` is one where nobody is asked.

Every command here is data passed to `decide` or the hook; none is run.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import modes
from workflow.guard import decide
from workflow.profile import load

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"

ASKING = ["default", "acceptEdits", "auto", "plan", None]  # None: the field absent
NEVER = ["bypassPermissions", "dontAsk", "turbo"]
ALL_MODES = ASKING + NEVER


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


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def mcp_write():
    return {
        "tool_name": "mcp__github__create_or_update_file",
        "tool_input": {"owner": "acme", "repo": "demo", "path": "README.md", "content": "x", "message": "m", "branch": "main"},
    }


def with_mode(event, mode, **extra):
    ev = dict(event, **extra)
    if mode is not None:
        ev["permission_mode"] = mode
    return ev


def act(profile, event, mode, role="attended", branch="feature", **extra):
    return decide(with_mode(event, mode, **extra), profile, role, profile.root, branch)


ATTENDED_ASKS = {
    "base-branch push": bash("git push origin main"),
    "feature force-push": bash("git push --force origin feature"),
    "deploy command": bash("scripts/deploy.sh staging"),
    "admin merge": bash("gh pr merge 5 --admin"),
    "GitHub MCP write": mcp_write(),
}


# ---------- the shared list of modes ----------


def test_modes_classify_as_the_spec_says():
    for m in ("default", "acceptEdits", "auto", "plan", None):
        assert not modes.never_asks(m), m
    for m in ("bypassPermissions", "dontAsk", "turbo", "", 5):
        assert modes.never_asks(m), m


def test_modes_module_parses_as_python_3_7():
    ast.parse((KIT / "scripts/workflow/modes.py").read_text(), feature_version=(3, 7))


def test_modes_module_imports_nothing():
    tree = ast.parse((KIT / "scripts/workflow/modes.py").read_text())
    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]


# ---------- attended asks ----------


@pytest.mark.parametrize("what", list(ATTENDED_ASKS))
@pytest.mark.parametrize("mode", ASKING)
def test_attended_ask_stays_an_ask_in_modes_that_ask(prof, what, mode):
    assert act(prof, ATTENDED_ASKS[what], mode).action == "ask"


@pytest.mark.parametrize("what", list(ATTENDED_ASKS))
@pytest.mark.parametrize("mode", NEVER)
def test_attended_ask_is_refused_in_modes_that_never_ask(prof, what, mode):
    asked = act(prof, ATTENDED_ASKS[what], None)
    d = act(prof, ATTENDED_ASKS[what], mode)
    assert d.action == "deny"
    assert d.reason.startswith(asked.reason)
    extra = d.reason[len(asked.reason):]
    assert f"`{mode}`" in extra
    assert "would have asked" in extra
    assert "Shift+Tab" in extra


@pytest.mark.parametrize("cmd", ["git push origin main", "scripts/deploy.sh staging", "gh pr merge 5 --admin"])
def test_bash_refusal_gives_the_command_to_run_by_hand(prof, cmd):
    d = act(prof, bash(cmd), "bypassPermissions")
    assert f"`{cmd}`" in d.reason
    assert "your own terminal" in d.reason


def test_mcp_refusal_says_do_it_on_github(prof):
    d = act(prof, mcp_write(), "dontAsk")
    assert "on GitHub" in d.reason
    assert "terminal" not in d.reason


def test_unknown_mode_is_named(prof):
    d = act(prof, bash("scripts/deploy.sh"), "turbo")
    assert d.action == "deny"
    assert "`turbo`" in d.reason and "doesn't know" in d.reason


def test_a_mode_that_isnt_text_is_named(prof):
    d = act(prof, bash("scripts/deploy.sh"), 5)
    assert d.action == "deny" and "`5`" in d.reason


def test_known_never_ask_mode_isnt_called_unknown(prof):
    assert "doesn't know" not in act(prof, bash("scripts/deploy.sh"), "bypassPermissions").reason


@pytest.mark.parametrize(
    "mode, shown",
    [("", '`""`'), ("  ", '`"  "`'), ("a\nb", '`"a\\nb"`'), (" default", '`" default"`'), (["x"], '`["x"]`'), ({"k": 1}, '`{"k": 1}`')],
)
def test_odd_modes_are_named_readably(prof, mode, shown):
    d = act(prof, bash("scripts/deploy.sh"), mode)
    assert d.action == "deny"
    first = d.reason.split("\n")[1]
    assert shown in first and "doesn't know" in first


# ---------- unchanged: ticket and conductor, denies, allows ----------

EVENTS = [
    *ATTENDED_ASKS.values(),
    bash("ls -la"),
    bash("git status"),
    bash("git push origin claude/build-7"),
    bash("git push --force origin claude/build-7"),
    {"tool_name": "Read", "tool_input": {"file_path": "README.md"}},
    {"tool_name": "mcp__github__issue_read", "tool_input": {"owner": "acme", "repo": "demo", "issue_number": 1, "method": "get"}},
]


@pytest.mark.parametrize("role", ["ticket", "conductor"])
@pytest.mark.parametrize("i", range(len(EVENTS)))
def test_ticket_and_conductor_decisions_are_the_same_in_every_mode(prof, role, i):
    first = act(prof, EVENTS[i], None, role=role, branch="claude/build-7")
    for mode in ALL_MODES:
        assert act(prof, EVENTS[i], mode, role=role, branch="claude/build-7") == first, mode


SOLO_DENIES = [
    bash("git push origin main"),
    bash("git push -u origin HEAD:main"),
    bash("gh pr merge 5 --admin"),
    bash("gh api -X DELETE repos/acme/demo/rulesets/42"),
]


@pytest.mark.parametrize("i", range(len(SOLO_DENIES)))
def test_denies_are_unchanged_in_every_mode(solo, i):
    first = act(solo, SOLO_DENIES[i], None)
    assert first.action == "deny"
    for mode in ALL_MODES:
        assert act(solo, SOLO_DENIES[i], mode) == first, mode


@pytest.mark.parametrize("ev", [bash("ls"), bash("git status"), bash("git push origin feature"), {"tool_name": "Read", "tool_input": {"file_path": "x"}}])
def test_allows_are_unchanged_in_every_mode(prof, ev):
    for mode in ALL_MODES:
        assert act(prof, ev, mode).action == "allow", mode


# ---------- subagents ----------


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.parametrize("what", list(ATTENDED_ASKS))
def test_a_subagents_event_gets_the_sessions_decision(prof, mode, what):
    own = act(prof, ATTENDED_ASKS[what], mode)
    sub = act(prof, ATTENDED_ASKS[what], mode, agent_id="a1b2c3", agent_type="Explore")
    assert sub == own


# ---------- solo mode's remaining asks ----------


SOLO_ASKS = {
    "feature force-push": bash("git push --force origin feature"),
    "ruleset create": bash("gh api -X POST repos/acme/demo/rulesets --input ruleset.json"),
    "MCP ruleset create": {"tool_name": "mcp__github__create_repository_ruleset", "tool_input": {"owner": "acme", "repo": "demo"}},
}


@pytest.mark.parametrize("what", list(SOLO_ASKS))
def test_solo_mode_asks_are_refused_in_bypass_permissions(solo, what):
    asked = act(solo, SOLO_ASKS[what], None)
    assert asked.action == "ask"
    d = act(solo, SOLO_ASKS[what], "bypassPermissions")
    assert d.action == "deny" and d.reason.startswith(asked.reason)


# ---------- end to end through the hook ----------


def run_hook(event, cwd, env_extra):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd), **env_extra}
    env.pop("WORKFLOW_EXPERIENCE", None)
    p = subprocess.run([sys.executable, str(CLI), "hook", "guard"], input=json.dumps(event), capture_output=True, text=True, cwd=cwd, env=env)
    return p


def test_hook_guard_denies_in_a_mode_that_never_asks(repo):
    ev = with_mode(bash("scripts/deploy.sh staging"), "bypassPermissions", cwd=str(repo))
    p = run_hook(ev, repo, {"WORKFLOW_ROLE": "attended"})
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "`bypassPermissions`" in out["permissionDecisionReason"]


def test_hook_guard_still_asks_in_default_mode(repo):
    ev = with_mode(bash("scripts/deploy.sh staging"), "default", cwd=str(repo))
    p = run_hook(ev, repo, {"WORKFLOW_ROLE": "attended"})
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


# ---------- docs ----------


def test_enforcement_doc_has_the_mode_table():
    doc = (KIT / "docs/enforcement.md").read_text()
    rows = {line.split("|")[1].strip(): line for line in doc.splitlines() if line.startswith("| ") and line.count("|") == 4}
    for mode in ("`default`", "`acceptEdits`", "`auto`", "`plan`", "none sent (an older Claude Code)"):
        assert rows[mode].split("|")[2].strip() == "prompts", mode
    for mode in ("`bypassPermissions`", "`dontAsk`", "any other value"):
        assert rows[mode].split("|")[2].strip().startswith("refused, with the guard's reason"), mode
    assert "names the value" in rows["any other value"]
    assert "refused by Claude Code" in rows["headless `claude -p` runs"]
    for line in rows.values():
        if "prompts" in line or "refused" in line:
            assert line.split("|")[3].strip() == "refused", line
    assert "no safeguard where nobody is asked" in doc
    assert "claude -p" in doc
    assert "the ruleset is what protects" in doc


def test_readme_row_covers_the_refusal_in_a_mode_that_never_asks():
    readme = (KIT / "README.md").read_text()
    row = next(line for line in readme.splitlines() if line.startswith("| **\"[workflow guard, …]"))
    assert "modes that ask" in row
    assert "nobody is asked" in row and "doesn't know" in row


def test_changelog_notes_the_change_under_unreleased():
    text = (KIT / "CHANGELOG.md").read_text()
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "#52" in unreleased


# ---------- sensitive data ----------


def _sensitive(root: Path):
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(_toml(None) + "[sensitive]\npatterns = ['\\bMRN-\\d{6}\\b']\n")
    return load(root)


@pytest.mark.parametrize(
    "event",
    [
        bash('gh issue comment 5 --body "about MRN-123456"'),
        {"tool_name": "mcp__github__add_issue_comment", "tool_input": {"owner": "acme", "repo": "demo", "issue_number": 5, "body": "about MRN-123456"}},
    ],
)
def test_a_sensitive_data_refusal_never_repeats_the_text_or_suggests_posting_it(tmp_path, event):
    p = _sensitive(tmp_path)
    asked = act(p, event, None)
    assert asked.action == "ask"
    d = act(p, event, "dontAsk")
    assert d.action == "deny" and d.reason.startswith(asked.reason)
    extra = d.reason[len(asked.reason):]
    assert "MRN-123456" not in extra
    assert "terminal" not in extra and "on GitHub" not in extra
    assert "sensitive-data pattern" in extra


def test_a_long_unknown_mode_is_shown_cut(prof):
    d = act(prof, bash("scripts/deploy.sh"), "x" * 200)
    assert "x" * 80 + "…" in d.reason and "x" * 81 not in d.reason

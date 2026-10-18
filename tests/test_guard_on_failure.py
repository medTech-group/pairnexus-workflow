"""#57: the guard's hook blocks on failure.

The guard's PreToolUse entry carries `"onFailure": "block"` and a 30-second
timeout, so a guard that times out, can't start or prints invalid output blocks
the tool in every role; the other hooks keep Claude Code's default. What set-up
installs and what `vendor update` rewrites (seam 3), the hook end to end with
the entry as installed (seam 2), and the docs and skills (seam 4).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_guard_no_python import (KINDS, LAYOUTS, MCP_TOOLS, MERGE, PUSH, Setup, _bash,
                                  _decision, _mcp)
from workflow import cli, vendor

KIT = Path(__file__).resolve().parents[1]
OTHERS = {"Stop": 15, "UserPromptSubmit": 10, "SessionStart": 600}

# The guard's entry as 0.1.8 wrote it into a project's settings.
GUARD_018 = {
    "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit|mcp__.*[Gg]it[Hh]ub.*",
    "hooks": [{
        "type": "command",
        "command": 'F="$CLAUDE_PROJECT_DIR/.claude/workflow/bin/workflow.py"; '
                   'if [ -f "$F" ] && command -v python3 >/dev/null 2>&1; then exec python3 -B "$F" hook guard; fi; exit 0',
        "timeout": 15,
    }],
}
OWN_PRE = {"matcher": "Bash", "hooks": [{"type": "command", "command": "./scripts/lint-hook.sh", "timeout": 5}]}
OWN_STOP = {"hooks": [{"type": "command", "command": "./scripts/notify.sh"}]}


def _kit_entries(hooks, event):
    return [e for e in hooks.get(event, []) if any(vendor.HOOK_TAG in h["command"] or "CLAUDE_PLUGIN_ROOT" in h["command"]
                                                   for h in e["hooks"])]


def _all_hooks():
    on_disk = json.loads((KIT / "hooks/hooks.json").read_text())["hooks"]
    return {"vendored": vendor.merge_hooks({})["hooks"], "plugin": vendor.plugin_hooks()["hooks"], "hooks.json": on_disk}


# ---------- what set-up installs (seam 3) ----------


@pytest.mark.parametrize("where", ["vendored", "plugin", "hooks.json"])
def test_the_guards_entry_blocks_on_failure_with_a_30_second_timeout(where):
    (entry,) = _kit_entries(_all_hooks()[where], "PreToolUse")
    assert entry["matcher"] == vendor.GUARD_MATCHER
    (hook,) = entry["hooks"]
    assert hook["onFailure"] == "block"
    assert hook["timeout"] == 30


@pytest.mark.parametrize("where", ["vendored", "plugin", "hooks.json"])
def test_the_other_hooks_keep_the_default_and_their_timeouts(where):
    hooks = _all_hooks()[where]
    for event, timeout in OTHERS.items():
        (entry,) = _kit_entries(hooks, event)
        (hook,) = entry["hooks"]
        assert hook.get("onFailure", "continue") == "continue", event
        assert hook["timeout"] == timeout, event


def test_the_guards_budget_stays_under_its_timeout():
    # The guard refuses with its own reason before Claude Code's timeout cuts it off.
    assert cli.GUARD_BUDGET == 27
    assert cli.GUARD_BUDGET < vendor.KIT_HOOKS["PreToolUse"][0]["hooks"][0]["timeout"]


def test_vendor_update_rewrites_a_0_1_8_guard_entry_and_keeps_the_projects_hooks(tmp_path):
    vendor.install(KIT, tmp_path, None, no_mattpocock=True)
    settings_file = tmp_path / vendor.SETTINGS
    settings = json.loads(settings_file.read_text())
    settings["hooks"]["PreToolUse"] = [OWN_PRE, GUARD_018]
    settings["hooks"]["Stop"] = [OWN_STOP] + settings["hooks"]["Stop"]
    settings["permissions"] = {"allow": ["Bash(ls:*)"]}
    settings_file.write_text(json.dumps(settings, indent=2))

    vendor.install(KIT, tmp_path, None, no_mattpocock=True, update=True)
    after = json.loads(settings_file.read_text())
    (guard,) = _kit_entries(after["hooks"], "PreToolUse")
    assert guard == vendor.KIT_HOOKS["PreToolUse"][0]
    assert guard["matcher"] == vendor.GUARD_MATCHER
    assert guard["hooks"][0]["onFailure"] == "block" and guard["hooks"][0]["timeout"] == 30
    assert GUARD_018 not in after["hooks"]["PreToolUse"]
    assert OWN_PRE in after["hooks"]["PreToolUse"]
    assert OWN_STOP in after["hooks"]["Stop"]
    assert after["permissions"] == {"allow": ["Bash(ls:*)"]}


# ---------- the hook end to end, as installed (seam 2) ----------


class Installed(Setup):
    """Runs the guard's command exactly as the installed entry has it."""

    def run(self, sub, event, **env):
        hooks = vendor.plugin_hooks()["hooks"] if self.layout == "plugin" else vendor.merge_hooks({})["hooks"]
        (entry,) = _kit_entries(hooks, "PreToolUse")
        assert entry["hooks"][0]["onFailure"] == "block"
        stdin = event if isinstance(event, str) else json.dumps(event)
        return subprocess.run([shutil.which("sh"), "-c", entry["hooks"][0]["command"]], input=stdin,
                              capture_output=True, text=True, env={**self.env, **env}, cwd=self.proj)


ATTENDED_EVENTS = (
    [_bash(c, m) for c in (PUSH, MERGE) for m in (None, "default", "dontAsk", "someNewMode")]
    + [_mcp(t, m) for t in MCP_TOOLS for m in ("default", "dontAsk")]
    + [_bash("ls -la"), _bash("git status; echo push"),
       {"tool_name": "Edit", "tool_input": {"file_path": "notes.md", "old_string": "a", "new_string": PUSH}},
       {"tool_name": "Write", "tool_input": {"file_path": "x.sh", "content": f"#!/bin/sh\n{PUSH}\n"}},
       _mcp("mcp__github__issue_read"), "{}", "not json at all", ""]
)


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("kind", KINDS + ("working",))
@pytest.mark.parametrize("solo", [False, True])
def test_every_attended_case_of_the_installed_guard_exits_0(tmp_path, layout, kind, solo):
    s = Installed(tmp_path, layout, "missing" if kind == "working" else kind, solo=solo)
    if kind == "working":  # the real python3, so the CLI decides
        s.env["PATH"] = str(Path(shutil.which("python3")).parent) + ":" + s.env["PATH"]
    for event in ATTENDED_EVENTS:
        for role in ("attended", ""):
            p = s.run("guard", event, WORKFLOW_ROLE=role)
            _decision(p)  # exits 0, and any output is a decision with its reason
            assert p.returncode == 0, (event, role, p.stderr)


# ---------- docs and skills (seam 4) ----------


def test_enforcement_md_names_the_minimum_version_and_the_timeout():
    doc = (KIT / "docs/enforcement.md").read_text()
    assert "2.1.295" in doc
    assert '"onFailure": "block"' in doc
    assert "30-second timeout" in doc and "15-second" not in doc
    assert "27 seconds" in doc


def test_the_readme_covers_a_command_blocked_by_the_guards_timeout():
    readme = (KIT / "README.md").read_text()
    start = readme.index("### When something goes wrong")
    table = readme[start:readme.index("###", start + 4)]
    (row,) = [l for l in table.splitlines() if "timed out" in l or "timeout" in l]
    assert "30" in row and "split" in row and "2.1.295" in row


def test_the_claude_md_section_says_to_offer_splitting_a_timed_out_command():
    step = [l for l in (KIT / "skills/setup-workflow/SKILL.md").read_text().splitlines()
            if l.startswith("**8. A \"Workflow\" section in `CLAUDE.md`.**")]
    (line,) = step
    assert "times out" in line and "split or simplify" in line


def test_update_workflow_names_the_rewritten_guard_entry_in_its_pr():
    skill = (KIT / "skills/update-workflow/SKILL.md").read_text()
    (line,) = [l for l in skill.splitlines() if l.startswith("8. **The PR,**")]
    assert "guard's hook entry" in line and "onFailure" in line


def test_the_changelog_notes_it_under_unreleased_without_a_version_bump():
    log = (KIT / "CHANGELOG.md").read_text()
    unreleased = log[log.index("## Unreleased"):log.index("\n## ", log.index("## Unreleased") + 1)]
    assert "#57" in unreleased and "guard's hook entry" in unreleased
    assert (KIT / "VERSION").read_text().strip() == "0.1.11"

"""#56: the hook commands' can't-decide fallback without a working python3,
in a vendored project and in the plugin.

The hook commands run under `sh` with an event on stdin (seam 2: the hook end
to end), with python3 old (a real 3.9 when there is one, else `_old_python`
run by the current Python, as #53's tests do), missing, and failing (a stub
exiting non-zero). Then what set-up installs (seam 3) and the docs (seam 4).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import fallback, vendor

KIT = Path(__file__).resolve().parents[1]
KINDS = ("old", "missing", "failing")
LAYOUTS = ("vendored", "plugin")
ASKING = (None, "default", "acceptEdits", "auto", "plan")
NEVER_ASKING = ("bypassPermissions", "dontAsk", "someNewMode")
PUSH = "git push origin main"
MERGE = "gh pr merge 12 --merge"
MCP_TOOLS = (
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
    "mcp__github__delete_file",
    "mcp__github__merge_pull_request",
)


def _bash(command, mode=None):
    event = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": command}}
    if mode is not None:
        event["permission_mode"] = mode
    return event


def _mcp(tool, mode=None):
    event = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"owner": "o", "repo": "r"}}
    if mode is not None:
        event["permission_mode"] = mode
    return event


def _old_python_binary():
    for cand in (os.environ.get("OLD_PYTHON"), shutil.which("python3.9")):
        if cand and Path(cand).exists():
            return cand
    found = sorted(Path.home().glob(".local/share/uv/python/cpython-3.9*/bin/python3.9"))
    return str(found[0]) if found else None


def _path(tmp_path, kind):
    """A PATH with sh, awk, git and the like, and python3 as `kind` says."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("sh", "tr", "sed", "awk", "head", "printf", "cat", "env", "git"):
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    py = bindir / "python3"
    if kind == "failing":
        py.write_text("#!/bin/sh\nexit 1\n")
        py.chmod(0o755)
    elif kind == "old" and _old_python_binary():
        py.symlink_to(_old_python_binary())
    elif kind == "old":
        # `python3 -B <the CLI> hook …`, handed to _old_python as the entry point does on a 3.9.
        run = (
            "import os,sys; sys.path.insert(0, os.path.dirname(sys.argv[1])); "
            "from workflow import _old_python; sys.exit(_old_python.main(sys.argv[2:]))"
        )
        py.write_text(f"#!/bin/sh\nshift\nexec {sys.executable} -B -c '{run}' \"$@\"\n")
        py.chmod(0o755)
    return str(bindir)


def _kit_at(cli: Path):
    cli.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(KIT / "scripts/workflow", cli.with_suffix(""), ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(KIT / "scripts/workflow.py", cli)


class Setup:
    def __init__(self, tmp_path, layout, kind, solo=False):
        self.layout = layout
        self.proj = tmp_path / "proj"
        self.proj.mkdir()
        plugin = tmp_path / "plugin"
        if layout == "vendored":
            _kit_at(self.proj / vendor.HOOK_TAG)
        else:
            _kit_at(plugin / "scripts/workflow.py")
        if solo:
            (self.proj / ".claude/workflow").mkdir(parents=True, exist_ok=True)
            (self.proj / ".claude/workflow/profile.toml").write_text("[project]\nname = \"x\"\n\n[repo]\nruleset = false\n")
        self.env = {"PATH": _path(tmp_path, kind), "CLAUDE_PROJECT_DIR": str(self.proj),
                    "CLAUDE_PLUGIN_ROOT": str(plugin), "WORKFLOW_ROLE": "attended"}

    def run(self, sub, event, **env):
        cmd = vendor.hook_command(sub, plugin=self.layout == "plugin")
        stdin = event if isinstance(event, str) else json.dumps(event)
        return subprocess.run([shutil.which("sh"), "-c", cmd], input=stdin, capture_output=True, text=True,
                              env={**self.env, **env}, cwd=self.proj)


def _decision(p):
    assert p.returncode == 0, (p.returncode, p.stderr)
    if not p.stdout.strip():
        return None
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecisionReason"]
    return out["permissionDecision"]


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("kind", KINDS)
def test_attended_push_and_merge_are_asked_or_refused(tmp_path, layout, kind):
    s = Setup(tmp_path, layout, kind)
    for command in (PUSH, MERGE):
        for mode in ASKING:
            assert _decision(s.run("guard", _bash(command, mode))) == "ask", (command, mode)
        for mode in NEVER_ASKING:
            assert _decision(s.run("guard", _bash(command, mode))) == "deny", (command, mode)
    for tool in MCP_TOOLS:
        assert _decision(s.run("guard", _mcp(tool))) == "ask", tool
        assert _decision(s.run("guard", _mcp(tool, "default"))) == "ask", tool
        assert _decision(s.run("guard", _mcp(tool, "dontAsk"))) == "deny", tool


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("kind", KINDS)
def test_attended_solo_mode_refuses_a_push_or_a_merge(tmp_path, layout, kind):
    s = Setup(tmp_path, layout, kind, solo=True)
    for event in (_bash(PUSH), _bash(MERGE, "default"), _mcp("mcp__github__merge_pull_request", "acceptEdits")):
        p = s.run("guard", event)
        assert _decision(p) == "deny", event
        assert "ruleset = false" in json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("kind", KINDS)
def test_attended_anything_else_prints_nothing_and_exits_0(tmp_path, layout, kind):
    s = Setup(tmp_path, layout, kind)
    others = [
        _bash("ls -la"),
        _bash("git status; echo push"),
        _bash("gh pr view 3 && echo merge"),
        {"tool_name": "Edit", "permission_mode": "bypassPermissions",
         "tool_input": {"file_path": "notes.md", "old_string": "a", "new_string": f"run {PUSH}, then {MERGE}"}},
        {"tool_name": "Write", "tool_input": {"file_path": "x.sh", "content": f"#!/bin/sh\n{PUSH}\n"}},
        _mcp("mcp__github__issue_read"),
        "{}",
        "not json at all",
    ]
    for event in others:
        p = s.run("guard", event)
        assert (p.returncode, p.stdout) == (0, ""), (event, p.stdout, p.stderr)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_a_run_is_still_refused_every_tool(tmp_path, kind, role):
    s = Setup(tmp_path, "vendored", kind)
    for event in (_bash("ls"), {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}, _bash(PUSH)):
        assert _decision(s.run("guard", event, WORKFLOW_ROLE=role)) == "deny", event


def test_the_restore_commands_still_pass_with_the_kit_missing(tmp_path):
    env = {"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(tmp_path), "WORKFLOW_ROLE": "ticket"}
    cmd = vendor.hook_command("guard")
    for command in vendor.RESTORE_COMMANDS:
        p = subprocess.run(["sh", "-c", cmd], input=json.dumps(_bash(command)), capture_output=True, text=True, env=env)
        assert (p.returncode, p.stdout) == (0, ""), command
    p = subprocess.run(["sh", "-c", cmd], input=json.dumps(_bash("ls")), capture_output=True, text=True, env=env)
    assert _decision(p) == "deny" and "missing" in p.stdout


@pytest.mark.parametrize("kind", KINDS)
def test_the_plugin_never_refuses_every_tool(tmp_path, kind):
    # Without a python3 that runs, whatever WORKFLOW_ROLE says. An old python3
    # still runs the old-Python fallback, which reads the role as the
    # CLI does.
    s = Setup(tmp_path, "plugin", kind)
    for role in ("attended", "") if kind == "old" else ("attended", "ticket", "conductor", ""):
        assert _decision(s.run("guard", _bash("ls"), WORKFLOW_ROLE=role)) is None, role
        assert _decision(s.run("guard", _bash(PUSH), WORKFLOW_ROLE=role)) in ("ask", "deny"), role


@pytest.mark.parametrize("kind", KINDS)
def test_the_plugins_session_start_says_what_is_wrong(tmp_path, kind):
    s = Setup(tmp_path, "plugin", kind)
    p = s.run("repair", "{}")
    assert p.returncode == 0, p.stderr
    message = json.loads(p.stdout)["systemMessage"]
    assert "python3" in message.lower() and "3.11" in message


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("sub", ["gate", "context"])
def test_the_other_hooks_stay_quiet(tmp_path, layout, sub):
    s = Setup(tmp_path, layout, "missing")
    p = s.run(sub, "{}")
    assert (p.returncode, p.stdout) == (0, "")


# The raw-text match: the shell's reading of an event agrees with fallback.py --

PARITY = [
    PUSH,
    MERGE,
    "git -C repo push --force-with-lease",
    "/usr/bin/git push",
    "cd x && git push",
    "git add . ; git commit -m 'push it'",
    "git commit -m wip\ngit push",
    "git \\\npush origin main",
    "git \\npush",
    "echo \"x\\\"; git push\"",
    "git status; echo push",
    "echo git | xargs push",
    "github push",
    "git pushy",
    "GIT PUSH",
    "gh pr view && gh pr merge 3",
    "gh pr create --title merge",
    "gh merge pr",
    "gh pr merge",
    "git-push",
    "my_git push",
    "ls -la",
    "",
]


def _shell_decision(event_text, project):
    p = subprocess.run(["sh", str(KIT / "scripts/workflow/fallback.sh")], input=event_text, capture_output=True,
                       text=True, env={"PATH": os.environ["PATH"], "CLAUDE_PROJECT_DIR": str(project)})
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None


@pytest.mark.parametrize("command", PARITY)
def test_the_shell_reads_a_command_as_fallback_py_does(tmp_path, command):
    for mode in (None, "default", "dontAsk", "x"):
        event = _bash(command, mode)
        want = fallback.decide(event, False, "why")
        assert _shell_decision(json.dumps(event), tmp_path) == (want[0] if want else None), (command, mode)


def test_the_shell_reads_only_the_command(tmp_path):
    # The words in a description, a file's content or another tool's input never count.
    events = [
        {"tool_name": "Bash", "tool_input": {"description": PUSH, "command": "ls"}},
        {"tool_name": "Bash", "tool_input": {"command": "ls", "description": f"\"command\": \"{PUSH}\""}},
        {"tool_name": "Edit", "tool_input": {"file_path": "a", "new_string": json.dumps({"command": PUSH})}},
        {"tool_name": "mcp__other__run", "tool_input": {"command": PUSH}},
        {"tool_name": "mcp__github__create_pull_request", "tool_input": {"body": MERGE}},
    ]
    for event in events:
        assert _shell_decision(json.dumps(event), tmp_path) is None, event


def test_the_shell_reads_the_solo_line_as_fallback_py_does(tmp_path):
    profile = tmp_path / ".claude/workflow/profile.toml"
    profile.parent.mkdir(parents=True)
    texts = [
        "ruleset = false\n",
        "\ufeffruleset = false\n",
        "[repo]\n  ruleset=false # solo\n",
        "ruleset = true\nruleset = false\n",
        'ruleset = "false"\nruleset = false\n',
        "ruleset = falsey\n",
        "# ruleset = false\n",
        "rulesets = false\n",
        "ruleset = false\r\n",
        "",
    ]
    for text in texts:
        profile.write_bytes(text.encode("utf-8"))
        want = fallback.decide(_bash(PUSH), fallback.solo(tmp_path), "why")[0]
        assert _shell_decision(json.dumps(_bash(PUSH)), tmp_path) == want, repr(text)


def test_the_shell_reads_a_truncated_or_spaced_event(tmp_path):
    event = json.dumps(_bash(PUSH, "dontAsk"), indent=2)
    assert _shell_decision(event, tmp_path) == "deny"
    assert _shell_decision(json.dumps(_bash(PUSH))[:-5], tmp_path) == "ask"
    assert _shell_decision('{"permission_mode": null, "tool_name": "Bash", "tool_input": {"command": "git push"}}',
                           tmp_path) == "ask"
    assert _shell_decision('{"permission_mode": 3, "tool_name": "Bash", "tool_input": {"command": "git push"}}',
                           tmp_path) == "deny"


# What set-up installs (seam 3) ------------------------------------------------


def test_the_plugins_hooks_file_is_the_vendored_hooks_rooted_at_the_plugin():
    hooks = json.loads((KIT / "hooks/hooks.json").read_text())
    assert hooks == vendor.plugin_hooks(), "regenerate hooks/hooks.json (see vendor.plugin_hooks)"
    for event, entries in vendor.KIT_HOOKS.items():
        (mine,) = hooks["hooks"][event]
        (theirs,) = entries
        assert mine.get("matcher") == theirs.get("matcher")
        assert mine["hooks"][0]["timeout"] == theirs["hooks"][0]["timeout"]
        command = mine["hooks"][0]["command"]
        assert vendor.PLUGIN_CLI in command and "CLAUDE_PROJECT_DIR" not in command
        assert "command -v python3" in command and "python3 -B" in command
    guard = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "fallback.sh" in guard and "fallback.sh" in vendor.KIT_HOOKS["PreToolUse"][0]["hooks"][0]["command"]
    assert "WORKFLOW_ROLE" not in guard  # attended only: it never refuses every tool


def test_vendoring_copies_the_shell_fallback():
    files = vendor.plan(KIT, None)
    assert files[".claude/workflow/bin/workflow/fallback.sh"] == KIT / "scripts/workflow/fallback.sh"


# Docs (seam 4) ----------------------------------------------------------------


def test_install_docs_say_plugin_mode_fails_like_vendored():
    text = " ".join((KIT / "docs/install.md").read_text().split())
    assert "plugin mode fails the same way as vendored" in text.lower()
    assert "pushes and merges are still asked" in text

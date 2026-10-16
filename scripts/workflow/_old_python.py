"""The kit's hooks on a Python older than 3.11 (#22).

The kit needs Python 3.11 (tomllib), but `python3` on a person's own machine
is often older (macOS's is 3.9). The entry point used to exit 1 there, which
Claude Code reads as a hook error and then runs the tool anyway: every hook
failed open. `scripts/workflow.py` hands an old Python to this module instead,
which fails closed where the kit would:
- `hook guard`: a ticket or conductor session (WORKFLOW_ROLE set to anything
  but `attended`, or with it unset and the kit set up, a branch matching the
  profile's `run.ticket_branch`, read roughly) is refused every tool; an
  attended session is asked before a push or a merge (git, `gh pr merge`, the
  GitHub MCP tools that push or merge), and otherwise left alone;
- `hook repair` (SessionStart): says what is wrong and how to fix it;
- `hook gate` and `hook context`: nothing (nothing to check without the kit);
- anything else: says what it needs and exits 1.

Keep it to the standard library and to syntax Python 3.7 reads (a test
checks): it runs on exactly the interpreters the rest of the kit can't. It
never raises: an error refuses the tool when WORKFLOW_ROLE is firm.
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

from . import modes  # noqa: F401  the modes that never ask, shared with the guard (#52)

NEEDS = "3.11"
DEFAULT_TICKET_BRANCH = "claude/build-*"
_PUSH = re.compile(r"\bgit\b[^;&|\n]*\bpush\b")
_MERGE = re.compile(r"\bgh\b[^;&|\n]*\bpr\b[^;&|\n]*\bmerge\b")
_TICKET_BRANCH = re.compile(r"""^\s*ticket_branch\s*=\s*["']([^"']+)["']""", re.M)
_MCP_PUSH = ("merge_pull_request", "push_files", "create_or_update_file", "delete_file")


def _branch(where):
    if not where:
        return None
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=where,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    b = out.stdout.strip()
    return b if out.returncode == 0 and b and b != "HEAD" else None


def _ticket_branch(root):
    """The profile's run.ticket_branch, or None when the kit isn't set up (the
    CLI never takes a role from the branch without a profile)."""
    try:
        with open(os.path.join(root, ".claude", "workflow", "profile.toml"), encoding="utf-8", errors="replace") as f:
            m = _TICKET_BRANCH.search(f.read())
    except (OSError, ValueError):
        return None
    return m.group(1) if m else DEFAULT_TICKET_BRANCH


def _env_firm(env):
    """True or False when WORKFLOW_ROLE decides, else None."""
    role = (env.get("WORKFLOW_ROLE") or "").strip().lower()
    return (role != "attended") if role else None


def _firm(env, cwd):
    """True for a ticket or conductor session, as roles.role decides it."""
    firm = _env_firm(env)
    if firm is not None:
        return firm
    root = env.get("CLAUDE_PROJECT_DIR") or cwd
    pattern = _ticket_branch(root)
    b = (_branch(cwd) or _branch(root)) if pattern else None
    return bool(b) and fnmatch.fnmatchcase(b, pattern)


def _problem(version):
    return (
        "the workflow kit needs Python {} or newer and `python3` here is {}, so its hooks can't check "
        "anything. Install Python {}+ (python.org, Homebrew or your package manager) so that `python3` "
        "runs it, then start a new session"
    ).format(NEEDS, version, NEEDS)


def _decision(decision, reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}


def _guard(event, firm, version):
    if firm:
        return _decision("deny", "Refused: " + _problem(version) + ".")
    if not isinstance(event, dict):
        return None
    tool = event.get("tool_name")
    i = event.get("tool_input")
    cmd = i.get("command") if tool == "Bash" and isinstance(i, dict) else None
    mcp = isinstance(tool, str) and tool.startswith("mcp__") and "github" in tool.lower() and tool.endswith(_MCP_PUSH)
    if mcp or (isinstance(cmd, str) and (_PUSH.search(cmd) or _MERGE.search(cmd))):
        return _decision("ask", "The workflow's guard isn't running: " + _problem(version) + ". Allow this push or merge only if you mean to.")
    return None


def _repair(firm, version):
    if firm:
        ctx = (
            "The workflow kit can't run in this session: " + _problem(version) + ". This is a ticket or "
            "conductor session, so every tool is refused until it can. Stop and tell the owner."
        )
    else:
        ctx = (
            "The workflow kit can't run in this session: " + _problem(version) + ". Its guard, checks and "
            "Stop gate are off; pushes and merges ask first. Tell the person before doing workflow work."
        )
    return {"systemMessage": "Workflow kit: " + _problem(version) + ".", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ctx}}


def main(argv, stdin_text=None, env=None, version=None, cwd=None):
    env = os.environ if env is None else env
    version = version or "{}.{}.{}".format(*sys.version_info[:3])
    if len(argv) < 2 or argv[0] != "hook":
        sys.stderr.write("workflow needs Python {} or newer (for tomllib); python3 here is {}\n".format(NEEDS, version))
        return 1
    sub = argv[1]
    if sub not in ("guard", "repair"):
        return 0
    try:
        out = _hook(sub, stdin_text, env, version, cwd)
    except Exception:  # never exit non-zero: Claude Code would run the tool
        out = None
        if sub == "guard" and _env_firm(env):
            out = _decision("deny", "Refused: " + _problem(version) + ".")
    if out is not None:
        print(json.dumps(out))
    return 0


def _hook(sub, stdin_text, env, version, cwd):
    if sub == "guard" and _env_firm(env):  # nothing to read: every tool is refused
        return _guard(None, True, version)
    text = sys.stdin.buffer.read().decode("utf-8", "replace") if stdin_text is None else stdin_text
    try:
        event = json.loads(text) if text.strip() else {}
    except (ValueError, RecursionError):
        event = None
    here = event.get("cwd") if isinstance(event, dict) and isinstance(event.get("cwd"), str) else None
    firm = _firm(env, here or (str(cwd) if cwd else os.getcwd()))
    return _guard(event, firm, version) if sub == "guard" else _repair(firm, version)

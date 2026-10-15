"""The kit's hooks on a Python older than 3.11 (#22).

The kit needs Python 3.11 (tomllib), but `python3` on a person's own machine
is often older (macOS's is 3.9). The entry point used to exit 1 there, which
Claude Code reads as a hook error and then runs the tool anyway: every hook
failed open. `scripts/workflow.py` hands an old Python to this module instead,
which fails closed where the kit would:
- `hook guard`: a ticket or conductor session (WORKFLOW_ROLE set to anything
  but `attended`, or with it unset a branch matching the profile's
  `run.ticket_branch`) is refused every tool; an attended session is asked
  before a push or a merge, and otherwise left alone;
- `hook repair` (SessionStart): says what is wrong and how to fix it;
- `hook gate` and `hook context`: nothing (nothing to check without the kit);
- anything else: says what it needs and exits 1.

Keep it to the standard library and to syntax Python 3.6 reads: it runs on
exactly the interpreters the rest of the kit can't.
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

NEEDS = "3.11"
DEFAULT_TICKET_BRANCH = "claude/build-*"
_PUSH = re.compile(r"\bgit\b[^;&|\n]*\bpush\b")
_MERGE = re.compile(r"\bgh\b[^;&|\n]*\bpr\b[^;&|\n]*\bmerge\b")
_TICKET_BRANCH = re.compile(r"""^\s*ticket_branch\s*=\s*["']([^"']+)["']""", re.M)


def _branch(where):
    if not where:
        return None
    try:
        out = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=where,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    b = out.stdout.strip()
    return b if out.returncode == 0 and b else None


def _ticket_branch(root):
    try:
        with open(os.path.join(root, ".claude", "workflow", "profile.toml"), encoding="utf-8") as f:
            m = _TICKET_BRANCH.search(f.read())
    except (OSError, ValueError):
        return DEFAULT_TICKET_BRANCH
    return m.group(1) if m else DEFAULT_TICKET_BRANCH


def _firm(env, cwd):
    """True for a ticket or conductor session, as roles.role decides it."""
    role = (env.get("WORKFLOW_ROLE") or "").strip().lower()
    if role:
        return role != "attended"
    root = env.get("CLAUDE_PROJECT_DIR") or cwd
    b = _branch(cwd) or _branch(root)
    return bool(b) and fnmatch.fnmatchcase(b, _ticket_branch(root))


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
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return None
    i = event.get("tool_input")
    cmd = i.get("command") if isinstance(i, dict) else None
    if isinstance(cmd, str) and (_PUSH.search(cmd) or _MERGE.search(cmd)):
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
    text = sys.stdin.read() if stdin_text is None else stdin_text
    try:
        event = json.loads(text) if text.strip() else {}
    except ValueError:
        event = None
    here = event.get("cwd") if isinstance(event, dict) and isinstance(event.get("cwd"), str) else None
    firm = _firm(env, here or (str(cwd) if cwd else os.getcwd()))
    out = _guard(event, firm, version) if sub == "guard" else _repair(firm, version)
    if out is not None:
        print(json.dumps(out))
    return 0

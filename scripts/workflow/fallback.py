"""The can't-decide fallback (#53): what the guard's hook decides when the guard can't.

When the guard raises or runs out of time, the profile is invalid, the hook's
event can't be read, or `python3` is older than 3.11 (`_old_python`), an
attended session gets this one rule:
- a push or a merge is asked;
- it is refused in solo mode (the profile's `ruleset = false`) or in a mode
  where nobody is asked (see `modes`);
- everything else is left alone: no decision.
Ticket and conductor sessions are refused every tool instead, by the callers.

"A push or a merge" is one definition, used by the CLI's error paths and by
the old-Python fallback alike: `git … push`, `gh … pr … merge`, and the GitHub
MCP tools that push, write files or merge.

Keep it to the standard library and `modes`, and to syntax Python 3.7 reads (a
test checks): the old-Python fallback runs it on exactly the interpreters the
rest of the kit can't, and the CLI runs it when the kit's own code has failed,
so it reads nothing through the kit (the profile's `ruleset` from its first
plain line, as `_old_python` reads `ticket_branch`).
"""

import json
import os
import re

from . import modes

# A push is `git` then `push`, a merge `gh` then `pr` then `merge`, each within
# one part of the command (split at ; & | and newlines). Matched word by word,
# so it stays linear on any input: a pattern like `git[^;]*push` backtracks.
_SEPARATORS = re.compile(r"[;&|\n]")
_PUSH = ("git", "push")
_MERGE = ("gh", "pr", "merge")
_WORDS = {w: re.compile(r"\b" + w + r"\b") for w in _PUSH + _MERGE}
_WHY_LIMIT = 200
MCP_PUSH = ("merge_pull_request", "push_files", "create_or_update_file", "delete_file")
# The tools that run a command: Monitor runs it as Bash does, PowerShell in PowerShell.
COMMAND_TOOLS = ("Bash", "Monitor", "PowerShell")
_RULESET = re.compile(r"^[ \t]*ruleset[ \t]*=[ \t]*(\w+)", re.M)
PROFILE = os.path.join(".claude", "workflow", "profile.toml")
FIXES = (
    "To fix it: run `python3 .claude/workflow/bin/workflow.py profile check`, check that `python3 --version` "
    "is 3.11 or newer, and if neither shows the problem, report the error to the kit's maintainers."
)


def _string_field(name):
    # A JSON string value: characters other than a quote or a backslash, or an
    # escape, up to its closing quote or, in a truncated event, the end.
    return re.compile(r'"' + name + r'"\s*:\s*"((?:[^"\\]|\\.)*)')


_LOOSE = {name: _string_field(name) for name in ("tool_name", "command", "permission_mode")}


def push_or_merge(event):
    """"push" or "merge" when `event` (a PreToolUse event, as a dict) is one
    (a file write through GitHub counts as a push), else None."""
    if not isinstance(event, dict):
        return None
    tool = event.get("tool_name")
    if not isinstance(tool, str):
        return None
    if tool.startswith("mcp__") and "github" in tool.lower() and tool.endswith(MCP_PUSH):
        return "merge" if tool.endswith("merge_pull_request") else "push"
    inp = event.get("tool_input")
    cmd = inp.get("command") if tool in COMMAND_TOOLS and isinstance(inp, dict) else None
    if not isinstance(cmd, str):
        return None
    if tool == "PowerShell":
        cmd = cmd.lower()  # PowerShell and Windows ignore case: `Git Push` runs git.exe
    # A line continuation (`\` in a shell, a backtick in PowerShell) joins its lines.
    cmd = cmd.replace("\r\n", "\n")
    parts = _SEPARATORS.split(cmd.replace("\\\n", " ").replace("`\n", " "))
    if any(_in_order(p, _PUSH) for p in parts):
        return "push"
    return "merge" if any(_in_order(p, _MERGE) for p in parts) else None


def _in_order(text, words):
    pos = 0
    for w in words:
        m = _WORDS[w].search(text, pos)
        if not m:
            return False
        pos = m.end()
    return True


def read_event(text):
    """The hook's event from its text: the JSON object, or, when the text isn't
    one, what can still be read of it (the tool, a command and the
    permission mode, as JSON strings); None when nothing can."""
    try:
        event = json.loads(text)
    except (ValueError, RecursionError, TypeError):
        event = None
    if isinstance(event, dict):
        return event
    if not isinstance(text, str):
        return None
    found = {}
    for name, pattern in _LOOSE.items():
        m = pattern.search(text)
        if m:
            try:
                found[name] = json.loads('"' + m.group(1) + '"')
            except ValueError:
                found[name] = m.group(1)
    if "tool_name" not in found:
        return None
    event = {"tool_name": found["tool_name"], "tool_input": {}}
    if "command" in found:
        event["tool_input"]["command"] = found["command"]
    if "permission_mode" in found:
        event["permission_mode"] = found["permission_mode"]
    return event


def solo_from_text(text):
    """True when the profile's first plain `ruleset = …` line says false (solo
    mode), whatever else the profile holds."""
    m = _RULESET.search((text or "").lstrip("\ufeff"))
    return bool(m) and m.group(1) == "false"


def solo(root):
    """Solo mode, read from the profile under `root` without the kit; False
    when it can't be read."""
    try:
        with open(os.path.join(str(root), PROFILE), encoding="utf-8", errors="replace") as f:
            return solo_from_text(f.read())
    except (OSError, ValueError):
        return False


def _shown(mode):
    plain = isinstance(mode, str) and mode and mode == mode.strip() and mode.isprintable()
    shown = mode if plain else json.dumps(mode, default=str)
    if len(shown) > 80:
        shown = shown[:80] + "…"
    longest = max([len(r) for r in re.findall(r"`+", shown)] or [0])
    fence = "`" * (longest + 1)
    return fence + shown + fence if not longest else fence + " " + shown + " " + fence


def mode_lines(mode):
    """Why an ask was refused in a mode that never asks, and how to be asked."""
    name = _shown(mode)
    if modes.known(mode):
        first = "The kit would have asked you about this, but nobody is asked in the {} permission mode, so it was refused.".format(name)
    else:
        first = (
            "The kit would have asked you about this, but the permission mode is {}, which the kit doesn't know, "
            "so it counts as one where nobody is asked and this was refused. Tell the kit's maintainers about this mode."
        ).format(name)
    return [first, "To be asked, switch the permission mode (Shift+Tab, or the mode selector)."]


def _by_hand(event):
    tool = event.get("tool_name") if isinstance(event, dict) else None
    if tool in COMMAND_TOOLS:
        # The guard couldn't check it for sensitive data, so it isn't repeated.
        return "Or run it yourself in your own terminal (the command isn't repeated here, since nothing could check it)."
    return "Or do it yourself on GitHub."


def decide(event, solo_mode, why, fixes=FIXES):
    """The fallback's (decision, reason) for `event` in an attended session, or
    None to leave it alone. `solo_mode`: the profile says `ruleset = false`.
    `why`: what went wrong, for the reason (cut short when long, since an
    error's text can quote the input); `fixes`: how to put it right."""
    what = push_or_merge(event)
    if not what:
        return None
    if len(why) > _WHY_LIMIT:
        why = why[:_WHY_LIMIT] + "…"
    head = "The workflow's guard isn't working, so it couldn't check this {}: {}. {}".format(what, why, fixes)
    mode = event.get("permission_mode")
    if solo_mode:
        lines = [head, "In solo mode (`ruleset = false` in the profile) a push or a merge the guard can't check is refused.", _by_hand(event)]
        return "deny", "\n".join(lines)
    if modes.never_asks(mode):
        return "deny", "\n".join([head] + mode_lines(mode) + [_by_hand(event)])
    return "ask", head + " Allow it only if you mean to."


def output(decision, reason):
    """The PreToolUse hook's output for a decision."""
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision, "permissionDecisionReason": reason}}

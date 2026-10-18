"""The kit's hooks on a Python older than 3.11 (#22).

The kit needs Python 3.11 (tomllib), but `python3` on a person's own machine
is often older (macOS's is 3.9). The entry point used to exit 1 there, which
Claude Code reads as a hook error and then runs the tool anyway: every hook
failed open. `scripts/workflow.py` hands an old Python to this module instead,
which fails closed where the kit would:
- `hook guard`: a ticket or conductor session (WORKFLOW_ROLE set to anything
  but `attended`, or with it unset and the kit set up, a branch matching the
  profile's `run.ticket_branch`, read roughly) is refused every tool; an
  attended session gets the can't-decide fallback (`fallback`, #53): a push or
  a merge is asked, or refused in solo mode and in a mode where nobody is
  asked, and everything else is left alone;
- `hook repair` (SessionStart): says what is wrong and how to fix it;
- `hook gate` and `hook context`: nothing (nothing to check without the kit);
- `doctor`: a short report (#61): Your computer's `python3` as a gap with its
  fix, and every other line the full doctor gives as `cant_check` until
  `python3` is 3.11 or newer, with the full doctor's ids, groups, JSON and
  `--strict`;
- anything else: says what it needs and exits 1.

Keep it to the standard library (and the kit's `fallback` and `modes`, which
keep to it too) and to syntax Python 3.7 reads (a test checks): it runs on
exactly the interpreters the rest of the kit can't. It never raises: an error
refuses the tool when WORKFLOW_ROLE is firm.
"""

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap

NEEDS = "3.11"
DEFAULT_TICKET_BRANCH = "claude/build-*"
_TICKET_BRANCH = re.compile(r"""^\s*ticket_branch\s*=\s*["']([^"']+)["']""", re.M)


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


def _guard(event, firm, version, root=None):
    if firm:
        return _decision("deny", "Refused: " + _problem(version) + ".")
    from . import fallback  # here, inside main's try: a ticket session's refusal never depends on it

    why = "`python3` here is {} and the kit needs Python {} or newer".format(version, NEEDS)
    fixes = "To fix it: install Python {}+ (python.org, Homebrew or your package manager) so that `python3` runs it, then start a new session.".format(NEEDS)
    d = fallback.decide(event, fallback.solo(root) if root else False, why, fixes)
    return _decision(*d) if d else None


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
    if argv and argv[0] == "doctor":
        return _doctor(argv[1:], env, version, cwd)
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
    from . import fallback  # here, inside main's try, as in _guard

    text = sys.stdin.buffer.read().decode("utf-8", "replace") if stdin_text is None else stdin_text
    event = fallback.read_event(text) if text.strip() else {}
    here = event.get("cwd") if isinstance(event, dict) and isinstance(event.get("cwd"), str) else None
    where = here or (str(cwd) if cwd else os.getcwd())
    firm = _firm(env, where)
    if sub != "guard":
        return _repair(firm, version)
    return _guard(event, firm, version, env.get("CLAUDE_PROJECT_DIR") or where)


# ---------- `workflow doctor`'s short report (#61) ----------
#
# The full doctor (doctor.py) needs 3.11. Here it gives the lines the full
# doctor gives when nothing is wrong, by their ids and groups: `python3` as a
# gap, every other line `cant_check` until `python3` is 3.11 or newer. A test
# on the supported Python compares them with the full doctor's lines, so a
# line added there is added here too.

_DOCTOR_GROUPS = ("Your computer", "The kit", "GitHub", "Cloud", "Previews")
_DOCTOR_STATUSES = ("gap", "cant_check", "note", "fine")
_DOCTOR_LABELS = {"gap": "gap", "cant_check": "can't check", "note": "note", "fine": "fine"}
# Every line but `computer.python3`, in the full doctor's check order: its
# group, its id, the install mode it is given in (None: both), and what it
# checks, for someone new to building and for a developer.
_DOCTOR_LINES = (
    ("Your computer", "computer.claude_code", None, "which version of Claude Code you have", "Claude Code's version"),
    ("The kit", "kit.profile", None, "the kit's profile (.claude/workflow/profile.toml)", "`profile check`"),
    ("The kit", "kit.hooks", "vendored", "the kit's hooks", "Kit hooks in .claude/settings.json"),
    ("The kit", "kit.plugin", "plugin", "whether the kit's plugin is turned on for this project", "Whether the plugin is enabled"),
    ("The kit", "kit.vendor", "vendored", "whether the kit's copy in this project is as the kit wrote it", "`vendor verify`"),
    ("The kit", "kit.experience", None, "the project's default for how much you know about building", "project.experience"),
    ("The kit", "kit.ruleset", None, "whether the project means its main branch to be protected", "project.ruleset"),
    ("GitHub", "github.ruleset", None, "whether the main branch is protected on GitHub", "The base branch's ruleset"),
    ("GitHub", "github.required_checks", None, "whether GitHub requires the checks the kit's profile lists", "Required checks"),
    ("GitHub", "github.up_to_date", None, "whether pull requests must be up to date with the main branch", '"Require branches to be up to date"'),
    ("GitHub", "github.approvals", None, "how many approvals GitHub requires", "Required approvals"),
    ("GitHub", "github.code_owner_review", None, "whether GitHub requires a review from the code owners", '"Require review from Code Owners"'),
    ("GitHub", "github.linear_history", None, "whether GitHub requires a straight-line history", '"Require linear history"'),
    ("GitHub", "github.merge_commits", None, "whether GitHub allows merge commits", "Merge commits allowed"),
    ("GitHub", "github.auto_merge", None, "whether GitHub allows auto-merge", "Auto-merge allowed"),
    ("GitHub", "github.codeowners", None, "whether CODEOWNERS asks you to review changes to the kit and CI", "CODEOWNERS for /.claude/ and /.github/workflows/"),
    ("Cloud", "cloud.environments", None, "the two cloud environments for unattended runs", "The cloud environments"),
    ("Cloud", "cloud.contents", None, "what the cloud environments hold", "Environment contents"),
)
# The flags the full doctor takes a value for: taken here, and not read.
_DOCTOR_VALUES = ("--claude-version", "--rulesets", "--repo", "--environments", "--runs")
_DOCTOR_STDIN = ("--rulesets", "--repo", "--environments", "--runs")
_DOCTOR_USAGE = (
    "usage: workflow doctor [--claude-version VERSION] [--rulesets F] [--repo F] [--environments F] [--runs F] [--json] [--strict]\n\n"
    "What's set up and what isn't; changes nothing. With `python3` older than {} it gives a short report: "
    "`python3` as a gap, and every other line as can't check until `python3` is {} or newer. "
    "Exits 0 (--strict: 1 on a gap or a line it couldn't check).\n"
).format(NEEDS, NEEDS)
_EXPERIENCE_LEVELS = ("new", "developer")
_EXPERIENCE_FILE_MAX = 200  # bytes, as profile.py reads it


def _doctor(args, env, version, cwd):
    """`workflow doctor` on an old Python: exit 0, or 1 with --strict (there
    is always a gap); 2 for arguments the full doctor refuses. Never raises."""
    try:
        opts = _doctor_args(args)
        if isinstance(opts, str):
            if opts == "help":
                sys.stdout.write(_DOCTOR_USAGE)
                return 0
            sys.stderr.write("workflow doctor: " + opts + "\n")
            return 2
        as_json, strict = opts
        r = _doctor_report(_doctor_root(env, cwd), env, version)
        print(json.dumps(r, indent=2) if as_json else _doctor_text(r, min(100, shutil.get_terminal_size((100, 24)).columns)))
        return 1 if strict and not r["strict_ok"] else 0
    except Exception:  # advice never ends in a traceback
        sys.stderr.write("workflow needs Python {} or newer (for tomllib); python3 here is {}\n".format(NEEDS, version))
        return 1


def _doctor_args(args):
    """(--json, --strict), "help", or why the full doctor would refuse them."""
    as_json = strict = False
    stdin = 0
    k = 0
    while k < len(args):
        a = args[k]
        name, eq, value = a.partition("=")
        if a in ("-h", "--help"):
            return "help"
        if a == "--json":
            as_json = True
        elif a == "--strict":
            strict = True
        elif name in _DOCTOR_VALUES and eq:
            stdin += name in _DOCTOR_STDIN and value == "-"
        elif a in _DOCTOR_VALUES:
            if k + 1 == len(args):
                return "argument {}: expected one argument".format(a)
            k += 1
            stdin += a in _DOCTOR_STDIN and args[k] == "-"
        else:
            return "unrecognized arguments: " + a
        k += 1
    if stdin > 1:
        return "only one of --rulesets, --repo, --environments and --runs can be standard input (-)"
    return as_json, strict


def _doctor_root(env, cwd):
    """CLAUDE_PROJECT_DIR, else the nearest folder holding .git, else the
    current one (profile.project_root)."""
    if env.get("CLAUDE_PROJECT_DIR"):
        return env["CLAUDE_PROJECT_DIR"]
    here = os.path.realpath(str(cwd) if cwd else os.getcwd())
    d = here
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return here
        d = up


def _level(value):
    if not isinstance(value, str):
        return None
    v = value.strip().lstrip("\ufeff").strip().lower()
    return v if v in _EXPERIENCE_LEVELS else None


def _experience_file(root):
    """The level in .workflow/experience, read as profile.py reads it, or None.
    Only a regular file is opened, so a pipe never waits."""
    try:
        path = os.path.join(root, ".workflow", "experience")
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as f:
            data = f.read(_EXPERIENCE_FILE_MAX + 1)
        if len(data) > _EXPERIENCE_FILE_MAX:
            return None
        lines = data.decode("utf-8").strip().splitlines()
    except (OSError, ValueError, TypeError):  # UnicodeDecodeError is a ValueError
        return None
    return _level(lines[0]) if len(lines) == 1 else None


def _experience(root, env):
    """(level, source): WORKFLOW_EXPERIENCE, else the local file, else unknown.
    The profile's default isn't read: that needs tomllib."""
    lvl = _level(env.get("WORKFLOW_EXPERIENCE"))
    if lvl:
        return lvl, "environment"
    lvl = _experience_file(root)
    return (lvl, "local file") if lvl else (None, "unknown")


def _doctor_line(group, id_, status, message, fix, level):
    pick = 1 if level == "developer" else 0
    return {"group": group, "id": id_, "status": status, "message": message[pick], "fix": fix[pick], "offer": None}


def _doctor_report(root, env, version):
    """The report as the full doctor's `--json` gives it."""
    level, source = _experience(root, env)
    wording = level or "new"
    mode = "vendored" if os.path.exists(os.path.join(root, ".claude", "workflow", "lock.json")) else "plugin"
    until = "until `python3` is {} or newer".format(NEEDS)
    lines = [_doctor_line("Your computer", "computer.python3", "gap", (
        "Your computer's Python (`python3`) is version {}, but the kit needs {} or newer, so its hooks fall back to a "
        "simpler mode and this check gives only a short report.".format(version, NEEDS),
        "`python3` is {}; the kit needs {}+ (the hooks run their fallback, and doctor gives this short report).".format(version, NEEDS),
    ), (
        "Install Python {} or newer (from python.org, or `brew install python` on a Mac), then open a new terminal, "
        "start a new Claude session and run this check again.".format(NEEDS),
        "Put Python {}+ first on the PATH as `python3`, start a new session, then rerun doctor.".format(NEEDS),
    ), wording)]
    for group, id_, only, new, developer in _DOCTOR_LINES:
        if only in (None, mode):
            lines.append(_doctor_line(group, id_, "cant_check", (
                "Can't check {} {}.".format(new, until),
                "{} unchecked {}.".format(developer, until),
            ), (
                "First install a newer Python (see the Python line), then run this check again.",
                "Needs computer.python3 fixed first.",
            ), wording))
    # Grouped, the group with the most serious line first, as doctor.order does.
    rank = _DOCTOR_STATUSES.index
    groups = sorted({ln["group"] for ln in lines}, key=lambda g: (min(rank(ln["status"]) for ln in lines if ln["group"] == g), _DOCTOR_GROUPS.index(g)))
    lines = [ln for g in groups for ln in sorted((x for x in lines if x["group"] == g), key=lambda x: rank(x["status"]))]
    counts = {s: sum(ln["status"] == s for ln in lines) for s in _DOCTOR_STATUSES}
    return {
        "experience": {"level": level, "source": source, "default": None},
        "wording": wording,
        "counts": counts,
        "strict_ok": not (counts["gap"] or counts["cant_check"]),
        "lines": lines,
    }


def _wrap(text, width, first, rest):
    return textwrap.wrap(text, width, initial_indent=first, subsequent_indent=rest, break_long_words=False, break_on_hyphens=False)


def _doctor_text(r, width=100):
    """As doctor.text shows it."""
    c = r["counts"]
    width = max(40, width)

    def plural(n, s):
        return "{} {}".format(n, _DOCTOR_LABELS[s]) + ("s" if n != 1 and s in ("gap", "note") else "")

    out = _wrap("Workflow doctor: " + ", ".join(plural(c[s], s) for s in _DOCTOR_STATUSES if c[s] or s == "gap"), width, "", "")
    group = None
    for ln in r["lines"]:
        if ln["group"] != group:
            group = ln["group"]
            out += ["", group]
        out += _wrap(ln["message"], width, "  [{}] ".format(_DOCTOR_LABELS[ln["status"]]), " " * 6)
        if ln["fix"]:
            out += _wrap(ln["fix"], width, " " * 6 + ("Next: " if ln["status"] in ("note", "fine") else "Fix: "), " " * 8)
    return "\n".join(out)

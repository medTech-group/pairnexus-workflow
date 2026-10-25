"""The kit's hooks, and `workflow doctor`, on a Python older than 3.11 (#22, #61).

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
- `doctor`: a short report (#61): the `python3` running it as a gap with its
  fix, and every other line the full doctor gives as `cant_check` until
  `python3` is 3.11 or newer, with the full doctor's ids, groups, flags, JSON
  and `--strict`;
- anything else: says what it needs and exits 1.

Keep it to the standard library (and the kit's `fallback` and `modes`, which
keep to it too) and to syntax Python 3.7 reads (a test checks): it runs on
exactly the interpreters the rest of the kit can't. It never raises: an error
refuses the tool when WORKFLOW_ROLE is firm, and doctor still gives its gap.
"""

import argparse
import collections
import fnmatch
import json
import os
import re
import shutil
import stat
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


def _needs(version):
    return "workflow needs Python {} or newer (for tomllib); python3 here is {}\n".format(NEEDS, version)


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
        sys.stderr.write(_needs(version))
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


class _Words(collections.namedtuple("_Words", "new developer")):
    """A message or fix in both wordings, as doctor.Words."""

    def pick(self, wording):
        return self.developer if wording == "developer" else self.new


# Every line but `computer.python3`, in the full doctor's check order: its
# group, its id, the install mode it is given in (None: both; in the other
# mode the full doctor gives it only when something is wrong; "wrangler": only
# in a project with a Wrangler config at its root or a `[previews]` section in
# its profile, read as text, so roughly as the full doctor gives it), and what
# it checks.
_DOCTOR_LINES = (
    ("Your computer", "computer.claude_code", None, _Words("which version of Claude Code you have", "Claude Code's version")),
    ("The kit", "kit.profile", None, _Words("the kit's profile (.claude/workflow/profile.toml)", "`profile check`")),
    ("The kit", "kit.hooks", "vendored", _Words("the kit's hooks", "Kit hooks in .claude/settings.json")),
    ("The kit", "kit.plugin", "plugin", _Words("whether the kit's plugin is turned on for this project", "Whether the plugin is enabled")),
    ("The kit", "kit.vendor", "vendored", _Words("whether the kit's copy in this project is as the kit wrote it", "`vendor verify`")),
    ("The kit", "kit.experience", None, _Words("the project's default for how much you know about building", "project.experience")),
    ("The kit", "kit.ruleset", None, _Words("whether the project means its main branch to be protected", "project.ruleset")),
    ("GitHub", "github.ruleset", None, _Words("whether the main branch is protected on GitHub", "The base branch's ruleset")),
    ("GitHub", "github.required_checks", None, _Words("whether GitHub requires the checks the kit's profile lists", "Required checks")),
    ("GitHub", "github.up_to_date", None, _Words("whether pull requests must be up to date with the main branch", '"Require branches to be up to date"')),
    ("GitHub", "github.approvals", None, _Words("how many approvals GitHub requires", "Required approvals")),
    ("GitHub", "github.code_owner_review", None, _Words("whether GitHub requires a review from the code owners", '"Require review from Code Owners"')),
    ("GitHub", "github.linear_history", None, _Words("whether GitHub requires a straight-line history", '"Require linear history"')),
    ("GitHub", "github.merge_commits", None, _Words("whether GitHub allows merge commits", "Merge commits allowed")),
    ("GitHub", "github.auto_merge", None, _Words("whether GitHub allows auto-merge", "Auto-merge allowed")),
    ("GitHub", "github.codeowners", None, _Words("whether CODEOWNERS asks you to review changes to the kit and CI", "CODEOWNERS for /.claude/ and /.github/workflows/")),
    ("Cloud", "cloud.environments", None, _Words("the two cloud environments for unattended runs", "The cloud environments")),
    ("Cloud", "cloud.contents", None, _Words("what the cloud environments hold", "Environment contents")),
    ("Previews", "previews.setup", "wrangler", _Words("the project's try-it links", "Previews")),
)
# The Wrangler configs whose presence gives the Previews line ("wrangler"
# above): doctor's WRANGLER_TOML and WRANGLER_JSON, which this module can't import.
_WRANGLER_CONFIGS = ("wrangler.toml", "wrangler.json", "wrangler.jsonc")
# A `[previews]` table anywhere, or, above the first table, `previews = {…}` or
# `previews.on = …` (below it, a `previews` key is another table's, an area's).
_PREVIEWS_TABLE = re.compile(r"^[ \t]*\[[ \t]*[\"']?previews[\"']?[ \t]*[\].]", re.M)
_PREVIEWS_KEY = re.compile(r"^[ \t]*[\"']?previews[\"']?[ \t]*[.=]", re.M)
_FIRST_TABLE = re.compile(r"^[ \t]*\[", re.M)
# The files a session hands the full doctor: taken here, and not read.
_DOCTOR_FILES = ("rulesets", "repo", "environments", "runs", "checks", "prs", "org", "ci", "commits")
_EXPERIENCE_LEVELS = ("new", "developer")
_EXPERIENCE_FILE_MAX = 200  # bytes, as profile.py reads it


class _Refused(Exception):
    """argparse's exit (help, or arguments it refuses), as an exit code."""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


class _Parser(argparse.ArgumentParser):
    """Its writes guarded as 3.11's are, and its exits returned."""

    def _print_message(self, message, file=None):
        try:
            (file or sys.stderr).write(message)
        except (AttributeError, OSError):
            pass

    def error(self, message):
        if sys.stderr is not None:  # else print_usage falls back to stdout, the report's
            self.print_usage(sys.stderr)
        self.exit(2, "{}: error: {}\n".format(self.prog, message))

    def exit(self, status=0, message=None):
        if message:
            _say(message)
        _flush()
        raise _Refused(status)


def _doctor_parser():
    """cli.py's doctor parser, flag for flag. The files are taken, not read."""
    p = _Parser(prog="workflow doctor", description=(
        "What's set up and what isn't; changes nothing. With python3 older than {0} it gives a short report: "
        "python3 as a gap, and every other line as can't check until python3 is {0} or newer.").format(NEEDS))
    p.add_argument("--claude-version", metavar="VERSION", help="Claude Code's version (not read until python3 is {}+)".format(NEEDS))
    for flag in _DOCTOR_FILES:
        p.add_argument("--" + flag, metavar="F", help="as the full doctor takes it (not read until python3 is {}+)".format(NEEDS))
    p.add_argument("--now", metavar="TIME", help="as the full doctor takes it (not read until python3 is {}+)".format(NEEDS))
    p.add_argument("--json", action="store_true", help="every line's group, id, status, message, fix and offer, for skills")
    p.add_argument("--strict", action="store_true", help="exit 1 when any line is a gap or can't be checked (here, always)")
    return p


def _doctor(args, env, version, cwd):
    """`workflow doctor` on an old Python: exit 0, or 1 with --strict (there
    is always a gap); 2 for arguments the full doctor refuses. Never raises:
    a report that fails still gives the gap, and output that can't be
    written still exits as --strict says."""
    try:
        a = _doctor_parser().parse_args(args)
    except _Refused as e:
        return e.code
    except Exception:  # argparse itself failing: the flags as plainly given
        a = argparse.Namespace(json="--json" in args, strict="--strict" in args, **dict.fromkeys(_DOCTOR_FILES))
    if [getattr(a, f) for f in _DOCTOR_FILES].count("-") > 1:
        _say("workflow doctor: only one of --rulesets, --repo, --environments, --runs, --checks, --prs, --org, --ci and --commits can be standard input (-)\n")
        return 2
    try:
        r = _doctor_report(_doctor_root(env, cwd), env, version)
    except Exception:  # advice never ends in a traceback
        r = _doctor_report(None, env, version)  # reads no file
    try:
        print(json.dumps(r, indent=2) if a.json else _doctor_text(r, min(100, shutil.get_terminal_size((100, 24)).columns)))
        sys.stdout.flush()
    except Exception as e:  # a closed pipe, a full disk
        _drop(sys.stdout)
        _say("workflow doctor: couldn't write the report ({})\n".format(type(e).__name__))
    return 1 if a.strict and not r["strict_ok"] else 0


def _say(text):
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:  # no stderr either
        _drop(sys.stderr)


def _flush():
    try:
        sys.stdout.flush()
    except Exception:
        _drop(sys.stdout)


def _drop(stream):
    """Point a stream that can't be written at the null device, so the
    unwritten rest isn't flushed again at exit (which would exit 120). No
    stream (its descriptor was closed at start) has nothing to flush."""
    if stream is None:
        return
    try:
        null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null, stream.fileno())
        os.close(null)
    except Exception:  # an in-memory stream, or no file descriptors left
        pass


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
    Opened without waiting, and read only when it is a regular file, so a pipe
    never blocks."""
    try:
        fd = os.open(os.path.join(root, ".workflow", "experience"), os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    except (OSError, ValueError, TypeError):
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, "rb") as f:
            fd = None
            data = f.read(_EXPERIENCE_FILE_MAX + 1)
        if len(data) > _EXPERIENCE_FILE_MAX:
            return None
        lines = data.decode("utf-8").strip().splitlines()
    except (OSError, ValueError):  # UnicodeDecodeError is a ValueError
        return None
    finally:
        if fd is not None:
            os.close(fd)
    return _level(lines[0]) if len(lines) == 1 else None


def _experience(root, env):
    """(level, source): WORKFLOW_EXPERIENCE, else the local file, else unknown.
    The profile's default isn't read: that needs tomllib."""
    lvl = _level(env.get("WORKFLOW_EXPERIENCE"))
    if lvl:
        return lvl, "environment"
    lvl = _experience_file(root) if root else None
    return (lvl, "local file") if lvl else (None, "unknown")


def _has_previews(root):
    """The profile has a `[previews]` section, read as text: tomllib needs 3.11."""
    path = os.path.join(root, ".claude", "workflow", "profile.toml")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except (OSError, ValueError):
        return False
    first = _FIRST_TABLE.search(text)
    return bool(_PREVIEWS_TABLE.search(text) or _PREVIEWS_KEY.search(text[:first.start()] if first else text))


def _doctor_line(group, id_, status, message, fix, wording):
    return {"group": group, "id": id_, "status": status, "message": message.pick(wording), "fix": fix.pick(wording), "offer": None}


def _doctor_order(lines):
    """As doctor.order: grouped, the group with the most serious line first
    (ties in group order), the most serious line first within a group."""
    rank = _DOCTOR_STATUSES.index
    groups = {}
    for ln in lines:
        groups.setdefault(ln["group"], []).append(ln)
    for g in groups.values():
        g.sort(key=lambda ln: rank(ln["status"]))  # stable: check order within a status
    names = sorted(groups, key=lambda g: (min(rank(ln["status"]) for ln in groups[g]), _DOCTOR_GROUPS.index(g)))
    return [ln for g in names for ln in groups[g]]


def _doctor_report(root, env, version):
    """The report as the full doctor's `--json` gives it. With no root it
    reads no file: experience from the environment alone, and the vendored
    mode's lines."""
    level, source = _experience(root, env)
    wording = level or "new"
    plugin = bool(root) and not os.path.exists(os.path.join(root, ".claude", "workflow", "lock.json"))
    mode = "plugin" if plugin else "vendored"
    wrangler = bool(root) and (any(os.path.lexists(os.path.join(root, n)) for n in _WRANGLER_CONFIGS) or _has_previews(root))
    until = "until `python3` is {} or newer".format(NEEDS)
    lines = [_doctor_line("Your computer", "computer.python3", "gap", _Words(
        "The Python running this check (`python3`) is version {}, but the kit needs {} or newer, so its hooks fall back to a "
        "simpler mode and this check gives only a short report.".format(version, NEEDS),
        "`python3` here is {}; the kit needs {}+ (the hooks run their fallback, and doctor gives this short report).".format(version, NEEDS),
    ), _Words(
        "Install Python {} or newer (from python.org, or `brew install python` on a Mac), then open a new terminal, "
        "start a new Claude session and run this check again with `python3`.".format(NEEDS),
        "Put Python {}+ first on the PATH as `python3`, start a new session, then rerun doctor with it.".format(NEEDS),
    ), wording)]
    for group, id_, only_in, what in _DOCTOR_LINES:
        if only_in in (None, mode) or (only_in == "wrangler" and wrangler):
            lines.append(_doctor_line(group, id_, "cant_check", _Words(
                "Can't check {} {}.".format(what.new, until),
                "{} unchecked {}.".format(what.developer, until),
            ), _Words(
                "First install a newer Python (see the Python line), then run this check again.",
                "Needs computer.python3 fixed first.",
            ), wording))
    lines = _doctor_order(lines)
    counts = {s: sum(ln["status"] == s for ln in lines) for s in _DOCTOR_STATUSES}
    return {
        "experience": {"level": level, "source": source, "default": None},
        "wording": wording,
        "counts": counts,
        "strict_ok": not (counts["gap"] or counts["cant_check"]),
        "lines": lines,
        "merge_queue": None,
    }


def _wrap(text, width, first, rest):
    return textwrap.wrap(text, width, initial_indent=first, subsequent_indent=rest, break_long_words=False, break_on_hyphens=False)


def _plural(n, status):
    return "{} {}".format(n, _DOCTOR_LABELS[status]) + ("s" if n != 1 and status in ("gap", "note") else "")


def _doctor_text(r, width=100):
    """As doctor.text shows it (no line here has an offer)."""
    c = r["counts"]
    width = max(40, width)
    out = _wrap("Workflow doctor: " + ", ".join(_plural(c[s], s) for s in _DOCTOR_STATUSES if c[s] or s == "gap"), width, "", "")
    group = None
    for ln in r["lines"]:
        if ln["group"] != group:
            group = ln["group"]
            out += ["", group]
        out += _wrap(ln["message"], width, "  [{}] ".format(_DOCTOR_LABELS[ln["status"]]), " " * 6)
        if ln["fix"]:
            out += _wrap(ln["fix"], width, " " * 6 + ("Next: " if ln["status"] in ("note", "fine") else "Fix: "), " " * 8)
    return "\n".join(out)

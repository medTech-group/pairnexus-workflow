"""`workflow doctor`: one report of what's set up and what isn't (#34).

Each check is a function from what doctor was given (`Inputs`) to report
lines (`Line`). A line has a group, an id, a status, a message and a fix in
both wordings, and optionally an offer (an upgrade #32 builds). The report
picks one wording by experience (#16: what is checked, and each status, never
depend on it), puts the most serious line first and groups the rest.

Doctor never changes anything (#27): it reads files and runs `python3`,
`claude --version`, `gh api` (GETs only, when no file is given: for the
GitHub lines, the checks that ran on the base branch, the open pull requests,
whether a run has been made, and the merge queue's inputs) and `git rev-parse`
and `git show` (the workflow files as they are on `origin/<base>`, #246),
nothing else. It reads files only through
`_read_text` (and `_read_value`, `_read_json` on it), `_file` and
`_hash_file`, which never raise and never wait on a pipe; only a file given as
`-` (`--rulesets`, `--repo`, `--environments`, `--runs`, `--checks`,
`--prs`, `--org`, `--ci` or `--commits`) reads standard input, as asked. A check that fails unexpectedly becomes a
`cant_check` line, never a traceback: doctor is advice, and exits 0.

**Adding a group or a check** (the GitHub, Cloud and Previews tickets): write
a function `def check_x(i: Inputs) -> list[Line]`, decorate it with
`@_check(<group>, <id of its main line>)` (the line it falls back to if it
raises), add it to `CHECKS`, and put anything it reads on `Inputs` (filled in
by `cli.cmd_doctor`). The groups are in `GROUPS` already; the order, the
counts, the text, the JSON and `--strict` follow without change. A line
that needs GitHub's answers reads them through `_github(i)`, once for every
line; the required checks' line reads the checks that ran through
`_checks_ran(i, rep)` and the open pull requests through `_open_prs(i)`, and
the Cloud lines read the environments through `_environments(i)` and whether
a run has been made through `_runs(i)`, the same way.

**`workflow status`** runs only `LOCAL_CHECKS` (#62), through `report`, and
shows their gaps: a check added there must read nothing but this computer
and the checkout.
"""

from __future__ import annotations

import dataclasses
import difflib
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import textwrap
import time
import tomllib
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from . import estimate as estimate_mod
from . import issues as issues_mod
from . import posts as posts_mod
from . import profile as profile_mod
from . import protection as protection_mod
from . import updates as updates_mod
from . import vendor as vendor_mod
from .adopt import CODEOWNERS_PATHS
from .profile import EXPERIENCE_ENV, EXPERIENCE_FILE, Experience, Profile

# In the order a report shows them when nothing is wrong.
GROUPS = ("Your computer", "The kit", "GitHub", "Cloud", "Previews")
# Most serious first. A note is a state chosen on purpose; `cant_check` says
# how to check it.
STATUSES = ("gap", "cant_check", "note", "fine")
LABELS = {"gap": "gap", "cant_check": "can't check", "note": "note", "fine": "fine"}
# The upgrades a line may offer, by the names #47 and #48 use (the glossary's
# names: "Protect `main`" is the upgrade's name whatever the base branch).
OFFERS = {"protect_main": "Protect `main`", "restore_protection": "Restore protection", "set_up_unattended_runs": "Set up unattended runs",
          "require_checks": "Require these checks", "add_try_it_links": "Add try-it links", "use_merge_queue": "Use a merge queue"}

PYTHON_MIN = (3, 11)
# The oldest Claude Code that honours the guard's `onFailure: "block"` (#57,
# docs/enforcement.md).
CLAUDE_CODE_MIN = (2, 1, 295)
RUN_TIMEOUT = 10  # seconds, for `python3` and `claude --version`
# A version at the start of a line, so a wrapper's notice ("node v18.19.0")
# before it isn't taken for it. A pre-release ("-beta.1") comes before its version.
_VERSION = re.compile(r"^\s*v?([0-9]+)\.([0-9]+)\.([0-9]+)(-[0-9A-Za-z.-]+)?", re.M)
# What each of the kit's hooks is called in a report.
HOOK_NAMES = {"PreToolUse": "the guard", "Stop": "the status gate", "UserPromptSubmit": "the flow context", "SessionStart": "the session start"}
SETTINGS = vendor_mod.SETTINGS.as_posix()
SETTINGS_LOCAL = vendor_mod.SETTINGS_LOCAL.as_posix()
PROFILE = profile_mod.PROFILE_PATH.as_posix()
LOCK = vendor_mod.LOCK.as_posix()
COPY_CLI = vendor_mod.HOOK_TAG  # the vendored copy's CLI


@dataclass(frozen=True)
class Words:
    """A message or fix in both wordings: for someone new to building, and
    for a developer."""

    new: str
    developer: str

    def pick(self, level: str) -> str:
        return self.developer if level == "developer" else self.new


NONE = Words("", "")
# The fix of a line that waits on another one.
SETTINGS_FIRST = Words("First make Claude Code's settings readable (see the settings line).", "Needs kit.settings fixed first.")
PROFILE_FIRST = Words("First correct the kit's profile (see the profile line).", "Needs kit.profile fixed first.")
SET_UP_FIRST = Words("First set the kit up (see the profile line).", "Needs the kit set up first (kit.profile).")


@dataclass
class Line:
    group: str
    id: str
    status: str
    message: Words
    fix: Words = NONE
    offer: str | None = None

    def as_dict(self, level: str) -> dict:
        return {
            "group": self.group,
            "id": self.id,
            "status": self.status,
            "message": self.message.pick(level),
            "fix": self.fix.pick(level),
            "offer": self.offer,
        }


@dataclass
class Inputs:
    """What doctor reads: the checkout, the kit running it, and what a
    session hands it. GitHub's answers come from the files given, else from
    `gh api` when the GitHub lines first ask (`_github`), never otherwise."""

    root: Path
    kit_root: Path
    profile: Profile | None
    profile_error: str | None  # `profile check`'s error; None with no profile, or a good one
    experience: Experience
    claude_version: str | None = None  # --claude-version, which wins over `claude --version`
    environ: dict = field(default_factory=lambda: dict(os.environ))
    # --rulesets and --repo: GitHub's answers as files (`-`: standard input),
    # which win over `gh api`.
    rulesets_file: Path | str | None = None
    repo_file: Path | str | None = None
    # --environments (as `list_environments` returns them: only ever a file)
    # and --runs (the `workflow:run` issues, which win over `gh api`).
    environments_file: Path | str | None = None
    runs_file: Path | str | None = None
    # --checks (the checks that ran on the base branch's latest commit: its
    # check runs and statuses) and --prs (the open pull requests), which win
    # over `gh api` (#69).
    checks_file: Path | str | None = None
    prs_file: Path | str | None = None
    # --org (the owning organisation, for its plan), --ci (the check runs of
    # the base's last commits and of recent pull requests' heads, with the
    # workflow runs behind them) and --commits (the base's), which win over
    # `gh api`, and --now, where the 7 days end (#246).
    org_file: Path | str | None = None
    ci_file: Path | str | None = None
    commits_file: Path | str | None = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Only gaps are wanted (`workflow status`, #62, which keeps the gap lines
    # itself): a check may leave out what can only be a note or fine and
    # costs time. `check_profile` skips `profile check`'s warnings, whose globs
    # walk the tree.
    gaps_only: bool = False
    _github: _GitHub | None = field(default=None, repr=False)  # what the GitHub lines read, read once
    _environments: _Answer | None = field(default=None, repr=False)  # the environments listed, read once
    _runs: _Answer | None = field(default=None, repr=False)  # the `workflow:run` issues, read once
    _checks: _Answer | None = field(default=None, repr=False)  # the checks that ran on the base branch, read once
    _prs: _Answer | None = field(default=None, repr=False)  # the open pull requests, read once
    _ci: _Answer | None = field(default=None, repr=False)  # the CI behind the required checks, read once
    _commits: _Answer | None = field(default=None, repr=False)  # the base branch's commits, read once
    _run_open: bool | None = field(default=None, repr=False)  # a `workflow:run` issue is open, once the runs are read
    _mq: dict | None = field(default=None, repr=False)  # the JSON's merge_queue, once its check has run
    _gh_until: float | None = field(default=None, repr=False)  # when doctor stops waiting on GitHub (`_gh_deadline`)

    @property
    def vendored(self) -> bool:
        return updates_mod.mode(self.root) == "vendored"

    @property
    def path(self) -> str | None:
        return self.environ.get("PATH")

    @property
    def default(self) -> str | None:
        """The profile's project.experience."""
        return (self.profile.experience if self.profile else None) or None


@dataclass
class Ran:
    """A command's result: `out` when it ran and printed UTF-8; else `state`
    says why not: missing, failed (a non-zero exit), timeout or unreadable."""

    state: str
    out: str | None = None
    err: str = ""  # the last lines it printed on stderr, when asked for


def _run(i: Inputs, argv: list[str], timeout: float | None = None, stderr: bool = False) -> Ran:
    """Run a command with no shell and no input. Its whole process group is
    killed whenever doctor stops waiting (a timeout, Ctrl-C), so nothing it
    started is left running."""
    exe = shutil.which(argv[0], path=i.path)
    if not exe:
        return Ran("missing")
    try:
        p = subprocess.Popen([exe, *argv[1:]], cwd=i.root if i.root.is_dir() else None, env=i.environ,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE if stderr else subprocess.DEVNULL,
                             start_new_session=True)
    except (OSError, ValueError):
        return Ran("failed", err="it couldn't be started")
    timed_out, err = False, b""
    try:
        out, err = p.communicate(timeout=RUN_TIMEOUT if timeout is None else timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        if p.returncode is None:  # still running: a timeout, or doctor itself interrupted
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                p.kill()
            try:
                p.communicate(timeout=1)  # a detached grandchild may hold the pipe: don't wait on it
            except subprocess.TimeoutExpired:
                pass
            for f in (p.stdout, p.stderr):
                if f:
                    f.close()
    if timed_out:
        return Ran("timeout")
    if p.returncode:
        said = (err or b"").decode("utf-8", "replace").strip().splitlines()
        return Ran("failed", err="\n".join(said[-3:])[:600] if said else f"exit {p.returncode}")
    try:
        return Ran("ok", out.decode("utf-8"))
    except UnicodeDecodeError:
        return Ran("unreadable")


def _version(text: str | None) -> tuple[tuple[int, int, int], str] | None:
    """(major, minor, patch) and any pre-release suffix, from the first line
    that starts with a version."""
    m = _VERSION.search(text or "")
    return ((int(m.group(1)), int(m.group(2)), int(m.group(3))), m.group(4) or "") if m else None


def _older(found: tuple[tuple[int, int, int], str], need: tuple[int, int, int]) -> bool:
    v, pre = found
    return v < need or (v == need and bool(pre))


def _dotted(v) -> str:
    return ".".join(str(x) for x in v)


def _printable(text: str) -> str:
    """Text with what can't be printed (a control character, half a
    surrogate pair, an invisible one) escaped as `\\uXXXX`."""
    return "".join(ch if ch.isprintable() else f"\\u{ord(ch):04x}" for ch in text)


def _shown(value: str, most: int = 40) -> str:
    """A value someone gave, safe on one line in a code span."""
    v = _printable(" ".join(value.replace("`", "'").split()))
    return v if len(v) <= most else v[:most] + "…"


def _file(root: Path, rel: str | Path) -> tuple[Path, str | None]:
    """A path in the checkout, and why it can't be read as a regular file
    (None when it can, or is missing). A pipe or a directory is never opened."""
    path = Path(rel) if Path(rel).is_absolute() else root / rel
    try:
        if path.exists() and not path.is_file():
            return path, "it isn't a file"
    except OSError as e:
        return path, f"it can't be read ({type(e).__name__})"
    return path, None


def _read_text(root: Path, rel: str | Path) -> tuple[str | None, str | None]:
    """A text file's contents (a byte-order mark left out), and why it can't
    be read: (None, None) when it is missing. Never raises, and never blocks
    on a pipe."""
    path, err = _file(root, rel)
    if err:
        return None, err
    try:
        if not path.exists():
            return None, None
        return path.read_text(encoding="utf-8").removeprefix("\ufeff"), None
    except UnicodeDecodeError:
        return None, "it isn't UTF-8 text"
    except (OSError, ValueError) as e:
        return None, f"it can't be read ({type(e).__name__})"


def _parse_json(text: str, loads=json.loads):
    """JSON text's value, and why it can't be read."""
    if not text.strip():
        return None, "it is empty"
    try:
        return loads(text.removeprefix("\ufeff")), None
    except json.JSONDecodeError as e:
        return None, f"it isn't valid JSON ({e.msg}, line {e.lineno})"
    except RecursionError:
        return None, "it is nested too deeply to read"
    except ValueError as e:
        return None, f"it can't be read ({type(e).__name__}: {_shown(str(e), 60)})"


def _read_value(root: Path, rel: str | Path, loads=json.loads):
    """A JSON file's value, and why it can't be read: (None, None) when it is
    missing. Never raises, and never blocks on a pipe."""
    text, err = _read_text(root, rel)
    if err or text is None:
        return None, err
    return _parse_json(text, loads)


def _read_json(root: Path, rel: str | Path) -> tuple[dict, str | None]:
    """A JSON object file's contents, and why it can't be read: ({}, None)
    when it is missing. Never raises, and never blocks on a pipe."""
    data, err = _read_value(root, rel)
    if err or data is None:
        return {}, err
    if not isinstance(data, dict):
        return {}, "it doesn't hold a JSON object"
    return data, None


def _hash_file(path: Path) -> str | None:
    """A regular file's SHA-256, as the lock records it; None when it isn't
    one or can't be read."""
    try:
        if not path.is_file():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _relative(i: Inputs, text: str) -> str:
    """A message with the checkout's own path left out."""
    return text.replace(str(i.root) + os.sep, "").replace(str(i.root), ".")


def _home(i: Inputs, path: Path) -> str:
    """A path with the home directory as `~`, so a report posted on GitHub
    never carries a username."""
    home = (i.environ.get("HOME") or "").rstrip(os.sep)
    p = str(path)
    for h in dict.fromkeys((home, os.path.realpath(home) if home else "")):  # as given, and through any symlink
        if h and h != os.sep and (p == h or p.startswith(h + os.sep)):
            return "~" + p[len(h):]
    return p


def _check(group: str, id_: str):
    """Mark a check with its group and the id of its main line, for the
    `cant_check` line it becomes if it raises."""

    def mark(fn):
        fn.group, fn.id = group, id_
        return fn

    return mark


# ---------- Your computer ----------


@_check("Your computer", "computer.python3")
def check_python(i: Inputs) -> list[Line]:
    """`python3` on the PATH, the one the hooks run, not the Python running
    doctor, run as the hooks run it (`-B`, the environment as it is)."""
    g, id_ = "Your computer", "computer.python3"
    need = _dotted(PYTHON_MIN)
    install = Words(
        f"Install Python {need} or newer (from python.org, or `brew install python` on a Mac), then open a new terminal and start a new Claude session.",
        f"Put Python {need}+ first on the PATH as `python3`, then start a new session.",
    )
    ran = _run(i, ["python3", "-B", "-c", "import sys; print('%d.%d.%d' % tuple(sys.version_info[:3]))"])
    if ran.state == "missing":
        return [Line(g, id_, "gap", Words(
            "Python (`python3`) isn't installed, or your computer can't find it, so the kit's hooks fall back to a simpler mode.",
            f"No `python3` on the PATH: the hooks run their fallback (they need {need}+).",
        ), install)]
    if ran.state == "failed":
        return [Line(g, id_, "gap", Words(
            "Python (`python3`) is there but doesn't run, so the kit's hooks fall back to a simpler mode.",
            "`python3` on the PATH exits with an error: the hooks run their fallback.",
        ), install)]
    found = _version(ran.out)
    if found is None:
        why = Words(f"it didn't answer within {RUN_TIMEOUT} seconds", f"timed out after {RUN_TIMEOUT} s") if ran.state == "timeout" else Words(
            "its answer had no version in it", "printed no version")
        return [Line(g, id_, "cant_check", Words(
            f"Couldn't tell which version of Python (`python3`) your computer has: {why.new}.",
            f"`python3` on the PATH {why.developer}.",
        ), Words(
            f"Run `python3 --version` in a terminal: it should say {need} or newer.",
            f"Check `python3 --version` ({need}+ needed) and that it runs.",
        ))]
    v = found[0]
    if v[:2] < PYTHON_MIN:
        return [Line(g, id_, "gap", Words(
            f"Your computer's Python (`python3`) is version {_dotted(v)}, but the kit needs {need} or newer, so its hooks fall back to a simpler mode.",
            f"`python3` on the PATH is {_dotted(v)}; the kit needs {need}+ (the hooks run their fallback).",
        ), install)]
    return [Line(g, id_, "fine", Words(
        f"Python is ready (`python3` is version {_dotted(v)}).",
        f"`python3` on the PATH is {_dotted(v)} ({need}+ needed).",
    ))]


@_check("Your computer", "computer.claude_code")
def check_claude_code(i: Inputs) -> list[Line]:
    """Claude Code's version: `--claude-version` wins; a blank one counts as
    not given."""
    g, id_ = "Your computer", "computer.claude_code"
    need = _dotted(CLAUDE_CODE_MIN)
    given = bool(i.claude_version and i.claude_version.strip())
    ran = None if given else _run(i, ["claude", "--version"])
    found = _version(i.claude_version if given else ran.out)
    if found is None:
        if given:
            where = f"`--claude-version {_shown(i.claude_version)}` holds no version"
        elif ran.state == "timeout":
            where = f"no `--claude-version`, and `claude --version` timed out after {RUN_TIMEOUT} s"
        elif ran.state == "missing":
            where = "no `--claude-version`, and `claude` isn't on the PATH"
        else:
            where = "no `--claude-version`, and `claude --version` gave none"
        return [Line(g, id_, "cant_check", Words(
            "Couldn't tell which version of Claude Code you have.",
            f"Claude Code's version is unknown ({where}).",
        ), Words(
            f"Type `/status` in Claude Code, or run `claude --version` in a terminal: the version should be {need} or newer.",
            f"Run `claude --version` ({need}+ needed), or pass `--claude-version`.",
        ))]
    shown = _dotted(found[0]) + found[1]
    if _older(found, CLAUDE_CODE_MIN):
        return [Line(g, id_, "gap", Words(
            f"Claude Code is version {shown}, older than {need}: if the kit's guard ever fails or takes too long, this version lets the step run instead of stopping it.",
            f"Claude Code {shown} is older than {need}: a guard hook that fails or times out won't block (`onFailure: \"block\"` is ignored).",
        ), Words(
            "Update Claude Code (run `claude update` in a terminal, or update the desktop app), then start a new session.",
            f"Run `claude update` ({need}+), then restart the session.",
        ))]
    return [Line(g, id_, "fine", Words(
        f"Claude Code is new enough (version {shown}).",
        f"Claude Code {shown} ({need}+ needed).",
    ))]


# ---------- The kit ----------


def _user_settings(i: Inputs) -> tuple[str, Path | None]:
    """The user's settings file: its name in a report, and its path (None
    when there is no home directory to find it in)."""
    if i.environ.get("CLAUDE_CONFIG_DIR"):
        p = Path(i.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
        return _home(i, p), p
    home = i.environ.get("HOME")
    if not home:
        try:
            home = str(Path.home())
        except (RuntimeError, KeyError, OSError):
            return "~/.claude/settings.json", None
    return "~/.claude/settings.json", Path(home) / ".claude/settings.json"


@dataclass
class _Settings:
    """Claude Code's settings files as doctor reads them, least specific
    first: (name in a report, contents, why it can't be read)."""

    files: list[tuple[str, dict, str | None]]

    def project(self) -> tuple[dict, str | None]:
        _, data, err = self.files[1]
        return data, err

    def unreadable(self) -> list[tuple[str, str]]:
        return [(name, err) for name, _, err in self.files if err]

    def _winner(self, read) -> tuple[object, str | None]:
        """The most specific file's value (local, then project, then user):
        `read(contents)` gives a file's value, or None when it sets none."""
        value, where = None, None
        for name, data, _ in self.files:
            v = read(data)
            if v is not None:
                value, where = v, name
        return value, where

    def plugin(self) -> tuple[bool, str | None]:
        """Whether the kit's plugin is enabled, and which file says so."""
        def read(data):
            plugins = data.get("enabledPlugins")
            v = plugins.get(vendor_mod.PLUGIN_KEY) if isinstance(plugins, dict) else None
            return v if isinstance(v, bool) else None  # as Claude Code reads it: true or false

        on, where = self._winner(read)
        return bool(on), where

    def hooks_off(self) -> str | None:
        """The file whose `disableAllHooks: true` is in force: Claude Code
        then runs no hook. None when hooks run."""
        on, where = self._winner(lambda d: d.get("disableAllHooks") if isinstance(d.get("disableAllHooks"), bool) else None)
        return where if on is True else None


def _settings(i: Inputs) -> _Settings:
    user_name, user_path = _user_settings(i)
    files = []
    for name, path in ((user_name, user_path), (SETTINGS, SETTINGS), (SETTINGS_LOCAL, SETTINGS_LOCAL)):
        data, err = _read_json(i.root, path) if path else ({}, None)
        if not err and "enabledPlugins" in data and not isinstance(data["enabledPlugins"], dict):
            data, err = {}, "its enabledPlugins isn't an object"
        files.append((name, data, err))
    return _Settings(files)


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _is_kit(h) -> bool:
    return isinstance(h, dict) and vendor_mod._is_kit_hook(h)


def _kit_entries(settings: dict) -> dict[str, list]:
    """The settings' hook entries that run the kit, by event."""
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    out = {}
    for event, entries in hooks.items():
        kit = [e for e in _list(entries) if isinstance(e, dict) and any(_is_kit(h) for h in _list(e.get("hooks")))]
        if kit:
            out[event] = kit
    return out


def _hook_differences(settings: dict) -> list[str]:
    """How the kit's hooks in the settings differ from this kit version's own
    entries, as `vendor update` writes them: one phrase each."""
    kit = _kit_entries(settings)
    out = []
    for event in [*vendor_mod.KIT_HOOKS, *sorted(set(kit) - set(vendor_mod.KIT_HOOKS))]:
        mine, want = kit.get(event, []), vendor_mod.KIT_HOOKS.get(event)
        name = HOOK_NAMES.get(event, f"a hook on {event} that runs the kit")
        if want is None:
            out.append(f"{name} isn't one this version writes")
        elif not mine:
            out.append(f"{name} ({event}) is missing")
        elif any(not all(_is_kit(h) for h in _list(e.get("hooks"))) for e in mine):
            out.append(f"{name} ({event}) shares an entry with other hooks")
        elif mine != want:
            out.append(f"{name} ({event}) differs")
    return out


def _running_copy(i: Inputs) -> bool:
    """Whether the kit running doctor is this project's vendored copy."""
    copy = (i.root / ".claude/workflow").resolve()
    here = i.kit_root.resolve()
    return here == copy or copy in here.parents


def _lock_version(i: Inputs) -> str:
    v = _read_json(i.root, LOCK)[0].get("kit_version")
    return v.strip() if updates_mod.parse(v) else "unknown"


def _kit_version(i: Inputs) -> str:
    """The version of the kit running doctor: the lock's for the project's
    vendored copy, else the kit's own VERSION (a checkout of it, the plugin)."""
    if _running_copy(i):
        return _lock_version(i)
    path, err = _file(i.kit_root, "VERSION")
    try:
        v = None if err else path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        v = None
    return v if updates_mod.parse(v) else "unknown"


def _kit_name(version: str) -> str:
    return "this kit" if version == "unknown" else f"kit {version}"


def _copy_has_doctor(i: Inputs) -> bool:
    """Whether the project's vendored copy of the CLI knows `doctor` (copies
    vendored before it shipped don't)."""
    path, err = _file(i.root, ".claude/workflow/bin/workflow/cli.py")
    try:
        return not err and path.is_file() and 'add_parser("doctor"' in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


@_check("The kit", "kit.hooks")
def check_install(i: Inputs) -> list[Line]:
    """Claude Code's settings files read and run hooks at all; then,
    vendored, the hooks are this version's own entries; in plugin mode the
    plugin is enabled; both on is a gap naming which to turn off."""
    g = "The kit"
    if not i.root.is_dir():
        return []  # kit.profile says the folder isn't there
    s = _settings(i)
    lines: list[Line] = []
    bad = s.unreadable()
    if bad:
        listed = "; ".join(f"{name}: {why}" for name, why in bad)
        one = len(bad) == 1
        lines.append(Line(g, "kit.settings", "gap", Words(
            f"Claude Code can't read {'a settings file' if one else 'some settings files'} ({listed}), so it starts without {'it' if one else 'them'}, and the kit's hooks or plugin set there don't run.",
            f"Unreadable Claude Code settings ({listed}): Claude Code skips {'it' if one else 'them'}.",
        ), Words(
            f"Ask Claude to correct {'the file' if one else 'the files'} (valid JSON, saved as UTF-8), then start a new session.",
            f"Make {'it' if one else 'each'} a UTF-8 JSON object (enabledPlugins an object), then restart the session.",
        )))
    off = s.hooks_off()
    if off:
        lines.append(Line(g, "kit.hooks_off", "gap", Words(
            f"Every hook is turned off ({off} sets `disableAllHooks`), so the kit's guard doesn't run at all.",
            f"`disableAllHooks` is true in {off}: no hook runs, the guard included.",
        ), Words(
            f"Ask Claude to remove `\"disableAllHooks\": true` from {off}, then start a new session.",
            f"Drop `disableAllHooks` from {off}.",
        )))
    on, where = s.plugin()
    project_data, project_err = s.project()
    if i.vendored:
        lines += _vendored_hooks(i, project_data, project_err)
        if on:
            local = where if where in (SETTINGS, SETTINGS_LOCAL) else SETTINGS_LOCAL
            key = f'`"enabledPlugins": {{"{vendor_mod.PLUGIN_KEY}": false}}`'
            lines.append(Line(g, "kit.plugin", "gap", Words(
                f"The kit is on twice here: copied into this project and installed as a plugin (turned on in {where}), so its hooks run twice.",
                f"Both modes are on: the kit is vendored and the {vendor_mod.PLUGIN_KEY} plugin is enabled ({where}); the hooks run twice.",
            ), Words(
                f"Ask Claude to turn the plugin off for this project in {local}, and keep the copy, which unattended runs need.",
                f"Turn off the plugin, keep the vendored copy (runs need it): set {key} in {local}.",
            )))
        return lines
    # Plugin mode: no lock. A copy or kit hooks left without one is the
    # vendored mode with its record lost, not a project to install the plugin in.
    left = _file(i.root, COPY_CLI)[0].is_file() or bool(_kit_entries(project_data))
    if left:
        lines.append(Line(g, "kit.vendor", "gap", Words(
            f"This project has the kit's copy or its hooks, but the record of that copy ({LOCK}) is gone, so the copy can't be checked or updated.",
            f"Vendored files or kit hooks present, but no {LOCK}.",
        ), Words(
            f"Ask Claude to put back {LOCK} from git, or, to use the plugin instead, to remove the copy and its hooks.",
            f"Restore {LOCK} (`git log -- {LOCK}`), or remove .claude/workflow and the kit's hook entries for plugin mode.",
        )))
    if on:
        if left:
            return lines + [Line(g, "kit.plugin", "gap", Words(
                f"The kit's plugin is on (in {where}) beside what's left of a copy of the kit, so its hooks run twice.",
                f"Plugin enabled ({where}) and kit hooks or a copy left in the project: the hooks run twice.",
            ), Words(
                "Ask Claude to keep one: the copy (put back its record) or the plugin (remove the copy and its hooks).",
                "Pick one mode: restore the lock and disable the plugin, or remove the copy and its hooks.",
            ))]
        return lines + [Line(g, "kit.plugin", "fine", Words(
            "The kit's plugin is turned on for this project.",
            f"Plugin mode: {vendor_mod.PLUGIN_KEY} is enabled ({where}).",
        ))]
    if bad:
        return lines + [Line(g, "kit.plugin", "cant_check", Words(
            "Can't tell whether the kit's plugin is turned on until Claude Code's settings can be read.",
            "Plugin mode: whether the plugin is enabled can't be told until the settings read.",
        ), SETTINGS_FIRST)]
    if left:
        return lines
    if where:  # named, and turned off there
        return lines + [Line(g, "kit.plugin", "gap", Words(
            f"The kit's plugin is turned off for this project (in {where}), so its hooks don't run here.",
            f"Plugin mode, but {where} sets {vendor_mod.PLUGIN_KEY} to false.",
        ), Words(
            f"Ask Claude to remove the plugin's `false` from {where}, then start a new session.",
            f"Drop the `{vendor_mod.PLUGIN_KEY}: false` from {where}.",
        ))]
    return lines + [Line(g, "kit.plugin", "gap", Words(
        "The kit's plugin isn't turned on for this project, and there's no copy of the kit in it, so its hooks don't run here.",
        f"Plugin mode (no {LOCK}), but {vendor_mod.PLUGIN_KEY} isn't enabled in the user's or the project's settings.",
    ), Words(
        f"In Claude Code, type `/plugin install {vendor_mod.PLUGIN_KEY}` (or turn it on in `/plugin`), then start a new session.",
        f"`/plugin install {vendor_mod.PLUGIN_KEY}`, or enable it in `enabledPlugins`.",
    ))]


def _vendored_hooks(i: Inputs, data: dict, err: str | None) -> list[Line]:
    g, id_ = "The kit", "kit.hooks"
    if err:
        return [Line(g, id_, "cant_check", Words(
            f"Can't check the kit's hooks until Claude Code's settings file ({SETTINGS}) can be read.",
            f"Kit hooks unchecked: {SETTINGS} doesn't read.",
        ), SETTINGS_FIRST)]
    version = _kit_version(i)
    exists = _file(i.root, SETTINGS)[0].exists()
    if not exists:
        diffs = [f"{SETTINGS} is missing"]
        listed = diffs[0]
    else:
        diffs = _hook_differences(data)
        listed = "; ".join(diffs)
    if not diffs:
        return [Line(g, id_, "fine", Words(
            "The kit's hooks are in place, as this version of the kit writes them.",
            f"Kit hooks in {SETTINGS} match {_kit_name(version)}'s entries.",
        ))]
    if exists and not _running_copy(i):
        # Another kit's entries (a checkout of the kit, the plugin): only the
        # project's own copy knows the entries its version writes.
        own = Words(
            f"Run the check with the project's own copy: `python3 -B {COPY_CLI} doctor`.",
            f"Run the vendored copy's doctor: `python3 -B {COPY_CLI} doctor`.",
        ) if _copy_has_doctor(i) else Words(
            "This project's copy of the kit is older than this check: ask Claude to update the workflow kit, then run the check again.",
            "The vendored copy predates `doctor`: update it (`update-workflow`), then run its doctor.",
        )
        mine, theirs = version, _lock_version(i)
        versions = f" ({mine}; the copy is {theirs})" if mine != theirs else ""
        return [Line(g, id_, "cant_check", Words(
            f"The kit's hooks differ from those of the kit running this check ({listed}), but that isn't this project's own copy, so it can't say which is right.",
            f"Kit hooks compared with the entries of the kit at {_home(i, i.kit_root)}{versions}, not this project's copy: {listed}.",
        ), own)]
    return [Line(g, id_, "gap", Words(
        f"The kit's hooks in Claude Code's settings ({SETTINGS}) aren't the ones this version of the kit writes ({listed}), so they don't run as this version of the kit expects.",
        f"Kit hooks in {SETTINGS} differ from {_kit_name(version)}'s entries: {listed}.",
    ), Words(
        "Ask Claude to update the workflow kit: the update writes the kit's hooks again, and removes any other hook that runs the kit.",
        "Rerun the kit's update (`update-workflow`, which runs `vendor update`) to rewrite its entries; it also drops any project hook whose command calls the kit's CLI.",
    ))]


@_check("The kit", "kit.profile")
def check_profile(i: Inputs) -> list[Line]:
    """`profile check`: its errors are gaps, its warnings notes."""
    g, id_ = "The kit", "kit.profile"
    if not i.root.is_dir():
        return [Line(g, id_, "gap", Words(
            f"The project's folder ({_home(i, i.root)}) isn't there, so there's nothing to check in it.",
            f"The project directory {_home(i, i.root)} doesn't exist (CLAUDE_PROJECT_DIR, or the current directory).",
        ), Words(
            "Open the project's folder and run the check from there.",
            "Run doctor from the checkout, or set CLAUDE_PROJECT_DIR to it.",
        ))]
    if i.profile_error:
        err = _relative(i, i.profile_error).rstrip(".")
        return [Line(g, id_, "gap", Words(
            f"The kit's profile ({PROFILE}, its settings for this project) has a mistake, so the kit can't use it: {err}.",
            f"`profile check` fails: {err}.",
        ), Words(
            f"Ask Claude to correct {PROFILE}, then run this again.",
            f"Correct {PROFILE} (`workflow profile check` says what's wrong).",
        ))]
    if i.profile is None:
        return [Line(g, id_, "gap", Words(
            f"The kit isn't set up in this project yet: it has no profile ({PROFILE}).",
            f"No {PROFILE}.",
        ), Words(
            "Ask Claude to set the workflow up for this project.",
            "Run the setup-workflow skill.",
        ))]
    if i.gaps_only:
        return []  # its warnings are notes
    warnings = [_relative(i, w) for w in profile_mod.check(i.profile)]
    if warnings:
        n = len(warnings)
        return [Line(g, id_, "note", Words(
            f"The kit's profile works, with {n} thing{'s' if n > 1 else ''} to tidy that {'don' if n > 1 else 'doesn'}'t stop it.",
            f"`profile check` warns: {'; '.join(warnings)}.",
        ), Words(
            "When you have a moment, ask Claude to run `workflow profile check` and tidy what it lists.",
            f"Tidy them in {PROFILE} when convenient.",
        ))]
    return [Line(g, id_, "fine", Words(
        f"The kit's profile ({PROFILE}) is in order.",
        "`profile check` passes with no warnings.",
    ))]


def _copy_problems(i: Inputs, lock: dict) -> list[str]:
    """`vendor verify`'s file part, read as doctor reads files: the files the
    lock lists that are missing, changed (not kept on purpose) or in
    conflict. The hooks and the plugin are `check_install`'s."""
    keeps = lock.get("kept") if isinstance(lock.get("kept"), dict) else {}
    raw = lock.get("conflicts")
    conflicts = sorted(str(c) for c in raw) if isinstance(raw, (dict, list)) else []
    missing, changed, outside = [], [], []
    for dst, h in lock["files"].items():
        if dst in conflicts:
            continue  # said once, as a conflict
        rel = PurePosixPath(str(dst))
        if rel.is_absolute() or ".." in rel.parts:  # the lock's path itself: a symlinked folder inside is fine
            outside.append(str(dst))
            continue
        path = i.root / rel
        try:
            there = path.exists()
        except OSError:
            there = True
        if not there:
            missing.append(dst)
            continue
        cur = _hash_file(path)
        if cur != h and (cur is None or keeps.get(dst) != cur):
            changed.append(dst)
    out = []
    for what, paths in (("missing", missing), ("changed by hand", changed), ("with an update's conflict to settle", conflicts),
                        ("outside the project", outside)):
        if paths:
            out.append(f"{what}: {', '.join(paths[:5])}" + (f" and {len(paths) - 5} more" if len(paths) > 5 else ""))
    return out


@_check("The kit", "kit.vendor")
def check_vendor(i: Inputs) -> list[Line]:
    """`vendor verify`, vendored only: the copy is as the kit wrote it."""
    if not i.vendored:
        return []
    g, id_ = "The kit", "kit.vendor"
    lock, err = _read_json(i.root, LOCK)
    if not err and not isinstance(lock.get("files"), dict):
        err = "it has no files map"
    if err:
        return [Line(g, id_, "gap", Words(
            f"The record of the kit's copy ({LOCK}) can't be read ({err}), so the copy can't be checked.",
            f"`vendor verify` can't read {LOCK}: {err}.",
        ), Words(
            f"Ask Claude to put back {LOCK} from the last kit update.",
            f"Restore {LOCK} from git (`git log -- {LOCK}`).",
        ))]
    problems = _copy_problems(i, lock)
    if problems:
        listed = "; ".join(problems)
        return [Line(g, id_, "gap", Words(
            f"The kit's copy in this project isn't as the kit wrote it ({listed}).",
            f"`vendor verify`: {listed}.",
        ), Words(
            "Ask Claude to look at the changed files: an update of the kit puts its own files back, and a change you meant to keep can be recorded.",
            "`vendor update` (update-workflow) restores the copy; `vendor resolve --keep <file>` records a deliberate edit, `vendor resolve <file>` a settled conflict.",
        ))]
    mp = lock.get("mattpocock_skills") or ("vendored" if lock.get("mattpocock_sha") else "not_vendored")
    if mp == "not_vendored":
        return [Line(g, id_, "note", Words(
            "The kit's copy is as the kit wrote it, but without Matt Pocock's skills, which building and reviewing tickets use.",
            "`vendor verify` passes, but Matt Pocock's skills aren't vendored (`vendor verify --strict` fails on this).",
        ), Words(
            "Ask Claude to update the workflow kit with Matt Pocock's skills, or to record that you go without them.",
            "`vendor update --mattpocock <checkout>`, or `--no-mattpocock` to decline them on purpose.",
        ))]
    return [Line(g, id_, "fine", Words(
        "The kit's copy in this project is as the kit wrote it.",
        f"`vendor verify` passes ({_kit_name(_lock_version(i))}).",
    ))]


_SOURCE_WORDS = {
    "environment": Words(f"set in the environment variable {EXPERIENCE_ENV}", f"from {EXPERIENCE_ENV}"),
    "local file": Words(f"set on this computer in {EXPERIENCE_FILE.as_posix()}", f"from {EXPERIENCE_FILE.as_posix()}"),
    "profile": Words("the project's default level", "from project.experience"),
}
_LEVEL_WORDS = {"new": "someone new to building", "developer": "a developer"}
_DEFAULT_WORDS = {"new": "new to building", "developer": "developer"}


def _skipped(exp: Experience) -> list[tuple[str, str]]:
    """The settings `resolve_experience` skipped, from its "ignored <name>:
    why" warnings: (name, why)."""
    out = []
    for w in exp.warnings:
        name, _, why = w.partition(":")
        out.append((name.removeprefix("ignored ").strip(), why.strip()))
    return out


@_check("The kit", "kit.experience")
def check_experience(i: Inputs) -> list[Line]:
    """The project's default and the person's level with its source, as
    `workflow status` reports it (#43)."""
    g, id_ = "The kit", "kit.experience"
    exp, default = i.experience, i.default
    if i.profile_error:
        d = Words(" The project's default can't be read until its profile is corrected.", "; project default: unreadable (profile error)")
    elif default:
        d = Words(f" The project's default level is {_DEFAULT_WORDS[default]}.", f"; project default: {default}")
    else:
        d = Words(" The project has no default level.", "; no project default")
    if exp.source == "profile":
        d = NONE  # the level is the default: said once
    skipped = _skipped(exp)
    names = " and ".join(n for n, _ in skipped)
    many = len(skipped) > 1
    sk = Words(f" Skipped {names}: {'each' if many else 'it'} should say `new` or `developer`." if skipped else "",
               "".join(f"; skipped {n} ({why})" for n, why in skipped))
    sk_fix = Words(f"Put `new` or `developer` in {names}, or remove {'them' if many else 'it'}.",
                   f"Set {names} to `new` or `developer`, or unset {'them' if many else 'it'}.")
    if exp.level:
        src = _SOURCE_WORDS[exp.source]
        msg = Words(
            f"Claude words things for {_LEVEL_WORDS[exp.level]} ({src.new}).{d.new}{sk.new}",
            f"Experience: {exp.level} ({src.developer}){d.developer}{sk.developer}.",
        )
        return [Line(g, id_, "note", msg, sk_fix)] if skipped else [Line(g, id_, "fine", msg)]
    return [Line(g, id_, "note", Words(
        f"Nobody has said how much you know about building software, so Claude explains things as for someone new to it.{d.new}{sk.new}",
        f"Experience: unknown (worded as new){d.developer}{sk.developer}.",
    ), Words(
        "Start a Claude session and answer its first question, how much you know; or ask Claude to set the project's default."
        + (" " + sk_fix.new if skipped else ""),
        f"Set {EXPERIENCE_ENV}, {EXPERIENCE_FILE.as_posix()} or project.experience to `new` or `developer`.",
    ))]


@_check("The kit", "kit.ruleset")
def check_ruleset(i: Inputs) -> list[Line]:
    """The profile's `project.ruleset`. `true` is fine here: the GitHub lines
    check it against GitHub."""
    g, id_ = "The kit", "kit.ruleset"
    if i.profile is None:
        return [Line(g, id_, "cant_check", Words(
            "Can't tell whether the project means its main branch to be protected until the kit's profile can be read.",
            "project.ruleset unknown: no readable profile.",
        ), PROFILE_FIRST if i.profile_error else SET_UP_FIRST)]
    base = i.profile.base_branch
    upgrade = OFFERS["protect_main"]
    if i.profile.ruleset is True:
        return [Line(g, id_, "fine", Words(
            f"The project's profile says `{base}` is protected on GitHub by a ruleset.",
            f"project.ruleset = true: `{base}` should have a ruleset.",
        ))]
    if i.profile.ruleset is False:
        return [Line(g, id_, "note", Words(
            f"Solo mode: `{base}` isn't protected on GitHub, chosen on purpose; while you work with Claude, the kit's guard keeps changes off `{base}`.",
            f"project.ruleset = false (solo mode): no ruleset on `{base}` expected.",
        ), Words(
            f"When you want GitHub to protect `{base}` too, ask Claude to \"{upgrade}\".",
            f"Run the upgrade-setup skill's \"{upgrade}\" for the ruleset.",
        ), offer="protect_main")]
    return [Line(g, id_, "note", Words(
        f"Whether `{base}` is protected is not set (as before): the project was set up before solo mode, so nothing new is asked of it.",
        "project.ruleset: not set (as before).",
    ), Words(
        f"Nothing to do; ask Claude to \"{upgrade}\" if GitHub doesn't protect `{base}` yet.",
        "Nothing to do; set project.ruleset to true or false to say which.",
    ))]


# ---------- GitHub ----------
#
# The ruleset, the merge settings and CODEOWNERS (#59). Whether the base branch
# is protected is `workflow protection`'s read-back (`protection.check`), called
# as it is; these lines only word what it found and read the other rules of
# the rulesets it counted. GitHub's answers come from --rulesets and --repo
# when given, else from `gh api` (only GETs), read once for every line.

GH_TIMEOUT = 30  # seconds, for one `gh api` call
GH_BUDGET = 60  # seconds, for all of them
# What CODEOWNERS should cover (docs/enforcement.md §3).
OWNED = ("/.claude/", "/.github/workflows/")
# How `gh` says it isn't signed in, and how GitHub says rulesets need a paid
# plan (a private repository on GitHub Free).
_SIGNED_OUT = re.compile(r"gh auth login|GH_TOKEN|not logged in|authentication required|HTTP 401", re.I)
_PLAN = re.compile(r"upgrade to github|make this repository public", re.I)
# How `gh` says it couldn't reach GitHub, and how GitHub says to wait.
_OFFLINE = re.compile(r"error connecting to|proxyconnect|connection refused|no such host|dial tcp|i/o timeout|check your internet connection|TLS handshake", re.I)
_RATE_LIMIT = re.compile(r"rate limit|wait a few minutes|HTTP 429", re.I)
# The files doctor takes instead of `gh`, as a developer's fix names them.
GIVE_FILES = "--rulesets and --repo files (GET repos/<repo>/rulesets/<id> each in full, GET repos/<repo>)"
# The upgrade that requires the checks (#38), offered on the required checks' line (#69).
REQUIRE_CHECKS = OFFERS["require_checks"]
# A CODEOWNERS owner: @login, @org/team, or an email address.
_OWNER = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9_-]*)(?:/[A-Za-z0-9._-]+)?|[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class _Kind:
    """A kind of missing protection the read-back reports: its line's id
    (None: the main line says it), and a few plain words for the main line."""

    line: str | None
    short: str


KINDS = {
    "no_rulesets": _Kind(None, "it has no ruleset"),
    "not_on_base": _Kind("github.protection.base", "no ruleset covers it"),
    "unsure": _Kind("github.protection.base", "a ruleset may not cover it"),
    "not_active": _Kind("github.protection.active", "a ruleset is turned off"),
    "evaluate": _Kind("github.protection.active", "a ruleset only reports"),
    "bypass": _Kind("github.protection.bypass", "someone may skip its rules"),
    "bypass_unread": _Kind("github.protection.bypass", "who may skip its rules can't be seen"),
    "deletion": _Kind("github.protection.deletions", "it can be deleted"),
    "non_fast_forward": _Kind("github.protection.force_pushes", "it can be force-pushed"),
    "pull_request": _Kind("github.protection.pull_requests", "pull requests aren't required"),
}
assert set(KINDS) == set(protection_mod.KINDS)


@dataclass
class _Answer:
    """One of GitHub's answers: its value, or why it couldn't be read (in
    both wordings) and how to read it."""

    value: object = None
    why: Words | None = None
    fix: Words = NONE


@dataclass
class _GitHub:
    """What the GitHub lines read: the read-back (or why not), whether its
    "not protected" rests on what this account can't see, and the merge
    settings (or why not)."""

    report: protection_mod.Report | None = None
    report_why: _Answer | None = None
    unseen: _Answer | None = None  # protected, but for bypass lists only an admin can read
    plan: bool = False  # GitHub said rulesets need a paid plan: read as no rulesets
    # Without the default branch, the readings differ but neither protects the
    # base branch: the ruleset line still says so. The other lines can't be
    # checked, unless neither reading puts a ruleset on it (then `report` is
    # set, and they read as with none).
    unprotected_either: bool = False
    merge: dict | None = None
    merge_why: _Answer | None = None
    settings: dict | None = None  # the repository's settings as given (its owner and visibility, #246)


ADMIN = Words(
    "Ask the repository's admin to run this check, or to look at the ruleset's bypass list in Settings → Rules.",
    "Rerun with an admin's `gh`, or give --rulesets from an admin's GET repos/<repo>/rulesets/<id>.",
)


def _sign_in(missing: bool, give: str = GIVE_FILES) -> Words:
    return Words(
        ("Install GitHub's command-line tool (`gh`, from cli.github.com) and sign in with `gh auth login`"
         if missing else "Sign in with `gh` (run `gh auth login` in a terminal)") + ", or ask a cloud session to check the set-up.",
        ("Install gh and run `gh auth login`" if missing else "Run `gh auth login`")
        + f", or give {give}; or ask a cloud session to check the set-up.",
    )


def _again(give: str = GIVE_FILES) -> Words:
    return Words(
        "Run the check again in a while; if it says the same, ask a cloud session to check the set-up.",
        f"Rerun, or give {give}.",
    )


def _scrubbed(i: Inputs, text: str) -> str:
    """Text from `gh`, on one line, with the home directory as `~`."""
    home = (i.environ.get("HOME") or "").rstrip(os.sep)
    for h in dict.fromkeys((home, os.path.realpath(home) if home else "")):
        if h and h != os.sep:
            text = text.replace(h + os.sep, "~" + os.sep)
    return _shown(_relative(i, text), 120)


def _gh(i: Inputs, path: str, deadline: float, flag: str, paginate: bool = False, give: str = GIVE_FILES) -> _Answer:
    """`gh api <path>`'s JSON (with `paginate`, the pages as a list), read
    with a GET and nothing else, within what is left of `GH_BUDGET`. A
    developer's fix names `give`, the files to give instead."""
    left = deadline - time.monotonic()
    shown = path.split("?")[0]
    again = _again(give)
    if left <= 0:
        return _Answer(why=Words(f"GitHub didn't answer within {GH_BUDGET} seconds", f"GitHub's reads took over {GH_BUDGET} s, before `gh api {shown}`"), fix=again)
    timeout = min(GH_TIMEOUT, left)
    ran = _run(i, ["gh", "api", *(["--paginate"] if paginate else []), path], timeout=timeout, stderr=True)
    offline = _OFFLINE.search(ran.err)
    lines = ran.err.splitlines()
    err = _scrubbed(i, next((ln for ln in lines if _OFFLINE.search(ln)), "") if offline else (lines[-1] if lines else ""))
    if ran.state == "missing":
        return _Answer(why=Words("GitHub's command-line tool (`gh`) isn't installed here", f"no `gh` on the PATH, and no {flag} file"), fix=_sign_in(True, give))
    if ran.state == "failed" and _SIGNED_OUT.search(ran.err):
        return _Answer(why=Words("`gh` isn't signed in to GitHub", f"`gh api` isn't signed in ({err})"), fix=_sign_in(False, give))
    repo = i.profile.repo
    if ran.state == "failed" and "HTTP 404" in ran.err and shown in (f"repos/{repo}", f"repos/{repo}/rulesets"):
        return _Answer(why=Words(f"GitHub has no repository `{repo}` that your `gh` can see", f"`gh api {shown}` failed: {err}"), fix=Words(
            f"Check the repository's name in the kit's profile (`project.repo` in {PROFILE}) and that your GitHub account can see it; or ask a cloud session to check the set-up.",
            f"Check project.repo ({repo}) and gh's access to it, or give {give}.",
        ))
    if ran.state == "failed" and offline:
        return _Answer(why=Words(f"`gh` couldn't reach GitHub ({err})", f"`gh api {shown}` couldn't connect: {err}"), fix=Words(
            "Check your internet connection (or the proxy), then run the check again; or ask a cloud session to check the set-up.",
            f"Check the network or proxy and rerun, or give {give}.",
        ))
    if ran.state == "failed" and _RATE_LIMIT.search(ran.err):
        return _Answer(why=Words(f"GitHub asked `gh` to slow down ({err})", f"`gh api {shown}` was rate limited: {err}"), fix=again)
    if ran.state == "failed" and "HTTP 403" in ran.err:
        return _Answer(why=Words(f"GitHub refused to show it to your `gh`: {err}", f"`gh api {shown}` was refused: {err}"), fix=Words(
            "Your GitHub account may not be allowed to read this: ask the repository's admin to run the check, or ask a cloud session to check the set-up.",
            f"gh's token lacks access (HTTP 403): use an admin's gh, or give {give}.",
        ))
    if ran.state == "timeout":
        budget = "" if timeout >= GH_TIMEOUT else f", the rest of the {GH_BUDGET} s for all of GitHub's reads"
        n = round(timeout)
        return _Answer(why=Words(f"GitHub didn't answer within {n} second{'' if n == 1 else 's'}{budget}", f"`gh api {shown}` timed out after {timeout:.0f} s{budget}"), fix=again)
    if ran.state != "ok":
        said = err if ran.state == "failed" else "its answer isn't UTF-8 text"
        return _Answer(why=Words(f"GitHub answered `gh` with an error: {said}", f"`gh api {shown}` failed: {said}"), fix=again)
    try:
        values = posts_mod.decode_values(ran.out)
    except posts_mod.CommentsError as e:
        values, bad = [], str(e)
    else:
        bad = None if values else "it printed nothing"
    if bad:
        return _Answer(why=Words("GitHub's answer to `gh` couldn't be read", f"`gh api {shown}`'s output isn't JSON ({bad})"), fix=again)
    return _Answer(values if paginate else values[0])


def _given(i: Inputs, given: Path | str, flag: str, fix: Words | None = None, what: str = "GitHub's answer") -> _Answer:
    """A file given on the command line (`-`: standard input), read as doctor
    reads files: `what` it should hold, and the `fix` when it can't be read
    (by default, the GitHub files')."""
    fix = fix or Words(
        f"Ask Claude to fetch it from GitHub again (as `workflow protection` takes it), or leave out {flag} to read GitHub with `gh`.",
        f"Give {flag} as `workflow protection` takes it, or leave it out to use `gh api`.",
    )
    if given == "":
        return _Answer(why=Words(f"the {flag} file was given no path", f"{flag} was given no path"), fix=fix)
    elif given == "-":
        shown = "standard input"
        value, err = _stdin(what)
    else:
        shown = _shown(_home(i, Path(given)), 120)
        value, err = _read_value(i.root, given, protection_mod.loads)
        if err is None and value is None:
            err = f"it holds null, not {what}" if _file(i.root, given)[0].exists() else "it isn't there"
    if err:
        return _Answer(why=Words(f"the {flag} file ({shown}): {err}", f"{flag} {shown}: {err}"), fix=fix)
    return _Answer(value)


def _stdin(what: str = "GitHub's answer"):
    """Standard input's JSON, read as UTF-8, as `workflow protection` reads
    it; never waited on at a terminal."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None, f"standard input is a terminal or closed, not {what}"
        text = sys.stdin.buffer.read().decode("utf-8")
        if not text.strip():
            return None, "standard input was empty"
    except UnicodeDecodeError:
        return None, "it isn't UTF-8 text"
    except (OSError, ValueError, AttributeError) as e:
        return None, f"standard input can't be read ({type(e).__name__})"
    return _parse_json(text, protection_mod.loads)


def _rulesets(i: Inputs, deadline: float) -> tuple[_Answer, bool]:
    """The rulesets, each in full: from --rulesets, else the list (pages of
    summaries) and then each one through `gh api`. And whether GitHub said
    rulesets need a paid plan, read as none."""
    if i.rulesets_file is not None:
        return _given(i, i.rulesets_file, "--rulesets"), False
    repo = i.profile.repo
    listed = _gh(i, f"repos/{repo}/rulesets?includes_parents=true&per_page=100", deadline, "--rulesets", paginate=True)
    if listed.why:
        plan = _PLAN.search(listed.why.developer) is not None
        return (_Answer([]) if plan else listed), plan
    flat = [x for page in listed.value for x in (page if isinstance(page, list) else [page])]
    ids = [x.get("id") if isinstance(x, dict) else None for x in flat]
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in ids):
        return _Answer(why=Words("GitHub's list of rulesets couldn't be read", "`gh api`'s list of rulesets has an entry without an id"), fix=_again()), False
    full = []
    for n in ids:
        one = _gh(i, f"repos/{repo}/rulesets/{n}", deadline, "--rulesets")
        if one.why:
            return one, False
        full.append(one.value)
    return _Answer(full), False


def _not_github(e: Exception, what: str) -> _Answer:
    rulesets = "rulesets" in what
    return _Answer(why=Words(f"{what} aren't in the shape GitHub gives them", _upper(str(e))), fix=Words(
        f"Ask Claude to fetch {what} from GitHub again" + (", each ruleset in full" if rulesets else "") + ", as `workflow protection` takes them.",
        f"Give {GIVE_FILES}, as `workflow protection` takes them.",
    ))


def _bypass_seen(rulesets):
    """The rulesets with a bypass list that couldn't be read taken as empty,
    as the kit sets it (pages of rulesets as they are)."""
    def seen(rs):
        return {**rs, "bypass_actors": []} if isinstance(rs, dict) and "bypass_actors" not in rs else rs

    if not isinstance(rulesets, list):
        return rulesets
    return [[seen(r) for r in x] if isinstance(x, list) else seen(x) for x in rulesets]


def _gh_deadline(i: Inputs) -> float:
    """When doctor stops waiting on GitHub: `GH_BUDGET` after its first
    read, for all of them (the GitHub lines' and the runs')."""
    if i._gh_until is None:
        i._gh_until = time.monotonic() + GH_BUDGET
    return i._gh_until


def _github(i: Inputs) -> _GitHub | None:
    """GitHub's answers and the read-back, once for every line; None with no
    readable profile (the lines then wait on it)."""
    if i.profile is None:
        return None
    if i._github is not None:
        return i._github
    base = i.profile.base_branch
    deadline = _gh_deadline(i)
    gh = i._github = _GitHub()
    settings = _given(i, i.repo_file, "--repo") if i.repo_file is not None else _gh(i, f"repos/{i.profile.repo}", deadline, "--repo")
    accepted = None  # the settings the read-back took
    gh.settings = settings.value if not settings.why and isinstance(settings.value, dict) else None
    if settings.why:
        gh.merge_why = settings
    else:
        try:
            # The read-back of no rulesets: its merge settings, the settings checked as it checks them.
            gh.merge = protection_mod.check([], base, settings.value).merge
            accepted = settings.value
        except protection_mod.ProtectionError as e:
            gh.merge_why = _not_github(e, "the repository's settings")
    rulesets, gh.plan = _rulesets(i, deadline)
    if rulesets.why:
        gh.report_why = rulesets
        return gh
    # The settings the rulesets are read with: the accepted ones, or, when
    # only their merge settings are wrong, their default branch alone.
    raw = settings.value.get("default_branch") if isinstance(settings.value, dict) else None
    placed = accepted if accepted is not None else {"default_branch": raw} if isinstance(raw, str) else None
    known = placed is not None and placed.get("default_branch") is not None
    seen = _bypass_seen(rulesets.value)
    try:
        if known:
            rep = protection_mod.check(rulesets.value, base, placed)
        else:
            # The default branch unknown: read it as the base branch and as
            # another. When the two readings differ, every ruleset line rests
            # on what can't be seen; when they agree, either is the answer.
            either = [{**(placed or {}), "default_branch": d} for d in (base, f"{base}-not")]
            rep, other = (protection_mod.check(rulesets.value, base, settings_) for settings_ in either)
            gh.unprotected_either = not any(protection_mod.check(seen, base, settings_).protected for settings_ in either)
            placed = either[0]
    except protection_mod.ProtectionError as e:
        gh.report_why = _not_github(e, "GitHub's rulesets")
        return gh
    differ = not known and _substance(rep) != _substance(other)
    if differ:
        no_default = settings.why is None
        gh.report_why = _Answer(why=Words(
            "a ruleset applies to GitHub's default branch, and "
            + ("the repository's settings don't say which branch that is" if no_default else f"the repository's settings couldn't be read: {settings.why.new}")
            + f", so it can't tell whether that is `{base}`",
            "a ruleset targets ~DEFAULT_BRANCH, and " + ("the settings have no default_branch" if no_default else settings.why.developer),
        ), fix=settings.fix if settings.why else Words(
            "Ask Claude to fetch the repository's settings from GitHub in full, with its default branch.",
            "Give --repo with default_branch (GET repos/<repo>).",
        ))
        if rep.effective or other.effective:
            return gh
        # Neither reading puts a ruleset on the base branch: the lines that
        # read its rules read the same in both, so they read this one.
    gh.report = rep
    # What the read-back can't see counts as missing there, so an unknown never
    # reads as protected. When it would read protected with unread bypass
    # lists as empty, "not protected" is only an unknown: never removed
    # protection.
    if not rep.protected and protection_mod.check(seen, base, placed).protected:
        gh.unseen = _Answer(why=Words(
            "who may skip its ruleset's rules can be seen only by the repository's admins",
            "; ".join(m for k, m in zip(rep.kinds, rep.missing) if k == "bypass_unread"),
        ), fix=ADMIN)
    return gh


def _substance(rep: protection_mod.Report) -> tuple:
    """What the lines read from a read-back: two readings alike in this give
    the same lines (`check` keeps the caller's rulesets, so they compare by
    identity)."""
    return rep.protected, rep.kinds, rep.required_checks, [id(rs) for rs in rep.effective]


def _waits(i: Inputs, id_: str, what: Words, answer: _Answer | None, group: str = "GitHub") -> Line:
    """A line that can't be checked: GitHub's answer (or what else it reads)
    couldn't be read, or (`answer` None) the profile couldn't."""
    if answer is None:
        why = Words("the kit's profile can't be read", "the profile doesn't read (project.repo, project.base_branch)") if i.profile_error else Words(
            "the kit isn't set up here yet (it has no profile)", "no profile (project.repo, project.base_branch)")
        fix = PROFILE_FIRST if i.profile_error else SET_UP_FIRST
    else:
        why, fix = answer.why, answer.fix
    return Line(group, id_, "cant_check", Words(f"Can't check {what.new}: {_relative(i, why.new)}.", f"{what.developer} unchecked: {_relative(i, why.developer)}."), fix)


def _report(i: Inputs, id_: str, what: Words) -> tuple[protection_mod.Report | None, Line | None]:
    """The read-back, or the line saying it can't be checked."""
    gh = _github(i)
    if gh is None or gh.report is None:
        return None, _waits(i, id_, what, gh.report_why if gh else None)
    return gh.report, None


def _rules(rep: protection_mod.Report, type_: str) -> list[dict]:
    """The rules of this type in the active rulesets on the base branch,
    each one's parameters (an object, empty when it has none)."""
    return [r.get("parameters") or {} for rs in rep.effective for r in rs["rules"] if r["type"] == type_]


def _count(count: int, one: str, many: str) -> str:
    """`one` for one, else the number and `many`."""
    return one if count == 1 else f"{count} {many}"


def _upper(text: str) -> str:
    return text[:1].upper() + text[1:]


def _plan_words(gh: _GitHub) -> Words:
    return Words(" GitHub said rulesets on a private repository need a paid plan.", " (GitHub: rulesets need a paid plan on this private repository.)") if gh.plan else NONE


@_check("GitHub", "github.ruleset")
def check_protection(i: Inputs) -> list[Line]:
    """Whether the base branch is protected, by the read-back, against the
    profile's `project.ruleset`; each missing protection its own gap."""
    g, id_ = "GitHub", "github.ruleset"
    gh = _github(i)
    if gh is not None and gh.report_why is not None and gh.unprotected_either and (i.profile.ruleset is not False or gh.report is not None):
        # In solo mode only with no ruleset on the base branch either way: a
        # ruleset with holes that may be on it isn't a choice to note.
        return [_unprotected_either(i, gh)]
    rep, wait = _report(i, id_, Words("whether the main branch is protected on GitHub", "The base branch's protection"))
    if wait:
        return [wait]
    gh, base, ruleset = _github(i), i.profile.base_branch, i.profile.ruleset
    protect, restore = OFFERS["protect_main"], OFFERS["restore_protection"]
    if gh.unseen and ruleset is False:
        return [Line(g, id_, "note", Words(
            f"Solo mode: whether GitHub protects `{base}` can't be seen ({gh.unseen.why.new}); either way is fine in solo mode.",
            f"Solo mode (project.ruleset = false); protection of `{base}` unknown: {gh.unseen.why.developer}.",
        ), Words(
            f"When you want GitHub to protect `{base}`, ask Claude to \"{protect}\".",
            f"Run upgrade-setup's \"{protect}\" to leave solo mode.",
        ), offer="protect_main")]
    if gh.unseen:
        return [_waits(i, id_, Words(f"whether GitHub protects `{base}`", f"`{base}`'s protection"), gh.unseen)]
    plan = _plan_words(gh)
    plan_fix = Words(" Rulesets on a private repository need a paid GitHub plan (Team or above), or the repository made public.",
                     " Needs a paid plan for a private repository, or a public one.") if gh.plan else NONE
    if rep.protected:
        if ruleset is False:
            return [Line(g, id_, "note", Words(
                f"GitHub protects `{base}` with a ruleset, though the kit's profile still says solo mode.",
                f"`{base}` is protected, but project.ruleset = false (solo mode).",
            ), Words(
                f"Ask Claude to \"{protect}\": it sees the protection and opens the pull request that leaves solo mode.",
                f"Run upgrade-setup's \"{protect}\": the read-back finds it protected and its pull request sets project.ruleset = true.",
            ), offer="protect_main")]
        return [Line(g, id_, "fine", Words(
            f"GitHub protects `{base}`: changes reach it only through pull requests, and it can't be deleted or force-pushed.",
            f"`workflow protection`: `{base}` is protected (deletions restricted, force pushes blocked, pull requests required, no bypass list).",
        ))]
    found = _found(rep)
    plain = ", ".join(dict.fromkeys(KINDS[k].short for k, _ in found))
    listed = "; ".join(m for _, m in found)
    if ruleset is False and not rep.effective:
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't protect `{base}` ({plain}), chosen on purpose; while you work with Claude, the kit's guard keeps changes off `{base}`.{plan.new}",
            f"Solo mode (project.ruleset = false): `{base}` isn't protected, as expected: {listed}.{plan.developer}",
        ), Words(
            f"When you want GitHub to protect `{base}` too, ask Claude to \"{protect}\".{plan_fix.new}",
            f"Run upgrade-setup's \"{protect}\" for the ruleset.{plan_fix.developer}",
        ), offer="protect_main")]
    if ruleset is True:
        main = Line(g, id_, "gap", Words(
            f"The kit's profile says GitHub protects `{base}`, but it doesn't any more ({plain}): protection that was removed or weakened is never trusted.{plan.new}",
            f"Removed protection: project.ruleset = true, but the read-back finds `{base}` unprotected: {listed}.{plan.developer}",
        ), Words(
            f"Ask Claude to \"{restore}\": it puts the ruleset back.{plan_fix.new}",
            f"Run upgrade-setup's \"{restore}\" (`restore_protection`), then read it back with `workflow protection`.{plan_fix.developer}",
        ), offer="restore_protection")
        offer = restore
    else:  # `ruleset` absent, or solo mode with a ruleset on the base branch that has holes
        main = Line(g, id_, "gap", Words(
            f"GitHub doesn't protect `{base}` ({plain}), so {_consequence(rep, found)}.{plan.new}",
            f"`workflow protection`: `{base}` isn't protected: {listed}.{plan.developer}",
        ), Words(
            f"Ask Claude to \"{protect}\".{plan_fix.new}",
            f"Run upgrade-setup's \"{protect}\", or set the ruleset up by hand (docs/enforcement.md §1).{plan_fix.developer}",
        ), offer="protect_main")
        offer = protect
    return [main] + _missing_lines(found, base, offer)


def _unprotected_either(i: Inputs, gh: _GitHub) -> Line:
    """The ruleset line when the default branch is unknown but the base
    branch is unprotected whichever it is: what is missing can't be told, but
    that something is can."""
    g, id_ = "GitHub", "github.ruleset"
    base, ruleset = i.profile.base_branch, i.profile.ruleset
    protect, restore = OFFERS["protect_main"], OFFERS["restore_protection"]
    unknown = gh.report_why
    if ruleset is False:
        return Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't protect `{base}`, whichever branch is its default, chosen on purpose.",
            f"Solo mode (project.ruleset = false): `{base}` unprotected under either reading of ~DEFAULT_BRANCH ({unknown.why.developer}).",
        ), Words(
            f"When you want GitHub to protect `{base}` too, ask Claude to \"{protect}\".",
            f"Run upgrade-setup's \"{protect}\" for the ruleset.",
        ), offer="protect_main")
    if ruleset is True:
        return Line(g, id_, "gap", Words(
            f"The kit's profile says GitHub protects `{base}`, but it doesn't any more, whichever branch is GitHub's default: protection that was removed or weakened is never trusted. What is missing can't be told: {unknown.why.new}.",
            f"Removed protection: project.ruleset = true, but `{base}` is unprotected under either reading of ~DEFAULT_BRANCH ({unknown.why.developer}).",
        ), Words(
            f"Ask Claude to \"{restore}\": it puts the ruleset back.",
            f"Run upgrade-setup's \"{restore}\" (`restore_protection`); give --repo to see what is missing.",
        ), offer="restore_protection")
    return Line(g, id_, "gap", Words(
        f"GitHub doesn't protect `{base}`, whichever branch is its default. What is missing can't be told: {unknown.why.new}.",
        f"`{base}` is unprotected under either reading of ~DEFAULT_BRANCH ({unknown.why.developer}).",
    ), Words(
        f"Ask Claude to \"{protect}\".",
        f"Run upgrade-setup's \"{protect}\"; give --repo to see what is missing.",
    ), offer="protect_main")


def _consequence(rep: protection_mod.Report, found: list[tuple[str, str]]) -> str:
    """What could happen to the base branch, from what is missing."""
    kinds = {k for k, _ in found}
    if not rep.effective:
        return "a change could reach it without a pull request, or its history could be lost"
    out = []
    if "pull_request" in kinds:
        out.append("a change could reach it without a pull request")
    if kinds & {"deletion", "non_fast_forward"}:
        out.append("its history could be lost")
    if kinds & {"bypass", "bypass_unread"}:
        out.append("someone could skip its rules")
    return ", or ".join(out) or "it isn't protected"


def _found(rep: protection_mod.Report) -> list[tuple[str, str]]:
    """What the read-back found missing, by kind. A ruleset on other branches
    (or one that may be) is left out while another one covers the base
    branch: it is someone's other ruleset, not this one's problem."""
    found = list(zip(rep.kinds, rep.missing))
    return [(k, m) for k, m in found if not (k in ("not_on_base", "unsure") and rep.effective)]


def _protection_words(id_: str, kinds: list[str], base: str) -> tuple[str, str]:
    """A missing protection's line in plain words, and a developer's fix."""
    n = len(kinds)
    if id_ == "github.protection.active":
        off, evaluating = kinds.count("not_active"), kinds.count("evaluate")
        parts = ([f"{_count(off, 'a ruleset', 'rulesets')} that would protect `{base}` {'is' if off == 1 else 'are'} turned off"] if off else []) + (
            [f"{_count(evaluating, 'a ruleset', 'rulesets')} only {'reports' if evaluating == 1 else 'report'}, without blocking anything"] if evaluating else [])
        return _upper("; ".join(parts)) + ".", "Set the ruleset's enforcement to active."
    if id_ == "github.protection.base":
        if "unsure" in kinds:
            return (f"{_upper(_count(n, 'a ruleset', 'rulesets'))} on GitHub may not cover `{base}`: {'its' if n == 1 else 'their'} branch pattern can't be matched here, so no ruleset is known to protect it.",
                    f"Name `{base}` in the ruleset (`~DEFAULT_BRANCH` or `refs/heads/{base}`) rather than by a pattern.")
        return (f"{_upper(_count(n, 'a ruleset', 'rulesets'))} on GitHub {'doesn' if n == 1 else 'don'}'t cover `{base}`: it applies to other branches or tags, so no ruleset protects it.",
                f"Make the ruleset include `~DEFAULT_BRANCH` or `refs/heads/{base}`, and not exclude it.")
    if id_ == "github.protection.bypass":
        if "bypass" in kinds:
            return f"People or apps on a ruleset's bypass list can skip its rules on `{base}`.", "Empty the ruleset's bypass list."
        return (f"Who may skip the ruleset's rules on `{base}` can't be seen (that needs admin access on GitHub), so it can't count as protecting it.",
                ADMIN.developer)
    rule, words = {
        "github.protection.deletions": ("deletion", f"`{base}` can be deleted on GitHub: no active ruleset stops it."),
        "github.protection.force_pushes": ("non_fast_forward", f"Someone could force push to `{base}`, rewriting its history: no active ruleset stops it."),
        "github.protection.pull_requests": ("pull_request", f"Changes can reach `{base}` without a pull request: no active ruleset requires one."),
    }[id_]
    return words, f"Add a `{rule}` rule to an active ruleset on `{base}`."


def _missing_lines(found: list[tuple[str, str]], base: str, offer: str) -> list[Line]:
    """Each kind of missing protection the read-back found, as its own gap,
    in plain words and with the read-back's own words for a developer."""
    by_line: dict[str, list[tuple[str, str]]] = {}
    for kind, words in found:
        if KINDS[kind].line:
            by_line.setdefault(KINDS[kind].line, []).append((kind, words))
    out = []
    for id_, items in by_line.items():
        kinds = [k for k, _ in items]
        new, dev_fix = _protection_words(id_, kinds, base)
        unread = set(kinds) == {"bypass_unread"}
        out.append(Line("GitHub", id_, "cant_check" if unread else "gap", Words(new, _upper("; ".join(w for _, w in items)) + "."),
                        ADMIN if unread else Words(f"Ask Claude to \"{offer}\": it puts this right.", dev_fix)))
    return out


def _solo_unprotected(rep: protection_mod.Report, i: Inputs) -> bool:
    """Solo mode with no ruleset on the base branch at all, as chosen."""
    return i.profile.ruleset is False and not rep.protected and not rep.effective


# The checks that ran on the base branch and the open pull requests (#69):
# read only when the required checks' line needs them, from --checks and --prs
# when given, else with `gh api` (GETs only) within the GitHub lines' budget.
GIVE_CHECKS = "--checks (GET repos/<repo>/commits/<base>/check-runs and .../status, every page, in one file)"
GIVE_PRS = "--prs (GET repos/<repo>/pulls?state=open, every page)"
PRS_FIX = Words(
    "Ask Claude to fetch the open pull requests from GitHub again, as `workflow ready --prs` takes them, or leave out --prs to read GitHub with `gh`.",
    "Give --prs as `workflow ready --prs` takes it (GET repos/<repo>/pulls?state=open), or leave it out to use `gh api`.",
)
# What the pull requests that add required checks to the profile carry in their
# body (upgrade-setup's pull request that leaves solo mode, and its profile pull
# request).
REQUIRED_CHECKS_MARKER = "<!-- workflow:required-checks -->"


def _split_checks(value) -> tuple[list, list]:
    """(check-run pages, combined-status pages) from what --checks holds:
    GET .../check-runs answers, GET .../status answers and statuses
    (GET .../statuses), as pages or one list, in any order."""
    runs, combined, plain = [], [], []

    def go(v, depth: int) -> None:
        if depth > 6:
            raise protection_mod.ProtectionError("it is nested deeper than GitHub nests check runs")
        if isinstance(v, list):
            for x in v:
                go(x, depth + 1)
        elif isinstance(v, dict) and "check_runs" in v and "statuses" in v:
            # Both side by side in one object: each read as its own.
            runs.append({k: v[k] for k in ("check_runs", "total_count") if k in v})
            combined.append({"statuses": v["statuses"]})
        elif isinstance(v, dict) and "check_runs" in v:
            runs.append(v)
        elif isinstance(v, dict) and "statuses" in v:
            combined.append(v)
        elif isinstance(v, dict) and "context" in v:
            plain.append(v)
        else:
            raise protection_mod.ProtectionError("it isn't check runs or statuses, as GitHub gives them")

    go(value, 0)
    if plain:
        combined.append({"statuses": plain})
    return runs, combined


def _read_checks(i: Inputs) -> _Answer:
    """The base branch's latest commit's statuses, then that commit's check
    runs, with `gh api`: (check-run pages, combined-status pages)."""
    repo, deadline = i.profile.repo, _gh_deadline(i)
    ref = urllib.parse.quote(i.profile.base_branch, safe="/")
    status = _gh(i, f"repos/{repo}/commits/{ref}/status?per_page=100", deadline, "--checks", paginate=True, give=GIVE_CHECKS)
    if status.why:
        return status
    sha = next((x.get("sha") for x in status.value if isinstance(x, dict) and isinstance(x.get("sha"), str)), None)
    if sha is None or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        return _Answer(why=Words("GitHub's answer didn't name the commit", "GET .../status has no sha"), fix=_again(GIVE_CHECKS))
    runs = _gh(i, f"repos/{repo}/commits/{sha}/check-runs?per_page=100", deadline, "--checks", paginate=True, give=GIVE_CHECKS)
    return runs if runs.why else _Answer((runs.value, status.value))


def _checks_ran(i: Inputs, rep: protection_mod.Report) -> list[dict] | None:
    """The checks that ran on the base branch's latest commit that the
    ruleset doesn't require (#66's "checks that ran", so never the try-it
    link's), each with its result; None when they can't be read."""
    if i._checks is None:
        if i.checks_file is not None:
            given = _given(i, i.checks_file, "--checks", what="check runs")
            try:
                i._checks = given if given.why else _Answer(_split_checks(given.value))
            except protection_mod.ProtectionError as e:
                i._checks = _Answer(why=Words(f"the --checks file: {e}", f"--checks: {e}"))
        else:
            i._checks = _read_checks(i)
    if i._checks.why:
        return None
    try:
        return protection_mod.checks_ran(*i._checks.value, rep.required_checks)
    except protection_mod.ProtectionError:
        return None


def _open_prs(i: Inputs) -> _Answer:
    """The open pull requests, each with a number and its body, from --prs
    (as `workflow ready --prs` takes them), else `gh api`."""
    if i._prs is None:
        if i.prs_file is not None:
            answer = _given(i, i.prs_file, "--prs", what="pull requests", fix=PRS_FIX)
        else:
            answer = _gh(i, f"repos/{i.profile.repo}/pulls?state=open&per_page=100", _gh_deadline(i), "--prs", paginate=True, give=GIVE_PRS)
        if not answer.why:
            try:
                prs = estimate_mod._flatten(answer.value)
            except RecursionError:  # nested deeper than any list of pages
                prs = [None]
            if all(isinstance(pr, dict) and isinstance(pr.get("number"), int) and not isinstance(pr.get("number"), bool) and pr["number"] > 0 for pr in prs):
                answer = _Answer(prs)
            else:
                answer = _Answer(why=Words(
                    "the --prs file isn't a list of pull requests, each with a positive whole number" if i.prs_file is not None else "GitHub's list of pull requests couldn't be read",
                    "--prs isn't a list of pull requests, each with a positive whole number" if i.prs_file is not None else "`gh api`'s pull requests aren't a list of pull requests, each with a positive whole number",
                ), fix=_again(GIVE_PRS) if i.prs_file is None else PRS_FIX)
        i._prs = answer
    return i._prs


def _marked(prs: list[dict], repo: str) -> list[int]:
    """The open pull requests that carry the required-checks marker, each
    once. One whose head is in another repository (a fork's, or a deleted
    one's), where its shape says so, isn't counted: anyone can open one."""
    def own(pr: dict) -> bool:
        if "isCrossRepository" in pr and pr["isCrossRepository"] is not False:  # `gh pr list --json`'s
            return False
        head = pr.get("head")
        if not isinstance(head, dict) or "repo" not in head:
            return True  # a shape that doesn't say (search's, the issues list's): the body is all there is
        full = head["repo"].get("full_name") if isinstance(head["repo"], dict) else None
        return isinstance(full, str) and issues_mod._same_repo(full, repo)

    return list(dict.fromkeys(pr["number"] for pr in prs
                              if str(pr.get("state") or "open").lower() == "open" and REQUIRED_CHECKS_MARKER in str(pr.get("body") or "") and own(pr)))


def _check_names(names) -> str:
    return _most(f"`{_shown(c)}`" for c in names)


def _ran_names(ran: list[dict]) -> str:
    return _most(f"`{_shown(c['name'])}` ({c['result']})" for c in ran)


MOST_NAMES = 10  # check names a line lists; the rest are counted


def _most(shown) -> str:
    shown = list(shown)
    more = len(shown) - MOST_NAMES
    return ", ".join(shown[:MOST_NAMES]) + (f" and {more} more" if more > 0 else "")


def _offerable(i: Inputs, rep: protection_mod.Report) -> list[dict]:
    """The checks to offer to require: those that ran on the base branch and
    the ruleset doesn't require. Never in solo mode (the pull request that
    leaves it comes first), nor while the base branch isn't protected (`protect_main`
    or `restore_protection` come first), nor when they can't be read."""
    if i.profile.ruleset is False or not rep.protected:
        return []
    return _checks_ran(i, rep) or []


def _with_offer(line: Line, ran: list[dict], base: str) -> Line:
    """The line carrying the `require_checks` offer, naming the checks that ran."""
    one = len(ran) == 1
    return Line(line.group, line.id, line.status, Words(
        line.message.new + f" {'A check has' if one else 'Checks have'} run on `{base}` that {'isn' if one else 'aren'}'t required yet: {_ran_names(ran)}.",
        line.message.developer + f" Ran on `{base}`, not required: {_ran_names(ran)}.",
    ), line.fix, offer="require_checks")


def _gap_fix(base: str, missing: list[str], ran: list[dict]) -> Words:
    """The fix of the gap naming listed checks the ruleset doesn't require:
    the offer's when they all ran; else they can be ticked once they have."""
    waiting = [c for c in missing if c not in {r["name"] for r in ran}]
    if not waiting:
        return _offer_fix(base)
    one, shown = len(waiting) == 1, _check_names(waiting)
    if ran:
        return Words(
            f"Ask Claude to \"{REQUIRE_CHECKS}\" for the checks that have run; {shown} can be ticked once {'it has' if one else 'they have'} run on `{base}`.",
            f"Run upgrade-setup's \"{REQUIRE_CHECKS}\" for what ran; {shown} can be added once {'it has' if one else 'they have'} run on `{base}`.",
        )
    return Words(
        f"Ask Claude to \"{REQUIRE_CHECKS}\", once {'it has' if one else 'they have'} run on `{base}`.",
        f"Run upgrade-setup's \"{REQUIRE_CHECKS}\" once {shown} {'has' if one else 'have'} run (adds {'it' if one else 'them'} to the ruleset with \"up to date\" on).",
    )


def _offer_fix(base: str) -> Words:
    return Words(
        f"Ask Claude to \"{REQUIRE_CHECKS}\": it shows the checks that ran on `{base}` for you to tick.",
        f"Run upgrade-setup's \"{REQUIRE_CHECKS}\" (`require_checks`): the ticked checks go in the ruleset, with \"up to date\" on, and in ci.required_checks.",
    )


@_check("GitHub", "github.required_checks")
def check_required_checks(i: Inputs) -> list[Line]:
    """The profile's `ci.required_checks` against the ruleset, with the
    `require_checks` offer when checks ran on the base branch that the ruleset
    doesn't require (#69); and the checks the ruleset requires that the
    profile doesn't list (`github.profile_checks`)."""
    g, id_ = "GitHub", "github.required_checks"
    if i.profile is None:
        return [_waits(i, id_, Words("which checks GitHub requires", "Required checks"), None)]
    base, listed = i.profile.base_branch, list(i.profile.required_checks)
    upgrade = REQUIRE_CHECKS
    if not listed:
        gh = _github(i)
        rep = gh.report if gh else None
        line = Line(g, id_, "note", Words(
            f"Checks not required yet: the kit's profile lists no checks that must pass before a pull request merges into `{base}`.",
            "ci.required_checks is empty: checks not required yet.",
        ), Words(
            f"Once your project's checks have run on `{base}`, ask Claude to \"{upgrade}\".",
            f"After CI has run on `{base}`, run upgrade-setup's \"{upgrade}\".",
        ))
        if rep is None:
            return [line]
        if rep.required_checks:  # GitHub requires some: the profile's line (github.profile_checks) says which
            line = Line(g, id_, "note", Words(
                f"The kit's profile lists no checks that must pass before a pull request merges into `{base}`, though GitHub requires some (see the line on the profile's checks).",
                "ci.required_checks is empty, though the ruleset requires checks (github.profile_checks).",
            ), Words(
                "Add the checks GitHub requires to the kit's profile " + ("once you've left solo mode" if i.profile.ruleset is False else "first") + " (see the line on the profile's checks).",
                "Add the ruleset's required checks to ci.required_checks " + ("after leaving solo mode" if i.profile.ruleset is False else "first") + " (github.profile_checks).",
            ))
        ran = _offerable(i, rep)
        if ran:
            line = _with_offer(Line(g, id_, "note", line.message, _offer_fix(base)), ran, base)
        return [line] + _profile_checks(i, rep)
    rep, wait = _report(i, id_, Words("whether GitHub requires the checks the kit's profile lists", "ci.required_checks against the ruleset"))
    if wait:
        return [wait]
    names = _check_names(listed)
    if _solo_unprotected(rep, i):
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't require the checks the kit's profile lists ({names}), since nothing protects `{base}` there yet.",
            f"Solo mode: no ruleset on `{base}` requires ci.required_checks ({names}).",
        ), Words(
            f"They're required when you ask Claude to \"{OFFERS['protect_main']}\".",
            f"\"{OFFERS['protect_main']}\" adds them to the ruleset it creates.",
        ))] + _profile_checks(i, rep)
    ran = _offerable(i, rep)
    missing = [c for c in listed if c not in rep.required_checks]
    if missing and i.profile.ruleset is False:
        # Solo mode with a ruleset on the base branch: "Require these checks"
        # waits for the pull request that leaves solo mode (#38), so never a gap.
        shown = _check_names(missing)
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't require {'this check' if len(missing) == 1 else 'these checks'} the kit's profile lists yet: {shown}. {'It' if len(missing) == 1 else 'They'} can be required once you've left solo mode.",
            f"Solo mode: ci.required_checks not required by any active ruleset on `{base}`: {shown}.",
        ), Words(
            f"Once you've left solo mode (ask Claude to \"{OFFERS['protect_main']}\"), ask Claude to \"{upgrade}\".",
            f"Leave solo mode (\"{OFFERS['protect_main']}\"), then run upgrade-setup's \"{upgrade}\".",
        ))] + _profile_checks(i, rep)
    if missing:
        shown = _check_names(missing)
        line = Line(g, id_, "gap", Words(
            f"GitHub doesn't require {'this check' if len(missing) == 1 else 'these checks'} the kit's profile lists to pass before a pull request merges: {shown}.",
            f"ci.required_checks not required by any active ruleset on `{base}`: {shown}.",
        ), _gap_fix(base, missing, ran))
    elif ran:
        # The profile and the ruleset agree, but a check added to CI later has run.
        line = Line(g, id_, "note", Words(
            f"GitHub requires the checks the kit's profile lists ({names}), but neither lists every check that runs on `{base}`.",
            f"Every ci.required_checks name is required on `{base}` ({names}); not every check that ran is.",
        ), _offer_fix(base))
    else:
        line = Line(g, id_, "fine", Words(
            f"GitHub requires the checks the kit's profile lists to pass before a pull request merges ({names}).",
            f"Every ci.required_checks name is required on `{base}` ({names}).",
        ))
    return [_with_offer(line, ran, base) if ran else line] + _profile_checks(i, rep)


def _profile_checks(i: Inputs, rep: protection_mod.Report) -> list[Line]:
    """The checks the ruleset requires that the profile doesn't list: a note
    while an open pull request carrying the marker adds them, else a gap
    (the merge rule and the conductor read the profile); `cant_check` when
    the pull requests can't be read. In solo mode a note either way: the
    profile catches up once it has been left. No line when the profile
    lists them all."""
    g, id_ = "GitHub", "github.profile_checks"
    base, listed = i.profile.base_branch, set(i.profile.required_checks)
    unlisted = [c for c in rep.required_checks if c not in listed]
    if not unlisted:
        return []
    one, names = len(unlisted) == 1, _check_names(unlisted)
    them = "it" if one else "them"
    solo = i.profile.ruleset is False
    prs = _open_prs(i)
    marked = [] if prs.why else _marked(prs.value, i.profile.repo)
    if solo and not marked:
        # Solo mode, never a gap: the profile catches up once it has been
        # left (the pull request that leaves it lists only the checks ticked).
        protect = OFFERS["protect_main"]
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub requires {'a check' if one else 'checks'} the kit's profile doesn't list ({names}).",
            f"Solo mode: required on `{base}` but not in ci.required_checks: {names}.",
        ), Words(
            f"Once you've left solo mode (ask Claude to \"{protect}\"), ask Claude to add {them} to the kit's profile (`ci.required_checks` in {PROFILE}) in a pull request.",
            f"After \"{protect}\"'s pull request merges, add {them} to ci.required_checks in a pull request, unless that pull request already did.",
        ))]
    if prs.why:
        return [Line(g, id_, "cant_check", Words(
            f"GitHub requires {'a check' if one else 'checks'} the kit's profile doesn't list ({names}), and whether a pull request is adding {them} to the profile can't be checked: {_relative(i, prs.why.new)}.",
            f"Required on `{base}` but not in ci.required_checks: {names}; open pull requests unchecked: {_relative(i, prs.why.developer)}.",
        ), prs.fix)]
    if marked:
        refs, many = _listing(_refs(marked)), len(marked) > 1
        prs_word = f"pull request{'s' if many else ''} {refs}"
        return [Line(g, id_, "note", Words(
            f"GitHub requires {'a check' if one else 'checks'} the kit's profile doesn't list yet ({names}): {prs_word} {'add' if many else 'adds'} {them}, so the profile catches up when {'one' if many else 'it'} merges.",
            f"Required on `{base}` but not in ci.required_checks yet: {names}; open {refs} ({REQUIRED_CHECKS_MARKER}) {'update' if many else 'updates'} the profile.",
        ), Words(
            f"Review and merge {prs_word}.",
            f"Merge {refs}.",
        ))]
    return [Line(g, id_, "gap", Words(
        f"GitHub requires {'a check' if one else 'checks'} to pass that the kit's profile doesn't list ({names}). The kit reads the required checks from its profile, so the two should agree.",
        f"Required on `{base}` but not in ci.required_checks: {names} (the merge rule and the conductor read the profile).",
    ), Words(
        f"Ask Claude to add {them} to the kit's profile (`ci.required_checks` in {PROFILE}) in a pull request.",
        f"Add {them} to ci.required_checks in a pull request.",
    ))]


@_check("GitHub", "github.up_to_date")
def check_ruleset_rules(i: Inputs) -> list[Line]:
    """The ruleset's other rules the kit cares about: "up to date",
    approvals, Code Owners review and linear history (docs/enforcement.md §1),
    read from the active rulesets on the base branch. With none, the ruleset
    line has said so, and these have nothing to read."""
    g = "GitHub"
    whats = {
        "github.up_to_date": Words("whether pull requests must be up to date with the main branch", "\"Require branches to be up to date\""),
        "github.approvals": Words("how many approvals GitHub requires", "Required approvals"),
        "github.code_owner_review": Words("whether GitHub requires a review from the code owners", "\"Require review from Code Owners\""),
        "github.linear_history": Words("whether GitHub requires a straight-line history", "The linear-history rule"),
    }
    reads = [_report(i, id_, what) for id_, what in whats.items()]
    if reads[0][1]:
        return [wait for _, wait in reads]
    rep = reads[0][0]
    if not rep.effective:
        return []
    base = i.profile.base_branch
    lines = []
    strict = [p.get("strict_required_status_checks_policy") is True for p in _rules(rep, "required_status_checks")]
    if rep.queue:
        lines.append(_queue_up_to_date(rep, base))
    elif rep.queue_unsure and not any(strict):
        lines.append(Line(g, "github.up_to_date", "cant_check", Words(
            f"Can't tell whether a merge queue keeps pull requests up to date with `{base}`: {_shown(rep.queue_unsure[0], 300)}.",
            f"Merge queue unknown on `{base}`, and strict_required_status_checks_policy isn't true: {_shown('; '.join(rep.queue_unsure), 300)}.",
        ), Words(
            f"Check in Settings → Rules whether that ruleset applies to `{base}`; naming `{base}` itself (not a pattern) lets the kit tell.",
            f"Name refs/heads/{base} (or ~DEFAULT_BRANCH, with --repo's default_branch) in its include, so the reader can count it.",
        )))
    elif not strict and not i.profile.required_checks:
        lines.append(Line(g, "github.up_to_date", "note", Words(
            f"\"Require branches to be up to date\" comes with the required checks, and none are required on `{base}` yet.",
            f"No required_status_checks rule on `{base}` (ci.required_checks is empty), so no strict_required_status_checks_policy.",
        ), Words(
            f"It's turned on with the checks, when you ask Claude to \"{REQUIRE_CHECKS}\".",
            f"\"{REQUIRE_CHECKS}\" adds the rule with strict_required_status_checks_policy = true.",
        )))
    elif not any(strict):
        lines.append(Line(g, "github.up_to_date", "gap", Words(
            f"GitHub lets a pull request merge without being up to date with `{base}`, so two changes that each pass alone can break `{base}` together.",
            f"strict_required_status_checks_policy isn't true on `{base}` (\"Require branches to be up to date\" off"
            + (", and no required_status_checks rule)." if not strict else ")."),
        ), Words(
            f"Ask Claude to turn on \"Require branches to be up to date\" in the ruleset (\"{REQUIRE_CHECKS}\" does it).",
            "Set strict_required_status_checks_policy = true in the ruleset's required_status_checks rule.",
        )))
    else:
        lines.append(Line(g, "github.up_to_date", "fine", Words(
            f"Pull requests must be up to date with `{base}` before they merge.",
            f"strict_required_status_checks_policy is true on `{base}`.",
        )))
    prs = _rules(rep, "pull_request")
    counts = [p.get("required_approving_review_count") for p in prs if "required_approving_review_count" in p]
    unread = [c for c in counts if not isinstance(c, int) or isinstance(c, bool) or c < 0]
    most = max((c for c in counts if c not in unread), default=0)
    if unread:
        lines.append(Line(g, "github.approvals", "cant_check", Words(
            f"Can't tell how many approvals GitHub requires on `{base}`: the ruleset's number can't be read.",
            f"required_approving_review_count on `{base}` isn't a count: {_shown(json.dumps(unread[0]))}.",
        ), Words(
            "Ask Claude to fetch the ruleset from GitHub again, in full.",
            "Pass the ruleset as GitHub returns it (GET repos/<repo>/rulesets/<id>).",
        )))
    elif most > 0:
        lines.append(Line(g, "github.approvals", "note", Words(
            f"GitHub needs {_count(most, 'an approving review', 'approving reviews')} before a pull request merges into `{base}`, so unattended runs will stop at \"ready for review\" and wait for you.",
            f"required_approving_review_count = {most} on `{base}`: unattended runs stop at \"ready for review\" (merge.mode owner).",
        ), Words(
            "That's your choice; to let runs merge on their own, ask Claude to set the ruleset's required approvals to 0.",
            "Keep it, or set required_approving_review_count to 0 so runs can merge.",
        )))
    else:
        lines.append(Line(g, "github.approvals", "fine", Words(
            "GitHub doesn't need an approving review before a pull request merges, so unattended runs can merge.",
            f"required_approving_review_count is 0 on `{base}`.",
        )))
    if any(p.get("require_code_owner_review") is True for p in prs):
        lines.append(Line(g, "github.code_owner_review", "gap", Words(
            "GitHub requires a review from the code owners, but Claude's sessions post as you, and GitHub never lets you approve your own pull request, so one that touches the kit could never merge.",
            "require_code_owner_review is true while sessions post as the owner: an owner-authored PR touching a CODEOWNERS path can't merge.",
        ), Words(
            "Ask Claude to turn off \"Require review from Code Owners\" in the ruleset; CODEOWNERS still asks for your review.",
            "Set require_code_owner_review = false (docs/enforcement.md §1); turn it on only when agents have their own GitHub identity.",
        )))
    else:
        lines.append(Line(g, "github.code_owner_review", "fine", Words(
            "GitHub doesn't require the code owners' review, so pull requests Claude opens as you can merge.",
            "require_code_owner_review is off.",
        )))
    if _rules(rep, "required_linear_history"):
        lines.append(Line(g, "github.linear_history", "gap", Words(
            f"GitHub requires a straight-line history on `{base}` (\"Require linear history\"), which refuses the merge commits the kit merges with.",
            f"A required_linear_history rule is active on `{base}`: merge commits are refused.",
        ), Words(
            "Ask Claude to turn off \"Require linear history\" in the ruleset.",
            "Remove the required_linear_history rule.",
        )))
    else:
        lines.append(Line(g, "github.linear_history", "fine", Words(
            f"GitHub accepts merge commits on `{base}` (no \"Require linear history\").",
            "No required_linear_history rule.",
        )))
    try:  # the merge queue's lines (#246), said only where a queue fits or is on
        lines += check_merge_queue(i)
    except Exception as e:  # advice never ends in a traceback
        lines.append(_failed(i, check_merge_queue, e))
    return lines


def _queue_up_to_date(rep: protection_mod.Report, base: str) -> Line:
    """`github.up_to_date` with a merge queue in force: the queue meets it
    (#243), and a ruleset still keeping "up to date" on is named, for the
    owner to turn it off there. Its fix never turns "up to date" on."""
    keeping = [rs for rs in rep.effective for r in rs["rules"] if r["type"] == "required_status_checks"
               and (r.get("parameters") or {}).get("strict_required_status_checks_policy") is True]
    if not keeping:
        return Line("GitHub", "github.up_to_date", "fine", Words(
            f"The merge queue keeps pull requests up to date with `{base}`: each is tested against the latest `{base}` before it merges.",
            f"A merge_queue rule meets \"up to date\" on `{base}` (strict_required_status_checks_policy off).",
        ))
    keeping = list({id(rs): rs for rs in keeping}.values())  # a ruleset once, however many such rules it has
    names = _most(f"`{_shown(str(rs.get('name') or rs.get('id')))}`" for rs in keeping)
    org = any(rs.get("source_type") == "Organization" for rs in keeping)
    return Line("GitHub", "github.up_to_date", "note", Words(
        f"The merge queue keeps pull requests up to date with `{base}`, but \"Require branches to be up to date\" is still on in {names}, so GitHub may still make a pull request update before it can join the queue.",
        f"A merge_queue rule is in force on `{base}`, and strict_required_status_checks_policy is still true in {names}.",
    ), Words(
        f"Turn \"Require branches to be up to date\" off in {names}" + (" (an organisation's ruleset: its owners change it in the organisation's settings)." if org else "."),
        f"Turn it off: strict_required_status_checks_policy = false in {names}" + (" (an organisation ruleset)." if org else "."),
    ))


@_check("GitHub", "github.merge_commits")
def check_merge_settings(i: Inputs) -> list[Line]:
    """Merge commits and auto-merge allowed, from the repository's settings.
    Auto-merge off is a note in solo mode, whose runs never use it (#50)."""
    g = "GitHub"
    gh = _github(i)
    whats = (("github.merge_commits", "allow_merge_commit", Words("whether GitHub allows merge commits", "allow_merge_commit")),
             ("github.auto_merge", "allow_auto_merge", Words("whether GitHub allows auto-merge", "allow_auto_merge")))
    if gh is None or gh.merge is None:
        return [_waits(i, id_, what, gh.merge_why if gh else None) for id_, _, what in whats]
    lines = []
    for (id_, key, what), name in zip(whats, ("merge_commits", "auto_merge")):
        v = gh.merge[name]
        if v is None:
            lines.append(Line(g, id_, "cant_check", Words(
                f"Can't check {what.new}: GitHub shows that setting only to the repository's admins.",
                f"{key} isn't in the repository's settings (it needs admin access).",
            ), Words(
                "Ask the repository's admin to run this check, or to look in Settings → General → Pull Requests.",
                "Rerun with an admin's `gh`, or give --repo from an admin's GET repos/<repo>.",
            )))
        elif v:
            lines.append(Line(g, id_, "fine", Words(
                "GitHub allows merge commits, which the kit merges with." if name == "merge_commits" else "GitHub allows auto-merge, which unattended runs can use.",
                f"{key} is true.",
            )))
        elif name == "merge_commits":
            lines.append(Line(g, id_, "gap", Words(
                "GitHub doesn't allow merge commits, which is how the kit merges pull requests.",
                "allow_merge_commit is false: sessions and the conductor merge with a merge commit.",
            ), Words(
                "Ask Claude to turn on \"Allow merge commits\" (Settings → General → Pull Requests).",
                "Set allow_merge_commit = true (PATCH repos/<repo>, or upgrade-setup's \"Protect `main`\").",
            )))
        else:
            solo = i.profile.ruleset is False
            lines.append(Line(g, id_, "note" if solo else "gap", Words(
                "GitHub doesn't allow auto-merge" + (", which solo mode's runs never use." if solo else ", which unattended runs merge with in their auto-merge mode."),
                "allow_auto_merge is false" + (" (solo mode: runs never use auto-merge)." if solo else ": a run's merge.mode auto-merge can't arm it."),
            ), Words(
                ("When you leave solo mode, ask" if solo else "Ask") + " Claude to turn on \"Allow auto-merge\" (Settings → General → Pull Requests).",
                "Set allow_auto_merge = true" + (" when leaving solo mode." if solo else " (PATCH repos/<repo>, or upgrade-setup's \"Protect `main`\")."),
            )))
    return lines


# ---------- the merge queue (#246) ----------
# GitHub's merge queue, suggested and never a gap: where checks are required,
# the queue is off and GitHub offers it ("in any public repository owned by an
# organization, or in private repositories owned by organizations using GitHub
# Enterprise Cloud"). Beside it, the `merge_group` check over the workflows
# behind the required checks, read from `origin/<base>`, never the checkout's;
# and the signals the check-setup skill words its recommendation from. Each
# input is read only once a line needs it: --org, --ci and --commits when
# given, else with `gh api` (GETs only, one page each); the workflow files
# with `git`, from what the checkout holds of `origin/<base>`.

USE_MERGE_QUEUE = OFFERS["use_merge_queue"]
GIVE_ORG = "--org (GET orgs/<owner>)"
GIVE_CI = "--ci (each commit's GET .../commits/<sha>/check-runs and GET .../actions/runs?head_sha=<sha>)"
GIVE_COMMITS = "--commits (GET repos/<repo>/commits?sha=<base>&per_page=100)"
ACTIONS_APP = "github-actions"  # the app behind GitHub Actions' check runs
WINDOW = timedelta(days=7)  # how often the base moved, counted over this
CI_COMMITS = 5  # the base's last commits, and the open pull requests' heads, whose CI is read with `gh`
# An organisation's plans as GET orgs/<owner> names them: Enterprise Cloud has
# the queue; these don't. Any other name is read as not known.
ENTERPRISE_PLAN = "enterprise"
PLANS_WITHOUT = ("free", "team", "pro")
_SHA = re.compile(r"[0-9a-fA-F]{40}")
UNCHECKED = {"status": "cant_check", "clean": False, "workflows": [], "checks": []}  # the merge_group check's JSON, not read
_WORKFLOW_FILE = re.compile(r"\.github/workflows/[^/\x00-\x1f]+\.ya?ml")
# The keys of a workflow's `on:` block, read line by line with no YAML library.
_TOP_ON = re.compile(r"""(?:on|"on"|'on')[ ]*:(?:[ ]+(.*))?""")
_KEY = re.compile(r"""([A-Za-z_][\w-]*|"[^"\n]*"|'[^'\n]*')[ ]*:(?:[ ]+(.*))?""")
_ALIAS = re.compile(r"(?:^|[\s:\[,])[&*!|>][\w-]")  # an anchor, alias, tag or block scalar
_PATTERN = re.compile(r"[?+\[\]!\\]")  # filter-pattern characters the kit doesn't match


def parse_now(value: str | None) -> datetime | None:
    """--now as a time with its zone; now when not given; None when it isn't one."""
    if value is None:
        return datetime.now(timezone.utc)
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None and "T" in value and 1970 < t.year < 9999 else None


def _iso(value) -> datetime | None:
    """GitHub's time (UTC when it gives no zone), or None."""
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _org_plan(i: Inputs, login: str) -> str | None:
    """The organisation's plan, casefolded, from --org or `gh api`; None
    when it can't be read (only the organisation's owners can see it)."""
    if i.org_file is not None:
        got = _given(i, i.org_file, "--org", what="the organisation")
    else:
        got = _gh(i, f"orgs/{urllib.parse.quote(login, safe='')}", _gh_deadline(i), "--org", give=GIVE_ORG)
    plan = got.value.get("plan") if isinstance(got.value, dict) else None
    name = plan.get("name") if isinstance(plan, dict) else None
    return name.casefold() if isinstance(name, str) and name else None


def _availability(i: Inputs, gh: _GitHub) -> str | None:
    """Whether GitHub offers this repository a merge queue: "yes", "check_plan"
    (a private organisation repository whose plan can't be read), or None (a
    personal repository, a private one on a plan without it, or an owner the
    settings don't name)."""
    s = gh.settings or {}
    owner = s.get("owner") if isinstance(s.get("owner"), dict) else {}
    if owner.get("type") != "Organization":
        return None
    visibility = s.get("visibility")
    if visibility not in ("public", "private", "internal"):
        visibility = {True: "private", False: "public"}.get(s.get("private"))
    if visibility in ("public", "internal"):  # internal: only Enterprise has it
        return "yes"
    if visibility != "private":
        return None
    login = owner.get("login") if isinstance(owner.get("login"), str) and owner.get("login") else i.profile.repo.split("/")[0]
    plan = _org_plan(i, login)
    if plan == ENTERPRISE_PLAN:
        return "yes"
    return None if plan in PLANS_WITHOUT else "check_plan"


def _commits(i: Inputs) -> _Answer:
    """The base branch's commits, newest first, each an object with a sha:
    from --commits, else one page through `gh api`; read once."""
    if i._commits is None:
        fix = Words(
            "Ask Claude to fetch the main branch's commits from GitHub again, or leave out --commits to read them with `gh`.",
            f"Give {GIVE_COMMITS}, as the GitHub API returns them, or leave it out to use `gh api`.",
        )
        if i.commits_file is not None:
            got = _given(i, i.commits_file, "--commits", fix, "commits")
        else:
            ref = urllib.parse.quote(i.profile.base_branch, safe="/")
            got = _gh(i, f"repos/{i.profile.repo}/commits?sha={ref}&per_page=100", _gh_deadline(i), "--commits", give=GIVE_COMMITS)
        if not got.why:
            try:
                commits = estimate_mod._flatten(got.value) if isinstance(got.value, list) else None
            except RecursionError:  # nested deeper than any list of pages
                commits = None
            if commits is None or not all(isinstance(c, dict) and isinstance(c.get("sha"), str) for c in commits):
                got = _Answer(why=Words("the main branch's commits couldn't be read", "the commits aren't a list of commits, each with a sha"), fix=fix)
            else:
                got = _Answer(commits)
        i._commits = got
    return i._commits


def _first_parents(commits: list[dict]) -> tuple[list[tuple[str, datetime | None]], bool]:
    """The base's own history from its newest commit, by first parents: each
    commit's sha and committer time; and whether it runs off the list."""
    by_sha = {c["sha"]: c for c in commits}
    out, seen = [], set()
    if not commits:
        return out, False
    c = commits[0]
    while c is not None and c["sha"] not in seen:
        seen.add(c["sha"])
        committer = (c.get("commit") or {}).get("committer") if isinstance(c.get("commit"), dict) else None
        out.append((c["sha"], _iso(committer.get("date")) if isinstance(committer, dict) else None))
        parents = c.get("parents")
        if parents == []:
            return out, False  # the first commit
        first = parents[0].get("sha") if isinstance(parents, list) and isinstance(parents[0], dict) else None
        if not isinstance(first, str):
            return out, True  # a parent it can't follow: only "at least"
        c = by_sha.get(first)
    return out, c is None


def _moved(i: Inputs) -> tuple[int | None, bool]:
    """How many commits reached the base in the 7 days to `now`, by first
    parents (each merge or push once), and whether that is only "at least"
    (the list ends inside the window). None when it can't be read."""
    commits = _commits(i)
    if commits.why:
        return None, False
    chain, off = _first_parents(commits.value)
    start, n = i.now - WINDOW, 0
    for _, when in chain:
        if when is None:
            return None, False
        if when <= start:
            return n, False
        if when <= i.now:
            n += 1
    return (None, False) if off and not n else (n, off)


@dataclass
class _CICommit:
    """One commit's CI: its check runs and the workflow runs behind them."""

    sha: str
    base: bool
    runs: list[dict]
    workflow_runs: list[dict]


def _items(value, key: str) -> list[dict] | None:
    """GitHub's answer (or its pages) as the list under `key`; None when it
    isn't one, or holds fewer than its `total_count` (a page missing)."""
    pages = value if isinstance(value, list) else [value]
    if not all(isinstance(p, dict) and isinstance(p.get(key), list) for p in pages):
        return None
    items = [x for p in pages for x in p[key]]
    totals = [p["total_count"] for p in pages if isinstance(p.get("total_count"), int) and not isinstance(p.get("total_count"), bool)]
    if totals and len(items) < max(totals):
        return None
    return items if all(isinstance(x, dict) for x in items) else None


def _an_id(v) -> bool:
    return v is None or isinstance(v, (int, str)) and not isinstance(v, bool)


def _parse_ci(entries) -> list[_CICommit] | None:
    """--ci's entries, each with its check runs (a name and an app with a
    slug, as GitHub gives them) and workflow runs; None when they aren't."""
    if not isinstance(entries, list):
        return None
    out = []
    for e in entries:
        if not isinstance(e, dict) or not isinstance(e.get("sha"), str) or not isinstance(e.get("base"), bool):
            return None
        runs = _items(e.get("check_runs"), "check_runs")
        flows = _items(e["workflow_runs"], "workflow_runs") if "workflow_runs" in e else []
        if runs is None or flows is None:
            return None
        if not all(isinstance(r.get("name"), str) and isinstance(r.get("app"), dict) and isinstance(r["app"].get("slug"), str)
                   and (r.get("check_suite") is None or isinstance(r["check_suite"], dict) and _an_id(r["check_suite"].get("id"))) for r in runs):
            return None
        if not all(_an_id(w.get("check_suite_id")) and (w.get("path") is None or isinstance(w["path"], str)) for w in flows):
            return None
        out.append(_CICommit(e["sha"], e["base"], runs, flows))
    return out


def _ci(i: Inputs) -> _Answer:
    """The CI of the base's last commits and of the open pull requests' heads,
    from --ci, else `gh api`; read once."""
    if i._ci is None:
        if i.ci_file is not None:
            got = _given(i, i.ci_file, "--ci", Words(
                "Ask Claude to fetch the checks that ran on the main branch and on the open pull requests again, as check-setup gathers them.",
                f"Give {GIVE_CI}, as check-setup gathers them.",
            ), "CI runs")
        else:
            got = _read_ci(i)
        if not got.why:
            parsed = _parse_ci(got.value)
            got = _Answer(parsed) if parsed is not None else _Answer(why=Words(
                "the checks that ran aren't in the shape GitHub gives them",
                "the CI runs aren't a list of {sha, base, check_runs, workflow_runs}, every page, each check run with a name and its app's slug",
            ), fix=Words("Ask Claude to fetch them again, as check-setup gathers them.", f"Give {GIVE_CI}."))
        i._ci = got
    return i._ci


def _read_ci(i: Inputs) -> _Answer:
    """The CI read with `gh api`: the base's last `CI_COMMITS` commits, by
    first parents, and as many open pull requests' heads."""
    commits = _commits(i)
    if commits.why:
        return commits
    base = [sha for sha, _ in _first_parents(commits.value)[0][:CI_COMMITS]]
    prs = _open_prs(i)
    heads = [] if prs.why else [(pr.get("head") or {}).get("sha") for pr in prs.value if isinstance(pr.get("head"), dict)]
    heads = [s for s in heads if isinstance(s, str) and s not in base][:CI_COMMITS]
    repo, deadline, out = i.profile.repo, _gh_deadline(i), []
    for sha, on_base in [(s, True) for s in base] + [(s, False) for s in heads]:
        if not _SHA.fullmatch(sha):
            if not on_base:
                continue  # a pull request's head: the others still tell
            return _Answer(why=Words("GitHub named a commit the kit can't read", f"{_shown(sha)} isn't a commit sha"), fix=_again(GIVE_CI))
        runs = _gh(i, f"repos/{repo}/commits/{sha}/check-runs?per_page=100", deadline, "--ci", give=GIVE_CI)
        flows = runs if runs.why else _gh(i, f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100", deadline, "--ci", give=GIVE_CI)
        cut = not flows.why and (_items(runs.value, "check_runs") is None or _items(flows.value, "workflow_runs") is None)
        if flows.why or cut and not on_base:
            if on_base:
                return flows
            continue  # a pull request's head: the others still tell
        out.append({"sha": sha, "base": on_base, "check_runs": runs.value, "workflow_runs": flows.value})
    return _Answer(out)


def _ci_minutes(ci: list[_CICommit], required: list[str]) -> dict:
    """CI's longest and typical (median) time on the base's commits, in whole
    minutes: on each commit whose required checks have all finished, the
    longest of their runs that passed, failed or timed out, each from its own start to
    its own end (so a re-run, or another workflow, never stretches it)."""
    took = []
    for c in ci:
        mine = [r for r in c.runs if r["name"] in required]
        if not c.base or any(r.get("status") != "completed" for r in mine):
            continue
        runs = [r for r in mine if r.get("conclusion") in ("success", "failure", "timed_out")]  # a skipped or cancelled run took no CI time
        times = [(_iso(r.get("started_at")), _iso(r.get("completed_at"))) for r in runs]
        spans = [(end - start).total_seconds() for start, end in times if start and end and end >= start]
        if spans:
            took.append(round(max(spans) / 60))
    return {"longest": max(took) if took else None, "typical": statistics.median_low(took) if took else None, "commits": len(took)}


def _signals(i: Inputs, rep: protection_mod.Report) -> dict:
    """What check-setup words its recommendation from (#243): CI's length
    on the base, how often the base moved in the 7 days to `now`, and
    whether unattended runs are set up or one is in progress."""
    runs = _runs(i)  # first: the Cloud lines read it too, within the same budget
    ci = _ci(i)
    moved, at_least = _moved(i)
    p = i.profile
    return {
        "now": i.now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ci_minutes": _ci_minutes(ci.value, rep.required_checks) if not ci.why else {"longest": None, "typical": None, "commits": 0},
        "base_commits_7d": moved,
        "base_commits_at_least": at_least,
        "runs_set_up": bool(p.ticket_environment and p.conductor_environment),
        "run_in_progress": None if runs.why else i._run_open,
    }


def _minutes(n: int) -> str:
    return "under a minute" if not n else _count(n, "a minute", "minutes")


def _signal_words(i: Inputs, s: dict) -> Words:
    base, ci = i.profile.base_branch, s["ci_minutes"]
    day = i.now.astimezone(timezone.utc).strftime("%d %b %Y")
    if ci["typical"] is None:
        took = Words(f"how long CI takes on `{base}` couldn't be read", "CI time on the base: unknown")
    else:
        about = ("" if not ci["typical"] else "about ") + _minutes(ci["typical"])
        took = Words(f"CI takes {about} on `{base}` (the longest {_minutes(ci['longest'])})",
                     f"CI on `{base}`: typical {ci['typical']} min, longest {ci['longest']} (over {_count(ci['commits'], 'its last commit', 'commits')})")
    n = s["base_commits_7d"]
    if n is None:
        moved = Words(f"how often `{base}` moves couldn't be read", "base moves in 7 days: unknown")
    else:
        more = "at least " if s["base_commits_at_least"] else ""
        moved = Words(f"`{base}` moved {more}{_count(n, 'once', 'times')} in the 7 days to {day}",
                      f"{more}{n} first-parent commits on `{base}` in the 7 days to {s['now']}")
    if s["run_in_progress"]:
        runs = Words("an unattended run is in progress", "a run is in progress")
    elif s["runs_set_up"]:
        runs = Words("unattended runs are set up", "runs set up" + (", none in progress" if s["run_in_progress"] is False else ""))
    else:
        runs = Words("unattended runs aren't set up", "runs not set up")
    return Words(f"{_upper(took.new)}, {moved.new}, and {runs.new}.", f"{took.developer}; {moved.developer}; {runs.developer}.")


def _queue_line(i: Inputs, rep: protection_mod.Report, available: str | None, signals: dict) -> Line:
    g, id_, base = "GitHub", "github.merge_queue", i.profile.base_branch
    said = _signal_words(i, signals)
    if rep.queue:
        return Line(g, id_, "fine", Words(
            f"GitHub's merge queue is on for `{base}`: it tests each pull request against the latest `{base}` (and those queued ahead of it) before merging it. {said.new}",
            f"A merge_queue rule is in force on `{base}`. {said.developer}",
        ))
    plan = available == "check_plan"
    return Line(g, id_, "note", Words(
        f"A merge queue could keep pull requests up to date with `{base}` for you"
        + (", if your plan has it: on a private repository GitHub offers it only with GitHub Enterprise Cloud, and the kit can't tell this organisation's plan (only its owners can see it), so check before taking the upgrade" if plan else "")
        + f". It tests each pull request against the latest `{base}` before merging it, so a green pull request never has to be updated and tested again. {said.new}",
        "Merge queue off; " + ("a private repository has it only on GitHub Enterprise Cloud, and the organisation's plan can't be told (check first)" if plan else "available")
        + f"; \"up to date\" holds today. {said.developer}",
    ), Words(
        ("If your organisation is on GitHub Enterprise Cloud and it fits" if plan else "If it fits")
        + f", ask Claude to \"{USE_MERGE_QUEUE}\": it first adds the queue's trigger to your CI in a pull request for you to merge.",
        (f"Confirm the plan is Enterprise Cloud, then run" if plan else "Run") + f" upgrade-setup's \"{USE_MERGE_QUEUE}\" (`use_merge_queue`): merge_group in the workflows first, then the ruleset.",
    ), offer="use_merge_queue")


def _flow_list(text: str) -> list[str] | None:
    """`[a, 'b', "c"]`, or a single plain value, as its items; None when it isn't one of those."""
    text = text.strip()
    if text.startswith("["):
        if not text.endswith("]") or any(c in text[1:-1] for c in "[]{}"):
            return None
        parts = [p.strip() for p in text[1:-1].split(",") if p.strip()]
    elif text and text[0] not in "{&*!|>":
        parts = [text]
    else:
        return None
    return [_unquoted(p) for p in parts]


def _unquoted(v: str) -> str:
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def _uncommented(v: str) -> str:
    """A value with a trailing ` # comment` left out."""
    m = re.search(r"(?:^|\s)#", v)
    return (v[:m.start()] if m else v).strip()


def _block(lines: list[str]) -> tuple[dict | None, str]:
    """The keys of an indented block of lines, each with its inline value
    and the lines under it; or (None, why it can't be read)."""
    if not lines:
        return None, "it has nothing under it"
    indent = len(lines[0]) - len(lines[0].lstrip(" "))
    keys: dict = {}
    current = None
    for ln in lines:
        at = len(ln) - len(ln.lstrip(" "))
        if at < indent:
            return None, "its indentation can't be followed"
        if at > indent:
            keys[current][1].append(ln)
            continue
        m = _KEY.fullmatch(ln.strip())
        if not m:
            return None, f"a line under it isn't a key: {_shown(ln.strip())}"
        current = _unquoted(m.group(1))
        if current in keys:
            return None, f"it names `{_shown(current)}` twice"
        keys[current] = (_uncommented(m.group(2) or ""), [])
    return keys, ""


def _branch_matches(pattern: str, base: str) -> bool:
    """A filter pattern with `*` and `**` against the base branch's name."""
    rx = "".join(".*" if part == "**" else "[^/]*" if part == "*" else re.escape(part) for part in re.split(r"(\*\*|\*)", pattern))
    return re.fullmatch(rx, base) is not None


def _triggers(text: str, base: str) -> tuple[str, str]:
    """A workflow's `merge_group` state for the base: ("ready", ""),
    ("missing", ""), ("excluded", which filter leaves it out), or
    ("cant_check", why), read from its `on:` keys line by line. Anything it
    can't follow is `cant_check`, never fine."""
    lines = [ln for ln in text.removeprefix("\ufeff").splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    markers = [k for k, ln in enumerate(lines) if not ln[0].isspace() and _uncommented(ln) in ("---", "...")]
    if [k for k in markers if k and not (k == len(lines) - 1 and _uncommented(lines[k]) == "...")]:
        return "cant_check", "it holds more than one YAML document"
    ons = [k for k, ln in enumerate(lines) if not ln[0].isspace() and _TOP_ON.fullmatch(ln.rstrip())]
    if len(ons) != 1:
        return "cant_check", "it has no `on:` key" if not ons else "it has `on:` more than once"
    k = ons[0]
    inline = _uncommented(_TOP_ON.fullmatch(lines[k].rstrip()).group(1) or "")
    if inline.startswith("["):
        return "cant_check", "its `on:` is a list, not a mapping with `pull_request:`"
    if inline:
        if inline[0] in "{&*!|>":
            return "cant_check", "its `on:` is written in a form the kit doesn't read (one key per line)"
        return "cant_check", f"its `on:` is a single event (`{_shown(inline)}`), not a mapping with `pull_request:`"
    body = []
    for ln in lines[k + 1:]:
        if not ln[0].isspace():
            break
        body.append(ln)
    if any("\t" in ln[:len(ln) - len(ln.lstrip())] for ln in body):
        return "cant_check", "its `on:` is indented with tabs"
    if any(_ALIAS.search(_uncommented(ln)) for ln in body):
        return "cant_check", "its `on:` uses an anchor, an alias, a tag or a block scalar, which the kit doesn't follow"
    if body and body[0].lstrip(" ").startswith("-"):
        return "cant_check", "its `on:` is a list, not a mapping with `pull_request:`"
    keys, why = _block(body)
    if keys is None:
        return "cant_check", f"its `on:` can't be read: {why}"
    if "pull_request" not in keys:
        return "cant_check", "its `on:` has no `pull_request:` (" + (", ".join(f"`{_shown(x)}`" for x in keys) or "no events") + ")"
    if "merge_group" not in keys:
        return "missing", ""
    value, under = keys["merge_group"]
    if value and value not in ("null", "~", "{}"):
        return "cant_check", "its `merge_group:` is written in a form the kit doesn't read (one key per line)"
    if not under:
        return "ready", ""
    filters, why = _block(under)
    if filters is None or set(filters) - {"types", "branches", "branches-ignore"}:
        return "cant_check", f"its `merge_group:` can't be read: {why or 'it has a key GitHub does not give it'}"
    if "branches" in filters and "branches-ignore" in filters:
        return "cant_check", "its `merge_group:` has both `branches` and `branches-ignore`"
    for name in ("branches", "branches-ignore"):
        if name not in filters:
            continue
        value, under = filters[name]
        items = _flow_list(value) if value else [_unquoted(_uncommented(ln.strip()[1:])) if ln.strip().startswith("- ") else None for ln in under]
        if items == [] and name == "branches-ignore":
            continue  # it ignores nothing
        if not items or None in items:
            return "cant_check", f"its `merge_group:` `{name}` filter can't be read"
        if any(_PATTERN.search(p) for p in items):
            return "cant_check", f"its `merge_group:` `{name}` filter has a pattern the kit doesn't match"
        hit = any(_branch_matches(p, base) for p in items)
        if hit == (name == "branches-ignore"):
            return "excluded", name
    return "ready", ""


def _base_ref(i: Inputs) -> str | None:
    """`origin/<base>`'s commit in this checkout, or None when it isn't there."""
    ran = _run(i, ["git", "rev-parse", "--verify", "-q", f"refs/remotes/origin/{i.profile.base_branch}^{{commit}}"])
    sha = (ran.out or "").strip()
    return sha if ran.state == "ok" and _SHA.fullmatch(sha) else None


def _merge_group(i: Inputs, rep: protection_mod.Report) -> tuple[Line, dict]:
    """The `merge_group` check: each required check traced through its check
    runs to the workflow behind it, and each such workflow read from
    `origin/<base>`. A gap only with the queue on; with it off, its state for
    the upgrade (a note where a trigger is missing)."""
    g, id_, base = "GitHub", "github.merge_group", i.profile.base_branch
    what = Words("whether the workflows behind the required checks run for a merge queue", "The merge_group check")
    ci = _ci(i)
    if ci.why:
        return _waits(i, id_, what, ci), dict(UNCHECKED)
    ref = _base_ref(i)
    if ref is None:
        return Line(g, id_, "cant_check", Words(
            f"Can't check {what.new}: `origin/{base}` isn't in this checkout, and the kit reads them as they are on `{base}`, never the checkout's.",
            f"{what.developer} unchecked: no refs/remotes/origin/{base} here.",
        ), Words(f"Run `git fetch origin {base}`, then check the set-up again.", f"Run `git fetch origin {base}` and rerun.")), dict(UNCHECKED)
    checks, paths, statuses = [], [], _status_contexts(i, rep)
    for name in rep.required_checks:
        runs = [r for c in ci.value for r in c.runs if r["name"] == name]
        others = sorted({r["app"]["slug"] for r in runs} - {ACTIONS_APP}) or (["a commit status"] if not runs and name in statuses else [])
        suites = {r["check_suite"]["id"] for r in runs if isinstance(r.get("check_suite"), dict) and r["check_suite"].get("id") is not None}
        flows = sorted({w["path"] for c in ci.value for w in c.workflow_runs if w.get("check_suite_id") in suites and isinstance(w.get("path"), str)})
        state = "other_ci" if others else "no_run" if not runs else "actions" if flows else "unknown_workflow"
        checks.append({"name": name, "state": state, "app": others[0] if others else (ACTIONS_APP if runs else None), "workflows": flows if state == "actions" else []})
        paths += [p for p in flows if state == "actions" and p not in paths]
    workflows = []
    for path in paths:
        if not _WORKFLOW_FILE.fullmatch(path):
            workflows.append({"path": path, "state": "cant_check", "why": "it isn't a workflow file in `.github/workflows/`", "file": True})
            continue
        shown = _run(i, ["git", "show", f"{ref}:{path}"])
        if shown.state != "ok":
            workflows.append({"path": path, "state": "cant_check", "why": f"it isn't on `{base}` (or can't be read there)", "file": True})
            continue
        state, why = _triggers(shown.out, base)
        workflows.append({"path": path, "state": state, "why": why})
    return _merge_group_line(i, rep, checks, workflows)


def _status_contexts(i: Inputs, rep: protection_mod.Report) -> set[str]:
    """The contexts of the statuses on the base's latest commit (--checks,
    else `gh`, as the required checks' offer reads them): CI that reports
    statuses, not check runs, is another CI service. Empty when unreadable."""
    _checks_ran(i, rep)  # reads them, once
    if i._checks is None or i._checks.why:
        return set()
    try:
        return {r.name for r in protection_mod._statuses(i._checks.value[1])}
    except protection_mod.ProtectionError:
        return set()


def _files_named(paths: list[str]) -> str:
    return _most(f"`{_shown(PurePosixPath(p).name, 60)}`" for p in paths)


def _merge_group_line(i: Inputs, rep: protection_mod.Report, checks: list[dict], workflows: list[dict]) -> tuple[Line, dict]:
    g, id_, base = "GitHub", "github.merge_group", i.profile.base_branch
    found: list[tuple[str, Words, Words]] = []  # (status, what, fix)
    on = rep.queue
    lacking = [w["path"] for w in workflows if w["state"] == "missing"]
    narrow = [w["path"] for w in workflows if w["state"] == "excluded" and w["why"] == "branches"]
    ignoring = [w["path"] for w in workflows if w["state"] == "excluded" and w["why"] == "branches-ignore"]
    for w in workflows:
        name = _files_named([w["path"]])
        if w["state"] == "missing":
            found.append(("gap" if on else "note", Words(
                f"{name} doesn't run for a merge queue (no `merge_group:` beside `pull_request:`)" + (", so its checks never come and pull requests wait in the queue" if on else ""),
                f"no merge_group trigger in {name}",
            ), NONE))
        elif w["state"] == "excluded":
            found.append(("gap" if on else "note", Words(
                f"{name}'s `merge_group:` has a `{w['why']}` filter that leaves out `{base}`",
                f"{name}: merge_group's {w['why']} filter leaves out `{base}`",
            ), NONE))
        elif w["state"] == "cant_check":
            fix = Words(
                f"Make sure {name} is a workflow file in `.github/workflows/` on `{base}`, as UTF-8 text; then check the set-up again.",
                f"{name} must be a UTF-8 file under .github/workflows/ on `{base}`; then rerun.",
            ) if w.get("file") else Words(
                f"Edit {name} so the kit can read its triggers: `on:` as a mapping with one event per line, each named once, `pull_request:` among them,"
                " and `merge_group:`'s filters as plain lists; then check the set-up again.",
                f"Make on: in {name} a block mapping (one key per line, no duplicates) with pull_request:, merge_group filters as plain lists (read line by line, no YAML library).",
            )
            found.append(("cant_check", Words(f"{name} can't be read for its triggers: {w['why']}", f"{name}: {w['why']}"), fix))
    for c in checks:
        name = f"`{_shown(c['name'])}`"
        if c["state"] == "other_ci":
            found.append(("cant_check", Words(
                f"{name} comes from {_shown(c['app'])}, another CI service, which the kit can't check: GitHub's rule is that such CI must also run on pushes to `gh-readonly-queue/{base}/*` branches",
                f"{name} is from app {_shown(c['app'])}, not GitHub Actions: it must run on push to gh-readonly-queue/{base}/*",
            ), Words(
                f"Set {name}'s CI service to also run on pushes to `gh-readonly-queue/{base}/*` before taking a merge queue.",
                f"Trigger {name} on push to gh-readonly-queue/{base}/**.",
            )))
        elif c["state"] == "no_run":
            found.append(("cant_check", Words(
                f"no run seen of {name} on `{base}` or the open pull requests, so which workflow runs it can't be told",
                f"no run seen of {name} on the base or recent PR heads",
            ), Words(
                f"Let {name} run once (on a pull request or on `{base}`), then check the set-up again.",
                f"Run {name} once, then rerun (or point the upgrade at its workflow).",
            )))
        elif c["state"] == "unknown_workflow":
            found.append(("cant_check", Words(
                f"which workflow runs {name} can't be told: none of the workflow runs given matches its check suite",
                f"{name}: no workflow run matches its check_suite id",
            ), Words(
                "Ask Claude to fetch the checks that ran again, with the workflow runs behind them.",
                f"Give {GIVE_CI}, with each commit's workflow runs.",
            )))
    if lacking:
        files = _files_named(lacking)
        fix = Words(
            f"Ask Claude to add `merge_group:` beside `pull_request:` in {files} (covering `{base}`) in a pull request; CI files are yours to review and merge.",
            f"Add merge_group: (covering `{base}`) beside pull_request: in {files}; CI config is a protected path, so the owner merges it.",
        ) if on else Words(
            f"When you take a merge queue, \"{USE_MERGE_QUEUE}\" adds `merge_group:` to {files} in a pull request first.",
            f"\"{USE_MERGE_QUEUE}\" adds merge_group to {files} in a PR first.",
        )
        found.append(("gap" if on else "note", NONE, fix))
    if narrow:
        files = _files_named(narrow)
        found.append(("gap" if on else "note", NONE, Words(
            f"Ask Claude to widen the `branches` filter of `merge_group:` in {files} to cover `{base}`, in a pull request; CI files are yours to review and merge.",
            f"Widen merge_group's branches filter in {files} to cover `{base}` (a PR to a protected path: the owner merges it).",
        )))
    if ignoring:
        files = _files_named(ignoring)
        found.append(("gap" if on else "note", NONE, Words(
            f"Ask Claude to take `{base}` out of the `branches-ignore` filter of `merge_group:` in {files}, in a pull request; CI files are yours to review and merge.",
            f"Stop merge_group's branches-ignore filter in {files} matching `{base}` (a PR to a protected path: the owner merges it).",
        )))
    status = min((s for s, _, _ in found), key=_rank, default="fine")
    ready = [w["path"] for w in workflows if w["state"] == "ready"]
    state = {"status": status, "clean": status == "fine" and bool(workflows), "workflows": workflows, "checks": checks}
    if status == "fine":
        names = _files_named(ready)
        return Line(g, id_, "fine", Words(
            f"Every workflow behind a required check also runs for a merge queue (`merge_group`): {names}.",
            f"merge_group on every workflow behind a required check: {names}.",
        )), state
    whats = [w for _, w, _ in sorted(found, key=lambda f: _rank(f[0])) if w is not NONE]
    fixes = list(dict.fromkeys(f for _, _, f in sorted(found, key=lambda f: _rank(f[0])) if f is not NONE))
    return Line(g, id_, status, Words(
        "For a merge queue, the workflows behind the required checks must also run on `merge_group`: " + "; ".join(w.new for w in whats) + ".",
        "merge_group check: " + "; ".join(w.developer for w in whats) + ".",
    ), Words(" ".join(f.new for f in fixes), " ".join(f.developer for f in fixes))), state


@_check("GitHub", "github.merge_queue")
def check_merge_queue(i: Inputs) -> list[Line]:  # run by check_ruleset_rules, so not in CHECKS
    """The merge-queue suggestion (a note offering "Use a merge queue",
    never a gap) where it fits, or the queue's line once it is on; with
    either, the `merge_group` check. No line where GitHub won't give one,
    nothing is required, or the read-back can't be read (the other lines
    say so). The queue's state, the check and the signals also go in the
    JSON's `merge_queue`."""
    gh = _github(i)
    if gh is None or gh.report is None:
        return []
    rep = gh.report
    unsure = bool(rep.queue_unsure) and not rep.queue
    mq = i._mq = {"queue": None if unsure else rep.queue, "available": None, "merge_group": None, "signals": None}
    if unsure and any(p.get("strict_required_status_checks_policy") is True for p in _rules(rep, "required_status_checks")):
        # "Up to date" is met either way, so github.up_to_date is fine: the
        # queue rule that may apply is said here (without "up to date" on,
        # github.up_to_date says it).
        base = i.profile.base_branch
        return [Line("GitHub", "github.merge_queue", "cant_check", Words(
            f"Can't tell whether GitHub's merge queue is on for `{base}`: {_shown(rep.queue_unsure[0], 300)}.",
            f"Merge queue unknown on `{base}`: {_shown('; '.join(rep.queue_unsure), 300)}.",
        ), Words(
            f"Check in Settings → Rules whether that ruleset applies to `{base}`; naming `{base}` itself (not a pattern) lets the kit tell.",
            f"Name refs/heads/{base} (or ~DEFAULT_BRANCH, with --repo's default_branch) in its include, so the reader can count it.",
        ))]
    if not rep.queue:
        if unsure or i.profile.ruleset is False or not rep.protected or not rep.required_checks:
            return []
        mq["available"] = _availability(i, gh)
        if mq["available"] is None:
            return []
    mq["signals"] = _signals(i, rep)
    lines = [_queue_line(i, rep, mq["available"], mq["signals"])]
    if rep.required_checks:
        line, mq["merge_group"] = _merge_group(i, rep)
        if not rep.queue and line.status == "cant_check":
            # The queue is off: what can't be checked is for the upgrade to
            # read (the JSON keeps it), never a problem with the set-up.
            line = dataclasses.replace(line, status="note")
        lines.append(line)
    return lines


@dataclass
class _Rule:
    """A CODEOWNERS rule: what it matches (None: it can't be read), whether
    it names an owner, and the part of its path before any wildcard, from
    the root (None: it matches at any depth)."""

    match: re.Pattern | None
    owned: bool
    prefix: str | None


def _anchored(pat: str) -> bool:
    """A slash at its start or in its middle ties a pattern to the root."""
    body = pat.rstrip("/")
    return body.startswith("/") or "/" in body


def _prefix(pat: str) -> str | None:
    """The part of a pattern's path before any wildcard, from the root; None
    when it matches at any depth."""
    if not _anchored(pat):
        return None
    body = pat.lstrip("/")
    cut = min((body.index(c) for c in "*?\\" if c in body), default=len(body))
    return body[:cut]


def _codeowners_pattern(pat: str) -> re.Pattern | None:
    """A CODEOWNERS pattern as a regex over a file's path, as GitHub reads it
    (gitignore's rules, except that a last part with a `*` in it, `docs/*`,
    takes only the files directly there): None when it can't be read."""
    dir_only = pat.endswith("/")
    anchored = _anchored(pat)
    body = pat.rstrip("/").lstrip("/")
    if not body:
        return None
    last = body.rsplit("/", 1)[-1]
    files_only = not dir_only and last != "**" and any(c in last for c in "*?")
    out, k = "", 0
    while k < len(body):
        if body.startswith("**/", k):
            out, k = out + "(?:.*/)?", k + 3
        elif body.startswith("**", k):
            out, k = out + ".*", k + 2
        elif body[k] == "*":
            out, k = out + "[^/]*", k + 1
        elif body[k] == "?":
            out, k = out + "[^/]", k + 1
        elif body[k] == "\\" and k + 1 < len(body):
            out, k = out + re.escape(body[k + 1]), k + 2
        else:
            out, k = out + re.escape(body[k]), k + 1
    # The pattern names the path itself (not for a directory-only pattern) or
    # a directory above it, whose files it then covers.
    tail = "" if files_only else "/.*" if dir_only else "(?:/.*)?"
    return re.compile(("" if anchored else "(?:.*/)?") + out + tail)


def _codeowners_rules(text: str) -> list[_Rule]:
    """Each rule, in order. Only `@login`, `@org/team` and email addresses
    count as owners."""
    rules = []
    for raw in text.splitlines():
        tokens = re.findall(r"(?:\\.|[^\s\\])+", raw.strip())
        if not tokens or tokens[0].startswith("#"):
            continue
        owners = []
        for t in tokens[1:]:
            if t.startswith("#"):
                break
            owners.append(t)
        rules.append(_Rule(_codeowners_pattern(tokens[0]), any(_OWNER.fullmatch(o) for o in owners), _prefix(tokens[0])))
    return rules


def _covers(rules: list[_Rule], folder: str) -> bool:
    """Whether every file under `folder` (`/.claude/`) has an owner: the last
    rule matching any file there names one, and no later rule that names
    nobody could match some file there."""
    inside = folder.strip("/")
    last = None
    for k, r in enumerate(rules):
        if r.match is not None and all(r.match.fullmatch(f"{inside}/{p}") for p in ("doctor-probe", "doctor-probe/doctor-probe")):
            last = k
    if last is None or not rules[last].owned:
        return False
    for r in rules[last + 1:]:
        if r.owned or r.match is None:
            continue
        # A later rule naming nobody, whose path could lead into the folder
        # (any depth, a wildcard before it, or inside it), takes files back.
        if r.prefix is None or (inside + "/").startswith(r.prefix) or r.prefix.startswith(inside + "/"):
            return False
    return True


@_check("GitHub", "github.codeowners")
def check_codeowners(i: Inputs) -> list[Line]:
    """CODEOWNERS, read from the checkout (the first of the places GitHub
    looks), names an owner for the kit and CI: every file under `/.claude/`
    and `/.github/workflows/`."""
    g, id_ = "GitHub", "github.codeowners"
    if not i.root.is_dir():
        return []  # kit.profile says the folder isn't there
    where, text, err = None, None, None
    for rel in CODEOWNERS_PATHS:
        text, err = _read_text(i.root, rel)
        if text is not None or err:
            where = rel
            break
    owned = ", ".join(f"`{p}`" for p in OWNED)
    fix = Words(
        f"Ask Claude to add {owned} with your GitHub name to CODEOWNERS (docs/enforcement.md §3 has the lines); it's a change you review and merge.",
        f"Add `/.claude/ @<owner>` and `/.github/workflows/ @<owner>` to {where or '.github/CODEOWNERS'} (docs/enforcement.md §3).",
    )
    if where is None:
        return [Line(g, id_, "gap", Words(
            f"There's no CODEOWNERS file, so GitHub doesn't ask you to review changes to the kit and CI ({owned}).",
            f"No CODEOWNERS ({', '.join(CODEOWNERS_PATHS)}): {owned} unowned.",
        ), fix)]
    if err:
        return [Line(g, id_, "gap", Words(
            f"GitHub's CODEOWNERS file ({where}) can't be read ({err}), so it can't ask you to review changes to the kit and CI.",
            f"{where}: {err}.",
        ), fix)]
    rules = _codeowners_rules(text)
    missing = [p for p in OWNED if not _covers(rules, p)]
    if missing:
        shown = ", ".join(f"`{p}`" for p in missing)
        return [Line(g, id_, "gap", Words(
            f"CODEOWNERS ({where}) doesn't name an owner for all of {shown}, so GitHub doesn't ask you to review every change there.",
            f"{where} leaves part or all of {shown} without an owner (the last matching rule names none, or a later ownerless rule takes some back).",
        ), fix)]
    return [Line(g, id_, "fine", Words(
        f"CODEOWNERS ({where}) asks you to review changes to the kit and CI ({owned}).",
        f"{where} owns {owned}.",
    ))]


# ---------- Cloud ----------
#
# The two environments the profile names (#60), from --environments, as
# `list_environments` returns them: only a cloud session can list them, so they
# only ever come from a file. When neither is listed, whether a run has been
# made (an issue labelled `workflow:run`) says whether that is a choice or a
# gap: from --runs, read as `charter estimate --runs` reads it, else `gh api`
# as the GitHub lines read GitHub, within the same time budget. Then always the
# note that nothing can read what an environment holds.

RUN_LABEL = estimate_mod.RUN_LABEL
# The file doctor takes instead of `gh` for the runs, as a developer's fix names it.
GIVE_RUNS = f"--runs (GET repos/<repo>/issues?labels={RUN_LABEL}&state=all)"
SET_UP_RUNS = OFFERS["set_up_unattended_runs"]
# How alike a listed name must be to the profile's to be named as a likely typo.
TYPO_LIKENESS = 0.8


class _Role(NamedTuple):
    """An environment the profile names: its key, what it's for, and its
    name (empty when the profile doesn't name it)."""

    key: str
    purpose: str
    name: str


def _roles(i: Inputs) -> tuple[_Role, _Role]:
    p = i.profile
    return (_Role("run.ticket_environment", "ticket sessions", p.ticket_environment),
            _Role("run.conductor_environment", "the conductor", p.conductor_environment))


def _active(state: str | None) -> bool:
    """An environment's state, as listed, that counts: none given, or active."""
    return state is not None and state.casefold() in ("", "active")


@dataclass
class _Listed:
    """The environments given: each one's state by name ("" when its entry
    has none), and whether the list goes on (`has_more`), so a name not in it
    may still be there."""

    states: dict[str, str]
    partial: bool


def _environments(i: Inputs) -> _Answer | None:
    """The environments listed in --environments, read once; None when no
    file was given."""
    if i.environments_file is None:
        return None
    if i._environments is None:
        i._environments = _read_environments(i)
    return i._environments


def _read_environments(i: Inputs) -> _Answer:
    """--environments as `list_environments` returns it (`{"environments":
    […], "has_more": …}`), the list alone, or a list of its pages (the
    last page's `has_more` says whether the list goes on)."""
    fix = Words(
        "Ask a cloud session to check the set-up again: it lists your environments for the check.",
        "Give --environments as list_environments returns it ({\"environments\": [{\"name\": …}, …], \"has_more\": false}), or a list of its pages.",
    )
    got = _given(i, i.environments_file, "--environments", fix, "the environments")
    if got.why:
        return got
    value = got.value
    pages = value if isinstance(value, list) and value and all(isinstance(x, dict) and "environments" in x and "name" not in x for x in value) else [value]
    entries, more = [], None
    for page in pages:
        if isinstance(page, dict):
            page, more = page.get("environments"), page.get("has_more")
        if not isinstance(page, list) or not isinstance(more, (bool, type(None))):
            entries = None
            break
        entries += page
    if entries is None or not all(isinstance(e, dict) and isinstance(e.get("name"), str) and isinstance(e.get("state"), (str, type(None))) for e in entries):
        return _Answer(why=Words(
            "the --environments file isn't a list of your environments in the shape Claude gets it",
            "--environments isn't list_environments' JSON (an environments list, each with a name and any state a string, and has_more true or false)",
        ), fix=fix)
    states: dict[str, str] = {}
    for e in entries:
        state = e.get("state") or ""
        if not _active(states.get(e["name"])):  # listed twice: an active one counts
            states[e["name"]] = state
    return _Answer(_Listed(states, more is True))


def _runs(i: Inputs) -> _Answer:
    """The `workflow:run` issues' numbers (an empty list: no run made yet),
    from --runs, else `gh api`; read once."""
    if i._runs is None:
        i._runs = _read_runs(i)
    return i._runs


def _label_names(issue: dict) -> set[str]:
    """An issue's labels, casefolded, as GitHub matches them: objects with a
    name, or names."""
    labels = issue.get("labels")
    names = [x.get("name") if isinstance(x, dict) else x for x in labels] if isinstance(labels, list) else []
    return {x.casefold() for x in names if isinstance(x, str)}


def _number(issue: dict) -> int | None:
    n = issue.get("number")
    return n if isinstance(n, int) and not isinstance(n, bool) else None


def _read_runs(i: Inputs) -> _Answer:
    """The runs, as `charter estimate --runs` reads them: a list of issues,
    the GitHub MCP tools' wrapped list or search's, or pages of any of them.
    An issue is an object with a number or labels, whose labels, if given,
    are a list; one without labels counts (it was fetched by its label), a
    pull request doesn't."""
    if i.runs_file is not None:
        got = _given(i, i.runs_file, "--runs", Words(
            f"Ask Claude to fetch the issues labelled `{RUN_LABEL}` from GitHub again, or leave out --runs to read them with `gh`.",
            f"Give {GIVE_RUNS}, as the GitHub API returns them, or leave it out to use `gh api`.",
        ), "the issues")
        source = Words("the --runs file", "--runs")
    else:
        path = f"repos/{i.profile.repo}/issues?labels={RUN_LABEL}&state=all&per_page=100"
        got = _gh(i, path, _gh_deadline(i), "--runs", give=GIVE_RUNS)
        source = Words("GitHub's answer to `gh`", f"`gh api repos/{i.profile.repo}/issues`")
    if got.why:
        return got
    issues = estimate_mod._flatten(got.value) if isinstance(got.value, (list, dict)) else None
    if issues is None:
        shape = "it isn't a list of issues"
    else:
        found = [x for x in issues if isinstance(x, dict) and isinstance(x.get("labels", []), list)
                 and (_number(x) is not None or "labels" in x)]
        runs = [x for x in found if "pull_request" not in x and ("labels" not in x or RUN_LABEL in _label_names(x))]
        states = [str(x.get("state") or "").casefold() for x in runs]
        i._run_open = True if "open" in states else None if "" in states else False  # a run without its state can't be told
        if runs or len(found) == len(issues):  # a run is a run, whatever else the file holds
            return _Answer([_number(x) for x in runs])
        shape = "an entry isn't an issue"
    return _Answer(why=Words(f"{source.new} can't be read: {shape}", f"{source.developer}: {shape}"), fix=Words(
        f"Ask Claude to fetch the issues labelled `{RUN_LABEL}` from GitHub again, as GitHub gives them.",
        f"Give {GIVE_RUNS}: a list of issues, as the GitHub API returns them.",
    ) if i.runs_file is not None else _again(GIVE_RUNS))


def _named(name: str) -> str:
    """An environment's name in a code span, exactly: one with a backtick,
    a space at either end, or a character that can't be shown plainly is
    shown as a JSON string; a long one keeps its end, where names differ."""
    if name == name.strip() and "`" not in name and name.isprintable():
        shown = name
    else:
        shown = _printable(json.dumps(name, ensure_ascii=False).replace("`", "\\u0060"))
    return f"`{shown if len(shown) <= 80 else shown[:39] + '…' + shown[-40:]}`"


def _close(name: str, names: list[str], taken: set[str]) -> str | None:
    """The listed name most like `name` (a likely typo), if one is close."""
    scored = [(difflib.SequenceMatcher(None, name.casefold(), n.casefold()).ratio(), n) for n in names if n not in taken]
    best = max(scored, default=(0.0, None))
    return best[1] if best[0] >= TYPO_LIKENESS else None


def _missing(listed: _Listed, role: _Role, taken: set[str]) -> tuple[Words, bool]:
    """Why one of the profile's environments isn't found, as a clause, and
    whether a listed name may be it misspelled."""
    if not role.name:
        return Words(f"the kit's profile doesn't name the one for {role.purpose} (`{role.key}` isn't set)", f"{role.key} isn't set"), False
    n = _named(role.name)
    state = listed.states.get(role.name)
    if state is not None:
        return Words(f"{n}, for {role.purpose}, is listed but not active (its state is {_named(state)})", f"{role.key} {n} is {_named(state)}, not active"), False
    close = _close(role.name, list(listed.states), taken)
    return Words(
        f"{n}, for {role.purpose}, isn't among your environments" + (f" (the list has {_named(close)}, which may be a typo for it)" if close else ""),
        f"{role.key} {n} isn't listed" + (f" (closest: {_named(close)})" if close else ""),
    ), close is not None


def _refs(numbers: list) -> list[str]:
    """The runs' issue numbers, each once."""
    return list(dict.fromkeys(f"#{n}" for n in numbers if n is not None))


def _listing(refs: list[str]) -> str:
    return ", ".join(refs[:3]) + (f" and {len(refs) - 3} more" if len(refs) > 3 else "")


@_check("Cloud", "cloud.environments")
def check_environments(i: Inputs) -> list[Line]:
    """Both of the profile's environments listed and active, by their exact
    names: fine. Neither, while no run has been made, is a note offering "Set
    up unattended runs"; one missing, either once a run has been made, or one
    environment named for both, a gap."""
    g, id_ = "Cloud", "cloud.environments"
    if i.profile is None:
        return [Line(g, id_, "cant_check", Words(
            "Can't check the cloud environments for unattended runs until the kit's profile, which names them, "
            + ("can be read." if i.profile_error else "is set up."),
            "Environments unchecked: no readable profile (run.ticket_environment, run.conductor_environment).",
        ), PROFILE_FIRST if i.profile_error else SET_UP_FIRST)]
    roles = _roles(i)
    ticket, conductor = roles
    if ticket.name and ticket.name == conductor.name:
        n = _named(ticket.name)
        return [Line(g, id_, "gap", Words(
            f"The kit's profile names one environment, {n}, for both ticket sessions and the conductor, but they need one each: "
            "ticket sessions run with no secrets and `WORKFLOW_ROLE=ticket`, the conductor with `WORKFLOW_ROLE=conductor`.",
            f"run.ticket_environment and run.conductor_environment are both {n}: one environment can't set WORKFLOW_ROLE=ticket and WORKFLOW_ROLE=conductor.",
        ), Words(
            f"Ask Claude to \"{SET_UP_RUNS}\": it walks you through making a second environment and naming each in the kit's profile.",
            f"Give each role its own environment and name (docs/enforcement.md §2); upgrade-setup's \"{SET_UP_RUNS}\" guides it.",
        ), offer="set_up_unattended_runs")]
    listed = _environments(i)
    if listed is None:
        return [Line(g, id_, "cant_check", Words(
            "Can't check the two cloud environments for unattended runs from here: only a cloud session can list them.",
            "Environments unchecked: no --environments (only a cloud session can list them, with list_environments).",
        ), Words(
            "Ask a cloud session to check the set-up.",
            "From a cloud session, give --environments (list_environments' JSON); or ask a cloud session to check the set-up.",
        ))]
    if listed.why:
        return [_waits(i, id_, Words("the cloud environments for unattended runs", "Environments"), listed, group=g)]
    envs = listed.value
    missing = [r for r in roles if not (r.name and _active(envs.states.get(r.name)))]
    if not missing:
        return [Line(g, id_, "fine", Words(
            f"Both cloud environments for unattended runs are ready: {_named(ticket.name)} for ticket sessions and {_named(conductor.name)} for the conductor.",
            f"run.ticket_environment {_named(ticket.name)} and run.conductor_environment {_named(conductor.name)} are both listed and active.",
        ))]
    unseen = [r for r in missing if r.name and r.name not in envs.states]
    if envs.partial and unseen:
        one = len(unseen) == 1
        shown = [_named(r.name) for r in unseen]
        names = " and ".join(shown)
        listed_not = f"doesn't list {shown[0]}" if one else f"lists neither {shown[0]} nor {shown[1]}"
        # The other one may already be missing for certain (not named, or not active).
        known = [_missing(envs, r, set())[0] for r in missing if r not in unseen]
        also = Words(f" Already missing: {known[0].new}.", f"; {known[0].developer}") if known else NONE
        fix_also = Words(
            f" Ask Claude to \"{SET_UP_RUNS}\" for the missing one.",
            f" Fix the other first ({known[0].developer}).",
        ) if known else NONE
        return [Line(g, id_, "cant_check", Words(
            f"Can't tell whether {names} {'is' if one else 'are'} there: the list of your environments given to the check isn't complete.{also.new}",
            f"--environments says has_more, and {listed_not}{also.developer}.",
        ), Words(
            f"Ask a cloud session to check the set-up again, with every environment listed.{fix_also.new}",
            f"Give every page of list_environments in --environments (a list of the pages).{fix_also.developer}",
        ))]
    taken = {r.name for r in roles}
    whys = [_missing(envs, r, taken) for r in missing]
    typo = any(t for _, t in whys)
    one = len(missing) == 1
    fix = Words(
        f"Ask Claude to \"{SET_UP_RUNS}\": it walks you through setting up {'the missing environment' if one else 'the two environments'} in claude.ai, "
        f"or putting {'its' if one else 'their'} exact {'name' if one else 'names'} in the kit's profile.",
        f"Create {'it' if one else 'them'} (claude.ai/code, the environment menu; docs/enforcement.md §2), or set "
        f"{' and '.join(r.key for r in missing)} to {'its' if one else 'their'} exact {'name' if one else 'names'}; upgrade-setup's \"{SET_UP_RUNS}\" guides {'it' if one else 'both'}.",
    )
    if one:
        there, = [r for r in roles if r not in missing]
        return [Line(g, id_, "gap", Words(
            f"Unattended runs need two cloud environments, and only {_named(there.name)} is ready: {whys[0][0].new}.",
            f"Half set up: {whys[0][0].developer}; {_named(there.name)} is listed and active.",
        ), fix, offer="set_up_unattended_runs")]
    new, dev = "; ".join(w.new for w, _ in whys), "; ".join(w.developer for w, _ in whys)
    runs = _runs(i)
    if runs.why is None and runs.value:
        refs = _refs(runs.value)
        many = len(refs) > 1 if refs else len(runs.value) > 1
        return [Line(g, id_, "gap", Words(
            f"A run has already been made ({_listing(refs) or f'an issue is labelled `{RUN_LABEL}`'}), but neither cloud environment for unattended runs is ready, "
            f"so the next run can't start: {new}.",
            f"{'Issues' if many else 'An issue'} labelled {RUN_LABEL} {'exist' if many else 'exists'}{f' ({_listing(refs)})' if refs else ''}, but neither environment is listed and active: {dev}.",
        ), fix, offer="set_up_unattended_runs")]
    retype = Words(
        " If a name above is a typo, it corrects that too.",
        " If a name above is a typo, correct it in the profile first.",
    ) if typo else NONE
    if runs.why is None:
        return [Line(g, id_, "note", Words(
            f"Unattended runs aren't set up yet, which is fine until you want Claude to work through tickets on its own. Neither of their two cloud environments is ready: {new}.",
            f"Unattended runs not set up: no issue is labelled {RUN_LABEL}, and neither environment is listed and active: {dev}.",
        ), Words(
            f"When you want unattended runs, ask Claude to \"{SET_UP_RUNS}\".{retype.new}",
            f"Run upgrade-setup's \"{SET_UP_RUNS}\" when you want runs.{retype.developer}",
        ), offer="set_up_unattended_runs")]
    return [Line(g, id_, "note", Words(
        f"Unattended runs don't look set up yet. Neither of their two cloud environments is ready: {new}. "
        f"If you've already made a run, this is a gap; whether one has been made couldn't be read ({_relative(i, runs.why.new)}).",
        f"Neither environment is listed and active: {dev}. A gap if a run has been made, which couldn't be read "
        f"({RUN_LABEL} issues: {_relative(i, runs.why.developer)}).",
    ), Words(
        f"If you've never made a run, nothing to do until you want one: then ask Claude to \"{SET_UP_RUNS}\".{retype.new} To check for a run: {runs.fix.new}",
        f"No run made: upgrade-setup's \"{SET_UP_RUNS}\" when wanted.{retype.developer} To tell: {runs.fix.developer}",
    ), offer="set_up_unattended_runs")]


@_check("Cloud", "cloud.contents")
def check_environment_contents(i: Inputs) -> list[Line]:
    """Always there: nothing can read what an environment holds (#27), so the
    owner confirms it by hand."""
    g, id_ = "Cloud", "cloud.contents"
    names = [r.name for r in _roles(i)] if i.profile is not None else ["", ""]
    t, c = (_named(n) if n else None for n in names)
    if t and names[0] == names[1]:
        both = Words(t, t)  # one named for both: the environments line says it needs two
        t = c = None
    elif t and c:
        both = Words(f"{t} or {c}", f"{t} and {c}")
    else:
        both = Words("the ticket and conductor environments", "the ticket and conductor environments")
    return [Line(g, id_, "note", Words(
        f"Nothing can read what a cloud environment holds, so no check can look inside {both.new}.",
        f"Contents of {both.developer} unchecked: nothing can read an environment's variables or secrets.",
    ), Words(
        f"Look for yourself in claude.ai (the environment menu, then Edit): the ticket environment{f' ({t})' if t else ''} should hold no keys or other secrets "
        f"and set `WORKFLOW_ROLE=ticket`; the conductor's{f' ({c})' if c else ''} sets `WORKFLOW_ROLE=conductor`.",
        f"Confirm by hand: {t or 'the ticket environment'}: no secrets, WORKFLOW_ROLE=ticket; {c or 'the conductor environment'}: "
        "WORKFLOW_ROLE=conductor (docs/enforcement.md §2).",
    ))]

# ---------- Previews ----------
#
# Try-it links (#41): the profile's `[previews]` section beside the project's
# Wrangler config, both read from the checkout. Only `wrangler.toml` is read,
# as TOML, and only when no `wrangler.json` or `wrangler.jsonc` is beside it,
# which Cloudflare could read instead: with one, the block can't be checked.
# A project with neither a Wrangler config nor a section gets no line. What
# Cloudflare holds (Access, Preview URLs, no live site) is #41's by-hand check.

WRANGLER_TOML = "wrangler.toml"
WRANGLER_JSON = ("wrangler.json", "wrangler.jsonc")
# upgrade-setup's fourth path (#116), which the note's fix names.
ADD_TRY_IT_LINKS = OFFERS["add_try_it_links"]
NO_BLOCK = "missing a `previews` block"  # what Cloudflare's build log says without it


def _previews_page(i: Inputs) -> str:
    """`docs/previews.md` as the reader finds it: by its path from the
    project's root when the kit running doctor is in the checkout (vendored,
    or the kit's own repository), else the kit's own, by its full path."""
    page = i.kit_root / "docs/previews.md"
    try:
        return f"`{page.resolve().relative_to(i.root.resolve()).as_posix()}`"
    except (OSError, ValueError):
        return f"the kit's `docs/previews.md` (`{_home(i, page)}`)"


def _wrangler_configs(i: Inputs) -> list[str]:
    """The Wrangler configs at the checkout's root, the JSON ones first."""
    return [n for n in (*WRANGLER_JSON, WRANGLER_TOML) if os.path.lexists(_file(i.root, n)[0])]  # a broken link counts, to be named


def _access_gap(page: str) -> Line:
    return Line("Previews", "previews.access", "gap", Words(
        "Your project has sensitive data and try-it links are on in the kit's profile (`on = true`), but you haven't confirmed "
        "that Cloudflare Access guards them (`access = true`). A try-it link is public: anyone with it can open it. "
        "The kit can't use its profile until this is settled.",
        "[sensitive] patterns with previews.on = true and access not true (Cloudflare Access unconfirmed): `profile check` refuses the profile.",
    ), Words(
        f"Turn on Cloudflare Access for the try-it links ({page}, step 7), then ask Claude to set `access = true` in the profile's "
        "`[previews]` section and `preview_urls = true` in the Wrangler config. Without Access, turn Preview URLs off in Cloudflare's dashboard and ask Claude to set (or keep) "
        "`preview_urls = false` in the Wrangler config and set `on = false` in the profile: `on = false` alone leaves the links public.",
        f"Put Cloudflare Access on the preview URLs ({page}, step 7), then set `access = true` and `preview_urls = true`. Without Access: Preview URLs off in the "
        "dashboard, `preview_urls = false` in the Wrangler config, and `on = false` (the profile alone changes nothing on Cloudflare).",
    ))


@_check("Previews", "previews.setup")
def check_previews(i: Inputs) -> list[Line]:
    """With `[previews] on = true`, the Wrangler config has a `[previews]`
    block: a gap without it, `cant_check` when only a JSON config could say.
    With `[sensitive]` patterns, `access` is true too: a gap otherwise, as
    `profile check` says. A Wrangler config and no section is a note offering
    "Add try-it links"; a section not turning them on is a note with no offer
    (chosen states are notes). Neither a config nor a section: no line."""
    g, id_ = "Previews", "previews.setup"
    if not i.root.is_dir():
        return []  # kit.profile says the folder isn't there
    page, configs = _previews_page(i), _wrangler_configs(i)
    if i.profile is None:
        lines = [_access_gap(page)] if (i.profile_error or "").startswith(profile_mod.ACCESS_REFUSED) else []
        if configs:
            lines.append(Line(g, id_, "cant_check", Words(
                "Can't check try-it links until the kit's profile " + ("can be read." if i.profile_error else "is set up."),
                "Previews unchecked: " + ("the profile doesn't read" if i.profile_error else "no profile") + " ([previews]).",
            ), PROFILE_FIRST if i.profile_error else SET_UP_FIRST))
        return lines
    p = i.profile.previews
    if not p.on:
        if p.section:  # turned off on purpose: no offer, so never a nag
            # The upgrade needs a Wrangler config, so it's named only beside one.
            fix = Words(
                f"To turn them on, ask Claude to \"{ADD_TRY_IT_LINKS}\": it follows {page} and turns them on in a pull request of its own.",
                f"upgrade-setup's \"{ADD_TRY_IT_LINKS}\" turns them on ({page}).",
            ) if configs else Words(
                f"To turn them on, follow {page}.",
                f"Follow {page}, then set `on = true`.",
            )
            return [Line(g, id_, "note", Words(
                "Try-it links aren't turned on in the kit's profile (its `[previews]` section doesn't say `on = true`).",
                "`[previews]` doesn't say `on = true`: previews off.",
            ), fix)]
        if not configs:
            return []
        return [Line(g, id_, "note", Words(
            f"Your project has a Wrangler config (`{configs[0]}`) but no try-it links yet: a working copy of each pull request's change, "
            "to try before you merge it. That's fine until you want them.",
            f"`{configs[0]}` found, and no `[previews]` section in the profile: previews not set up.",
        ), Words(
            f"When you want a try-it link on each pull request, ask Claude to \"{ADD_TRY_IT_LINKS}\": it takes you through the steps "
            f"in {page} one screen at a time, then turns them on in a pull request of its own.",
            f"Set previews up when wanted: upgrade-setup's \"{ADD_TRY_IT_LINKS}\" guides {page}, then opens the `[previews] on = true` PR.",
        ), offer="add_try_it_links")]
    lines = []
    if i.profile.sensitive_patterns:  # on = true there needs access = true, or the profile is refused
        lines.append(Line(g, "previews.access", "fine", Words(
            "Your project has sensitive data, and you've confirmed that Cloudflare Access guards its try-it links (`access = true`). "
            "The kit can't check Access itself: it relies on your word.",
            "`access = true`: the owner confirmed Cloudflare Access guards the preview URLs; the kit can't check Access itself.",
        )))
    return [_previews_block(i, page, configs)] + lines


def _previews_block(i: Inputs, page: str, configs: list[str]) -> Line:
    """`previews.setup` with `on = true`: whether the Wrangler config has
    its `[previews]` block."""
    g, id_ = "Previews", "previews.setup"
    on = "Try-it links are on in the kit's profile (`on = true`)"
    if not configs:
        return Line(g, id_, "gap", Words(
            f"{on}, but there's no Wrangler config (`{WRANGLER_TOML}`) at the project's root with the `[previews]` block "
            "Cloudflare's preview builds need.",
            f"on = true, but there's no {WRANGLER_TOML}, {' or '.join(WRANGLER_JSON)} at the root, so no `[previews]` block.",
        ), Words(
            f"Ask Claude to add a `{WRANGLER_TOML}` ending in an empty `[previews]` block, in a pull request: {page} shows it (step 6). "
            f"Without it, each preview build fails with \"{NO_BLOCK}\".",
            f"Add {WRANGLER_TOML} with `[previews]` ({page}, step 6); without it the build fails: \"{NO_BLOCK}\".",
        ))
    json_ones = [n for n in configs if n in WRANGLER_JSON]
    if json_ones:
        name = json_ones[0]
        return Line(g, id_, "cant_check", Words(
            f"Can't check `{name}` for the `\"previews\"` setting try-it links need: the check reads only a `{WRANGLER_TOML}`, "
            "and only when there's no JSON Wrangler config beside it.",
            f"`{name}` not read: only a {WRANGLER_TOML} with no JSON config beside it is.",
        ), Words(
            f"Look in `{name}` yourself for a `\"previews\"` key (`\"previews\": {{}}` is enough). If it's missing, ask Claude to add it "
            f"in a pull request: {page} has it (step 6).",
            f"Check `{name}` has a top-level `\"previews\"` object (`\"previews\": {{}}`); {page}, step 6.",
        ))
    text, err = _read_text(i.root, WRANGLER_TOML)
    data, detail = None, ""
    if text is not None:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            err, detail = "it isn't valid TOML", f" ({e})"
        except RecursionError:
            err, detail = "it isn't valid TOML", " (nested too deeply)"
    if data is None:
        why = err or "it links to a file that isn't there"  # listed, but missing: a broken link
        fix = Words(
            f"Ask Claude to correct `{WRANGLER_TOML}` so it reads as TOML, then run this again ({page}, step 6, shows the block).",
            f"Make {WRANGLER_TOML} valid TOML, with `[previews]` ({page}, step 6).",
        ) if detail else Words(
            f"Ask Claude to look at what `{WRANGLER_TOML}` is: it should be a text file Cloudflare can read ({page}, step 6).",
            f"Make {WRANGLER_TOML} a readable UTF-8 regular file ({page}, step 6).",
        )
        return Line(g, id_, "cant_check", Words(
            f"Can't check `{WRANGLER_TOML}` for the `[previews]` block try-it links need: {why}.",
            f"{WRANGLER_TOML} unreadable: {why}{detail}.",
        ), fix)
    block = data.get("previews")
    if isinstance(block, dict):
        return Line(g, id_, "fine", Words(
            f"Try-it links are on, and `{WRANGLER_TOML}` has the `[previews]` block Cloudflare's preview builds need.",
            f"on = true; {WRANGLER_TOML} has `[previews]`.",
        ))
    what = Words("has no `[previews]` block", "has no `[previews]` table") if block is None else Words(
        "has a `previews` setting that isn't a `[previews]` block", "has `previews` as a value, not a `[previews]` table")
    return Line(g, id_, "gap", Words(
        f"{on}, but `{WRANGLER_TOML}` {what.new}, which Cloudflare's preview builds need.",
        f"on = true, but {WRANGLER_TOML} {what.developer}.",
    ), Words(
        f"Ask Claude to add an empty `[previews]` block at the end of `{WRANGLER_TOML}`, in a pull request: {page} shows it (step 6). "
        f"Without it, each preview build fails with \"{NO_BLOCK}\".",
        f"Append `[previews]` to {WRANGLER_TOML} ({page}, step 6); without it the build fails: \"{NO_BLOCK}\".",
    ))


# Every check, in the order its lines show when they are equally serious: the
# profile first, since setting the kit up comes before anything it then checks.
CHECKS = [check_python, check_claude_code, check_profile, check_install, check_vendor, check_experience, check_ruleset,
          check_protection, check_required_checks, check_ruleset_rules, check_merge_settings, check_codeowners,
          check_environments, check_environment_contents, check_previews]
# The checks that read only this computer and the checkout: no `gh`, no
# network, and nothing a session hands in. `workflow status` runs these (#62),
# so the guided start can tell, with no network call, whether to offer "check
# the set-up". Claude Code's version and CODEOWNERS are local too, but #34
# doesn't name them for `status`.
LOCAL_CHECKS = [check_python, check_profile, check_install, check_vendor, check_ruleset]


# ---------- the report ----------


@dataclass
class Report:
    lines: list[Line]
    wording: str  # "new" or "developer"
    experience: Experience
    default: str | None  # the profile's project.experience
    # The merge queue's state, its merge_group check and the signals (#246);
    # None when its check didn't get that far.
    merge_queue: dict | None = None

    def counts(self) -> dict[str, int]:
        return {s: sum(ln.status == s for ln in self.lines) for s in STATUSES}

    def strict_ok(self) -> bool:
        """`--strict`: no gap and nothing it couldn't check. Notes never fail it."""
        c = self.counts()
        return not (c["gap"] or c["cant_check"])

    def as_dict(self) -> dict:
        return {
            "experience": {"level": self.experience.level, "source": self.experience.source, "default": self.default},
            "wording": self.wording,
            "counts": self.counts(),
            "strict_ok": self.strict_ok(),
            "lines": [ln.as_dict(self.wording) for ln in self.lines],
            "merge_queue": self.merge_queue,
        }


def _rank(status: str) -> int:
    return STATUSES.index(status)


def _removed_protection(ln: Line) -> bool:
    """Removed protection (#26): never trusted, so listed before every other line."""
    return ln.status == "gap" and ln.offer == "restore_protection"


def order(lines: list[Line]) -> list[Line]:
    """Grouped, the group with the most serious line first (ties in `GROUPS`
    order), and within a group the most serious line first (ties in check
    order). So the most serious line of all comes first, and removed
    protection before anything else."""
    groups: dict[str, list[Line]] = {}
    for ln in lines:
        groups.setdefault(ln.group, []).append(ln)
    for g in groups.values():
        g.sort(key=lambda ln: (not _removed_protection(ln), _rank(ln.status)))  # stable: check order within a status
    names = sorted(groups, key=lambda g: (not any(_removed_protection(ln) for ln in groups[g]), min(_rank(ln.status) for ln in groups[g]), GROUPS.index(g)))
    return [ln for g in names for ln in groups[g]]


def _failed(i: Inputs, check, e: Exception) -> Line:
    why = _relative(i, f"{type(e).__name__}: {e}")[:200]
    return Line(check.group, check.id, "cant_check", Words(
        f"This check couldn't run ({why}).",
        f"Check {check.__name__} raised {why}.",
    ), Words(
        "Run it again; if it says the same, ask Claude to look into it, since it may be a bug in the kit.",
        "Rerun; if it repeats, report it as a kit bug with this message.",
    ))


def report(i: Inputs, checks: list | None = None) -> Report:
    """Every check's lines, or only those of `checks` (`LOCAL_CHECKS`)."""
    lines: list[Line] = []
    for check in CHECKS if checks is None else checks:
        try:
            lines += check(i)
        except Exception as e:  # advice never ends in a traceback
            lines.append(_failed(i, check, e))
    for ln in lines:
        assert ln.status in STATUSES and ln.group in GROUPS and (ln.offer is None or ln.offer in OFFERS), ln
    return Report(order(lines), i.experience.wording_level, i.experience, i.default, i._mq)


def _plural(n: int, status: str) -> str:
    return f"{n} {LABELS[status]}" + ("s" if n != 1 and status in ("gap", "note") else "")


def _wrap(text: str, width: int, first: str, rest: str) -> list[str]:
    return textwrap.wrap(text, width, initial_indent=first, subsequent_indent=rest, break_long_words=False, break_on_hyphens=False)


def text(r: Report, width: int = 100) -> str:
    """Grouped lines, each wrapped to `width` with its fix indented below it.
    A note's fix is what to do if you want to change it: "Next", not "Fix"."""
    c = r.counts()
    width = max(40, width)
    out = _wrap("Workflow doctor: " + ", ".join(_plural(c[s], s) for s in STATUSES if c[s] or s == "gap"), width, "", "")
    group = None
    for ln in r.lines:
        if ln.group != group:
            group = ln.group
            out += ["", group]
        out += _wrap(ln.message.pick(r.wording), width, f"  [{LABELS[ln.status]}] ", " " * 6)
        fix = ln.fix.pick(r.wording)
        if fix:
            out += _wrap(fix, width, " " * 6 + ("Next: " if ln.status in ("note", "fine") else "Fix: "), " " * 8)
        if ln.offer:
            out += _wrap(f"Claude can offer: {OFFERS[ln.offer]}", width, " " * 6, " " * 8)
    return "\n".join(out)

"""`workflow doctor`: one report of what's set up and what isn't (#34).

Each check is a function from what doctor was given (`Inputs`) to report
lines (`Line`). A line has a group, an id, a status, a message and a fix in
both wordings, and optionally an offer (an upgrade #32 builds). The report
picks one wording by experience (#16: what is checked, and each status, never
depend on it), puts the most serious line first and groups the rest.

Doctor never changes anything (#27): it reads files and runs `python3`,
`claude --version` and `gh api` (GETs only, for the GitHub lines and whether
a run has been made, when no file is given), nothing else. It reads files
only through `_read_text` (and `_read_value`, `_read_json` on it), `_file`
and `_hash_file`, which never raise and never wait on a pipe; only a file
given as `-` (`--rulesets`, `--repo`, `--environments` or `--runs`) reads
standard input, as asked. A check that fails unexpectedly becomes a
`cant_check` line, never a traceback: doctor is advice, and exits 0.

**Adding a group or a check** (the GitHub, Cloud and Previews tickets): write
a function `def check_x(i: Inputs) -> list[Line]`, decorate it with
`@_check(<group>, <id of its main line>)` (the line it falls back to if it
raises), add it to `CHECKS`, and put anything it reads on `Inputs` (filled in
by `cli.cmd_doctor`). The groups are in `GROUPS` already; the order, the
counts, the text, the JSON and `--strict` follow without change. A line
that needs GitHub's answers reads them through `_github(i)`, once for every
line; the Cloud lines read the environments through `_environments(i)` and
whether a run has been made through `_runs(i)`, the same way.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from . import estimate as estimate_mod
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
OFFERS = {"protect_main": "Protect `main`", "restore_protection": "Restore protection", "set_up_unattended_runs": "Set up unattended runs"}

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
    _github: _GitHub | None = field(default=None, repr=False)  # what the GitHub lines read, read once
    _environments: _Answer | None = field(default=None, repr=False)  # the environments listed, read once
    _runs: _Answer | None = field(default=None, repr=False)  # the `workflow:run` issues, read once
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
# The upgrade that requires the checks (#38; #69 offers it on the required checks' line).
REQUIRE_CHECKS = "Require these checks"
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


@_check("GitHub", "github.required_checks")
def check_required_checks(i: Inputs) -> list[Line]:
    """The profile's `ci.required_checks` that the ruleset doesn't require.
    A check it requires that the profile doesn't list isn't a line here (#38's
    tickets add that note, and #69 the `require_checks` offer on this line)."""
    g, id_ = "GitHub", "github.required_checks"
    if i.profile is None:
        return [_waits(i, id_, Words("which checks GitHub requires", "Required checks"), None)]
    base, listed = i.profile.base_branch, list(i.profile.required_checks)
    upgrade = REQUIRE_CHECKS
    if not listed:
        return [Line(g, id_, "note", Words(
            f"Checks not required yet: the kit's profile lists no checks that must pass before a pull request merges into `{base}`.",
            "ci.required_checks is empty: checks not required yet.",
        ), Words(
            f"Once your project's checks have run on `{base}`, ask Claude to \"{upgrade}\".",
            f"After CI has run on `{base}`, run upgrade-setup's \"{upgrade}\".",
        ))]
    rep, wait = _report(i, id_, Words("whether GitHub requires the checks the kit's profile lists", "ci.required_checks against the ruleset"))
    if wait:
        return [wait]
    names = ", ".join(f"`{_shown(c)}`" for c in listed)
    if _solo_unprotected(rep, i):
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't require the checks the kit's profile lists ({names}), since nothing protects `{base}` there yet.",
            f"Solo mode: no ruleset on `{base}` requires ci.required_checks ({names}).",
        ), Words(
            f"They're required when you ask Claude to \"{OFFERS['protect_main']}\".",
            f"\"{OFFERS['protect_main']}\" adds them to the ruleset it creates.",
        ))]
    missing = [c for c in listed if c not in rep.required_checks]
    if missing:
        shown = ", ".join(f"`{_shown(c)}`" for c in missing)
        return [Line(g, id_, "gap", Words(
            f"GitHub doesn't require {'this check' if len(missing) == 1 else 'these checks'} the kit's profile lists to pass before a pull request merges: {shown}.",
            f"ci.required_checks not required by any active ruleset on `{base}`: {shown}.",
        ), Words(
            f"Ask Claude to \"{upgrade}\", once {'it has' if len(missing) == 1 else 'they have'} run on `{base}`.",
            f"Run upgrade-setup's \"{upgrade}\" (adds them to the ruleset with \"up to date\" on).",
        ))]
    return [Line(g, id_, "fine", Words(
        f"GitHub requires the checks the kit's profile lists to pass before a pull request merges ({names}).",
        f"Every ci.required_checks name is required on `{base}` ({names}).",
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
    if not strict and not i.profile.required_checks:
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
    return lines


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


# Every check, in the order its lines show when they are equally serious: the
# profile first, since setting the kit up comes before anything it then checks.
CHECKS = [check_python, check_claude_code, check_profile, check_install, check_vendor, check_experience, check_ruleset,
          check_protection, check_required_checks, check_ruleset_rules, check_merge_settings, check_codeowners,
          check_environments, check_environment_contents]


# ---------- the report ----------


@dataclass
class Report:
    lines: list[Line]
    wording: str  # "new" or "developer"
    experience: Experience
    default: str | None  # the profile's project.experience

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


def report(i: Inputs) -> Report:
    lines: list[Line] = []
    for check in CHECKS:
        try:
            lines += check(i)
        except Exception as e:  # advice never ends in a traceback
            lines.append(_failed(i, check, e))
    for ln in lines:
        assert ln.status in STATUSES and ln.group in GROUPS and (ln.offer is None or ln.offer in OFFERS), ln
    return Report(order(lines), i.experience.wording_level, i.experience, i.default)


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

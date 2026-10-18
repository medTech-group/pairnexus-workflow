"""`workflow doctor`: one report of what's set up and what isn't (#34).

Each check is a function from what doctor was given (`Inputs`) to report
lines (`Line`). A line has a group, an id, a status, a message and a fix in
both wordings, and optionally an offer (an upgrade #32 builds). The report
picks one wording by experience (#16: what is checked, and each status, never
depend on it), puts the most serious line first and groups the rest.

Doctor never changes anything (#27): it reads files and runs `python3`,
`claude --version` and `gh api` (GETs only, for the GitHub lines when no
file is given), nothing else. It reads files only through `_read_value`,
`_read_json`, `_file` and `_hash_file`, which never raise and never wait on
a pipe, and a check that fails unexpectedly becomes a `cant_check` line,
never a traceback: doctor is advice, and exits 0.

**Adding a group or a check** (the GitHub, Cloud and Previews tickets): write
a function `def check_x(i: Inputs) -> list[Line]`, decorate it with
`@_check(<group>, <id of its main line>)` (the line it falls back to if it
raises), add it to `CHECKS`, and put anything it reads on `Inputs` (filled in
by `cli.cmd_doctor`). The groups are in `GROUPS` already; the order, the
counts, the text, the JSON and `--strict` follow without change. A line
that needs GitHub's answers reads them through `_github(i)`, once for every
line (the Cloud lines, #60, would read the environments the same way).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import posts as posts_mod
from . import profile as profile_mod
from . import updates as updates_mod
from . import vendor as vendor_mod
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
    # --rulesets and --repo: GitHub's answers as files, which win over `gh api`.
    rulesets_file: Path | None = None
    repo_file: Path | None = None
    _github: object = field(default=None, repr=False)  # what the GitHub lines read, read once

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
    err: str = ""  # the last line it printed on stderr, when asked for


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
        return Ran("failed")
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
        return Ran("failed", err=said[-1][:300] if said else f"exit {p.returncode}")
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


def _shown(value: str, most: int = 40) -> str:
    """A value someone gave, safe on one line in a code span."""
    v = " ".join(value.replace("`", "'").split())
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


def _read_value(root: Path, rel: str | Path):
    """A JSON file's value, and why it can't be read: (None, None) when it is
    missing. Never raises, and never blocks on a pipe."""
    path, err = _file(root, rel)
    if err:
        return None, err
    try:
        if not path.exists():
            return None, None
        return json.loads(path.read_text(encoding="utf-8").removeprefix("\ufeff")), None
    except UnicodeDecodeError:
        return None, "it isn't UTF-8 text"
    except json.JSONDecodeError as e:
        return None, f"it isn't valid JSON ({e.msg}, line {e.lineno})"
    except (OSError, ValueError, RecursionError) as e:
        return None, f"it can't be read ({type(e).__name__})"


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

GH_TIMEOUT = 30  # seconds, for each `gh api` call
# Where GitHub looks for CODEOWNERS, in its order: the first one found is used.
CODEOWNERS_PLACES = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
# What CODEOWNERS should cover (docs/enforcement.md §3).
OWNED = ("/.claude/", "/.github/workflows/")
# How `gh` says it isn't signed in.
_SIGNED_OUT = re.compile(r"gh auth login|GH_TOKEN|not logged in|authentication required|HTTP 401", re.I)
# A protection kind the read-back reports, as a line: (id, the kind's words).
_KIND_LINES = {
    "not_on_base": "github.protection.base", "unsure": "github.protection.base", "not_active": "github.protection.active",
    "bypass": "github.protection.bypass", "deletion": "github.protection.deletions",
    "non_fast_forward": "github.protection.force_pushes", "pull_request": "github.protection.pull_requests",
}
# Each kind in a few plain words, for the main line's list.
_KIND_SHORT = {
    "no_rulesets": "it has no ruleset", "not_on_base": "a ruleset doesn't cover it", "unsure": "a ruleset doesn't cover it",
    "not_active": "a ruleset is turned off", "bypass": "someone may skip the rules", "deletion": "it can be deleted",
    "non_fast_forward": "it can be force-pushed", "pull_request": "pull requests aren't required",
}


@dataclass
class _Answer:
    """One of GitHub's answers: its value, or why it couldn't be read (in
    both wordings) and how to read it."""

    value: object = None
    why: Words | None = None
    fix: Words = NONE


@dataclass
class _GitHub:
    """What the GitHub lines read: the base branch, the read-back (or why
    not), and the merge settings (or why not)."""

    base: str
    report: object = None  # protection.Report
    report_why: _Answer | None = None
    merge: dict | None = None
    merge_why: _Answer | None = None


def _sign_in(missing: bool) -> Words:
    return Words(
        ("Install GitHub's command-line tool (`gh`, from cli.github.com) and sign in with `gh auth login`"
         if missing else "Sign in with `gh` (run `gh auth login` in a terminal)") + ", or ask a cloud session to check the set-up.",
        ("Install gh and run `gh auth login`" if missing else "Run `gh auth login`")
        + ", or give --rulesets and --repo files (GET repos/<repo>/rulesets/<id> each in full, GET repos/<repo>); or ask a cloud session to check the set-up.",
    )


def _gh(i: Inputs, path: str, paginate: bool = False) -> _Answer:
    """`gh api <path>`'s JSON (with `paginate`, the pages as a list), read
    with a GET and nothing else."""
    ran = _run(i, ["gh", "api", *(["--paginate"] if paginate else []), path], timeout=GH_TIMEOUT, stderr=True)
    if ran.state == "missing":
        return _Answer(why=Words("GitHub's command-line tool (`gh`) isn't installed here", "no `gh` on the PATH, and no file given"), fix=_sign_in(True))
    if ran.state == "failed" and _SIGNED_OUT.search(ran.err):
        return _Answer(why=Words("`gh` isn't signed in to GitHub", f"`gh api` isn't signed in ({_shown(ran.err, 120)})"), fix=_sign_in(False))
    if ran.state != "ok":
        said = {"failed": _shown(ran.err, 120), "timeout": f"no answer within {GH_TIMEOUT} s", "unreadable": "its answer isn't UTF-8 text"}[ran.state]
        return _Answer(why=Words(f"GitHub didn't answer `gh` ({said})", f"`gh api {path.split('?')[0]}` failed: {said}"), fix=_sign_in(False))
    try:
        values = posts_mod.decode_values(ran.out)
    except posts_mod.CommentsError as e:
        values, bad = [], str(e)
    else:
        bad = None if values else "it printed nothing"
    if bad:
        return _Answer(why=Words("GitHub's answer to `gh` couldn't be read", f"`gh api {path.split('?')[0]}`'s output isn't JSON ({bad})"), fix=_sign_in(False))
    return _Answer(values if paginate else values[0])


def _given(i: Inputs, path: Path, flag: str) -> _Answer:
    """A file given on the command line, read as doctor reads files."""
    shown = _home(i, path)
    fix = Words(
        f"Ask Claude to fetch it from GitHub again (as `workflow protection` takes it), or leave out {flag} to read GitHub with `gh`.",
        f"Give {flag} as `workflow protection` takes it, or leave it out to use `gh api`.",
    )
    value, err = _read_value(i.root, path)
    if err is None and value is None:
        err = "it isn't there"
    if err:
        return _Answer(why=Words(f"the {flag} file ({shown}) can't be read: {err}", f"{flag} {shown}: {err}"), fix=fix)
    return _Answer(value)


def _rulesets(i: Inputs, repo: str) -> _Answer:
    """The rulesets, each in full: from --rulesets, else the list (pages of
    summaries) and then each one through `gh api`."""
    if i.rulesets_file is not None:
        return _given(i, i.rulesets_file, "--rulesets")
    listed = _gh(i, f"repos/{repo}/rulesets?includes_parents=true&per_page=100", paginate=True)
    if listed.why:
        return listed
    flat = [x for page in listed.value for x in (page if isinstance(page, list) else [page])]
    ids = [x.get("id") if isinstance(x, dict) else None for x in flat]
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in ids):
        return _Answer(why=Words("GitHub's list of rulesets couldn't be read", "`gh api`'s list of rulesets has an entry without an id"), fix=_sign_in(False))
    full = []
    for n in ids:
        one = _gh(i, f"repos/{repo}/rulesets/{n}")
        if one.why:
            return one
        full.append(one.value)
    return _Answer(full)


def _not_github(e: Exception, what: str) -> _Answer:
    return _Answer(why=Words(f"{what} isn't in the shape the kit reads ({e})", f"{what}: {e}"), fix=Words(
        f"Ask Claude to fetch {what} from GitHub again, each ruleset in full, as `workflow protection` takes it.",
        "Pass GitHub's JSON as `workflow protection` takes it (GET repos/<repo>/rulesets/<id> each in full, GET repos/<repo>).",
    ))


def _github(i: Inputs) -> _GitHub | None:
    """GitHub's answers and the read-back, once for every line; None with no
    readable profile (the lines then wait on it)."""
    if i.profile is None:
        return None
    if i._github is None:
        from . import protection as protection_mod

        base, repo = i.profile.base_branch, i.profile.repo
        gh = _GitHub(base)
        settings = _given(i, i.repo_file, "--repo") if i.repo_file is not None else _gh(i, f"repos/{repo}")
        good_settings = None
        if settings.why:
            gh.merge_why = settings
        else:
            try:
                gh.merge = protection_mod.check([], base, settings.value).merge
                good_settings = settings.value
            except protection_mod.ProtectionError as e:
                gh.merge_why = _not_github(e, "the repository's settings")
        rulesets = _rulesets(i, repo)
        if rulesets.why:
            gh.report_why = rulesets
        else:
            try:
                gh.report = protection_mod.check(rulesets.value, base, good_settings)
            except protection_mod.ProtectionError as e:
                gh.report_why = _not_github(e, "the rulesets")
        i._github = gh
    return i._github


def _waits(i: Inputs, id_: str, what: Words, answer: _Answer | None) -> Line:
    """A line that can't be checked: GitHub's answer couldn't be read, or
    (`answer` None) the profile couldn't."""
    if answer is None:
        why = Words("the kit's profile can't be read", "no readable profile (project.repo, project.base_branch)")
        fix = PROFILE_FIRST if i.profile_error else SET_UP_FIRST
    else:
        why, fix = answer.why, answer.fix
    return Line("GitHub", id_, "cant_check", Words(f"Can't check {what.new}: {_relative(i, why.new)}.", f"{what.developer} unchecked: {_relative(i, why.developer)}."), fix)


def _protection_waits(i: Inputs, id_: str, what: Words) -> Line | None:
    gh = _github(i)
    if gh is None or gh.report is None:
        return _waits(i, id_, what, gh.report_why if gh else None)
    return None


def _solo_unprotected(i: Inputs) -> bool:
    gh = _github(i)
    return i.profile.ruleset is False and not gh.report.protected


def _rules(i: Inputs, type_: str) -> list[dict]:
    """The rules of this type in the active rulesets on the base branch,
    each one's parameters (an object, empty when it has none)."""
    out = []
    for rs in _github(i).report.effective:
        for r in rs["rules"]:
            if r["type"] == type_:
                out.append(r.get("parameters") or {})
    return out


def _n(count: int, one: str, many: str) -> str:
    return one if count == 1 else f"{count} {many}"


def _upper(text: str) -> str:
    return text[:1].upper() + text[1:]


@_check("GitHub", "github.ruleset")
def check_protection(i: Inputs) -> list[Line]:
    """Whether the base branch is protected, by the read-back, against the
    profile's `project.ruleset`; each missing protection its own gap."""
    g, id_ = "GitHub", "github.ruleset"
    wait = _protection_waits(i, id_, Words("whether the main branch is protected on GitHub", "The base branch's protection"))
    if wait:
        return [wait]
    base, rep, ruleset = i.profile.base_branch, _github(i).report, i.profile.ruleset
    protect, restore = OFFERS["protect_main"], OFFERS["restore_protection"]
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
    plain = ", ".join(dict.fromkeys(_KIND_SHORT[k] for k in rep.kinds))
    found = "; ".join(rep.missing)
    if ruleset is False:
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't protect `{base}` ({plain}), chosen on purpose; while you work with Claude, the kit's guard keeps changes off `{base}`.",
            f"Solo mode (project.ruleset = false): `{base}` isn't protected, as expected: {found}.",
        ), Words(
            f"When you want GitHub to protect `{base}` too, ask Claude to \"{protect}\".",
            f"Run upgrade-setup's \"{protect}\" for the ruleset.",
        ), offer="protect_main")]
    if ruleset is True:
        main = Line(g, id_, "gap", Words(
            f"The kit's profile says GitHub protects `{base}`, but it doesn't any more ({plain}): protection that was removed or weakened is never trusted.",
            f"Removed protection: project.ruleset = true, but the read-back finds `{base}` unprotected: {found}.",
        ), Words(
            f"Ask Claude to \"{restore}\": it puts the ruleset back.",
            f"Run upgrade-setup's \"{restore}\" (`restore_protection`), then read it back with `workflow protection`.",
        ), offer="restore_protection")
        offer = restore
    else:
        main = Line(g, id_, "gap", Words(
            f"GitHub doesn't protect `{base}` ({plain}), so a change could reach it without a pull request, or its history could be lost.",
            f"`workflow protection`: `{base}` isn't protected: {found}.",
        ), Words(
            f"Ask Claude to \"{protect}\".",
            f"Run upgrade-setup's \"{protect}\", or set the ruleset up by hand (docs/enforcement.md §1).",
        ), offer="protect_main")
        offer = protect
    return [main] + _missing_lines(rep, base, offer)


def _missing_lines(rep, base: str, offer: str) -> list[Line]:
    """Each kind of missing protection the read-back found, as its own gap,
    in plain words and with the read-back's own words for a developer."""
    by_line: dict[str, list[tuple[str, str]]] = {}
    for kind, words in zip(rep.kinds, rep.missing):
        if kind in _KIND_LINES:
            by_line.setdefault(_KIND_LINES[kind], []).append((kind, words))
    fix_new = Words(f"Ask Claude to \"{offer}\": it puts this right.", "")
    out = []
    for id_, found in by_line.items():
        kinds = [k for k, _ in found]
        n = len(found)
        if id_ == "github.protection.active":
            evaluating = sum("evaluate only" in w for _, w in found)
            parts = ([f"{_n(n - evaluating, 'a ruleset', 'rulesets')} that would protect `{base}` {'is' if n - evaluating == 1 else 'are'} turned off"] if n - evaluating else []) + (
                [f"{_n(evaluating, 'a ruleset', 'rulesets')} only {'reports' if evaluating == 1 else 'report'}, without blocking anything"] if evaluating else [])
            new = _upper("; ".join(parts)) + "."
            dev_fix = "Set the ruleset's enforcement to active."
        elif id_ == "github.protection.base":
            unsure = "unsure" in kinds
            new = (f"{_upper(_n(n, 'a ruleset', 'rulesets'))} on GitHub {'doesn' if n == 1 else 'don'}'t cover `{base}`"
                   + (", as far as GitHub's answer shows" if unsure else ": it applies to other branches") + ", so its rules don't protect it.")
            dev_fix = f"Make the ruleset include `~DEFAULT_BRANCH` or `refs/heads/{base}`, and not exclude it (give --repo for `~DEFAULT_BRANCH`)."
        elif id_ == "github.protection.bypass":
            unread = any("can't be read" in w for _, w in found)
            new = (f"People or apps on a ruleset's bypass list can skip its rules on `{base}`." if not unread else
                   f"Who may skip the ruleset's rules on `{base}` can't be seen (that needs admin access on GitHub), so it can't count as protecting it.")
            dev_fix = "Empty the ruleset's bypass list (reading it needs admin access)."
        elif id_ == "github.protection.deletions":
            new = f"`{base}` can be deleted on GitHub: no active ruleset stops it."
            dev_fix = f"Add a `deletion` rule (Restrict deletions) to an active ruleset on `{base}`."
        elif id_ == "github.protection.force_pushes":
            new = f"Someone could force push to `{base}`, rewriting its history: no active ruleset stops it."
            dev_fix = f"Add a `non_fast_forward` rule (Block force pushes) to an active ruleset on `{base}`."
        else:
            new = f"Changes can reach `{base}` without a pull request: no active ruleset requires one."
            dev_fix = f"Add a `pull_request` rule (Require a pull request before merging) to an active ruleset on `{base}`."
        out.append(Line("GitHub", id_, "gap", Words(new, "; ".join(w for _, w in found) + "."), Words(fix_new.new, dev_fix)))
    return out


@_check("GitHub", "github.required_checks")
def check_required_checks(i: Inputs) -> list[Line]:
    """The profile's `ci.required_checks` that the ruleset doesn't require.
    A check it requires that the profile doesn't list isn't a line here (#38's
    tickets add that note, and #69 the `require_checks` offer on this line)."""
    g, id_ = "GitHub", "github.required_checks"
    if i.profile is None:
        return [_waits(i, id_, Words("which checks GitHub requires", "Required checks"), None)]
    base, listed = i.profile.base_branch, list(i.profile.required_checks)
    upgrade = "Require these checks"
    if not listed:
        return [Line(g, id_, "note", Words(
            f"Checks not required yet: the kit's profile lists no checks that must pass before a pull request merges into `{base}`.",
            "ci.required_checks is empty: checks not required yet.",
        ), Words(
            f"Once your project's checks have run on `{base}`, ask Claude to \"{upgrade}\".",
            f"After CI has run on `{base}`, run upgrade-setup's \"{upgrade}\".",
        ))]
    wait = _protection_waits(i, id_, Words("whether GitHub requires the checks the kit's profile lists", "ci.required_checks against the ruleset"))
    if wait:
        return [wait]
    names = ", ".join(f"`{_shown(c)}`" for c in listed)
    if _solo_unprotected(i):
        return [Line(g, id_, "note", Words(
            f"Solo mode: GitHub doesn't require the checks the kit's profile lists ({names}), since nothing protects `{base}` there yet.",
            f"Solo mode: no ruleset on `{base}` requires ci.required_checks ({names}).",
        ), Words(
            f"They're required when you ask Claude to \"{OFFERS['protect_main']}\".",
            f"\"{OFFERS['protect_main']}\" adds them to the ruleset it creates.",
        ))]
    have = _github(i).report.required_checks
    missing = [c for c in listed if c not in have]
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
    approvals, Code Owners review and linear history (docs/enforcement.md §1)."""
    g = "GitHub"
    whats = {
        "github.up_to_date": Words("whether pull requests must be up to date with the main branch", "\"Require branches to be up to date\""),
        "github.approvals": Words("how many approvals GitHub requires", "Required approvals"),
        "github.code_owner_review": Words("whether GitHub requires a review from the code owners", "\"Require review from Code Owners\""),
        "github.linear_history": Words("whether GitHub requires a straight-line history", "The linear-history rule"),
    }
    waits = [_protection_waits(i, id_, what) for id_, what in whats.items()]
    if any(waits):
        return [w for w in waits if w]
    if _solo_unprotected(i):
        return []  # nothing protects the base branch, as chosen: the ruleset line says so
    base = i.profile.base_branch
    lines = []
    strict = [p.get("strict_required_status_checks_policy") is True for p in _rules(i, "required_status_checks")]
    if not strict:
        lines.append(Line(g, "github.up_to_date", "note", Words(
            f"\"Require branches to be up to date\" comes with the required checks, and no ruleset on `{base}` requires checks yet.",
            f"No required_status_checks rule on `{base}`, so no strict_required_status_checks_policy.",
        ), Words(
            "It's turned on with the checks, when you ask Claude to \"Require these checks\".",
            "\"Require these checks\" adds the rule with strict_required_status_checks_policy = true.",
        )))
    elif not any(strict):
        lines.append(Line(g, "github.up_to_date", "gap", Words(
            f"GitHub lets a pull request merge without being up to date with `{base}`, so two changes that each pass alone can break `{base}` together.",
            f"strict_required_status_checks_policy is false on `{base}` (\"Require branches to be up to date\" off).",
        ), Words(
            "Ask Claude to turn on \"Require branches to be up to date\" in the ruleset (it shows you where to click).",
            "Set strict_required_status_checks_policy = true in the ruleset's required_status_checks rule.",
        )))
    else:
        lines.append(Line(g, "github.up_to_date", "fine", Words(
            f"Pull requests must be up to date with `{base}` before they merge.",
            f"strict_required_status_checks_policy is true on `{base}`.",
        )))
    prs = _rules(i, "pull_request")
    counts = [p.get("required_approving_review_count") for p in prs]
    most = max((c for c in counts if isinstance(c, int) and not isinstance(c, bool)), default=0)
    if most > 0:
        lines.append(Line(g, "github.approvals", "note", Words(
            f"GitHub needs {_n(most, 'an approving review', 'approving reviews')} before a pull request merges into `{base}`, so unattended runs will stop at \"ready for review\" and wait for you.",
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
    if _rules(i, "required_linear_history"):
        lines.append(Line(g, "github.linear_history", "gap", Words(
            f"GitHub requires a straight-line history on `{base}`, which refuses the merge commits the kit merges with.",
            f"A required_linear_history rule is active on `{base}`: merge commits are refused.",
        ), Words(
            "Ask Claude to turn off \"Require linear history\" in the ruleset.",
            "Remove the required_linear_history rule.",
        )))
    else:
        lines.append(Line(g, "github.linear_history", "fine", Words(
            f"GitHub accepts merge commits on `{base}` (no straight-line history rule).",
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
                "Rerun with an admin's `gh`, or pass --repo from an admin's GET repos/<repo>.",
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
                ("When you leave solo mode, " if solo else "") + "ask Claude to turn on \"Allow auto-merge\" (Settings → General → Pull Requests).",
                "Set allow_auto_merge = true" + (" when leaving solo mode." if solo else " (PATCH repos/<repo>, or upgrade-setup's \"Protect `main`\")."),
            )))
    return lines


def _codeowners_pattern(pat: str) -> re.Pattern | None:
    """A CODEOWNERS pattern as a regex over a file's path (gitignore's rules,
    as GitHub reads them): None when it can't be read."""
    dir_only = pat.endswith("/")
    body = pat.rstrip("/")
    anchored = body.startswith("/") or "/" in body
    body = body.lstrip("/")
    if not body:
        return None
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
    return re.compile(("" if anchored else "(?:.*/)?") + out + ("/.*" if dir_only else "(?:/.*)?"))


def _codeowners_rules(text: str) -> list[tuple[re.Pattern | None, bool]]:
    """(pattern, has owners) for each rule, in order."""
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
        rules.append((_codeowners_pattern(tokens[0]), bool(owners)))
    return rules


def _owned(rules, path: str) -> bool:
    """Whether the last rule that matches the path names an owner."""
    last = None
    for pattern, owners in rules:
        if pattern is not None and pattern.fullmatch(path):
            last = owners
    return bool(last)


@_check("GitHub", "github.codeowners")
def check_codeowners(i: Inputs) -> list[Line]:
    """CODEOWNERS, read from the checkout (the first of the places GitHub
    looks), names an owner for the kit and CI: every file under `/.claude/`
    and `/.github/workflows/`."""
    g, id_ = "GitHub", "github.codeowners"
    if not i.root.is_dir():
        return []  # kit.profile says the folder isn't there
    where = None
    for rel in CODEOWNERS_PLACES:
        path, err = _file(i.root, rel)
        try:
            there = path.exists()
        except OSError:
            there = True
        if err or there:
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
            f"No CODEOWNERS ({', '.join(CODEOWNERS_PLACES)}): {owned} unowned.",
        ), fix)]
    path, err = _file(i.root, where)
    text = None
    if not err:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            err = "it isn't UTF-8 text"
        except (OSError, ValueError) as e:
            err = f"it can't be read ({type(e).__name__})"
    if err:
        return [Line(g, id_, "gap", Words(
            f"GitHub's CODEOWNERS file ({where}) can't be read ({err}), so it can't ask you to review changes to the kit and CI.",
            f"{where}: {err}.",
        ), fix)]
    rules = _codeowners_rules(text)
    missing = [p for p in OWNED if not all(_owned(rules, p.strip("/") + probe) for probe in ("/doctor-probe", "/doctor-probe/doctor-probe"))]
    if missing:
        shown = ", ".join(f"`{p}`" for p in missing)
        return [Line(g, id_, "gap", Words(
            f"CODEOWNERS ({where}) doesn't name an owner for all of {shown}, so GitHub doesn't ask you to review every change there.",
            f"{where} leaves part or all of {shown} without an owner (the last matching rule names none).",
        ), fix)]
    return [Line(g, id_, "fine", Words(
        f"CODEOWNERS ({where}) asks you to review changes to the kit and CI ({owned}).",
        f"{where} owns {owned}.",
    ))]


# Every check, in the order its lines show when they are equally serious: the
# profile first, since setting the kit up comes before anything it then checks.
CHECKS = [check_python, check_claude_code, check_profile, check_install, check_vendor, check_experience, check_ruleset,
          check_protection, check_required_checks, check_ruleset_rules, check_merge_settings, check_codeowners]


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


def _first(ln: Line) -> bool:
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
        g.sort(key=lambda ln: (not _first(ln), _rank(ln.status)))  # stable: check order within a status
    names = sorted(groups, key=lambda g: (not any(_first(ln) for ln in groups[g]), min(_rank(ln.status) for ln in groups[g]), GROUPS.index(g)))
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
            out.append(f"      Claude can offer: {OFFERS[ln.offer]}")
    return "\n".join(out)

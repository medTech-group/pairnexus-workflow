"""`workflow doctor`: one report of what's set up and what isn't (#34).

Each check is a function from what doctor was given (`Inputs`) to report
lines (`Line`). A line has a group, an id, a status, a message and a fix in
both wordings, and optionally an offer (an upgrade #32 builds). The report
picks one wording by experience (#16: what is checked, and each status, never
depend on it), puts the most serious line first and groups the rest.

Doctor never changes anything (#27): it reads files and runs `python3` and
`claude --version`, nothing else. A check that fails unexpectedly becomes a
`cant_check` line, never a traceback: doctor is advice, and exits 0.

**Adding a group or a check** (the GitHub, Cloud and Previews tickets): write
a function `def check_x(i: Inputs) -> list[Line]`, decorate it with
`@_check(<group>, <id of its main line>)` (the line it falls back to if it
raises), add it to `CHECKS`, and put anything it reads on `Inputs` (filled in
by `cli.cmd_doctor`). The groups are in `GROUPS` already; the order, the
counts, the text, the JSON and `--strict` follow without change.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

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
# before it isn't taken for it.
_VERSION = re.compile(r"^\s*v?([0-9]+)\.([0-9]+)\.([0-9]+)", re.M)
# What each of the kit's hooks is called in a report.
HOOK_NAMES = {"PreToolUse": "the guard", "Stop": "the status gate", "UserPromptSubmit": "the flow context", "SessionStart": "the session start"}
SETTINGS = vendor_mod.SETTINGS.as_posix()
SETTINGS_LOCAL = vendor_mod.SETTINGS_LOCAL.as_posix()
PROFILE = profile_mod.PROFILE_PATH.as_posix()
LOCK = vendor_mod.LOCK.as_posix()


@dataclass(frozen=True)
class Words:
    """A message or fix in both wordings: for someone new to building, and
    for a developer."""

    new: str
    developer: str

    def pick(self, level: str) -> str:
        return self.developer if level == "developer" else self.new


NONE = Words("", "")


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
    session hands it. Nothing here is fetched over the network."""

    root: Path
    kit_root: Path
    profile: Profile | None
    profile_error: str | None  # `profile check`'s error; None with no profile, or a good one
    experience: Experience
    claude_version: str | None = None  # --claude-version, which wins over `claude --version`
    environ: dict = field(default_factory=lambda: dict(os.environ))

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


def _run(i: Inputs, argv: list[str]) -> tuple[str | None, bool]:
    """(a command's standard output, whether it timed out); the output is
    None when the command is missing, fails or hangs. No shell, no input; on
    a timeout its whole process group is killed, so nothing is left running."""
    exe = shutil.which(argv[0], path=i.path)
    if not exe:
        return None, False
    try:
        p = subprocess.Popen([exe, *argv[1:]], cwd=i.root if i.root.is_dir() else None, env=i.environ,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except (OSError, ValueError):
        return None, False
    try:
        out, _ = p.communicate(timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            p.kill()
        p.communicate()
        return None, True
    if p.returncode:
        return None, False
    try:
        return out.decode("utf-8"), False
    except UnicodeDecodeError:
        return None, False


def _version(text: str | None) -> tuple[int, int, int] | None:
    m = _VERSION.search(text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _dotted(v) -> str:
    return ".".join(str(x) for x in v)


def _shown(value: str, most: int = 40) -> str:
    """A value someone gave, safe on one line in a code span."""
    v = " ".join(value.replace("`", "'").split())
    return v if len(v) <= most else v[:most] + "…"


def _read_json(root: Path, rel: str | Path) -> tuple[dict, str | None]:
    """A JSON object file's contents, and why it can't be read: ({}, None)
    when it is missing. Never raises, and never blocks on a pipe."""
    path = Path(rel) if Path(rel).is_absolute() else root / rel
    try:
        if not path.exists():
            return {}, None
        if not path.is_file():
            return {}, "it isn't a file"
        data = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return {}, "it isn't UTF-8 text"
    except json.JSONDecodeError as e:
        return {}, f"it isn't valid JSON ({e.msg}, line {e.lineno})"
    except (OSError, ValueError) as e:
        return {}, f"it can't be read ({type(e).__name__})"
    if not isinstance(data, dict):
        return {}, "it doesn't hold a JSON object"
    return data, None


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
    """`python3` on the PATH, the one the hooks run, not the Python running doctor."""
    g, id_ = "Your computer", "computer.python3"
    need = _dotted(PYTHON_MIN)
    install = Words(
        f"Install Python {need} or newer (from python.org, or `brew install python` on a Mac), then open a new terminal and start a new Claude session.",
        f"Put Python {need}+ first on the PATH as `python3`, then start a new session.",
    )
    if not shutil.which("python3", path=i.path):
        return [Line(g, id_, "gap", Words(
            "Python (`python3`) isn't installed, or your computer can't find it, so the kit's hooks can't run.",
            f"No `python3` on the PATH: the kit's hooks can't run it (they need {need}+).",
        ), install)]
    out, timed_out = _run(i, ["python3", "-I", "-c", "import sys; print('%d.%d.%d' % tuple(sys.version_info[:3]))"])
    v = _version(out)
    if v is None:
        why = Words(f"it didn't answer within {RUN_TIMEOUT} seconds", f"timed out after {RUN_TIMEOUT} s") if timed_out else Words("it didn't answer", "failed, or printed no version")
        return [Line(g, id_, "cant_check", Words(
            f"Couldn't tell which version of Python (`python3`) your computer has: {why.new}.",
            f"`python3` on the PATH {why.developer}.",
        ), Words(
            f"Run `python3 --version` in a terminal: it should say {need} or newer.",
            f"Check `python3 --version` ({need}+ needed) and that it runs.",
        ))]
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
    timed_out = False
    if given:
        v = _version(i.claude_version)
    else:
        out, timed_out = _run(i, ["claude", "--version"])
        v = _version(out)
    if v is None:
        if given:
            where = f"`--claude-version {_shown(i.claude_version)}` holds no version"
        elif timed_out:
            where = f"no `--claude-version`, and `claude --version` timed out after {RUN_TIMEOUT} s"
        else:
            where = "no `--claude-version`, and `claude --version` gave none"
        return [Line(g, id_, "cant_check", Words(
            "Couldn't tell which version of Claude Code you have.",
            f"Claude Code's version is unknown ({where}).",
        ), Words(
            f"Type `/status` in Claude Code, or run `claude --version` in a terminal: the version should be {need} or newer.",
            f"Run `claude --version` ({need}+ needed), or pass `--claude-version`.",
        ))]
    if v < CLAUDE_CODE_MIN:
        return [Line(g, id_, "gap", Words(
            f"Claude Code is version {_dotted(v)}, older than {need}: if the kit's guard ever fails or takes too long, this version lets the step run instead of stopping it.",
            f"Claude Code {_dotted(v)} is older than {need}: a guard hook that fails or times out won't block (`onFailure: \"block\"` is ignored).",
        ), Words(
            "Update Claude Code (run `claude update` in a terminal, or update the desktop app), then start a new session.",
            f"Run `claude update` ({need}+), then restart the session.",
        ))]
    return [Line(g, id_, "fine", Words(
        f"Claude Code is new enough (version {_dotted(v)}).",
        f"Claude Code {_dotted(v)} ({need}+ needed).",
    ))]


# ---------- The kit ----------


def _user_settings(i: Inputs) -> tuple[str, Path | None]:
    """The user's settings file: its name in a report, and its path (None
    when there is no home directory to find it in)."""
    if i.environ.get("CLAUDE_CONFIG_DIR"):
        p = Path(i.environ["CLAUDE_CONFIG_DIR"]) / "settings.json"
        return str(p), p
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

    def plugin(self) -> tuple[bool, str | None]:
        """Whether the kit's plugin is enabled, and which file says so: the
        most specific file naming it wins (local, then project, then user)."""
        on, where = False, None
        for name, data, _ in self.files:
            plugins = data.get("enabledPlugins")
            if isinstance(plugins, dict) and vendor_mod.PLUGIN_KEY in plugins:
                on, where = bool(plugins[vendor_mod.PLUGIN_KEY]), name
        return on, where

    def hooks_off(self) -> list[str]:
        """The files with `disableAllHooks` on: Claude Code then runs no hook."""
        return [name for name, data, _ in self.files if data.get("disableAllHooks")]


def _settings(i: Inputs) -> _Settings:
    user_name, user_path = _user_settings(i)
    files = [(user_name, *(_read_json(i.root, user_path) if user_path else ({}, None)))]
    for rel in (SETTINGS, SETTINGS_LOCAL):
        files.append((rel, *_read_json(i.root, rel)))
    return _Settings(files)


def _list(v) -> list:
    return v if isinstance(v, list) else []


def _is_kit(h) -> bool:
    return isinstance(h, dict) and vendor_mod._is_kit_hook(h)


def _hook_differences(settings: dict) -> list[str]:
    """How the kit's hooks in the settings differ from this kit version's own
    entries, as `vendor update` writes them: one phrase each."""
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    out = []
    for event in [*vendor_mod.KIT_HOOKS, *sorted(set(hooks) - set(vendor_mod.KIT_HOOKS))]:
        entries = [e for e in _list(hooks.get(event)) if isinstance(e, dict)]
        kit = [e for e in entries if any(_is_kit(h) for h in _list(e.get("hooks")))]
        want = vendor_mod.KIT_HOOKS.get(event)
        name = HOOK_NAMES.get(event, f"a hook on {event} that runs the kit")
        if want is None:
            if kit:
                out.append(f"{name} isn't one this version writes")
        elif not kit:
            out.append(f"{name} ({event}) is missing")
        elif any(not all(_is_kit(h) for h in _list(e.get("hooks"))) for e in kit):
            out.append(f"{name} ({event}) shares an entry with other hooks")
        elif kit != want:
            out.append(f"{name} ({event}) differs")
    return out


def _running_copy(i: Inputs) -> bool:
    """Whether the kit running doctor is this project's vendored copy."""
    copy = (i.root / ".claude/workflow").resolve()
    here = i.kit_root.resolve()
    return here == copy or copy in here.parents


def _kit_version(i: Inputs) -> str:
    """The version of the kit running doctor: the lock's for the project's
    vendored copy, else the kit's own VERSION (a checkout of it, the plugin)."""
    if _running_copy(i):
        return updates_mod.installed(i.root, i.kit_root) or "unknown"
    try:
        v = (i.kit_root / "VERSION").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return "unknown"
    return v if updates_mod.parse(v) else "unknown"


@_check("The kit", "kit.hooks")
def check_install(i: Inputs) -> list[Line]:
    """Claude Code's settings files are readable and run hooks at all; then,
    vendored, the hooks are this version's own entries; in plugin mode the
    plugin is enabled; both on is a gap naming which to turn off."""
    g = "The kit"
    s = _settings(i)
    lines: list[Line] = []
    bad = s.unreadable()
    if bad:
        listed = "; ".join(f"{name}: {why}" for name, why in bad)
        lines.append(Line(g, "kit.settings", "gap", Words(
            f"Claude Code can't read its settings ({listed}), so the kit's hooks may not run.",
            f"Unreadable Claude Code settings: {listed}.",
        ), Words(
            "Ask Claude to fix the file so it is valid JSON (saved as UTF-8), then start a new session.",
            "Make each a UTF-8 JSON object, then restart the session.",
        )))
    off = s.hooks_off()
    if off:
        lines.append(Line(g, "kit.hooks_off", "gap", Words(
            f"Every hook is turned off ({', '.join(off)} sets `disableAllHooks`), so the kit's guard doesn't run at all.",
            f"`disableAllHooks` is on in {', '.join(off)}: no hook runs, the guard included.",
        ), Words(
            f"Remove `\"disableAllHooks\": true` from {', '.join(off)}, then start a new session.",
            f"Drop `disableAllHooks` from {', '.join(off)}.",
        )))
    on, where = s.plugin()
    if i.vendored:
        lines += _vendored_hooks(i, s)
        if on:
            local = where if where in (SETTINGS, SETTINGS_LOCAL) else SETTINGS_LOCAL
            key = f'`"enabledPlugins": {{"{vendor_mod.PLUGIN_KEY}": false}}`'
            lines.append(Line(g, "kit.plugin", "gap", Words(
                f"The kit is on twice here: copied into this project and installed as a plugin (turned on in {where}), so its hooks run twice.",
                f"Both modes are on: the kit is vendored and the {vendor_mod.PLUGIN_KEY} plugin is enabled ({where}); the hooks run twice.",
            ), Words(
                f"Turn the plugin off for this project and keep the copy, which unattended runs need: put {key} in {local}.",
                f"Turn off the plugin, keep the vendored copy (runs need it): set {key} in {local}.",
            )))
        return lines
    if on:
        return lines + [Line(g, "kit.plugin", "fine", Words(
            "The kit's plugin is turned on for this project.",
            f"Plugin mode: {vendor_mod.PLUGIN_KEY} is enabled ({where}).",
        ))]
    if bad:
        return lines + [Line(g, "kit.plugin", "cant_check", Words(
            "Can't tell whether the kit's plugin is turned on until Claude Code's settings can be read.",
            "Plugin mode: whether the plugin is enabled can't be told until the settings read.",
        ), Words(
            "Fix the settings file first (see the settings line).",
            "Fix the unreadable settings first (kit.settings).",
        ))]
    where_off = f" (turned off in {where})" if where else ""
    return lines + [Line(g, "kit.plugin", "gap", Words(
        f"The kit's plugin isn't turned on for this project{where_off}, and there's no copy of the kit in it, so its hooks don't run here.",
        f"Plugin mode (no {LOCK}), but {vendor_mod.PLUGIN_KEY} isn't enabled" + (f": {where} turns it off." if where else " in the user's or the project's settings."),
    ), Words(
        f"In Claude Code, type `/plugin install {vendor_mod.PLUGIN_KEY}` (or turn it on in `/plugin`), then start a new session.",
        f"`/plugin install {vendor_mod.PLUGIN_KEY}`, or enable it in `enabledPlugins`.",
    ))]


def _vendored_hooks(i: Inputs, s: _Settings) -> list[Line]:
    g, id_ = "The kit", "kit.hooks"
    data, err = s.project()
    if err:
        return [Line(g, id_, "cant_check", Words(
            f"Can't check the kit's hooks until Claude Code's settings file ({SETTINGS}) can be read.",
            f"Kit hooks unchecked: {SETTINGS} doesn't read.",
        ), Words(
            "Fix the settings file first (see the settings line).",
            "Fix the settings first (kit.settings).",
        ))]
    diffs = _hook_differences(data)
    version = _kit_version(i)
    if not diffs:
        return [Line(g, id_, "fine", Words(
            "The kit's hooks are in place, as this version of the kit writes them.",
            f"Kit hooks in {SETTINGS} match kit {version}'s entries.",
        ))]
    listed = "; ".join(diffs)
    if not _running_copy(i):
        # Another kit's entries (a checkout of the kit, the plugin): only the
        # project's own copy knows the entries its version writes.
        copy = updates_mod.installed(i.root, i.kit_root) or "unknown"
        return [Line(g, id_, "cant_check", Words(
            f"The kit's hooks differ from those of the kit running this check ({listed}), but that isn't this project's own copy of the kit, so it can't say which is right.",
            f"Kit hooks compared with kit {version} (running doctor), not this project's copy ({copy}): {listed}.",
        ), Words(
            "Run the check with the project's own copy: `python3 -B .claude/workflow/bin/workflow.py doctor`.",
            "Run the vendored copy's doctor: `python3 -B .claude/workflow/bin/workflow.py doctor`.",
        ))]
    return [Line(g, id_, "gap", Words(
        f"The kit's hooks in {SETTINGS} aren't the ones this version of the kit writes ({listed}), so some of its checks may not run as they should.",
        f"Kit hooks in {SETTINGS} differ from kit {version}'s entries: {listed}.",
    ), Words(
        "Ask Claude to update the workflow kit: the update writes the kit's hooks again.",
        "Rerun the kit's update (`update-workflow`, which runs `vendor update`) to rewrite its entries; it also drops any project hook whose command calls the kit's CLI.",
    ))]


def _relative(i: Inputs, text: str) -> str:
    """An error message with the checkout's own path left out."""
    return text.replace(str(i.root) + os.sep, "").replace(str(i.root), ".")


@_check("The kit", "kit.profile")
def check_profile(i: Inputs) -> list[Line]:
    """`profile check`: its errors are gaps, its warnings notes."""
    g, id_ = "The kit", "kit.profile"
    if i.profile_error:
        err = _relative(i, i.profile_error)
        return [Line(g, id_, "gap", Words(
            f"The kit's profile ({PROFILE}, its settings for this project) has a mistake, so the kit can't use it: {err}",
            f"`profile check` fails: {err}",
        ), Words(
            f"Ask Claude to fix {PROFILE}, then run this again.",
            f"Fix {PROFILE} (`workflow profile check` says what's wrong).",
        ))]
    if i.profile is None:
        return [Line(g, id_, "gap", Words(
            f"The kit isn't set up in this project yet: it has no profile ({PROFILE}).",
            f"No {PROFILE}.",
        ), Words(
            "Ask Claude to set the workflow up for this project.",
            "Run the setup-workflow skill.",
        ))]
    warnings = profile_mod.check(i.profile)
    if warnings:
        listed = "; ".join(warnings)
        return [Line(g, id_, "note", Words(
            f"The kit's profile works, with {len(warnings)} thing{'s' if len(warnings) > 1 else ''} to tidy: {listed}.",
            f"`profile check` warns: {listed}.",
        ), Words(
            f"None of these stops the kit; ask Claude to fix them in {PROFILE} when you can.",
            f"Fix them in {PROFILE} when convenient.",
        ))]
    return [Line(g, id_, "fine", Words(
        f"The kit's profile ({PROFILE}) is in order.",
        "`profile check` passes with no warnings.",
    ))]


@_check("The kit", "kit.vendor")
def check_vendor(i: Inputs) -> list[Line]:
    """`vendor verify`, vendored only: the copy is as the kit wrote it. The
    hooks and the plugin are `check_install`'s."""
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
    if _read_json(i.root, SETTINGS)[1]:
        return [Line(g, id_, "cant_check", Words(
            "Can't check the kit's copy until Claude Code's settings file can be read.",
            f"`vendor verify` needs {SETTINGS} to read.",
        ), Words(
            "Fix the settings file first (see the settings line).",
            "Fix the settings first (kit.settings).",
        ))]
    try:
        r = vendor_mod.verify(i.root)
    except (vendor_mod.VendorError, OSError, ValueError, AttributeError, TypeError) as e:
        why = _relative(i, str(e) or type(e).__name__)
        return [Line(g, id_, "gap", Words(
            f"The kit's copy in this project can't be checked: {why}.",
            f"`vendor verify` fails: {why}.",
        ), Words(
            "Ask Claude to update the workflow kit, which writes its copy again.",
            "Rerun `vendor update` (the update-workflow skill).",
        ))]
    problems = []
    for key, what in (("missing", "missing"), ("changed", "changed by hand"), ("conflicts", "with an update's conflict to settle")):
        if r[key]:
            problems.append(f"{what}: {', '.join(r[key][:5])}" + (f" and {len(r[key]) - 5} more" if len(r[key]) > 5 else ""))
    if problems:
        listed = "; ".join(problems)
        return [Line(g, id_, "gap", Words(
            f"The kit's copy in this project isn't as the kit wrote it ({listed}).",
            f"`vendor verify`: {listed}.",
        ), Words(
            "Ask Claude to look at the changed files: an update of the kit puts its own files back, and a change you meant to keep can be recorded.",
            "`vendor update` (update-workflow) restores the copy; `vendor resolve --keep <file>` records a deliberate edit, `vendor resolve <file>` a settled conflict.",
        ))]
    if r["mattpocock"] == "not_vendored":
        return [Line(g, id_, "note", Words(
            "The kit's copy is as the kit wrote it, but without Matt Pocock's skills, which building and reviewing tickets use.",
            "`vendor verify` passes, but Matt Pocock's skills aren't vendored (`--strict` fails on this).",
        ), Words(
            "Ask Claude to update the workflow kit with Matt Pocock's skills, or to record that you go without them.",
            "`vendor update --mattpocock <checkout>`, or `--no-mattpocock` to decline them on purpose.",
        ))]
    return [Line(g, id_, "fine", Words(
        "The kit's copy in this project is as the kit wrote it.",
        f"`vendor verify` passes (kit {r['version'] or 'unknown'}).",
    ))]


_SOURCE_WORDS = {
    "environment": Words(f"set in the environment variable {EXPERIENCE_ENV}", f"from {EXPERIENCE_ENV}"),
    "local file": Words(f"set on this computer in {EXPERIENCE_FILE.as_posix()}", f"from {EXPERIENCE_FILE.as_posix()}"),
    "profile": Words("the project's default, project.experience", "from project.experience"),
}
_LEVEL_WORDS = {"new": "someone new to building", "developer": "a developer"}
_DEFAULT_WORDS = {"new": "new to building", "developer": "developer"}


def _skipped_names(exp: Experience) -> list[str]:
    """The settings `resolve_experience` skipped ("ignored <name>: why")."""
    return [w.split(":", 1)[0].removeprefix("ignored ").strip() for w in exp.warnings]


@_check("The kit", "kit.experience")
def check_experience(i: Inputs) -> list[Line]:
    """The project's default and the person's level with its source, as
    `workflow status` reports it (#43)."""
    g, id_ = "The kit", "kit.experience"
    exp, default = i.experience, i.default
    if i.profile_error:
        d = Words(" The project's default can't be read until its profile is fixed.", " project default: unreadable (profile error).")
    elif default:
        d = Words(f" The project's default level is {_DEFAULT_WORDS[default]}.", f" project default: {default}.")
    else:
        d = Words(" The project has no default level.", " no project default.")
    if exp.source == "profile":
        d = NONE  # the level is the default: said once
    skipped = Words(
        f" Skipped {' and '.join(_skipped_names(exp))}: it should say `new` or `developer`." if exp.warnings else "",
        f" Skipped: {'; '.join(exp.warnings)}." if exp.warnings else "",
    )
    skipped_fix = Words("Put `new` or `developer` in the skipped setting, or remove it.", "Set the skipped value to `new` or `developer`, or unset it.")
    if exp.level:
        src = _SOURCE_WORDS[exp.source]
        msg = Words(
            f"Claude words things for {_LEVEL_WORDS[exp.level]} ({src.new}).{d.new}{skipped.new}",
            f"Experience: {exp.level} ({src.developer})" + (f";{d.developer}" if d.developer else ".") + skipped.developer,
        )
        return [Line(g, id_, "note", msg, skipped_fix)] if exp.warnings else [Line(g, id_, "fine", msg)]
    return [Line(g, id_, "note", Words(
        f"Nobody has said how much you know about building software, so Claude explains things as for someone new to it.{d.new}{skipped.new}",
        f"Experience: unknown (worded as new);{d.developer}{skipped.developer}",
    ), Words(
        "Start a Claude session and answer its first question, how much you know; or ask Claude to set the project's default."
        + (" " + skipped_fix.new if exp.warnings else ""),
        f"Set {EXPERIENCE_ENV}, {EXPERIENCE_FILE.as_posix()} or project.experience to `new` or `developer`.",
    ))]


@_check("The kit", "kit.ruleset")
def check_ruleset(i: Inputs) -> list[Line]:
    """The profile's `project.ruleset`. `true` is fine here: the GitHub lines
    check it against GitHub."""
    g, id_ = "The kit", "kit.ruleset"
    if i.profile is None:
        first = Words("Fix the kit's profile first (see the profile line).", "Fix the profile first (kit.profile).") if i.profile_error else Words(
            "Set the kit up first (see the profile line).", "Set the kit up first (kit.profile).")
        return [Line(g, id_, "cant_check", Words(
            "Can't tell whether the project means its main branch to be protected until the kit's profile can be read.",
            "project.ruleset unknown: no readable profile.",
        ), first)]
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


# Every check, in the order its lines show when they are equally serious.
CHECKS = [check_python, check_claude_code, check_install, check_profile, check_vendor, check_experience, check_ruleset]


# ---------- the report ----------


@dataclass
class Report:
    lines: list[Line]
    level: str  # the wording: "new" or "developer"
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
            "wording": self.level,
            "counts": self.counts(),
            "strict_ok": self.strict_ok(),
            "lines": [ln.as_dict(self.level) for ln in self.lines],
        }


def _rank(status: str) -> int:
    return STATUSES.index(status)


def order(lines: list[Line]) -> list[Line]:
    """Grouped, the group with the most serious line first (ties in `GROUPS`
    order), and within a group the most serious line first (ties in check
    order). So the most serious line of all comes first."""
    groups: dict[str, list[Line]] = {}
    for ln in lines:
        groups.setdefault(ln.group, []).append(ln)
    for g in groups.values():
        g.sort(key=lambda ln: _rank(ln.status))  # stable: check order within a status
    names = sorted(groups, key=lambda g: (min(_rank(ln.status) for ln in groups[g]), GROUPS.index(g)))
    return [ln for g in names for ln in groups[g]]


def _failed(check, e: Exception) -> Line:
    why = f"{type(e).__name__}: {e}"[:200]
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
            lines.append(_failed(check, e))
    for ln in lines:
        assert ln.status in STATUSES and ln.group in GROUPS and (ln.offer is None or ln.offer in OFFERS), ln
    return Report(order(lines), i.experience.wording_level, i.experience, i.default)


def _plural(n: int, status: str) -> str:
    return f"{n} {LABELS[status]}" + ("s" if n != 1 and status in ("gap", "note") else "")


def text(r: Report, width: int = 100) -> str:
    """Grouped lines, each wrapped to `width` with its fix indented below it.
    A note's fix is what to do if you want to change it: "Next", not "Fix"."""
    c = r.counts()
    width = max(40, width)
    out = textwrap.wrap("Workflow doctor: " + ", ".join(_plural(c[s], s) for s in STATUSES if c[s] or s == "gap"), width)
    group = None
    for ln in r.lines:
        if ln.group != group:
            group = ln.group
            out += ["", group]
        mark = f"  [{LABELS[ln.status]}] "
        out += textwrap.wrap(ln.message.pick(r.level), width, initial_indent=mark, subsequent_indent=" " * 6, break_long_words=False, break_on_hyphens=False)
        fix = ln.fix.pick(r.level)
        if fix:
            label = "Next: " if ln.status in ("note", "fine") else "Fix: "
            out += textwrap.wrap(fix, width, initial_indent=" " * 6 + label, subsequent_indent=" " * 8, break_long_words=False, break_on_hyphens=False)
        if ln.offer:
            out.append(f"      Claude can offer: {OFFERS[ln.offer]}")
    return "\n".join(out)

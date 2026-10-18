"""`workflow doctor`: one report of what's set up and what isn't (#34).

Each check is a function from what doctor was given (`Inputs`) to report
lines (`Line`). A line has a group, an id, a status, a message and a fix in
both wordings, and optionally an offer (an upgrade #32 builds). The report
picks one wording by experience (#16: what is checked, and each status, never
depend on it), puts the most serious line first and groups the rest.

Doctor never changes anything (#27): it reads files and runs `python3` and
`claude --version`, nothing else.

**Adding a group or a check** (the GitHub, Cloud and Previews tickets): write
a function `def check_x(i: Inputs) -> list[Line]`, add it to `CHECKS`, and put
anything it reads on `Inputs` (filled in by `cli.cmd_doctor`). The group goes
in `GROUPS` already; the order, the counts, the text, the JSON and `--strict`
follow without change.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
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
# The upgrades a line may offer, by the names #47 and #48 use.
OFFERS = {"protect_main": "Protect `main`", "restore_protection": "Restore protection", "set_up_unattended_runs": "Set up unattended runs"}

PYTHON_MIN = (3, 11)
# The oldest Claude Code that honours the guard's `onFailure: "block"` (#57,
# docs/enforcement.md).
CLAUDE_CODE_MIN = (2, 1, 295)
RUN_TIMEOUT = 10  # seconds, for `python3` and `claude --version`
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
# What each of the kit's hooks is called in a report.
HOOK_NAMES = {"PreToolUse": "the guard", "Stop": "the status gate", "UserPromptSubmit": "the flow context", "SessionStart": "the session start"}


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


def _run(i: Inputs, argv: list[str]) -> str | None:
    """A command's standard output, or None when it is missing, fails or
    hangs. Run in the checkout with nothing written: no shell, no input."""
    exe = shutil.which(argv[0], path=i.path)
    if not exe:
        return None
    try:
        p = subprocess.run([exe, *argv[1:]], cwd=i.root, env=i.environ, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=RUN_TIMEOUT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return p.stdout if p.returncode == 0 else None


def _version(text: str | None) -> tuple[int, int, int] | None:
    m = _VERSION.search(text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _dotted(v) -> str:
    return ".".join(str(x) for x in v)


# ---------- Your computer ----------


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
            "Python (`python3`) isn't installed, or your computer can't find it, so the kit's safety checks can't run.",
            f"No `python3` on the PATH: the kit's hooks can't run it (they need {need}+).",
        ), install)]
    out = _run(i, ["python3", "-I", "-c", "import sys; print('%d.%d.%d' % tuple(sys.version_info[:3]))"])
    v = _version(out)
    if v is None:
        return [Line(g, id_, "cant_check", Words(
            "Couldn't tell which version of Python (`python3`) your computer has: it didn't answer.",
            "`python3` on the PATH failed, or printed no version.",
        ), Words(
            f"Run `python3 --version` in a terminal: it should say {need} or newer.",
            f"Check `python3 --version` ({need}+ needed) and that it runs.",
        ))]
    if v[:2] < PYTHON_MIN:
        return [Line(g, id_, "gap", Words(
            f"Your computer's Python (`python3`) is version {_dotted(v)}, but the kit needs {need} or newer, so its safety checks fall back to a simpler mode.",
            f"`python3` on the PATH is {_dotted(v)}; the kit needs {need}+ (the hooks run their fallback).",
        ), install)]
    return [Line(g, id_, "fine", Words(
        f"Python is ready (`python3` is version {_dotted(v)}).",
        f"`python3` on the PATH is {_dotted(v)} ({need}+ needed).",
    ))]


def check_claude_code(i: Inputs) -> list[Line]:
    g, id_ = "Your computer", "computer.claude_code"
    need = _dotted(CLAUDE_CODE_MIN)
    given = i.claude_version is not None
    v = _version(i.claude_version if given else _run(i, ["claude", "--version"]))
    if v is None:
        where = f"`--claude-version {i.claude_version[:40]}` holds no version" if given else "no `--claude-version`, and `claude --version` gave none"
        return [Line(g, id_, "cant_check", Words(
            "Couldn't tell which version of Claude Code you have.",
            f"Claude Code's version is unknown ({where}).",
        ), Words(
            f"Run `claude --version` in a terminal: it should say {need} or newer.",
            f"Run `claude --version` ({need}+ needed), or pass `--claude-version`.",
        ))]
    if v < CLAUDE_CODE_MIN:
        return [Line(g, id_, "gap", Words(
            f"Claude Code is version {_dotted(v)}, older than {need}: if the kit's safety check ever fails or takes too long, this version lets the command run instead of stopping it.",
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


def _settings(root: Path, rel) -> dict:
    """A settings file's JSON object; {} when it is missing. Raises
    VendorError when it can't be read."""
    return vendor_mod._settings(root, Path(rel))


def _user_settings(i: Inputs) -> Path:
    home = i.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(i.environ.get("HOME") or str(Path.home()), ".claude")
    return Path(home) / "settings.json"


def _plugin_on(i: Inputs) -> tuple[bool, str | None]:
    """Whether the kit's plugin is enabled here, and in which file: the most
    specific settings that name it win (the project's local file, then the
    project's, then the user's)."""
    on, where = False, None
    for label, path in (
        ("~/.claude/settings.json", _user_settings(i)),
        (vendor_mod.SETTINGS.as_posix(), i.root / vendor_mod.SETTINGS),
        (vendor_mod.SETTINGS_LOCAL.as_posix(), i.root / vendor_mod.SETTINGS_LOCAL),
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, ValueError):
            continue  # an unreadable file is the hooks line's to report
        plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
        if isinstance(plugins, dict) and vendor_mod.PLUGIN_KEY in plugins:
            on, where = bool(plugins[vendor_mod.PLUGIN_KEY]), label
    return on, where


def _hook_differences(settings: dict) -> list[str]:
    """How the kit's hooks in the settings differ from this kit version's own
    entries, as `vendor update` writes them: one phrase each."""
    hooks = settings.get("hooks") if isinstance(settings.get("hooks"), dict) else {}
    out = []
    for event in [*vendor_mod.KIT_HOOKS, *sorted(set(hooks) - set(vendor_mod.KIT_HOOKS))]:
        entries = [e for e in (hooks.get(event) or []) if isinstance(e, dict)]
        kit = [e for e in entries if any(isinstance(h, dict) and vendor_mod._is_kit_hook(h) for h in (e.get("hooks") or []))]
        want = vendor_mod.KIT_HOOKS.get(event)
        name = HOOK_NAMES.get(event, f"a kit hook on {event}")
        if want is None:
            if kit:
                out.append(f"{name} isn't one this version writes")
        elif not kit:
            out.append(f"{name} ({event}) is missing")
        elif kit != want:
            out.append(f"{name} ({event}) differs")
    return out


def _kit_version(i: Inputs) -> str:
    """The version of the kit running doctor, whose hook entries are compared:
    the project's lock for its vendored copy, else the kit's own VERSION (a
    checkout of the kit, or the plugin)."""
    copy = (i.root / ".claude/workflow").resolve()
    here = i.kit_root.resolve()
    if here == copy or copy in here.parents:
        return updates_mod.installed(i.root, i.kit_root) or "this version"
    try:
        v = (i.kit_root / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "this version"
    return v if updates_mod.parse(v) else "this version"


def check_install(i: Inputs) -> list[Line]:
    """Vendored: the hooks are this version's own entries. Plugin mode: the
    plugin is enabled. Both on: a gap naming which to turn off."""
    g = "The kit"
    lines: list[Line] = []
    on, where = _plugin_on(i)
    if i.vendored:
        version = _kit_version(i)
        try:
            diffs = _hook_differences(_settings(i.root, vendor_mod.SETTINGS))
        except vendor_mod.VendorError as e:
            diffs = None
            lines.append(Line(g, "kit.hooks", "gap", Words(
                f"The kit can't read its settings file (.claude/settings.json), so its safety checks may not run: {e}.",
                f"Can't read the kit's hooks: {e}.",
            ), Words(
                "Ask Claude to fix .claude/settings.json (it must be valid JSON), then run this again.",
                "Fix .claude/settings.json so it is a valid JSON object.",
            )))
        if diffs:
            lines.append(Line(g, "kit.hooks", "gap", Words(
                f"The kit's safety hooks in .claude/settings.json aren't the ones this version of the kit writes ({'; '.join(diffs)}), so some of its checks may not run as they should.",
                f"Kit hooks in .claude/settings.json differ from kit {version}'s entries: {'; '.join(diffs)}.",
            ), Words(
                "Ask Claude to update the workflow kit: the update writes the hooks again and keeps your project's own.",
                "Rerun the kit's update (`update-workflow`, which runs `vendor update`) to rewrite its entries; the project's own hooks are kept.",
            )))
        elif diffs is not None:
            lines.append(Line(g, "kit.hooks", "fine", Words(
                "The kit's safety hooks are in place, as this version of the kit writes them.",
                f"Kit hooks in .claude/settings.json match kit {version}'s entries.",
            )))
        if on:
            local = where if where in (vendor_mod.SETTINGS.as_posix(), vendor_mod.SETTINGS_LOCAL.as_posix()) else vendor_mod.SETTINGS_LOCAL.as_posix()
            key = f'`"enabledPlugins": {{"{vendor_mod.PLUGIN_KEY}": false}}`'
            lines.append(Line(g, "kit.plugin", "gap", Words(
                f"The kit is on twice here: copied into this project and installed as a plugin (turned on in {where}), so its checks run twice.",
                f"Both modes are on: the kit is vendored and the {vendor_mod.PLUGIN_KEY} plugin is enabled ({where}); the hooks run twice.",
            ), Words(
                f"Turn the plugin off for this project and keep the copy, which unattended runs need: put {key} in {local}.",
                f"Turn off the plugin, keep the vendored copy (runs need it): set {key} in {local}.",
            )))
        return lines
    if on:
        return [Line(g, "kit.plugin", "fine", Words(
            "The kit's plugin is turned on for this project.",
            f"Plugin mode: {vendor_mod.PLUGIN_KEY} is enabled ({where}).",
        ))]
    return [Line(g, "kit.plugin", "gap", Words(
        "The kit's plugin isn't turned on for this project, and there's no copy of the kit in it, so its safety checks don't run here.",
        f"Plugin mode (no .claude/workflow/lock.json), but {vendor_mod.PLUGIN_KEY} isn't enabled in the user's or the project's settings.",
    ), Words(
        f"In Claude Code, type `/plugin install {vendor_mod.PLUGIN_KEY}` (or turn it on in `/plugin`), then start a new session.",
        f"`/plugin install {vendor_mod.PLUGIN_KEY}`, or enable it in `enabledPlugins`.",
    ))]


def check_profile(i: Inputs) -> list[Line]:
    """`profile check`: its errors are gaps, its warnings notes."""
    g, id_ = "The kit", "kit.profile"
    if i.profile_error:
        return [Line(g, id_, "gap", Words(
            f"The kit's settings file (.claude/workflow/profile.toml) has a mistake, so the kit can't use it: {i.profile_error}",
            f"`profile check` fails: {i.profile_error}",
        ), Words(
            "Ask Claude to fix .claude/workflow/profile.toml, then run this again.",
            "Fix .claude/workflow/profile.toml (`workflow profile check` says what's wrong).",
        ))]
    if i.profile is None:
        return [Line(g, id_, "gap", Words(
            "The kit isn't set up in this project yet: it has no settings file (.claude/workflow/profile.toml).",
            f"No {profile_mod.PROFILE_PATH.as_posix()}.",
        ), Words(
            "Ask Claude to set the workflow up for this project.",
            "Run the setup-workflow skill.",
        ))]
    warnings = profile_mod.check(i.profile)
    if warnings:
        return [Line(g, id_, "note", Words(
            f"The kit's settings file works, with {len(warnings)} thing{'s' if len(warnings) > 1 else ''} to tidy: {'; '.join(warnings)}.",
            f"`profile check` warns: {'; '.join(warnings)}.",
        ), Words(
            "None of these stops the kit; ask Claude to fix them in .claude/workflow/profile.toml when you can.",
            "Fix them in .claude/workflow/profile.toml when convenient.",
        ))]
    return [Line(g, id_, "fine", Words(
        "The kit's settings file (.claude/workflow/profile.toml) is in order.",
        "`profile check` passes with no warnings.",
    ))]


def check_vendor(i: Inputs) -> list[Line]:
    """`vendor verify`, vendored only: the copy is as the kit wrote it. The
    hooks and the plugin are `check_install`'s."""
    if not i.vendored:
        return []
    g, id_ = "The kit", "kit.vendor"
    fix = Words(
        "Ask Claude to update the workflow kit, which puts its files back (or `git checkout -- .claude` to undo changes you didn't mean).",
        "`vendor update` (the update-workflow skill) restores the copy; `vendor resolve --keep <file>` records a deliberate edit.",
    )
    try:
        r = vendor_mod.verify(i.root)
    except vendor_mod.VendorError as e:
        return [Line(g, id_, "gap", Words(
            f"The kit's copy in this project can't be checked: {e}.",
            f"`vendor verify` fails: {e}.",
        ), fix)]
    problems = []
    for key, what in (("missing", "missing"), ("changed", "changed by hand"), ("conflicts", "with an update's conflict to settle")):
        if r[key]:
            problems.append(f"{what}: {', '.join(r[key][:5])}" + (f" and {len(r[key]) - 5} more" if len(r[key]) > 5 else ""))
    if r["mattpocock"] == "not_vendored":
        problems.append("Matt Pocock's skills aren't vendored")
    if problems:
        return [Line(g, id_, "gap", Words(
            f"The kit's copy in this project isn't as the kit wrote it ({'; '.join(problems)}).",
            f"`vendor verify`: {'; '.join(problems)}.",
        ), fix)]
    return [Line(g, id_, "fine", Words(
        "The kit's copy in this project is as the kit wrote it.",
        f"`vendor verify` passes (kit {r['version'] or 'unknown'}).",
    ))]


_SOURCE_WORDS = {
    "environment": Words(f"set in the environment, {EXPERIENCE_ENV}", f"from {EXPERIENCE_ENV}"),
    "local file": Words(f"set in this computer's {EXPERIENCE_FILE.as_posix()}", f"from {EXPERIENCE_FILE.as_posix()}"),
    "profile": Words("the project's default, project.experience", "from project.experience"),
}
_LEVEL_WORDS = {"new": "someone new to building", "developer": "a developer"}


def check_experience(i: Inputs) -> list[Line]:
    """The project's default and the person's level with its source, as
    `workflow status` reports it (#43)."""
    g, id_ = "The kit", "kit.experience"
    exp = i.experience
    default = (i.profile.experience if i.profile else None) or None
    d_new = f"The project's default is {_LEVEL_WORDS[default]}." if default else "The project has no default."
    d_dev = f"project default: {default}." if default else "no project default."
    warned = "; ".join(exp.warnings)
    if exp.level:
        src = _SOURCE_WORDS[exp.source]
        msg = Words(
            f"Claude words things for {_LEVEL_WORDS[exp.level]} ({src.new}). {d_new}" + (f" Skipped: {warned}." if warned else ""),
            f"Experience: {exp.level} ({src.developer}); {d_dev}" + (f" Skipped: {warned}." if warned else ""),
        )
        if not warned:
            return [Line(g, id_, "fine", msg)]
        return [Line(g, id_, "note", msg, Words(
            f"Put `new` or `developer` in the setting it skipped, or remove it.",
            f"Set the skipped value to `new` or `developer`, or unset it.",
        ))]
    return [Line(g, id_, "note", Words(
        f"Nobody has said how much you know about building software, so Claude explains things as for someone new to it. {d_new}" + (f" Skipped: {warned}." if warned else ""),
        f"Experience: unknown (worded as new); {d_dev}" + (f" Skipped: {warned}." if warned else ""),
    ), Words(
        "Start a Claude session and answer its first question, how much you know; or ask Claude to set the project's default.",
        f"Set {EXPERIENCE_ENV}, {EXPERIENCE_FILE.as_posix()} or project.experience to `new` or `developer`.",
    ))]


def check_ruleset(i: Inputs) -> list[Line]:
    """The profile's `project.ruleset`. `true` is fine here: the GitHub lines
    check it against GitHub."""
    g, id_ = "The kit", "kit.ruleset"
    if i.profile is None:
        return [Line(g, id_, "cant_check", Words(
            "Can't tell whether the project means its main branch to be protected until the kit's settings file reads.",
            "project.ruleset can't be read until the profile loads.",
        ), Words(
            "Fix the kit's settings file first (the line above says how).",
            "Fix the profile first (see kit.profile).",
        ))]
    base = i.profile.base_branch
    if i.profile.ruleset is True:
        return [Line(g, id_, "fine", Words(
            f"The project's settings say `{base}` is protected on GitHub by a ruleset.",
            f"project.ruleset = true: `{base}` should have a ruleset.",
        ))]
    if i.profile.ruleset is False:
        return [Line(g, id_, "note", Words(
            f"Solo mode: `{base}` isn't protected on GitHub, chosen on purpose; while you work with Claude, the kit's guard keeps changes off `{base}`.",
            f"project.ruleset = false (solo mode): no ruleset on `{base}` expected.",
        ), Words(
            f"When you want GitHub to protect `{base}` too, ask Claude to \"Protect `{base}`\".",
            f"Run the upgrade-setup skill's \"Protect `{base}`\" for the ruleset.",
        ), offer="protect_main")]
    return [Line(g, id_, "note", Words(
        f"Whether `{base}` is protected is not set (as before): the project was set up before solo mode, so nothing new is asked of it.",
        "project.ruleset: not set (as before).",
    ), Words(
        "Nothing to do; ask Claude to \"Protect `main`\" if GitHub doesn't protect it yet.",
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
    names = sorted(groups, key=lambda g: (min(_rank(ln.status) for ln in groups[g]), GROUPS.index(g) if g in GROUPS else len(GROUPS)))
    return [ln for g in names for ln in groups[g]]


def report(i: Inputs) -> Report:
    lines = [ln for check in CHECKS for ln in check(i)]
    for ln in lines:
        assert ln.status in STATUSES and ln.group in GROUPS and (ln.offer is None or ln.offer in OFFERS), ln
    return Report(order(lines), i.experience.wording_level, i.experience, (i.profile.experience if i.profile else None) or None)


def _plural(n: int, status: str) -> str:
    return f"{n} {LABELS[status]}" + ("s" if n != 1 and status in ("gap", "note") else "")


def text(r: Report) -> str:
    c = r.counts()
    head = ", ".join(_plural(c[s], s) for s in STATUSES if c[s] or s == "gap")
    out = [f"Workflow doctor: {head}"]
    group = None
    for ln in r.lines:
        if ln.group != group:
            group = ln.group
            out += ["", group]
        out.append(f"  [{LABELS[ln.status]}] {ln.message.pick(r.level)}")
        fix = ln.fix.pick(r.level)
        if fix:
            out.append(f"      Fix: {fix}")
        if ln.offer:
            out.append(f"      Claude can offer: {OFFERS[ln.offer]}")
    return "\n".join(out)

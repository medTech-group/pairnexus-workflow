"""The project's workflow profile (.claude/workflow/profile.toml)."""

from __future__ import annotations

import glob
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import presets as presets_mod
from . import roles as roles_mod

PROFILE_PATH = Path(".claude/workflow/profile.toml")

EXPLORERS = {"browser", "api", "cli", "none"}

# Never protected whatever the patterns say (guard.matches): `.env.example`,
# `.env.sample`, `.env.template`, and Claude Code's own `.claude/worktrees/`.
DEFAULT_PROTECTED = [
    ".claude/**",
    ".github/workflows/**",
    ".github/CODEOWNERS",
    "CODEOWNERS",
    "**/.env",
    "**/.env.*",
]
DEFAULT_TEST_PATHS = [
    "**/test_*.py",
    "**/*_test.py",
    "**/*.test.*",
    "**/*.spec.*",
    "**/*_test.dart",
    "**/*_test.go",
    "**/conftest.py",
]


class ProfileError(ValueError):
    pass


# Who writes code (#338): `guard.code_writers`, "ticket" (only ticket sessions)
# or "any"; absent is not answered. Written as a plain line, as `ruleset` is,
# so it can be read from a profile that doesn't parse (`plain_code_writers`).
CODE_WRITERS = ("ticket", "any")
_CODE_WRITERS_LINE = re.compile(r'^[ \t]*code_writers[ \t]*=[ \t]*"([^"\n]*)"', re.M)


# Every key the profile may hold, so a typo ("required_check", "[area]") fails
# instead of being quietly ignored. None: any key (area names).
ALLOWED: dict[str, set[str] | None] = {
    "project": {"name", "repo", "base_branch", "rules", "flow_addendum", "owner", "guided_start", "ruleset", "experience"},
    "commands": {"setup", "setup_check", "typecheck", "test_file", "suite", "package", "select_suites"},
    "ci": {"required_checks", "killed_markers", "none", "path_filtered"},
    "ui": {"explorer", "start", "sizes", "notes"},
    "guard": {"protected_paths", "deploy_commands", "test_paths", "allow_new_skips", "code_writers", "code_paths"},
    "sensitive": {"description", "patterns"},
    "previews": {"provider", "on", "access"},
    "areas": None,
    "repair": {"commands"},
    "release": {"steps"},
    "run": {
        "ticket_branch",
        "check_in_minutes",
        "max_parallel",
        "max_retries",
        "review_rounds",
        "review_passes",
        "small_max_lines",
        "small_max_files",
        "ticket_environment",
        "conductor_environment",
        "environment_setup",
        "permission_mode",
        "preset",
    },
}
PREVIEW_PROVIDERS = ("cloudflare",)
PERMISSION_MODES = {"auto", "acceptEdits", "bypassPermissions", "dontAsk"}
SUITE_KEYS = {"name", "run", "files", "group", "passed", "failed", "skipped", "errors", "total", "cwd"}
PACKAGE_KEYS = {"name", "path", "typecheck", "test_file", "cwd"}
RELEASE_STEP_KEYS = {"name", "run", "smoke"}
OWNER = re.compile(r"^[A-Za-z0-9-]+$")
# How much the people working here know: `project.experience`, the
# WORKFLOW_EXPERIENCE variable and the local file (resolve_experience).
EXPERIENCE_LEVELS = ("new", "developer")
EXPERIENCE_ENV = "WORKFLOW_EXPERIENCE"
EXPERIENCE_FILE = Path(".workflow/experience")  # untracked: .workflow/ is in .gitignore
_EXPERIENCE_FILE_MAX = 200  # bytes: one short line


def _unknown(keys, allowed: set[str], where: str) -> None:
    bad = sorted(k for k in keys if k not in allowed)
    if bad:
        raise ProfileError(
            f"{where}: unknown key{'s' if len(bad) > 1 else ''} {', '.join(repr(k) for k in bad)}; "
            f"allowed: {', '.join(sorted(allowed))}"
        )


@dataclass
class Suite:
    name: str
    run: str
    files: str = ""  # glob(s) relative to the project root, even when cwd is set
    group: int = 8
    cwd: str = ""  # relative to the root; the shard runs there, given its files relative to it
    passed: str = r"(\d+) passed"
    failed: str = r"(\d+) failed"
    skipped: str = r"(\d+) skipped"
    errors: str = r"(\d+) errors?"
    # Optional: a regex for the runner's total, when its total includes skips and
    # failures (gotestsum's "DONE 42 tests"); then passed = total - skipped - failed - errors.
    total: str = ""


@dataclass
class Package:
    """A part of the project with its own typecheck or one-file test command
    (a backend and a web app, say). `path` is a glob, relative to the project
    root, for the files it covers; the commands run in `cwd` when set."""

    name: str
    path: str
    typecheck: str = ""
    test_file: str = ""
    cwd: str = ""


@dataclass
class Previews:
    """`[previews]`: whether pull requests get try-it links. An absent section
    is previews off. `access` is the owner's word that Cloudflare Access guards
    the preview URLs; the kit can't check it."""

    provider: str = "cloudflare"
    on: bool = False
    access: bool = False
    section: bool = False  # the profile has a [previews] section: off by choice, not never set up


# How `profile check`'s error begins for a sensitive project's previews
# without Access, which doctor's Previews line repeats in plain words.
ACCESS_REFUSED = "previews.on is true but previews.access isn't"


def _previews(raw: dict, sensitive: bool, section: bool) -> Previews:
    provider = raw.get("provider", "cloudflare")
    if provider not in PREVIEW_PROVIDERS:
        names = " or ".join(f'"{x}"' for x in PREVIEW_PROVIDERS)
        raise ProfileError(f"previews.provider must be {names}, not {repr(provider)[:40]}")
    on, access = raw.get("on", False), raw.get("access", False)
    for k, v in (("on", on), ("access", access)):
        if not isinstance(v, bool):
            raise ProfileError(f"previews.{k} must be true or false, not {repr(v)[:40]}")
    p = Previews(provider=provider, on=on, access=access, section=section)
    if p.on and not p.access and sensitive:
        raise ProfileError(
            f"{ACCESS_REFUSED}: this project has [sensitive] patterns, so its "
            "previews must sit behind Cloudflare Access (set access = true once you've confirmed it), or not be made (on = false)"
        )
    return p


@dataclass
class Profile:
    root: Path
    name: str
    repo: str
    base_branch: str = "main"
    owner: str = ""
    rules: list[str] = field(default_factory=list)
    flow_addendum: str = ""
    guided_start: bool = True
    # False is solo mode; None (absent) is as before solo mode existed.
    ruleset: bool | None = None
    # The project's default: "new" or "developer"; "" (absent): no default.
    experience: str = ""
    setup: str = ""
    setup_check: str = ""
    typecheck: str = ""
    test_file: str = ""
    suites: list[Suite] = field(default_factory=list)
    # Reads a PR's changed paths on stdin and prints the suites they need (evidence.select).
    select_suites: str = ""
    packages: list[Package] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    killed_markers: list[str] = field(default_factory=list)
    ci_none: bool = False
    path_filtered: list[str] = field(default_factory=list)
    explorer: str = "none"
    ui_start: list[str] = field(default_factory=list)
    ui_sizes: list[str] = field(default_factory=list)
    ui_notes: str = ""
    protected_paths: list[str] = field(default_factory=lambda: list(DEFAULT_PROTECTED))
    deploy_commands: list[str] = field(default_factory=list)
    test_paths: list[str] = field(default_factory=lambda: list(DEFAULT_TEST_PATHS))
    allow_new_skips: bool = False
    # Who writes code (#338): "ticket", "any", or None (not answered). Read it
    # through `code_rule`, which also counts the base branch's profile.
    code_writers: str | None = None
    code_paths: list[str] = field(default_factory=list)
    sensitive_description: str = ""
    sensitive_patterns: list[str] = field(default_factory=list)
    previews: Previews = field(default_factory=Previews)
    areas: dict[str, list[str]] = field(default_factory=dict)
    repair: list[str] = field(default_factory=list)
    release_steps: list[dict] = field(default_factory=list)
    ticket_branch: str = "claude/build-*"
    check_in_minutes: int = 20
    max_parallel: int = 2
    max_retries: int = 1
    review_rounds: int = 3
    # The Correctness passes allowed after the last counted round (#256).
    review_passes: int = 2
    # The small threshold (#257): a review in which no counted round ran Spec
    # counts only while the diff, outside tests, is within both.
    small_max_lines: int = 60
    small_max_files: int = 4
    ticket_environment: str = ""
    conductor_environment: str = ""
    environment_setup: str = ""
    permission_mode: str = "auto"
    # The run charter's recommended preset (presets.py); attended builds never read it.
    preset: str = "normal"


def project_root(start: Path | None = None) -> Path:
    """$CLAUDE_PROJECT_DIR, else the nearest directory holding .git, else cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        if (d / ".git").exists():
            return d
    return here


def _strs(v, where: str) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v else []
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ProfileError(f"{where}: expected a list of strings")
    return list(v)


def _int(v, where: str, default: int, lo: int = 0, hi: int = 10_000) -> int:
    if v is None:
        return default
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise ProfileError(f"{where}: expected a whole number from {lo} to {hi}")
    return v


def _cwd(v, where: str) -> str:
    cwd = str(v or "")
    if cwd and (Path(cwd).is_absolute() or ".." in Path(cwd).parts):
        raise ProfileError(f"{where}.cwd must be a directory relative to the project root, inside it")
    return cwd


def _packages(raw) -> list[Package]:
    if not isinstance(raw, list):
        raise ProfileError("commands.package must be an array of tables ([[commands.package]])")
    out: list[Package] = []
    for i, pk in enumerate(raw):
        where = f"commands.package[{i}]"
        if not isinstance(pk, dict):
            raise ProfileError(f"{where} must be a table")
        _unknown(pk, PACKAGE_KEYS, where)
        for k in PACKAGE_KEYS:
            if k in pk and not isinstance(pk[k], str):
                raise ProfileError(f"{where}.{k} must be a string")
        if not pk.get("name") or not pk.get("path"):
            raise ProfileError(f"{where} needs name and path (a glob, relative to the project root, for the files it covers)")
        if not pk.get("typecheck") and not pk.get("test_file"):
            raise ProfileError(f"{where} ({pk['name']}): give typecheck, test_file or both")
        if Path(pk["path"]).is_absolute() or ".." in Path(pk["path"]).parts:
            raise ProfileError(f"{where}.path must be a glob relative to the project root, inside it")
        out.append(
            Package(
                name=pk["name"],
                path=pk["path"],
                typecheck=pk.get("typecheck", ""),
                test_file=pk.get("test_file", ""),
                cwd=_cwd(pk.get("cwd"), where),
            )
        )
    names = [p.name for p in out]
    if len(names) != len(set(names)):
        raise ProfileError("commands.package names must be unique")
    return out


def _shown(v) -> str:
    return repr(v) if len(repr(v)) <= 40 else repr(v)[:39] + "…"


def _code_writers(guard: dict) -> str | None:
    v = guard.get("code_writers")
    if v is not None and not (isinstance(v, str) and v in CODE_WRITERS):
        raise ProfileError(
            f'guard.code_writers must be "ticket" (only ticket sessions write code) or "any" (any session), not {_shown(v)}; '
            "leave it out while it isn't answered"
        )
    return v


def _code_paths(guard: dict) -> list[str]:
    v = guard.get("code_paths", [])
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise ProfileError(f"guard.code_paths must be a list of globs (relative to the checkout's top level), not {_shown(v)}")
    return list(v)


def plain_code_writers(text: str | None) -> str | None:
    """`code_writers` from the profile's first plain `code_writers = "…"` line,
    whatever else the profile holds (it may not parse): "ticket", "any", or
    None when there is no such line or it holds neither."""
    m = _CODE_WRITERS_LINE.search((text or "").lstrip("\ufeff"))
    return m.group(1) if m and m.group(1) in CODE_WRITERS else None


def parse(data: dict, root: Path) -> Profile:
    if not isinstance(data, dict):
        raise ProfileError("the profile must be a TOML document of tables")
    tables = sorted(ALLOWED)
    for k, v in data.items():
        if k not in ALLOWED:
            raise ProfileError(f"unknown table [{k}]; allowed: {', '.join(f'[{t}]' for t in tables)}")
        if not isinstance(v, dict):
            raise ProfileError(f"[{k}] must be a table")
        if ALLOWED[k] is not None:
            _unknown(v, ALLOWED[k], f"[{k}]")
    proj = data.get("project") or {}
    name = proj.get("name")
    repo = proj.get("repo")
    if not isinstance(name, str) or not name:
        raise ProfileError("project.name is required")
    if not isinstance(repo, str) or repo.count("/") != 1:
        raise ProfileError("project.repo must be owner/repo")
    owner = proj.get("owner") or ""
    if not isinstance(owner, str) or (owner and not OWNER.match(owner)):
        raise ProfileError("project.owner must be a GitHub login (letters, digits and hyphens), without the @")
    cmds = data.get("commands") or {}
    suites = []
    raw_suites = cmds.get("suite") or []
    if not isinstance(raw_suites, list):
        raise ProfileError("commands.suite must be an array of tables ([[commands.suite]])")
    for i, s in enumerate(raw_suites):
        if not isinstance(s, dict) or not s.get("name") or not s.get("run"):
            raise ProfileError(f"commands.suite[{i}] needs name and run")
        _unknown(s, SUITE_KEYS, f"commands.suite[{i}]")
        if s.get("files") and "{files}" not in str(s["run"]):
            raise ProfileError(
                f"commands.suite[{i}] ({s['name']}): files is set but run has no {{files}}, so every shard "
                "would run the whole suite; put {files} where the test files go, or leave files empty"
            )
        cwd = _cwd(s.get("cwd"), f"commands.suite[{i}]")
        for k in ("passed", "failed", "skipped", "errors", "total"):
            if k in s:
                try:
                    re.compile(str(s[k]))
                except re.error as e:
                    raise ProfileError(f"commands.suite[{i}].{k}: {s[k]!r} is not a valid regex ({e})")
        suites.append(
            Suite(
                name=str(s["name"]),
                run=str(s["run"]),
                files=str(s.get("files", "")),
                group=_int(s.get("group"), f"commands.suite[{i}].group", 8, 1, 1000),
                cwd=cwd,
                passed=str(s.get("passed", Suite.passed)),
                failed=str(s.get("failed", Suite.failed)),
                skipped=str(s.get("skipped", Suite.skipped)),
                errors=str(s.get("errors", Suite.errors)),
                total=str(s.get("total") or ""),
            )
        )
    names = [s.name for s in suites]
    if len(names) != len(set(names)):
        raise ProfileError("commands.suite names must be unique")
    select_suites = cmds.get("select_suites", "")
    if not isinstance(select_suites, str):
        raise ProfileError("commands.select_suites must be a command, as one string")
    if select_suites.strip() and "none" in names:
        raise ProfileError("commands.suite: no suite may be named \"none\" with commands.select_suites, which prints none when no suite is needed")
    ci = data.get("ci") or {}
    ui = data.get("ui") or {}
    explorer = ui.get("explorer", "none")
    if not isinstance(explorer, str) or explorer not in EXPLORERS:
        raise ProfileError(f"ui.explorer must be one of {sorted(EXPLORERS)}")
    guard = data.get("guard") or {}
    sens = data.get("sensitive") or {}
    patterns = _strs(sens.get("patterns"), "sensitive.patterns")
    for p in patterns:
        try:
            re.compile(p)
        except re.error as e:
            raise ProfileError(f"sensitive.patterns: {p!r} is not a valid regex ({e})")
    previews = _previews(data.get("previews") or {}, bool(patterns), "previews" in data)
    areas_raw = data.get("areas") or {}
    areas = {k: _strs(v, f"areas.{k}") for k, v in areas_raw.items()}
    rel = data.get("release") or {}
    steps = rel.get("steps") or []
    if not isinstance(steps, list):
        raise ProfileError("release.steps must be an array of tables ([[release.steps]])")
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or not st.get("name") or not st.get("run"):
            raise ProfileError(f"release.steps[{i}] needs name and run")
        _unknown(st, RELEASE_STEP_KEYS, f"release.steps[{i}]")
    run = data.get("run") or {}
    ci_none = ci.get("none", False)
    if not isinstance(ci_none, bool):
        raise ProfileError("ci.none must be true or false")
    pmode = str(run.get("permission_mode") or "auto")
    if pmode not in PERMISSION_MODES:
        raise ProfileError(f"run.permission_mode must be one of {sorted(PERMISSION_MODES)} (a mode that prompts would stall an unattended session)")
    preset = run.get("preset", presets_mod.DEFAULT)
    if not (isinstance(preset, str) and preset in presets_mod.PRESETS):
        names = ", ".join(presets_mod.PRESETS[:-1]) + f" or {presets_mod.PRESETS[-1]}"
        shown = repr(preset) if len(repr(preset)) <= 40 else repr(preset)[:39] + "…"
        raise ProfileError(f"run.preset must be {names}, not {shown}; leave it out for {presets_mod.DEFAULT}")
    guided = proj.get("guided_start", True)
    if not isinstance(guided, bool):
        raise ProfileError("project.guided_start must be true or false")
    ruleset = proj.get("ruleset")
    if ruleset is not None and not isinstance(ruleset, bool):
        raise ProfileError(f"project.ruleset must be true or false (false is solo mode), not {repr(ruleset)[:40]}; leave it out for no solo mode")
    experience = proj.get("experience")
    if experience is not None and experience not in EXPERIENCE_LEVELS:
        levels = " or ".join(f'"{x}"' for x in EXPERIENCE_LEVELS)
        raise ProfileError(f"project.experience must be {levels}, not {repr(experience)[:40]}; leave it out for no project default")
    allow = guard.get("allow_new_skips", False)
    if not isinstance(allow, bool):
        raise ProfileError("guard.allow_new_skips must be true or false")
    code_writers, code_paths = _code_writers(guard), _code_paths(guard)
    return Profile(
        root=root,
        name=name,
        repo=repo,
        base_branch=str(proj.get("base_branch") or "main"),
        owner=owner,
        rules=_strs(proj.get("rules"), "project.rules"),
        flow_addendum=str(proj.get("flow_addendum") or ""),
        guided_start=guided,
        ruleset=ruleset,
        experience=experience or "",
        setup=str(cmds.get("setup") or ""),
        setup_check=str(cmds.get("setup_check") or ""),
        typecheck=str(cmds.get("typecheck") or ""),
        test_file=str(cmds.get("test_file") or ""),
        suites=suites,
        select_suites=select_suites.strip(),
        packages=_packages(cmds.get("package") or []),
        required_checks=_strs(ci.get("required_checks"), "ci.required_checks"),
        killed_markers=_strs(ci.get("killed_markers"), "ci.killed_markers"),
        ci_none=ci_none,
        path_filtered=_strs(ci.get("path_filtered"), "ci.path_filtered"),
        explorer=explorer,
        ui_start=_strs(ui.get("start"), "ui.start"),
        ui_sizes=_strs(ui.get("sizes"), "ui.sizes"),
        ui_notes=str(ui.get("notes") or ""),
        protected_paths=_strs(guard.get("protected_paths"), "guard.protected_paths")
        if "protected_paths" in guard
        else list(DEFAULT_PROTECTED),
        deploy_commands=_strs(guard.get("deploy_commands"), "guard.deploy_commands"),
        test_paths=_strs(guard.get("test_paths"), "guard.test_paths")
        if "test_paths" in guard
        else list(DEFAULT_TEST_PATHS),
        allow_new_skips=allow,
        code_writers=code_writers,
        code_paths=code_paths,
        sensitive_description=str(sens.get("description") or ""),
        sensitive_patterns=patterns,
        previews=previews,
        areas=areas,
        repair=_strs((data.get("repair") or {}).get("commands"), "repair.commands"),
        release_steps=list(steps),
        ticket_branch=str(run.get("ticket_branch") or "claude/build-*"),
        check_in_minutes=_int(run.get("check_in_minutes"), "run.check_in_minutes", 20, 1, 1440),
        max_parallel=_int(run.get("max_parallel"), "run.max_parallel", 2, 1, 16),
        max_retries=_int(run.get("max_retries"), "run.max_retries", 1, 0, 5),
        review_rounds=_int(run.get("review_rounds"), "run.review_rounds", 3, 1, 10),
        review_passes=_int(run.get("review_passes"), "run.review_passes", 2, 0, 10),
        small_max_lines=_int(run.get("small_max_lines"), "run.small_max_lines", 60, 1, 1000),
        small_max_files=_int(run.get("small_max_files"), "run.small_max_files", 4, 1, 50),
        ticket_environment=str(run.get("ticket_environment") or ""),
        conductor_environment=str(run.get("conductor_environment") or ""),
        environment_setup=str(run.get("environment_setup") or ""),
        permission_mode=pmode,
        preset=preset,
    )


@dataclass
class Experience:
    """How much the person knows, and where that came from.

    `level` is "new", "developer" or None (unknown); `source` is "environment",
    "local file", "profile" or "unknown". `warnings` name values skipped on the
    way. Wording uses `wording_level`: unknown counts as new to building."""

    level: str | None
    source: str
    warnings: list[str] = field(default_factory=list)

    @property
    def wording_level(self) -> str:
        """The level wording follows: unknown counts as new to building."""
        return self.level or "new"


_LEVELS_WORDS = " or ".join(EXPERIENCE_LEVELS)


def _level(value) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lstrip("\ufeff").strip().lower()  # a byte-order mark too
    return v if v in EXPERIENCE_LEVELS else None


def _read_experience_file(root) -> tuple[str | None, str]:
    """(the level, why it was skipped) from the local file: (None, "") when
    there is no file to read. Never raises. A skipped file's text is never
    shown, since the path might lead anywhere (a symlink to a secret)."""
    try:
        path = Path(root) / EXPERIENCE_FILE
        if path.is_dir():
            return None, "it is a directory"
        if not path.is_file():
            return None, ""
        with path.open("rb") as f:
            data = f.read(_EXPERIENCE_FILE_MAX + 1)
    except (OSError, ValueError, TypeError):
        return None, ""
    if len(data) > _EXPERIENCE_FILE_MAX:
        return None, "it is longer than one short line"
    try:
        lines = data.decode("utf-8").strip().splitlines()
    except UnicodeDecodeError:
        return None, "it isn't UTF-8 text"
    if not lines:
        return None, "it is empty"
    if len(lines) > 1:
        return None, "it holds more than one line"
    lvl = _level(lines[0])
    return (lvl, "") if lvl else (None, f"it holds neither {_LEVELS_WORDS}")


def resolve_experience(root: Path | None, profile_value=None, environ=None) -> Experience:
    """The person's experience. First match wins: WORKFLOW_EXPERIENCE in the
    environment, the untracked .workflow/experience file, the profile's
    project.experience, else unknown. An unrecognised environment or file
    value is skipped with a warning, which never repeats the value. The guard
    tickets call it from a hook, so it never raises, whatever it is given."""
    env = os.environ if environ is None else environ
    warnings: list[str] = []
    try:
        raw = env.get(EXPERIENCE_ENV)
    except Exception:  # the guard may hand it any mapping
        raw = None
    if isinstance(raw, str) and raw.strip():
        lvl = _level(raw)
        if lvl:
            return Experience(lvl, "environment", warnings)
        warnings.append(f"ignored {EXPERIENCE_ENV}: it holds neither {_LEVELS_WORDS}")
    if root is not None:
        lvl, why = _read_experience_file(root)
        if lvl:
            return Experience(lvl, "local file", warnings)
        if why:
            warnings.append(f"ignored {EXPERIENCE_FILE.as_posix()}: {why} (write {_LEVELS_WORDS})")
    lvl = profile_value if profile_value in EXPERIENCE_LEVELS else None
    if lvl:
        return Experience(lvl, "profile", warnings)
    return Experience(None, "unknown", warnings)


def load(root: Path | None = None, required: bool = True) -> Profile | None:
    root = root or project_root()
    path = root / PROFILE_PATH
    if not path.exists():
        if required:
            raise ProfileError(f"no profile at {path}; run the setup-workflow skill first")
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ProfileError(f"{path}: {e}") from e
    return parse(data, root)


# ---------- which profile counts for who writes code (#339) ----------


@dataclass
class CodeRule:
    """Who writes code and where code is, from the profile that counts: the
    working tree's and the base branch's as last fetched (`origin/<base>`),
    whichever is stricter. `code_writers` "ticket" beats "any" or None, and
    the code-path lists are joined. `protected_paths`, `repo` and
    `base_branch` are the working tree's, or the base's when the working
    tree's profile is missing or invalid; `profile` is the whole profile that
    counts (the working tree's, else the base's), None when neither parses.
    `sources` names what was read: "working tree", "origin/main", …"""

    code_writers: str | None = None
    code_paths: list[str] = field(default_factory=list)
    protected_paths: list[str] = field(default_factory=lambda: list(DEFAULT_PROTECTED))
    repo: str | None = None
    base_branch: str = "main"
    profile: Profile | None = None
    sources: list[str] = field(default_factory=list)

    def writes_code(self) -> bool:
        """Whether this session may write code: under "ticket", only one whose
        `WORKFLOW_ROLE` is `ticket` (trimmed, any case), never one that is a
        ticket session only by its branch or by a value that isn't a role;
        under "any" or unanswered, every session, as before."""
        if self.code_writers != "ticket":
            return True
        return roles_mod.env_role() == "ticket" and roles_mod.unrecognised() is None


def _git(root: Path, *args: str) -> str | None:
    try:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return p.stdout.decode("utf-8", errors="replace") if p.returncode == 0 else None


def _base_text(root: Path, base: str) -> tuple[str | None, str | None]:
    """(the ref read, the base's profile text) from `origin/<base>`, else
    `origin/HEAD`, as last fetched: (None, None) when neither ref exists, and
    (ref, None) when the ref has no profile."""
    for name in (base, "HEAD"):
        ref = f"refs/remotes/origin/{name}"
        if _git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None:
            return f"origin/{name}", _git(root, "show", f"{ref}:{PROFILE_PATH.as_posix()}")
    return None, None


def _rule_fields(data: dict) -> dict:
    """The keys the rule needs from a profile this kit may not fully read (a
    later release's, with keys it doesn't know): each read on its own, one
    that is invalid left out, everything else ignored."""
    out: dict = {}
    proj = data.get("project") if isinstance(data.get("project"), dict) else {}
    guard = data.get("guard") if isinstance(data.get("guard"), dict) else {}
    for key, read in (("code_writers", _code_writers), ("code_paths", _code_paths)):
        try:
            out[key] = read(guard)
        except ProfileError:
            pass
    try:
        if "protected_paths" in guard:
            out["protected_paths"] = _strs(guard["protected_paths"], "guard.protected_paths")
    except ProfileError:
        pass
    if isinstance(proj.get("repo"), str) and proj["repo"].count("/") == 1:
        out["repo"] = proj["repo"]
    if isinstance(proj.get("base_branch"), str) and proj["base_branch"]:
        out["base_branch"] = proj["base_branch"]
    return out


def _stricter(a: str | None, b: str | None) -> str | None:
    return "ticket" if "ticket" in (a, b) else "any" if "any" in (a, b) else None


def code_rule(root: Path | None = None) -> CodeRule:
    """Which profile counts for who writes code: the one helper the guard,
    the hooks, doctor and status call. Never raises; with neither profile
    readable, a rule with nothing answered (as before)."""
    root = root or project_root()
    tree: Profile | None = None
    tree_data = None
    try:
        tree_data = tomllib.loads((root / PROFILE_PATH).read_text(encoding="utf-8"))
        tree = parse(tree_data, root)
    except (OSError, ValueError):  # missing, not UTF-8, TOML that doesn't parse, or invalid
        pass
    base_branch = "main"
    if tree is not None:
        base_branch = tree.base_branch
    elif isinstance(tree_data, dict):
        base_branch = _rule_fields(tree_data).get("base_branch", "main")
    ref, text = _base_text(root, base_branch)
    base: Profile | None = None
    fields: dict = {}
    if text is not None:
        try:
            data = tomllib.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            fields = _rule_fields(data)
            try:
                base = parse(data, root)
            except ProfileError:
                pass
        if fields.get("code_writers") is None and plain_code_writers(text):
            fields["code_writers"] = plain_code_writers(text)  # a base that doesn't parse, or doesn't validate
    rule = CodeRule(sources=[ref] if text is not None else [])
    if tree is None:
        rule.code_writers = fields.get("code_writers")
        rule.code_paths = list(fields.get("code_paths", []))
        rule.protected_paths = list(fields.get("protected_paths", DEFAULT_PROTECTED))
        rule.repo = fields.get("repo")
        rule.base_branch = fields.get("base_branch", base_branch)
        rule.profile = base
        return rule
    rule.sources.insert(0, "working tree")
    rule.code_writers = _stricter(tree.code_writers, fields.get("code_writers"))
    rule.code_paths = list(tree.code_paths) + [p for p in fields.get("code_paths", []) if p not in tree.code_paths]
    rule.protected_paths = list(tree.protected_paths)
    rule.repo, rule.base_branch, rule.profile = tree.repo, tree.base_branch, tree
    return rule


def slug(text: str) -> str:
    """A heading as its #anchor: lowercase, spaces to `-`, punctuation dropped."""
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


_FENCE = re.compile(r"^\s*(```|~~~)")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")


def headings(text: str) -> set[str]:
    """The anchors of a Markdown file's headings (outside code fences)."""
    out: set[str] = set()
    fenced = False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else _MD_HEADING.match(line)
        if m:
            out.add(slug(m.group(1)))
    return out


def globs(spec: str) -> list[str]:
    """A comma-separated glob list, as suites write `files`."""
    return [p.strip() for p in (spec or "").split(",") if p.strip()]


def matches(root: Path, pattern: str) -> bool:
    return any(True for _ in glob.iglob(str(root / pattern), recursive=True))


# The vendored kit's own folder, whose files are expected to be both code and
# protected (its scripts match a project's code paths), so never listed.
_KIT_FOLDER = ".claude/"
_LISTED = 10


def _code_warnings(profile: Profile) -> list[str]:
    """`profile check`'s warnings about `code_writers` and `code_paths`."""
    w: list[str] = []
    if profile.code_writers == "ticket" and not profile.code_paths:
        w.append('guard.code_writers is "ticket" but guard.code_paths is empty: no file counts as code, so the rule refuses nothing')
    if profile.code_writers is not None:
        try:
            text = (profile.root / PROFILE_PATH).read_text(encoding="utf-8")
        except (OSError, ValueError):
            text = None
        if text is not None and plain_code_writers(text) != profile.code_writers:
            w.append(
                f'guard.code_writers: write it as a plain line, code_writers = "{profile.code_writers}", under [guard]: '
                "it is read from that line when the profile doesn't parse"
            )
    if profile.code_paths:
        from .guard import matches  # the guard's own matching, as for protected_paths

        tracked = _git(profile.root, "ls-files", "-z") or ""
        both = [
            f
            for f in tracked.split("\0")
            if f and not f.startswith(_KIT_FOLDER) and matches(f, profile.code_paths) and matches(f, profile.protected_paths)
        ]
        if both:
            listed = ", ".join(both[:_LISTED]) + (f" and {len(both) - _LISTED} more" if len(both) > _LISTED else "")
            w.append(
                f"guard.code_paths and guard.protected_paths both match {len(both)} tracked file{'s' if len(both) > 1 else ''}, "
                f"which count as protected, not code: {listed}"
            )
    return w


def check(profile: Profile) -> list[str]:
    """Warnings that don't make the profile invalid: references to files that
    aren't there, globs that match nothing, and settings an unattended run needs."""
    w: list[str] = []
    root = profile.root
    if not profile.owner:
        w.append("project.owner is empty: approvals and the owner's comments can't be checked against a login")
    for r in profile.rules:
        part, _, anchor = r.partition("#")
        part, anchor = part.strip(), anchor.strip()
        if part and not (root / part).exists():
            w.append(f"project.rules: {part} doesn't exist (from {r!r})")
        elif part and anchor and (root / part).is_file():
            try:
                text = (root / part).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if slug(anchor) not in headings(text):
                w.append(f"project.rules: {part} has no heading matching #{anchor} (from {r!r})")
    if profile.flow_addendum and not (root / profile.flow_addendum).exists():
        w.append(f"project.flow_addendum: {profile.flow_addendum} doesn't exist")
    for s in profile.suites:
        if s.cwd and not (root / s.cwd).is_dir():
            w.append(f"commands.suite {s.name}: cwd {s.cwd} isn't a directory")
        for pat in globs(s.files):
            if not matches(root, pat):
                w.append(f"commands.suite {s.name}: files glob {pat!r} matches no file (globs are relative to the project root)")
    for pk in profile.packages:
        if pk.cwd and not (root / pk.cwd).is_dir():
            w.append(f"commands.package {pk.name}: cwd {pk.cwd} isn't a directory")
        if not matches(root, pk.path):
            w.append(f"commands.package {pk.name}: path {pk.path!r} matches no file (relative to the project root)")
    for area, pats in profile.areas.items():
        for pat in pats:
            if not matches(root, pat):
                w.append(f"areas.{area}: glob {pat!r} matches no file")
    if profile.setup and not profile.setup_check:
        w.append("commands.setup is set but commands.setup_check is empty: the session start never runs setup without a check")
    for must in (".claude/**", ".github/workflows/**"):
        if must not in profile.protected_paths:
            w.append(f"guard.protected_paths leaves out {must!r}: a list there replaces the defaults, so ticket sessions could change it")
    w.extend(_code_warnings(profile))
    if not profile.ticket_environment:
        w.append("run.ticket_environment is empty: name the claude.ai environment ticket sessions run in")
    if not profile.conductor_environment:
        w.append("run.conductor_environment is empty: name the claude.ai environment the conductor runs in")
    return w


def summary(profile: Profile) -> dict:
    """What `workflow profile check` prints: the parsed profile, in short."""
    return {
        "name": profile.name,
        "repo": profile.repo,
        "owner": profile.owner or None,
        "base_branch": profile.base_branch,
        "ruleset": profile.ruleset,
        "experience": profile.experience or None,
        "rules": profile.rules,
        "typecheck": profile.typecheck or None,
        "test_file": profile.test_file or None,
        "suites": [
            {"name": s.name, "run": s.run, "files": s.files or None, "cwd": s.cwd or None, "group": s.group}
            for s in profile.suites
        ],
        "select_suites": profile.select_suites or None,
        "packages": [
            {"name": p.name, "path": p.path, "typecheck": p.typecheck or None, "test_file": p.test_file or None, "cwd": p.cwd or None}
            for p in profile.packages
        ],
        "required_checks": profile.required_checks,
        "killed_markers": profile.killed_markers,
        "areas": profile.areas,
        "deploy_commands": profile.deploy_commands,
        "protected_paths": profile.protected_paths,
        "code_writers": profile.code_writers,
        "code_paths": profile.code_paths,
        "release_steps": [st.get("name") for st in profile.release_steps],
        "repair": profile.repair,
        "explorer": profile.explorer,
        "ticket_branch": profile.ticket_branch,
        "ci_none": profile.ci_none,
        "path_filtered": profile.path_filtered,
        "ticket_environment": profile.ticket_environment or None,
        "conductor_environment": profile.conductor_environment or None,
        "permission_mode": profile.permission_mode,
        "preset": profile.preset,
        "previews": {"provider": profile.previews.provider, "on": profile.previews.on, "access": profile.previews.access},
    }

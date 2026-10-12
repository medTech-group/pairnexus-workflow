"""The project's workflow profile (.claude/workflow/profile.toml)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROFILE_PATH = Path(".claude/workflow/profile.toml")

EXPLORERS = {"browser", "api", "cli", "none"}

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
]


class ProfileError(ValueError):
    pass


# Every key the profile may hold, so a typo ("required_check", "[area]") fails
# instead of being quietly ignored. None: any key (area names).
ALLOWED: dict[str, set[str] | None] = {
    "project": {"name", "repo", "base_branch", "rules", "flow_addendum", "owner"},
    "commands": {"setup", "typecheck", "test_file", "suite"},
    "ci": {"required_checks", "killed_markers", "none", "path_filtered"},
    "ui": {"explorer", "start", "sizes", "notes"},
    "guard": {"protected_paths", "deploy_commands", "test_paths", "allow_new_skips"},
    "sensitive": {"description", "patterns"},
    "areas": None,
    "repair": {"commands"},
    "release": {"steps"},
    "run": {
        "ticket_branch",
        "check_in_minutes",
        "max_parallel",
        "max_retries",
        "review_rounds",
        "ticket_environment",
        "conductor_environment",
        "permission_mode",
    },
}
PERMISSION_MODES = {"auto", "acceptEdits", "bypassPermissions", "dontAsk"}
SUITE_KEYS = {"name", "run", "files", "group", "passed", "failed", "skipped", "errors", "cwd"}
RELEASE_STEP_KEYS = {"name", "run", "smoke"}
OWNER = re.compile(r"^[A-Za-z0-9-]+$")


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
    files: str = ""
    group: int = 8
    cwd: str = ""  # relative to the root; the shard runs there, given its files relative to it
    passed: str = r"(\d+) passed"
    failed: str = r"(\d+) failed"
    skipped: str = r"(\d+) skipped"
    errors: str = r"(\d+) errors?"


@dataclass
class Profile:
    root: Path
    name: str
    repo: str
    base_branch: str = "main"
    owner: str = ""
    rules: list[str] = field(default_factory=list)
    flow_addendum: str = ""
    setup: str = ""
    typecheck: str = ""
    test_file: str = ""
    suites: list[Suite] = field(default_factory=list)
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
    sensitive_description: str = ""
    sensitive_patterns: list[str] = field(default_factory=list)
    areas: dict[str, list[str]] = field(default_factory=dict)
    repair: list[str] = field(default_factory=list)
    release_steps: list[dict] = field(default_factory=list)
    ticket_branch: str = "claude/build-*"
    check_in_minutes: int = 20
    max_parallel: int = 2
    max_retries: int = 1
    review_rounds: int = 3
    ticket_environment: str = ""
    conductor_environment: str = ""
    permission_mode: str = "auto"


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
        cwd = str(s.get("cwd") or "")
        if cwd and (Path(cwd).is_absolute() or ".." in Path(cwd).parts):
            raise ProfileError(f"commands.suite[{i}].cwd must be a directory relative to the project root, inside it")
        for k in ("passed", "failed", "skipped", "errors"):
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
            )
        )
    names = [s.name for s in suites]
    if len(names) != len(set(names)):
        raise ProfileError("commands.suite names must be unique")
    ci = data.get("ci") or {}
    ui = data.get("ui") or {}
    explorer = ui.get("explorer", "none")
    if explorer not in EXPLORERS:
        raise ProfileError(f"ui.explorer must be one of {sorted(EXPLORERS)}")
    guard = data.get("guard") or {}
    sens = data.get("sensitive") or {}
    patterns = _strs(sens.get("patterns"), "sensitive.patterns")
    for p in patterns:
        try:
            re.compile(p)
        except re.error as e:
            raise ProfileError(f"sensitive.patterns: {p!r} is not a valid regex ({e})")
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
    allow = guard.get("allow_new_skips", False)
    if not isinstance(allow, bool):
        raise ProfileError("guard.allow_new_skips must be true or false")
    return Profile(
        root=root,
        name=name,
        repo=repo,
        base_branch=str(proj.get("base_branch") or "main"),
        owner=owner,
        rules=_strs(proj.get("rules"), "project.rules"),
        flow_addendum=str(proj.get("flow_addendum") or ""),
        setup=str(cmds.get("setup") or ""),
        typecheck=str(cmds.get("typecheck") or ""),
        test_file=str(cmds.get("test_file") or ""),
        suites=suites,
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
        sensitive_description=str(sens.get("description") or ""),
        sensitive_patterns=patterns,
        areas=areas,
        repair=_strs((data.get("repair") or {}).get("commands"), "repair.commands"),
        release_steps=list(steps),
        ticket_branch=str(run.get("ticket_branch") or "claude/build-*"),
        check_in_minutes=_int(run.get("check_in_minutes"), "run.check_in_minutes", 20, 1, 1440),
        max_parallel=_int(run.get("max_parallel"), "run.max_parallel", 2, 1, 16),
        max_retries=_int(run.get("max_retries"), "run.max_retries", 1, 0, 5),
        review_rounds=_int(run.get("review_rounds"), "run.review_rounds", 3, 1, 10),
        ticket_environment=str(run.get("ticket_environment") or ""),
        conductor_environment=str(run.get("conductor_environment") or ""),
        permission_mode=pmode,
    )


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


def check(profile: Profile) -> list[str]:
    """Warnings that don't make the profile invalid: references to files that aren't there."""
    w: list[str] = []
    for r in profile.rules:
        part = r.split("#", 1)[0].strip()
        if part and not (profile.root / part).exists():
            w.append(f"project.rules: {part} doesn't exist (from {r!r})")
    if profile.flow_addendum and not (profile.root / profile.flow_addendum).exists():
        w.append(f"project.flow_addendum: {profile.flow_addendum} doesn't exist")
    for s in profile.suites:
        if s.cwd and not (profile.root / s.cwd).is_dir():
            w.append(f"commands.suite {s.name}: cwd {s.cwd} isn't a directory")
    return w


def summary(profile: Profile) -> dict:
    """What `workflow profile check` prints: the parsed profile, in short."""
    return {
        "name": profile.name,
        "repo": profile.repo,
        "owner": profile.owner or None,
        "base_branch": profile.base_branch,
        "rules": profile.rules,
        "typecheck": profile.typecheck or None,
        "test_file": profile.test_file or None,
        "suites": [
            {"name": s.name, "run": s.run, "files": s.files or None, "cwd": s.cwd or None, "group": s.group}
            for s in profile.suites
        ],
        "required_checks": profile.required_checks,
        "killed_markers": profile.killed_markers,
        "areas": profile.areas,
        "deploy_commands": profile.deploy_commands,
        "protected_paths": profile.protected_paths,
        "release_steps": [st.get("name") for st in profile.release_steps],
        "repair": profile.repair,
        "explorer": profile.explorer,
        "ticket_branch": profile.ticket_branch,
        "ci_none": profile.ci_none,
        "path_filtered": profile.path_filtered,
        "ticket_environment": profile.ticket_environment or None,
        "conductor_environment": profile.conductor_environment or None,
        "permission_mode": profile.permission_mode,
    }

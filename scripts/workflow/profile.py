"""The project's workflow profile (.claude/workflow/profile.toml)."""

from __future__ import annotations

import glob
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

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


# Every key the profile may hold, so a typo ("required_check", "[area]") fails
# instead of being quietly ignored. None: any key (area names).
ALLOWED: dict[str, set[str] | None] = {
    "project": {"name", "repo", "base_branch", "rules", "flow_addendum", "owner"},
    "commands": {"setup", "setup_check", "typecheck", "test_file", "suite", "package"},
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
        "environment_setup",
        "permission_mode",
    },
}
PERMISSION_MODES = {"auto", "acceptEdits", "bypassPermissions", "dontAsk"}
SUITE_KEYS = {"name", "run", "files", "group", "passed", "failed", "skipped", "errors", "total", "cwd"}
PACKAGE_KEYS = {"name", "path", "typecheck", "test_file", "cwd"}
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
class Profile:
    root: Path
    name: str
    repo: str
    base_branch: str = "main"
    owner: str = ""
    rules: list[str] = field(default_factory=list)
    flow_addendum: str = ""
    setup: str = ""
    setup_check: str = ""
    typecheck: str = ""
    test_file: str = ""
    suites: list[Suite] = field(default_factory=list)
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
    environment_setup: str = ""
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
        setup_check=str(cmds.get("setup_check") or ""),
        typecheck=str(cmds.get("typecheck") or ""),
        test_file=str(cmds.get("test_file") or ""),
        suites=suites,
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
        environment_setup=str(run.get("environment_setup") or ""),
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
        "rules": profile.rules,
        "typecheck": profile.typecheck or None,
        "test_file": profile.test_file or None,
        "suites": [
            {"name": s.name, "run": s.run, "files": s.files or None, "cwd": s.cwd or None, "group": s.group}
            for s in profile.suites
        ],
        "packages": [
            {"name": p.name, "path": p.path, "typecheck": p.typecheck or None, "test_file": p.test_file or None, "cwd": p.cwd or None}
            for p in profile.packages
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

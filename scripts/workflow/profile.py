"""The project's workflow profile (.claude/workflow/profile.toml)."""

from __future__ import annotations

import os
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


@dataclass
class Suite:
    name: str
    run: str
    files: str = ""
    group: int = 8
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
    rules: list[str] = field(default_factory=list)
    flow_addendum: str = ""
    setup: str = ""
    typecheck: str = ""
    test_file: str = ""
    suites: list[Suite] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    killed_markers: list[str] = field(default_factory=list)
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
    proj = data.get("project") or {}
    if not isinstance(proj, dict):
        raise ProfileError("[project] must be a table")
    name = proj.get("name")
    repo = proj.get("repo")
    if not isinstance(name, str) or not name:
        raise ProfileError("project.name is required")
    if not isinstance(repo, str) or repo.count("/") != 1:
        raise ProfileError("project.repo must be owner/repo")
    cmds = data.get("commands") or {}
    suites = []
    for i, s in enumerate(cmds.get("suite") or []):
        if not isinstance(s, dict) or not s.get("name") or not s.get("run"):
            raise ProfileError(f"commands.suite[{i}] needs name and run")
        suites.append(
            Suite(
                name=str(s["name"]),
                run=str(s["run"]),
                files=str(s.get("files", "")),
                group=_int(s.get("group"), f"commands.suite[{i}].group", 8, 1, 1000),
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
    import re

    patterns = _strs(sens.get("patterns"), "sensitive.patterns")
    for p in patterns:
        try:
            re.compile(p)
        except re.error as e:
            raise ProfileError(f"sensitive.patterns: {p!r} is not a valid regex ({e})")
    areas_raw = data.get("areas") or {}
    if not isinstance(areas_raw, dict):
        raise ProfileError("[areas] must be a table")
    areas = {k: _strs(v, f"areas.{k}") for k, v in areas_raw.items()}
    rel = data.get("release") or {}
    steps = rel.get("steps") or []
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or not st.get("name") or not st.get("run"):
            raise ProfileError(f"release.steps[{i}] needs name and run")
    run = data.get("run") or {}
    allow = guard.get("allow_new_skips", False)
    if not isinstance(allow, bool):
        raise ProfileError("guard.allow_new_skips must be true or false")
    return Profile(
        root=root,
        name=name,
        repo=repo,
        base_branch=str(proj.get("base_branch") or "main"),
        rules=_strs(proj.get("rules"), "project.rules"),
        flow_addendum=str(proj.get("flow_addendum") or ""),
        setup=str(cmds.get("setup") or ""),
        typecheck=str(cmds.get("typecheck") or ""),
        test_file=str(cmds.get("test_file") or ""),
        suites=suites,
        required_checks=_strs(ci.get("required_checks"), "ci.required_checks"),
        killed_markers=_strs(ci.get("killed_markers"), "ci.killed_markers"),
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

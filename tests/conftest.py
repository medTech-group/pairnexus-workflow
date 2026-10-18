import atexit
import compileall
import functools
import os
import json
import py_compile
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

# The kit's tests never ask GitHub for the latest release; tests that need an
# answer pass their own (tests/test_kit_015.py).
os.environ["WORKFLOW_UPDATE_CHECK"] = "off"

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "scripts"))

from workflow.profile import parse  # noqa: E402

BASE_PROFILE = {
    "project": {"name": "demo", "repo": "acme/demo", "base_branch": "main", "rules": ["CLAUDE.md#rules"]},
    "commands": {
        "typecheck": "true",
        "suite": [{"name": "unit", "run": "python3 run_tests.py {files}", "files": "tests/test_*.txt", "group": 2}],
    },
    "guard": {
        "deploy_commands": ["scripts/deploy.sh", "terraform apply"],
    },
    "sensitive": {"description": "PHI", "patterns": [r"\bMRN-\d{6}\b"]},
    "areas": {"messages": ["src/messages/**"]},
    "release": {"steps": [{"name": "deploy staging", "run": "scripts/deploy.sh staging"}]},
}


@pytest.fixture(autouse=True)
def _fresh_guard_budget(monkeypatch):
    """Each test's in-process hook gets the guard's whole time budget, however
    long the suite has run (`_STARTED` is set once, when the CLI is imported)."""
    import time

    from workflow import cli

    monkeypatch.setattr(cli, "_STARTED", time.monotonic())


@pytest.fixture
def profile(tmp_path):
    return parse(json.loads(json.dumps(BASE_PROFILE)), tmp_path)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def ticket_checkout(root, branch="claude/build-1"):
    """Make `root` a git checkout on a ticket branch with one commit, and return
    its head: a ticket session's merge is pinned to it (#87)."""
    git(root, "init", "-q", "-b", branch)
    git(root, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    return git(root, "rev-parse", "HEAD").strip()


def pinned(cmd, root):
    """`cmd` with `{sha}` filled in by a ticket checkout at `root`."""
    return cmd.replace("{sha}", ticket_checkout(root)) if "{sha}" in cmd else cmd


@pytest.fixture
def repo(tmp_path):
    """A git repo with a profile, on a ticket branch."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        """
[project]
name = "demo"
repo = "acme/demo"
[guard]
deploy_commands = ["scripts/deploy.sh"]
[sensitive]
patterns = ['\\bMRN-\\d{6}\\b']
"""
    )
    (tmp_path / "README.md").write_text("x")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


@functools.cache
def _compiled_kit_package() -> Path:
    """The kit's `scripts/workflow` package with its bytecode, made once per
    test run, outside every test's folder."""
    top = Path(tempfile.mkdtemp(prefix="kit-package-"))
    atexit.register(shutil.rmtree, top, True)
    _copy_source(top / "workflow")
    prefix, sys.pycache_prefix = sys.pycache_prefix, None  # in `__pycache__` beside each file, even with PYTHONPYCACHEPREFIX set
    try:
        assert compileall.compile_dir(top / "workflow", quiet=1, invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
    finally:
        sys.pycache_prefix = prefix
    return top / "workflow"


def copy_kit_package(dest, compiled=True):
    """Copy the kit's `scripts/workflow` package to `dest` as `vendor install`
    copies it, with its bytecode beside it unless `compiled` is false (#193).
    A fresh copy run with `-B` compiles every module on every run, about 0.2 s
    of each; this compiles it once per test run. The bytecode is checked
    against each file's source hash, so a copy whose source a test changes
    still runs that source."""
    if compiled:
        shutil.copytree(_compiled_kit_package(), dest)
    else:
        _copy_source(dest)


def _copy_source(dest):
    shutil.copytree(KIT / "scripts/workflow", dest, ignore=shutil.ignore_patterns("__pycache__"))


def at_once(calls):
    """Each call's result, in order, with 2 to 8 calls made at the same time
    (one per CPU, #193): for a test that runs the CLI many times, each run a
    process of its own that would otherwise wait for the one before.
    The caller checks the results as it checked them one by one. A call that
    raises raises here (the first in order, if several do), as the loop did,
    and the calls not yet started then aren't made."""
    calls = list(calls)
    cpus = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 2
    workers = max(1, min(len(calls), max(2, min(cpus, 8))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda call: call(), calls))

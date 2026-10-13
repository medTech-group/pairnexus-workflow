import os
import json
import subprocess
import sys
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


@pytest.fixture
def profile(tmp_path):
    return parse(json.loads(json.dumps(BASE_PROFILE)), tmp_path)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


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

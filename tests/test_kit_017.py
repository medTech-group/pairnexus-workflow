"""Kit 0.1.7: the kit's home in one place, ready for forks."""

import json
import re
import subprocess
import sys
from pathlib import Path

from workflow import updates, vendor

KIT = Path(__file__).resolve().parents[1]
HOME = re.compile(r"medtech-group/pairnexus-workflow", re.I)

# Where a file a project receives may still name the upstream outright: the one
# constant code reads, the weekly check's fallback for copies older than 0.1.7,
# the bootstrap lines that run before any copy exists, links to the README, and
# the plugin install commands. Anything else reads `workflow version --repo`.
ALLOWED = {
    "scripts/workflow/updates.py": 1,
    "templates/github/workflow-kit-update.yml": 1,
    "skills/setup-workflow/SKILL.md": 1,
    "skills/update-workflow/SKILL.md": 1,
    "skills/conductor/SKILL.md": 1,
    "docs/enforcement.md": 1,
    "docs/install.md": 3,
}


def test_shipped_files_name_the_kits_home_only_where_allowed():
    found: dict[str, int] = {}
    for src in vendor.plan(KIT, None).values():
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        n = len(HOME.findall(text))
        if n:
            found[src.relative_to(KIT).as_posix()] = n
    assert found == ALLOWED, (
        "A shipped file names medTech-group/pairnexus-workflow outright. Read the kit's home from "
        "`workflow version --repo` (updates.KIT_REPO) instead, or, for a bootstrap line or README link, "
        f"update ALLOWED: {found}"
    )


def _cli(*args, env=None):
    return subprocess.run([sys.executable, "-B", str(KIT / "scripts/workflow.py"), *args],
                          capture_output=True, text=True, env=env, cwd=KIT)


def test_version_repo_prints_the_home_without_asking_github(tmp_path):
    # No network: an unreachable proxy and an empty cache would make a lookup fail or hang.
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(tmp_path), "HTTPS_PROXY": "http://127.0.0.1:9",
           "WORKFLOW_UPDATE_CHECK": "on"}
    p = _cli("version", "--repo", env=env)
    assert p.returncode == 0 and p.stdout.strip() == updates.KIT_REPO
    assert not (tmp_path / "workflow-kit-latest.json").exists()


def test_version_json_names_the_home(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "TMPDIR": str(tmp_path), "WORKFLOW_UPDATE_CHECK": "off"}
    out = json.loads(_cli("version", "--json", env=env).stdout)
    assert out["kit_repo"] == updates.KIT_REPO


def test_weekly_check_reads_the_home_from_the_copy_with_a_fallback():
    t = (KIT / "templates/github/workflow-kit-update.yml").read_text()
    assert "workflow.py version --repo" in t
    assert "KIT: medTech-group" not in t  # no longer a fixed env value
    assert "|| KIT=medTech-group/pairnexus-workflow" in t

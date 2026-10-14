"""Kit 0.1.7: the kit's home in one place, ready for forks."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from workflow import updates, vendor

KIT = Path(__file__).resolve().parents[1]
HOME = re.compile(r"medtech-group/pairnexus-workflow", re.I)

# Where a file a project receives may still name the upstream outright: the one
# constant code reads, the weekly check's fallback for copies older than 0.1.7,
# the bootstrap lines that run before any copy exists, links to the README, and
# the plugin install commands. Anything else reads `workflow version --repo`.
ALLOWED = {
    # The constant itself: 0 once a fork points KIT_REPO at its own repository.
    "scripts/workflow/updates.py": int(updates.KIT_REPO.lower() == "medtech-group/pairnexus-workflow"),
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
    assert found == {k: n for k, n in ALLOWED.items() if n}, (
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


def _kit_lines() -> str:
    """The weekly check's two lines that work out the kit's home."""
    t = (KIT / "templates/github/workflow-kit-update.yml").read_text()
    lines = [l.strip() for l in t.splitlines() if l.strip().startswith(("KIT=$(", '[[ "$KIT"'))]
    assert len(lines) == 2, lines
    return "\n".join(lines)



@pytest.mark.parametrize(
    "cli, expected",
    [
        (None, "medTech-group/pairnexus-workflow"),  # no copy
        ("import sys; sys.exit(2)", "medTech-group/pairnexus-workflow"),  # a 0.1.6 copy: argparse refuses --repo
        ("print('acme/my-kit')", "acme/my-kit"),  # a fork's copy
        ("print('warning: x'); print('acme/my-kit')", "medTech-group/pairnexus-workflow"),  # more than the repo
        ("print('acme/..')", "medTech-group/pairnexus-workflow"),  # not a repository name
        ("print('acme/my-kit'); raise SystemExit(1)", "acme/my-kit"),  # printed, then failed
    ],
)
def test_weekly_check_works_out_the_kits_home(tmp_path, cli, expected):
    if cli is not None:
        (tmp_path / ".claude/workflow/bin").mkdir(parents=True)
        (tmp_path / ".claude/workflow/bin/workflow.py").write_text(cli)
    script = f"set -euo pipefail\n{_kit_lines()}\necho \"$KIT\"\n"
    p = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == expected

"""Tag and publish each kit version that has none yet: the GitHub release
workflow (`.github/workflows/release.yml`) runs it on every push to main.

A version's release point is the last commit on main's first-parent line that
carries it in VERSION, so a README fix merged before the next bump is in it.
A version already tagged is never moved. Its notes are its CHANGELOG entry;
the highest version is marked latest. Standard library and the `gh` CLI only.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def release_points(commits: list[tuple[str, str]]) -> dict[str, str]:
    """{version: sha} from (sha, VERSION) pairs, oldest first: each version's
    last commit. Anything that isn't a plain x.y.z is skipped."""
    points: dict[str, str] = {}
    for sha, version in commits:
        if SEMVER.match(version):
            points[version] = sha
    return points


def notes(changelog: str, version: str) -> str | None:
    m = re.search(rf"^## {re.escape(version)}(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)", changelog, re.S | re.M)
    return m.group(1).strip() if m else None


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main() -> int:
    shas = _git("log", "--first-parent", "--reverse", "--format=%H", "HEAD").split()
    commits = []
    for sha in shas:
        p = subprocess.run(["git", "show", f"{sha}:VERSION"], capture_output=True, text=True)
        if p.returncode == 0:
            commits.append((sha, p.stdout.strip()))
    points = release_points(commits)
    tags = set(_git("tag", "-l", "v*").split())
    changelog = open("CHANGELOG.md", encoding="utf-8").read()
    newest = max(points, key=key) if points else None
    for version in sorted(points, key=key):
        tag = f"v{version}"
        if tag in tags:
            continue
        body = notes(changelog, version)
        if body is None:
            print(f"{tag}: no CHANGELOG entry, not released", file=sys.stderr)
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(body + "\n")
        cmd = ["gh", "release", "create", tag, "--target", points[version], "--title", f"pairnexus-workflow {version}",
               "--notes-file", f.name, f"--latest={'true' if version == newest else 'false'}"]
        subprocess.run(cmd, check=True)
        print(f"released {tag} at {points[version][:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

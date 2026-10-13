"""Publish each kit version that has no GitHub release yet: the release
workflow (`.github/workflows/release.yml`) runs it on every push to main.

A version's release point is the last commit on main's first-parent line that
carries it in VERSION. From now on a version is released as soon as its bump
lands on main, so a later change reaches projects only with the next bump:
every change to shipped files bumps VERSION. (The first run released 0.1.0 to
0.1.4 at their last commits, README fixes included.)

Done means a GitHub release exists, not merely a tag: a tag without a release
(pushed by hand, or a release deleted) gets its release, at the tag as it
stands. A release is never moved. Its notes are its CHANGELOG entry; the
highest version is marked latest. Every version is tried, and any failure
fails the run at the end. Standard library and the `gh` CLI only.
"""

from __future__ import annotations

import json
import os
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


def plan(points: dict[str, str], released: set[str], tags: set[str], changelog: str) -> list[dict]:
    """What to publish: each version with no release, oldest first."""
    newest = max(points, key=key) if points else None
    out = []
    for version in sorted(points, key=key):
        tag = f"v{version}"
        if tag in released:
            continue
        out.append({
            "version": version,
            "tag": tag,
            "target": None if tag in tags else points[version],
            "notes": notes(changelog, version),
            "latest": version == newest,
        })
    return out


def command(step: dict, notes_file: str) -> list[str]:
    cmd = ["gh", "release", "create", step["tag"], "--title", f"pairnexus-workflow {step['version']}",
           "--notes-file", notes_file, f"--latest={'true' if step['latest'] else 'false'}"]
    return cmd + (["--target", step["target"]] if step["target"] else ["--verify-tag"])


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(run=subprocess.run) -> int:
    base = "origin/main" if subprocess.run(["git", "rev-parse", "--verify", "-q", "origin/main"],
                                           capture_output=True).returncode == 0 else "HEAD"
    commits = []
    for sha in _git("log", "--first-parent", "--reverse", "--format=%H", base).split():
        p = subprocess.run(["git", "show", f"{sha}:VERSION"], capture_output=True, text=True)
        if p.returncode == 0:
            commits.append((sha, p.stdout.strip()))
    listed = run(["gh", "release", "list", "--limit", "1000", "--json", "tagName"], capture_output=True, text=True)
    if listed.returncode:
        print(f"gh release list failed: {listed.stderr.strip()}", file=sys.stderr)
        return 1
    released = {r["tagName"] for r in json.loads(listed.stdout or "[]")}
    tags = set(_git("tag", "-l", "v*").split())
    with open("CHANGELOG.md", encoding="utf-8") as f:
        changelog = f.read()
    failed = []
    for step in plan(release_points(commits), released, tags, changelog):
        if step["notes"] is None:
            print(f"{step['tag']}: no CHANGELOG entry, not released", file=sys.stderr)
            failed.append(step["tag"])
            continue
        fd, path = tempfile.mkstemp(suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(step["notes"] + "\n")
            p = run(command(step, path))
        finally:
            os.unlink(path)
        if p.returncode:
            failed.append(step["tag"])
            print(f"{step['tag']}: gh release create failed", file=sys.stderr)
        else:
            print(f"released {step['tag']}" + (f" at {step['target'][:7]}" if step["target"] else " at its tag"))
    if failed:
        print("not released: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Is a newer release of the kit out? The update check.

The project's version is its lock's `kit_version` (vendored) or the kit's own
VERSION (plugin). The latest is the kit's latest GitHub release, read with
`gh api` where the session has it, else GitHub's public API (the kit's
repository is public). Remembered for six hours in the temp directory, so a
session start doesn't ask GitHub each time. Any failure means "don't know":
the check never stops a session, and never updates anything itself.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

KIT_REPO = "medTech-group/pairnexus-workflow"
CACHE_FOR = 6 * 3600
MISS_FOR = 3600  # a lookup that failed isn't tried again for an hour
TIMEOUT = 5
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse(version: str | None) -> tuple[int, int, int] | None:
    m = _SEMVER.match((version or "").strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def newer(latest: str | None, installed: str | None) -> bool:
    a, b = parse(latest), parse(installed)
    return bool(a and b and a > b)


def installed(root: Path, kit_root: Path) -> str | None:
    lock = root / ".claude/workflow/lock.json"
    if lock.exists():
        try:
            v = json.loads(lock.read_text(encoding="utf-8")).get("kit_version")
            return str(v) if parse(v) else None
        except (OSError, ValueError):
            return None
    v = kit_root / "VERSION"
    try:
        text = v.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text if parse(text) else None


def _cache() -> Path:
    return Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / "workflow-kit-latest.json"


def _from_gh() -> str | None:
    try:
        p = subprocess.run(
            ["gh", "api", f"repos/{KIT_REPO}/releases/latest", "--jq", ".tag_name"],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    tag = p.stdout.strip()
    return tag if p.returncode == 0 and parse(tag) else None


def _from_api() -> str | None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{KIT_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "pairnexus-workflow"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            tag = json.loads(r.read().decode("utf-8")).get("tag_name")
    except Exception:  # offline, rate limited, private, anything: "don't know"
        return None
    return tag if parse(tag) else None


def latest(fresh: bool = False, fetch=None) -> str | None:
    """The latest release's version ("0.1.5"), or None when it can't be read.
    `WORKFLOW_UPDATE_CHECK=off` turns the lookup off (the kit's own tests)."""
    if (os.environ.get("WORKFLOW_UPDATE_CHECK") or "").strip().lower() in ("off", "0", "false", "no"):
        return None
    cache = _cache()
    if not fresh:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            age = time.time() - float(data["at"])
            if parse(data.get("latest")) and age < CACHE_FOR:
                return data["latest"]
            if data.get("latest") is None and age < MISS_FOR:
                return None
        except (OSError, ValueError, KeyError, TypeError):
            pass
    tag = fetch() if fetch else (_from_gh() or _from_api())
    version = tag.lstrip("v") if tag else None
    try:
        cache.write_text(json.dumps({"at": time.time(), "latest": version}), encoding="utf-8")
    except OSError:
        pass
    return version


def check(root: Path, kit_root: Path, fresh: bool = False, fetch=None) -> dict:
    have = installed(root, kit_root)
    out = latest(fresh=fresh, fetch=fetch)
    return {"installed": have, "latest": out, "update_available": newer(out, have)}


def notice(result: dict) -> str | None:
    """The line a session start shows when a newer release is out."""
    if not result.get("update_available"):
        return None
    return (
        f"Workflow kit {result['latest']} is out; this project has {result['installed']}. "
        "Offer to update it (the `update-workflow` skill: a pull request the owner merges). "
        "The guided start offers it first; a run's kick-off asks before starting."
    )

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
import math
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

KIT_REPO = "medTech-group/pairnexus-workflow"
CACHE_FOR = 6 * 3600
MISS_FOR = 3600  # a lookup that failed isn't tried again for an hour
TIMEOUT = 5
HOOK_DEADLINE = 8  # the most a session start waits for the check
PLUGIN_UPDATE = "/plugin update pairnexus-workflow@pairnexus"
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse(version) -> tuple[int, int, int] | None:
    if not isinstance(version, str):
        return None
    m = _SEMVER.match(version.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def newer(latest, installed) -> bool:
    a, b = parse(latest), parse(installed)
    return bool(a and b and a > b)


def mode(root: Path) -> str:
    """"vendored" when the project holds a lock, else "plugin"."""
    return "vendored" if (root / ".claude/workflow/lock.json").exists() else "plugin"


def installed(root: Path, kit_root: Path) -> str | None:
    lock = root / ".claude/workflow/lock.json"
    if lock.exists():
        try:
            data = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        v = data.get("kit_version") if isinstance(data, dict) else None
        return v.strip() if parse(v) else None
    try:
        text = (kit_root / "VERSION").read_text(encoding="utf-8").strip()
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


def turned_off() -> bool:
    return (os.environ.get("WORKFLOW_UPDATE_CHECK") or "").strip().lower() in ("off", "0", "false", "no")


def _remembered() -> tuple[bool, str | None]:
    """(found, version): a fresh enough answer from the cache, if any."""
    try:
        data = json.loads(_cache().read_text(encoding="utf-8"))
        age = time.time() - float(data["at"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False, None
    if not math.isfinite(age) or age < 0:  # a clock moved back, or a bad file
        return False, None
    got = data.get("latest")
    if parse(got) and age < CACHE_FOR:
        return True, got.strip().lstrip("v")
    if got is None and age < MISS_FOR:
        return True, None
    return False, None


def _remember(version: str | None) -> None:
    cache = _cache()
    try:
        fd, tmp = tempfile.mkstemp(dir=cache.parent, prefix=".workflow-kit-latest.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"at": time.time(), "latest": version}, f)
        os.replace(tmp, cache)
    except OSError:
        pass


def latest(fresh: bool = False, fetch=None) -> str | None:
    """The latest release's version ("0.1.5"), or None when it can't be read.
    `WORKFLOW_UPDATE_CHECK=off` turns the lookup off (the kit's own tests)."""
    if turned_off():
        return None
    if not fresh:
        found, version = _remembered()
        if found:
            return version
    tag = fetch() if fetch else (_from_gh() or _from_api())
    version = tag.strip().lstrip("v") if parse(tag) else None
    _remember(version)
    return version


def check(root: Path, kit_root: Path, fresh: bool = False, fetch=None) -> dict:
    have = installed(root, kit_root)
    out = latest(fresh=fresh, fetch=fetch)
    return {
        "installed": have,
        "latest": out,
        "update_available": newer(out, have),
        "ahead": newer(have, out),
        "checked": not turned_off(),
        "mode": mode(root),
    }


def check_within(root: Path, kit_root: Path, seconds: float = HOOK_DEADLINE) -> dict | None:
    """`check`, given at most `seconds` (a DNS lookup has no timeout of its
    own); None when it took longer or failed, so a session start never waits
    on GitHub or breaks over it."""
    out: list = []

    def run():
        try:
            out.append(check(root, kit_root))
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(seconds)
    return out[0] if out else None


def how_to_update(result: dict) -> str:
    if result.get("mode") == "plugin":
        return f"type `{PLUGIN_UPDATE}`"
    return "the `update-workflow` skill: a pull request the owner merges"


def notice(result: dict | None, role: str = "attended") -> str | None:
    """The line a session start shows when a newer release is out."""
    if not result or not result.get("update_available"):
        return None
    head = f"Workflow kit {result['latest']} is out; this project has {result['installed']}."
    if role == "conductor":
        return head + " Raise it only at a run's kick-off (`WF version --fresh`), never mid-run: a run stays on its version."
    return (
        f"{head} Offer to update it ({how_to_update(result)}), unless an update pull request is already open. "
        "The guided start offers it first."
    )

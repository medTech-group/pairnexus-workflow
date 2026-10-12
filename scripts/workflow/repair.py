"""Environment repair: the profile's re-runnable commands.

Run at SessionStart, by `workflow repair`, and before each evidence shard, since
a container restart mid-session fires no hook. Never fails the caller: it
reports what each command did.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import time

TIMEOUT = 120
DEADLINE = 240  # the SessionStart hook's own timeout is 300 s


def run(commands: list[str], cwd: Path, timeout: int = TIMEOUT, deadline: int = DEADLINE) -> list[tuple[str, int, str]]:
    results = []
    end = time.monotonic() + deadline
    for c in commands:
        left = end - time.monotonic()
        if left <= 1:
            results.append((c, 124, "skipped: the repair deadline was reached"))
            continue
        try:
            p = subprocess.run(c, shell=True, cwd=cwd, capture_output=True, text=True, timeout=min(timeout, left))
            tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
            results.append((c, p.returncode, tail[0][:200]))
        except subprocess.TimeoutExpired:
            results.append((c, 124, f"timed out after {timeout}s"))
        except OSError as e:
            results.append((c, 127, str(e)[:200]))
    return results


def summary(results: list[tuple[str, int, str]]) -> str:
    if not results:
        return ""
    lines = ["Environment repair (the profile's [repair] commands):"]
    for c, code, tail in results:
        lines.append(f"- {'ok' if code == 0 else f'exit {code}'}: `{c}`" + (f" ({tail})" if code and tail else ""))
    return "\n".join(lines)

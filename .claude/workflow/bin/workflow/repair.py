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
DEADLINE = 240
HOOK_BUDGET = 570  # the SessionStart hook's own timeout is 600 s
CHECK_TIMEOUT = 30


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


def setup(command: str, check: str, cwd: Path, budget: int) -> tuple[str, int, str] | None:
    """The project's own dependencies (`commands.setup`), installed when
    `commands.setup_check` says they're missing: a fresh cloud session starts
    from a fresh clone, and the environment's setup script runs before the
    clone is there. None when there is no check, or the check passes."""
    if not command or not check:
        return None
    try:
        if subprocess.run(check, shell=True, cwd=cwd, capture_output=True, timeout=CHECK_TIMEOUT).returncode == 0:
            return None
    except (subprocess.TimeoutExpired, OSError):
        pass
    try:
        p = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=max(1, budget))
        tail = (p.stdout + p.stderr).strip().splitlines()[-1:] or [""]
        return (command, p.returncode, tail[0][:200])
    except subprocess.TimeoutExpired:
        return (command, 124, f"timed out after {budget}s")
    except OSError as e:
        return (command, 127, str(e)[:200])


def setup_summary(result: tuple[str, int, str] | None) -> str:
    if result is None:
        return ""
    c, code, tail = result
    if code == 0:
        return f"Project setup (commands.setup) ran, as commands.setup_check failed: ok: `{c}`"
    return (
        f"Project setup (commands.setup) FAILED, exit {code}: `{c}` ({tail}). "
        "Tests and typecheck will fail until it succeeds: run it again, or fix what it reports."
    )


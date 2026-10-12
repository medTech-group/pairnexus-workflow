"""Local full-suite evidence for the merge rule.

Runs each suite of the profile in shards against a clean checkout of one
commit, keeping each shard's result on disk under .workflow/evidence/<sha>/,
so a container restart re-runs only the unfinished shards. The report names the
command, head SHA, counts, duration and the failing output's tail, and compares
the count with the base branch's when given, which also catches skipped tests.
"""

from __future__ import annotations

import glob
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import repair
from .profile import Profile, Suite

EVIDENCE_DIR = Path(".workflow/evidence")


class EvidenceError(RuntimeError):
    pass


@dataclass
class ShardResult:
    suite: str
    index: int
    files: list[str]
    exit: int
    passed: int
    failed: int
    skipped: int
    errors: int
    seconds: float
    tail: str


def head_sha(root: Path) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if out.returncode:
        raise EvidenceError("not a git checkout")
    return out.stdout.strip()


def require_clean(root: Path) -> None:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, capture_output=True, text=True)
    dirty = [l for l in out.stdout.splitlines() if not l[3:].startswith(".workflow/")]
    if dirty:
        raise EvidenceError(
            "the working tree has uncommitted changes, so a run wouldn't prove the commit: "
            + ", ".join(l[3:] for l in dirty[:5])
        )


def shards(suite: Suite, root: Path) -> list[list[str]]:
    if not suite.files:
        return [[]]
    files: list[str] = []
    for pat in [p.strip() for p in suite.files.split(",") if p.strip()]:
        files += sorted(str(Path(f).relative_to(root)) for f in glob.glob(str(root / pat), recursive=True))
    files = sorted(dict.fromkeys(files))
    if not files:
        raise EvidenceError(f"suite {suite.name}: no files match {suite.files!r}")
    return [files[i : i + suite.group] for i in range(0, len(files), suite.group)]


def _count(pattern: str, text: str) -> int:
    return sum(int(x) for x in re.findall(pattern, text))


def run_shard(suite: Suite, index: int, files: list[str], root: Path) -> ShardResult:
    cmd = suite.run.replace("{files}", " ".join(_q(f) for f in files))
    t0 = time.monotonic()
    p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True)
    out = p.stdout + p.stderr
    tail = "\n".join(out.strip().splitlines()[-15:])
    return ShardResult(
        suite=suite.name,
        index=index,
        files=files,
        exit=p.returncode,
        passed=_count(suite.passed, _summary(out)),
        failed=_count(suite.failed, _summary(out)),
        skipped=_count(suite.skipped, _summary(out)),
        errors=_count(suite.errors, _summary(out)),
        seconds=round(time.monotonic() - t0, 1),
        tail=tail,
    )


def _summary(out: str) -> str:
    """The last lines, where test runners print their totals."""
    return "\n".join(out.strip().splitlines()[-5:])


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'" if re.search(r"[^\w./-]", s) else s


def collect(profile: Profile, root: Path, only: list[str] | None = None, fresh: bool = False, repair_first: bool = True) -> tuple[str, list[ShardResult]]:
    require_clean(root)
    sha = head_sha(root)
    base = root / EVIDENCE_DIR / sha
    base.mkdir(parents=True, exist_ok=True)
    results: list[ShardResult] = []
    suites = [s for s in profile.suites if not only or s.name in only]
    if not suites:
        raise EvidenceError("the profile has no [[commands.suite]] to run" + (f" named {only}" if only else ""))
    for suite in suites:
        for i, files in enumerate(shards(suite, root)):
            f = base / f"{suite.name}-{i:03d}.json"
            if f.exists() and not fresh:
                r = ShardResult(**json.loads(f.read_text()))
                if r.files == files and r.exit == 0:
                    results.append(r)
                    continue
            if repair_first and profile.repair:
                repair.run(profile.repair, root)
            r = run_shard(suite, i, files, root)
            f.write_text(json.dumps(asdict(r)))
            results.append(r)
            if head_sha(root) != sha:
                raise EvidenceError("HEAD moved while the suite ran; start again on the new commit")
    return sha, results


def report(sha: str, profile: Profile, results: list[ShardResult], base_count: int | None = None) -> tuple[bool, str]:
    by_suite: dict[str, list[ShardResult]] = {}
    for r in results:
        by_suite.setdefault(r.suite, []).append(r)
    ok = all(r.exit == 0 and r.failed == 0 and r.errors == 0 for r in results)
    total = sum(r.passed for r in results)
    lines = [f"**Local full suite on `{sha}`**: {'passed' if ok else 'FAILED'}", ""]
    for s in profile.suites:
        rs = by_suite.get(s.name)
        if not rs:
            continue
        lines.append(
            f"- **{s.name}** (`{s.run}`, {len(rs)} shard{'s' if len(rs) != 1 else ''}): "
            f"{sum(r.passed for r in rs)} passed, {sum(r.failed for r in rs)} failed, "
            f"{sum(r.errors for r in rs)} errors, {sum(r.skipped for r in rs)} skipped, "
            f"{round(sum(r.seconds for r in rs) / 60, 1)} min"
        )
    if base_count is not None:
        if total < base_count:
            ok = False
            lines.append(f"- **Fewer tests than the base branch:** {total} passed here, {base_count} on base. A test was removed or skipped.")
        else:
            lines.append(f"- Base branch: {base_count} passed; this commit: {total}.")
    bad = [r for r in results if r.exit or r.failed or r.errors]
    for r in bad[:3]:
        lines += ["", f"<details><summary>{r.suite} shard {r.index} (exit {r.exit})</summary>", "", "```", r.tail, "```", "</details>"]
    return ok, "\n".join(lines)

"""Local full-suite evidence for the merge rule.

Runs each suite of the profile in shards against a clean checkout of one
commit, keeping each shard's result and full output on disk under
.workflow/evidence/<sha>/, so a container restart re-runs only the unfinished
shards. The report names the command, head SHA, counts, duration and each
suite's output tail, the likely cause of a failure, and compares the count
with the base branch's (given, or run on a worktree of the base), which also
catches skipped tests. With `commands.select_suites` and a base ref, only the
suites a PR's changed files need run, on both (`select`).
"""

from __future__ import annotations

import dataclasses
import fnmatch
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import repair
from .posts import AGENT_MARKER
from .profile import Profile, Suite

EVIDENCE_DIR = Path(".workflow/evidence")
SUMMARY_LINES = 5
TAIL_LINES = 15
SHORT_TAIL = 5
CAUSE_LINES = 15
CAUSE = re.compile(r"Error|error:|Exception|Traceback|failed to|Cannot|refused|[Dd]ocker")
NO_COUNTS = "no test counts found in the output; check the suite's regexes"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
# Lines runners print after their totals that aren't totals (Playwright's report hints).
HINT = re.compile(r"To open last HTML report|Serving HTML report|show-report|Press Ctrl\+C to quit", re.I)
# pytest's summary: "==== 1 failed, 2 passed in 0.50s ====" (-v), or "3 passed in 0.12s" (-q).
PYTEST_BANNER = re.compile(r"^=+ .* in [\d.]+s")
PYTEST_QUIET = re.compile(
    r"^\s*\d+ (?:passed|failed|skipped|errors?|deselected|xfailed|xpassed|warnings?)\b.*\bin [\d.]+s\b"
)
PYTEST = re.compile(r"(?<![\w-])pytest\b")


# The report's first line, which `workflow merge-check` reads back (flow §4.2).
DIRTY = ", on a dirty tree: NOT A PROOF OF THE COMMIT"
FULL = "full suite"
SCOPED = "suites its files need"
_HEADLINE = re.compile(
    rf"\*\*Local (?:{FULL}|{SCOPED}) on `([0-9a-fA-F]{{7,40}})`\*\*: (passed|FAILED)(" + re.escape(DIRTY) + ")?"
)

# A change under these runs every suite: they can change what the selection runs.
DECIDES = (".github/workflows/", ".claude/workflow/")
SELECT_TIMEOUT = 120
# What commands.select_suites prints when no suite is needed (printing nothing runs every suite).
NONE_NEEDED = "none"


class EvidenceError(RuntimeError):
    pass


def headline(sha: str, ok: bool, dirty: bool = False, scoped: bool = False) -> str:
    """The report's first line: `**Local full suite on `<sha>`**: passed`, or
    `**Local suites its files need on `<sha>`**: passed` when some suites
    weren't needed (`select`)."""
    return f"**Local {SCOPED if scoped else FULL} on `{sha}`**: {'passed' if ok else 'FAILED'}{DIRTY if dirty else ''}"


def is_full(line: str) -> bool:
    """Whether a report's first line is the full suite's, not only the suites
    a pull request's files need."""
    return (line or "").strip().startswith(f"**Local {FULL} on ")


def read_headline(line: str) -> tuple[str, bool, bool] | None:
    """(sha, passed, dirty) from a report's first line, or None when the line
    isn't one `headline` writes."""
    m = _HEADLINE.fullmatch((line or "").strip())
    return (m.group(1).lower(), m.group(2) == "passed", bool(m.group(3))) if m else None


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
    run: str = ""
    cwd: str = ""
    log: str = ""
    causes: list[str] = field(default_factory=list)
    previous_failures: list[dict] = field(default_factory=list)

    @property
    def counted(self) -> int:
        return self.passed + self.failed + self.errors

    @property
    def ok(self) -> bool:
        """Exit 0, nothing failed or errored, and the regexes found something: a
        suite that runs nothing fails. A shard whose tests were all skipped counts
        zero tests and passes (the base comparison catches the skips)."""
        return self.exit == 0 and self.failed == 0 and self.errors == 0 and (self.counted > 0 or self.skipped > 0)

    @property
    def problem(self) -> str:
        return NO_COUNTS if self.exit == 0 and self.counted == 0 and self.skipped == 0 else ""

    @classmethod
    def load(cls, f: Path) -> "ShardResult":
        data = json.loads(f.read_text())
        known = {x.name for x in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def head_sha(root: Path) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if out.returncode:
        raise EvidenceError("not a git checkout")
    return out.stdout.strip()


def dirty_paths(root: Path) -> list[str]:
    """Uncommitted changes, and untracked files that aren't ignored, outside .workflow/."""
    out = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
    if out.returncode:
        raise EvidenceError("not a git checkout")
    return [l[3:] for l in out.stdout.splitlines() if l[3:] and not l[3:].startswith(".workflow/")]


def checked_head(root: Path, allow_dirty: bool = False) -> str:
    """HEAD, after the same check `collect` makes, for a run with no suite to run."""
    if not allow_dirty:
        require_clean(root)
    return head_sha(root)


def require_clean(root: Path) -> None:
    dirty = dirty_paths(root)
    if dirty:
        raise EvidenceError(
            "the working tree has uncommitted changes or untracked files, so a run wouldn't prove the commit "
            "(untracked tests change the result): "
            + ", ".join(dirty[:5])
            + (f" and {len(dirty) - 5} more" if len(dirty) > 5 else "")
            + ". Commit, stash or ignore them, or pass --allow-dirty to try a profile."
        )


def shards(suite: Suite, root: Path, empty_ok: bool = False) -> list[list[str]]:
    """Each shard's files, relative to the suite's cwd (the root when it has none).
    The `files` globs are relative to the project root, even when cwd is set. With
    empty_ok, a suite whose globs match nothing has no shards (for the base
    branch, which may not have the suite's files yet)."""
    if not suite.files:
        return [[]]
    files: list[str] = []
    for pat in [p.strip() for p in suite.files.split(",") if p.strip()]:
        files += sorted(str(Path(f).relative_to(root)) for f in glob.glob(str(root / pat), recursive=True))
    files = sorted(dict.fromkeys(files))
    if not files:
        if empty_ok:
            return []
        raise EvidenceError(f"suite {suite.name}: no files match {suite.files!r}")
    if suite.cwd:
        files = [os.path.relpath(root / f, root / suite.cwd) for f in files]
    return [files[i : i + suite.group] for i in range(0, len(files), suite.group)]


def _count(pattern: str, text: str) -> int:
    return sum(int(x) for x in re.findall(pattern, text) if str(x).isdigit())


def _lines(out: str) -> list[str]:
    """The output's lines without ANSI codes, blank lines and report hints."""
    lines = [ANSI.sub("", l).rstrip() for l in (out or "").splitlines()]
    return [l for l in lines if l.strip() and not HINT.search(l)]


def _summary(out: str) -> str:
    """The last lines, where test runners print their totals."""
    return "\n".join(_lines(out)[-SUMMARY_LINES:])


def _pytest_summary(out: str) -> str | None:
    """pytest's own summary line: the last `=== … in 0.5s ===` banner, or a final
    quiet `3 passed in 0.12s`; None when there is neither."""
    lines = _lines(out)
    banners = [l for l in lines if PYTEST_BANNER.match(l.strip())]
    if banners:
        return banners[-1]
    if lines and PYTEST_QUIET.match(lines[-1]):
        return lines[-1]
    return None


def counts(suite: Suite, stdout: str, stderr: str) -> dict[str, int]:
    """The counts from the runner's summary: for pytest its summary line only, so a
    failure message holding "3 passed" isn't added; otherwise the last lines of
    stdout, else of stderr (jest prints its totals there). With the suite's
    `total` regex, passed is the total less the skipped, failed and errors."""
    keys = ("passed", "failed", "skipped", "errors")
    pytest = bool(PYTEST.search(suite.run))
    for out in (stdout, stderr):
        text = (_pytest_summary(out) if pytest else None) or _summary(out)
        c = {k: _count(getattr(suite, k), text) for k in keys}
        if suite.total:
            total = _count(suite.total, text)
            c["passed"] = max(0, total - c["skipped"] - c["failed"] - c["errors"])
        if any(c.values()):
            return c
    return dict.fromkeys(keys, 0)


def causes(out: str) -> list[str]:
    """The first lines that look like the cause of a failure."""
    found = []
    for line in out.splitlines():
        if CAUSE.search(line):
            found.append(line.rstrip()[:300])
            if len(found) == CAUSE_LINES:
                break
    return found


def run_shard(
    suite: Suite, index: int, files: list[str], root: Path, log: Path | None = None, log_root: Path | None = None
) -> ShardResult:
    cmd = suite.run.replace("{files}", " ".join(_q(f) for f in files))
    cwd = root / suite.cwd if suite.cwd else root
    log_root = log_root or root
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    except OSError as e:  # the suite's cwd is missing, or the shell can't start
        why = f"couldn't run the suite in `{suite.cwd or '.'}`: {e.strerror or e}" + (
            f" (the suite's cwd `{suite.cwd}` doesn't exist here)" if suite.cwd and not cwd.is_dir() else ""
        )
        p = subprocess.CompletedProcess(cmd, 127, "", why)
    seconds = round(time.monotonic() - t0, 1)
    out = p.stdout + p.stderr
    log_name = ""
    if log is not None:
        log.write_text(
            f"$ {cmd}\n# cwd: {cwd}\n# exit: {p.returncode}\n\n--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}",
            encoding="utf-8",
        )
        log_name = str(log.relative_to(log_root)) if log.is_relative_to(log_root) else str(log)
    r = ShardResult(
        suite=suite.name,
        index=index,
        files=files,
        exit=p.returncode,
        seconds=seconds,
        tail="\n".join(out.strip().splitlines()[-TAIL_LINES:]),
        run=suite.run,
        cwd=suite.cwd,
        log=log_name,
        **counts(suite, p.stdout, p.stderr),
    )
    if not r.ok:
        r.causes = causes(out)
    return r


def _q(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'" if re.search(r"[^\w./-]", s) else s


def _next_log(base: Path, stem: str) -> Path:
    """`<stem>.<attempt>.log`, the attempt one more than any kept, so each
    attempt's output stays where previous_failures points."""
    seen = [0]
    for f in base.glob(f"{glob.escape(stem)}.*.log"):
        n = f.name[len(stem) + 1 : -len(".log")]
        if n.isdigit():
            seen.append(int(n))
    return base / f"{stem}.{max(seen) + 1}.log"


def collect(
    profile: Profile,
    root: Path,
    only: list[str] | None = None,
    fresh: bool = False,
    repair_first: bool = True,
    allow_dirty: bool = False,
    store: Path | None = None,
    empty_ok: bool = False,
    notes: list[str] | None = None,
    clean_check: bool = True,
) -> tuple[str, list[ShardResult]]:
    """Run (or resume) every shard of the suites on HEAD.

    With allow_dirty a dirty tree runs anyway, kept apart from the commit's
    evidence (<sha>-dirty) and never reused. The profile's repair commands run
    once, and again before a shard only when the shard before it failed. Each
    attempt's output is kept as `<suite>-NNN.<attempt>.log`. With empty_ok a
    suite whose files match nothing counts 0, with a line added to `notes`.
    Without clean_check (the base worktree, fresh from git, where only
    commands.setup has written) the tree isn't checked.
    """
    if allow_dirty:
        dirty = dirty_paths(root)
    else:
        if clean_check:
            require_clean(root)
        dirty = []
    sha = head_sha(root)
    base = (store or root / EVIDENCE_DIR) / (sha + ("-dirty" if dirty else ""))
    if dirty:
        shutil.rmtree(base, ignore_errors=True)
        fresh = True
    base.mkdir(parents=True, exist_ok=True)
    results: list[ShardResult] = []
    suites = [s for s in profile.suites if not only or s.name in only]
    if not suites:
        raise EvidenceError("the profile has no [[commands.suite]] to run" + (f" named {only}" if only else ""))
    repaired = False
    last_failed = False
    log_root = store.parent.parent if store else root
    for suite in suites:
        if empty_ok and suite.cwd and not (root / suite.cwd).is_dir():
            if notes is not None:
                notes.append(f"suite {suite.name}: its cwd `{suite.cwd}` doesn't exist here, so it counts 0")
            continue
        parts = shards(suite, root, empty_ok=empty_ok)
        if not parts and notes is not None:
            notes.append(f"suite {suite.name}: no files match {suite.files!r} here, so it counts 0")
        for i, files in enumerate(parts):
            f = base / f"{suite.name}-{i:03d}.json"
            earlier: list[dict] = []
            if f.exists():
                old = ShardResult.load(f)
                same = old.files == files and old.run == suite.run and old.cwd == suite.cwd
                if same and old.ok and not fresh:
                    results.append(old)
                    continue
                if same:
                    earlier = list(old.previous_failures)
                    if not old.ok:
                        earlier.append(
                            {"exit": old.exit, "passed": old.passed, "failed": old.failed, "errors": old.errors, "log": old.log}
                        )
            if repair_first and profile.repair and (not repaired or last_failed):
                repair.run(profile.repair, root)
                repaired = True
            r = run_shard(suite, i, files, root, log=_next_log(base, f"{suite.name}-{i:03d}"), log_root=log_root)
            r.previous_failures = earlier
            f.write_text(json.dumps(asdict(r)))
            results.append(r)
            last_failed = not r.ok
            if head_sha(root) != sha:
                raise EvidenceError("HEAD moved while the suite ran; start again on the new commit")
    return sha, results


def resolve_ref(root: Path, ref: str) -> str:
    """The commit `ref` names here, or an EvidenceError at once."""
    p = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=root, capture_output=True, text=True)
    if p.returncode or not p.stdout.strip():
        raise EvidenceError(f"--base-ref {ref}: not a commit here ({(p.stderr.strip() or 'unknown revision')[:200]})")
    return p.stdout.strip()


@dataclass
class Selection:
    """Which suites a PR's changed files need. `names` None: every suite, with
    `why` (empty when the profile has no `commands.select_suites`)."""

    names: list[str] | None
    why: str = ""
    command: str = ""
    against: str = ""
    skipped: list[str] = field(default_factory=list)


def changed_paths(root: Path, base_sha: str) -> list[str]:
    """The paths changed since the merge base with `base_sha`; a rename is its
    old path and its new one."""
    p = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z", f"{base_sha}...HEAD"], cwd=root, capture_output=True)
    if p.returncode:
        raise EvidenceError((p.stderr.decode(errors="replace").strip() or f"git diff exited {p.returncode}")[:300])
    try:
        paths = [x for x in p.stdout.decode("utf-8").split("\0") if x]
    except UnicodeDecodeError:
        raise EvidenceError("a changed path isn't UTF-8")
    if any("\n" in x or "\r" in x for x in paths):
        raise EvidenceError("a changed path has a line break in it")
    return paths


def _tests_of(suite: Suite, path: str) -> bool:
    """Whether `path` is (or was) one of the suite's test files, by its `files`
    globs; `fnmatch` lets `*` cross folders, so it errs towards running it."""
    for pat in [x.strip() for x in suite.files.split(",") if x.strip()]:
        if fnmatch.fnmatchcase(path, pat) or fnmatch.fnmatchcase(path, pat.replace("**/", "")):
            return True
    return False


def _base_branch_sha(root: Path, branch: str) -> str:
    p = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}^{{commit}}"], cwd=root, capture_output=True, text=True
    )
    return p.stdout.strip() if p.returncode == 0 else ""


def _run_selector(cmd: str, root: Path, base_sha: str, paths: list[str]) -> subprocess.CompletedProcess:
    """The command as the base branch has it: run in a worktree of `base_sha`
    (no `commands.setup`), so nothing the branch changes decides what runs."""
    wt = root / ".workflow" / f"select-{base_sha}"

    def remove() -> None:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=root, capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True)

    if wt.exists():
        remove()
    wt.parent.mkdir(parents=True, exist_ok=True)
    add = subprocess.run(["git", "worktree", "add", "--detach", str(wt), base_sha], cwd=root, capture_output=True, text=True)
    if add.returncode:
        raise OSError(f"couldn't add a worktree of the base ({add.stderr.strip()[:200]})")
    try:
        return subprocess.run(
            cmd, shell=True, cwd=wt, input="".join(f"{x}\n" for x in paths), capture_output=True, text=True, timeout=SELECT_TIMEOUT
        )
    finally:
        remove()


def select(profile: Profile, root: Path, ref: str, base_sha: str) -> Selection:
    """The suites the files changed since `ref` need, by the profile's
    `commands.select_suites`, run as the base branch has it (`_run_selector`):
    given the paths one a line on stdin, it prints a suite's name a line, or
    `none` when no suite is needed. A suite one of whose test files changed
    always runs. Every suite runs when the setting is unset, the profile says
    `ci.none`, `ref` isn't `origin/<base_branch>`, the paths can't be listed or
    none changed, a path is one that decides (`DECIDES`, or a file the command
    names), or the command fails, times out, prints nothing or names a suite
    the profile hasn't."""
    cmd = profile.select_suites
    if not cmd or not profile.suites:
        return Selection(None)

    def every(why: str) -> Selection:
        return Selection(None, why=why, command=cmd, against=ref)

    if profile.ci_none:
        return every("the profile says `ci.none`, so this report is the only proof of the commit")
    base = profile.base_branch
    if base_sha != _base_branch_sha(root, base):
        return every(f"`{ref}` isn't `origin/{base}` as fetched here, so the files changed since it may not be all the branch's")
    try:
        paths = changed_paths(root, base_sha)
    except EvidenceError as e:
        return every(f"couldn't list the files changed since `{ref}` ({e})")
    if not paths:
        return every(f"no file changed since `{ref}`")
    try:
        named = {w.removeprefix("./") for w in shlex.split(cmd)}
    except ValueError:
        named = set()
    for path in paths:
        if any(path.startswith(d) if d.endswith("/") else path == d for d in DECIDES):
            return every(f"`{path}` changed, and a change there can change what runs")
        if path in named:
            return every(f"`{path}`, which commands.select_suites runs, changed")
    try:
        p = _run_selector(cmd, root, base_sha, paths)
    except subprocess.TimeoutExpired:
        return every(f"`{cmd}` didn't finish in {SELECT_TIMEOUT} seconds")
    except OSError as e:
        return every(f"couldn't run `{cmd}` ({getattr(e, 'strerror', None) or e})")
    if p.returncode:
        tail = " ".join((p.stderr or p.stdout).strip().splitlines()[-2:])[:200]
        return every(f"`{cmd}` exited {p.returncode}" + (f": {tail}" if tail else ""))
    names = list(dict.fromkeys(x.strip() for x in p.stdout.splitlines() if x.strip()))
    if not names:
        return every(f"`{cmd}` printed no suite (it prints `{NONE_NEEDED}` when none is needed)")
    if names == [NONE_NEEDED]:
        names = []
    known = [s.name for s in profile.suites]
    unknown = [n for n in names if n not in known]
    if unknown:
        return every(f"`{cmd}` named {unknown[0][:60]!r}, which isn't a suite of the profile")
    names += [s.name for s in profile.suites if any(_tests_of(s, x) for x in paths)]
    return Selection(
        [n for n in known if n in names], command=cmd, against=ref, skipped=[n for n in known if n not in names]
    )


def _and(names: list[str]) -> str:
    if not names:
        return "no suite"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _selection_line(sel: Selection) -> str:
    if sel.names is None:
        return f"- **Every suite ran:** {sel.why}." if sel.why else ""
    given = f"the files changed since `{sel.against}`"
    if not sel.names:
        return f"- **No suite needed** for {given} (`{sel.command}`): {_and(sel.skipped)} didn't run."
    if not sel.skipped:
        return f"- Every suite was needed for {given} (`{sel.command}`)."
    return (
        f"- **Only the suites this PR's files need** (`{sel.command}`, given {given}): "
        f"ran {', '.join(sel.names)}; not needed: {', '.join(sel.skipped)}."
    )


@dataclass
class BaseCount:
    """The base branch's count. `problem` is set when there is no usable count:
    the base run errored or a shard failed, so nothing can be compared."""

    ref: str
    sha: str
    count: int | None
    notes: list[str] = field(default_factory=list)
    problem: str = ""


def base_count_from_ref(
    profile: Profile, root: Path, ref: str, only: list[str] | None = None, fresh: bool = False, sha: str | None = None
) -> BaseCount:
    """Run the same suites on a worktree of `ref` under .workflow/base-<sha>/, then
    remove it. The profile's `commands.setup` runs there first; nothing else is
    copied or linked in. A suite whose files match nothing on the base, or whose
    cwd isn't there, counts 0, with a note. Never raises for the base run itself: a run that errors or a
    shard that fails gives a BaseCount with `problem` and no count."""
    base_sha = sha or resolve_ref(root, ref)
    out = BaseCount(ref=ref, sha=base_sha, count=None)
    wt = root / ".workflow" / f"base-{base_sha}"

    def remove() -> None:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=root, capture_output=True)
        shutil.rmtree(wt, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True)

    if wt.exists():
        remove()
    wt.parent.mkdir(parents=True, exist_ok=True)
    add = subprocess.run(["git", "worktree", "add", "--detach", str(wt), base_sha], cwd=root, capture_output=True, text=True)
    if add.returncode:
        out.problem = f"couldn't add a worktree ({add.stderr.strip()[:300]})"
        return out
    try:
        if profile.setup:
            p = subprocess.run(profile.setup, shell=True, cwd=wt, capture_output=True, text=True)
            if p.returncode:
                tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-3:])
                out.problem = f"commands.setup (`{profile.setup}`) exited {p.returncode} in the base worktree: {tail[:300]}"
                return out
        prof = dataclasses.replace(profile, root=wt)
        _, results = collect(
            prof, wt, only=only, fresh=fresh, store=root / EVIDENCE_DIR, empty_ok=True, notes=out.notes, clean_check=False
        )
    except EvidenceError as e:
        out.problem = str(e)
        return out
    except OSError as e:
        out.problem = f"couldn't run the suites in the base worktree ({type(e).__name__}: {e})"
        return out
    finally:
        remove()
    bad = [r for r in results if not r.ok]
    if bad:
        r = bad[0]
        why = r.problem or f"exit {r.exit}, {r.failed} failed, {r.errors} errors"
        out.problem = f"{r.suite} shard {r.index} didn't pass there ({why})" + (
            f" and {len(bad) - 1} more" if len(bad) > 1 else ""
        )
        return out
    out.count = sum(r.passed for r in results)
    return out


def _short_tail(text: str) -> str:
    return "\n".join(text.strip().splitlines()[-SHORT_TAIL:])


def report(
    sha: str,
    profile: Profile,
    results: list[ShardResult],
    base_count: int | None = None,
    dirty: list[str] | None = None,
    base_label: str = "",
    base_problem: str = "",
    base_notes: list[str] | None = None,
    selection: Selection | None = None,
) -> tuple[bool, str]:
    """The evidence as Markdown, and whether it passes. `base_problem` (no usable
    base count, e.g. "no usable base count from main: …") doesn't fail it: the
    commit's own result stands, and the report says plainly that the count
    wasn't compared, so a base branch with its own failure doesn't block every
    PR (the conductor opens an infra ticket for it instead). `selection` says
    which suites the PR's files needed; with none needed, nothing is compared."""
    by_suite: dict[str, list[ShardResult]] = {}
    for r in results:
        by_suite.setdefault(r.suite, []).append(r)
    ok = all(r.ok for r in results)
    total = sum(r.passed for r in results)
    errors = sum(r.errors for r in results)
    lines = ["", ""]  # the headline goes in last, once the base comparison is known
    if dirty:
        lines += [
            f"> **Not a proof of the commit.** Run with --allow-dirty on a working tree with {len(dirty)} "
            f"uncommitted or untracked path{'s' if len(dirty) != 1 else ''} ({', '.join(dirty[:5])}"
            f"{', …' if len(dirty) > 5 else ''}). Use it to try a profile, never for the merge rule.",
            "",
        ]
    sel = selection or Selection(None)
    if _selection_line(sel):
        lines.append(_selection_line(sel))
    for s in profile.suites:
        rs = by_suite.get(s.name)
        if not rs:
            continue
        line = (
            f"- **{s.name}** (`{s.run}`{f' in `{s.cwd}`' if s.cwd else ''}, {len(rs)} shard{'s' if len(rs) != 1 else ''}): "
            f"{sum(r.passed for r in rs)} passed, {sum(r.failed for r in rs)} failed, "
            f"{sum(r.errors for r in rs)} errors, {sum(r.skipped for r in rs)} skipped, "
            f"{round(sum(r.seconds for r in rs) / 60, 1)} min"
        )
        for r in rs:
            if r.ok and r.previous_failures:
                n = len(r.previous_failures)
                line += f"; shard {r.index} passed on retry after {n} failure{'s' if n != 1 else ''}"
            if r.problem:
                line += f"; shard {r.index}: {r.problem}"
            elif r.ok and r.counted == 0:
                line += f"; shard {r.index}: every test was skipped"
        lines.append(line)
        tail = _short_tail(rs[-1].tail)
        if tail:
            lines += ["  ```", *("  " + x for x in tail.splitlines()), "  ```"]
    if sel.names == []:
        pass  # nothing ran, so there is nothing to compare
    elif base_problem:
        lines.append(
            f"- **Not compared with the base branch:** {base_problem}. This shows the commit's own tests pass, "
            "not that none were removed or skipped; fix the base branch's suite (an infra ticket)."
        )
    elif base_count is not None:
        where = f" ({base_label})" if base_label else ""
        if total < base_count:
            ok = False
            why = (
                "Fewer tests passed than on the base branch, and some errored: the environment may be failing (see the errors above)."
                if errors
                else "A test was removed or skipped."
            )
            lines.append(f"- **Fewer tests than the base branch{where}:** {total} passed here, {base_count} on base. {why}")
        else:
            lines.append(f"- Base branch{where}: {base_count} passed; this commit: {total}.")
    else:
        lines.append("- No base-branch count given: this doesn't show whether tests were removed.")
    for n in base_notes or []:
        lines.append(f"- Base branch: {n}.")
    for r in [r for r in results if not r.ok][:3]:
        lines += ["", f"<details><summary>{r.suite} shard {r.index} (exit {r.exit})</summary>", ""]
        if r.problem:
            lines += [r.problem, ""]
        if r.causes:
            lines += ["Likely cause:", "", "```", *r.causes, "```", ""]
        lines += ["Tail:", "", "```", r.tail, "```"]
        if r.log:
            lines += ["", f"Full output: `{r.log}`"]
        lines.append("</details>")
    scoped = {r.suite for r in results} != {s.name for s in profile.suites}
    lines[0] = headline(sha, ok, bool(dirty), scoped=scoped)
    # The session posts this report on its PR: an agent's post, so it carries the marker.
    lines += ["", AGENT_MARKER]
    return ok, "\n".join(lines)

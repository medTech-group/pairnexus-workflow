"""`workflow`: the kit's command line. Python 3.11+, standard library only.

    workflow profile check
    workflow status [--issues F --prs F | --fetch] [--json]
    workflow doctor [--claude-version VERSION] [--rulesets F] [--repo F] [--environments F] [--runs F] [--checks F] [--prs F] [--json] [--strict]      (what's set up and what isn't; changes nothing)
    workflow protection --rulesets F [--repo F] [--base BRANCH] [--json]
    workflow protection --protect --repo F [--base BRANCH] [--check NAME ...] [--json]
    workflow protection --require-checks F --check NAME [--check NAME ...] [--json]
    workflow protection --checks-ran F [--statuses F] --rulesets F --repo F [--base BRANCH] [--json]
    workflow version [--fresh] [--json] | --repo | --starter
    workflow ready [--issues F --prs F | --fetch] [--exclude 1,2] [--only 1,2] [--override 3] [--running-area A ...] [--slots N] [--json]
    workflow charter defaults [--unprotected] | validate F [--approved] [--unprotected] | markdown F [--tickets 13:area,143:-] [--estimate F] | diff OLD NEW | reuse OLD | pin-plan F | questions [--unprotected]
    workflow charter estimate F [--tickets N | 13:area,143:-] [--runs F] [--security 13,143] [--now ISO] [--json]
    workflow charter splice --body F --charter F [--out F] [--tickets 13:area,143:-] [--estimate F]
    workflow state init --charter F --run-id ID [--by-hand N] [--read-through ID] | get --body F | put --body F --state F [--out F] | patch --body F --patch F [--out F]
    workflow render --template F --ticket F --charter F --slots F --tracking N [--by-hand N] [--out F] [--print]
    workflow comments --file F [--owner LOGIN] [--since-id N]
    workflow merge-check --pr F --files F --commits F --checks F --rulesets F --threads F --reviews F --comments F --permissions F --compare F [--preview F] [--asker LOGIN] [--review-rounds N] [--json]
    workflow merge-check --fetch N [any of the files above] [--charter F --check-logs DIR] [--asker LOGIN] [--review-rounds N] [--json]
    workflow preview --comments F --checks F --sha SHA [--json] | --fetch N [any of those] [--json]
    workflow briefing verify --file F
    workflow review-record --kind round|pass --round N --commit SHA --reviewers NAMES --clean|--not-clean
    workflow review-record [--kind spec] --round N --body F --reviewers spec,correctness --clean|--not-clean      (a spec's review, keyed to its body's SHA-256)
    workflow pr-template [--existing FILE]      (prints the file to write; exits 3 for a folder of templates)
    workflow adopt --owner LOGIN --repo OWNER/NAME --name NAME [--project DIR]      (a copy of the starter made yours)
    workflow evidence [--suite NAME ... | --all] [--base-count N | --base-ref BRANCH] [--fresh] [--allow-dirty]
        (with --base-ref and commands.select_suites, only the suites the changed files need)
    workflow repair
    workflow vendor install|update [--kit DIR] [--mattpocock DIR | --no-mattpocock] [--project DIR] [--adopt] [--strict-pin]
        (--kit defaults to the checkout this CLI runs from: give it when running a project's vendored copy)
    workflow vendor verify [--project DIR] [--strict] | resolve [--keep] PATH [--project DIR]
    workflow hook guard|gate|context|repair      (reads the hook's JSON on stdin)
"""

from __future__ import annotations

import argparse
import json
import contextlib
import os
import re
import shutil
import signal
import time
import subprocess
import sys
import threading
from pathlib import Path

_STARTED = time.monotonic()  # the guard's time budget counts from here, before the kit's modules load

from . import adopt as adopt_mod
from . import charter as charter_mod
from . import context as context_mod
from . import doctor as doctor_mod
from . import estimate as estimate_mod
from . import evidence as evidence_mod
from . import fetch as fetch_mod
from . import _old_python, fallback
from . import gate as gate_mod
from . import guard as guard_mod
from . import issues as issues_mod
from . import merge as merge_mod
from . import posts as posts_mod
from . import previews as previews_mod
from . import pr_template as pr_template_mod
from . import protection as protection_mod
from . import render as render_mod
from . import repair as repair_mod
from . import reviews as reviews_mod
from . import roles
from . import state as state_mod
from . import status as status_mod
from . import updates as updates_mod
from . import vendor as vendor_mod
from .profile import PROFILE_PATH, ProfileError, load, project_root, resolve_experience

KIT_ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def _json(path: str):
    return json.loads(_read(path))


def _out(obj) -> None:
    print(json.dumps(obj, indent=2) if not isinstance(obj, str) else obj)


def _fetch(repo: str, what: str) -> list[dict]:
    """Through `gh api` (the GitHub CLI, or Claude Code's built-in client).

    `--paginate --slurp` gives a list of pages; a client without `--slurp`
    prints the pages one after another, which are decoded one by one. The
    issues list keeps its pull requests: readiness resolves a PR blocker by them.
    """
    path = f"repos/{repo}/issues?state=all&per_page=100" if what == "issues" else f"repos/{repo}/pulls?state=open&per_page=100"

    def failed(p) -> SystemExit:
        return SystemExit(f"gh api {path} failed: {p.stderr.strip()[:300]}\nFetch with the GitHub MCP tools instead and pass --issues/--prs files.")

    p = subprocess.run(["gh", "api", "--paginate", "--slurp", path], capture_output=True, text=True)
    values: list = []
    if p.returncode == 0:
        values = [json.loads(p.stdout or "[]")]
    elif "slurp" in (p.stderr + p.stdout).lower():
        p = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True)
        if p.returncode:
            raise failed(p)
        try:
            values = posts_mod.decode_values(p.stdout)
        except posts_mod.CommentsError as e:
            raise SystemExit(f"gh api {path}: couldn't read its output ({e})")
    else:
        raise failed(p)
    items: list[dict] = []

    def add(v) -> None:
        if isinstance(v, list):
            for x in v:
                add(x)
        elif isinstance(v, dict):
            items.append(v)

    add(values)
    return items


# ---------- commands ----------


def cmd_profile(a) -> int:
    from . import profile as profile_mod

    prof = load()
    warnings = profile_mod.check(prof)
    _out({"ok": True, "warnings": warnings, **profile_mod.summary(prof)})
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return 0


def cmd_ready(a) -> int:
    prof = load(required=False)
    try:
        exclude = issues_mod.parse_numbers(a.exclude)
        only = issues_mod.parse_numbers(a.only) if a.only is not None else None
        overrides = issues_mod.parse_numbers(a.override)
        if only is not None and not only:
            raise ValueError("--only was given no ticket numbers")
    except ValueError as e:
        print(f"workflow ready: {e} (give numbers separated by commas, e.g. 13,#143)", file=sys.stderr)
        return 2
    if a.fetch:
        if not prof:
            raise SystemExit("--fetch needs a profile (project.repo)")
        issues, prs = _fetch(prof.repo, "issues"), _fetch(prof.repo, "pulls")
    else:
        if not a.issues or not a.prs:
            raise SystemExit("give --issues and --prs (JSON files, as the GitHub API returns them), or --fetch")
        issues, prs = _json(a.issues), _json(a.prs)
    verdicts = issues_mod.readiness(
        issues,
        prs,
        exclude=exclude,
        repo=prof.repo if prof else None,
        areas=list(prof.areas) if prof else None,
        protected=list(prof.protected_paths) if prof else None,
    )
    if only is not None:
        missing = sorted(only - {v.number for v in verdicts})
        verdicts = [v for v in verdicts if v.number in only]
        for n in missing:
            print(f"workflow ready: #{n} isn't an open ready-for-agent build ticket", file=sys.stderr)
    slots = a.slots if a.slots is not None else (prof.max_parallel if prof else 2)
    running = [r.strip().casefold() for r in a.running_area or [] if r and r.strip()]
    start = issues_mod.startable(verdicts, running, max(0, slots), overrides=overrides)
    if a.json:
        _out(
            {
                "ready": [v.__dict__ for v in verdicts if v.ready],
                "not_ready": [v.__dict__ for v in verdicts if not v.ready],
                "start_now": [v.number for v in start],
            }
        )
    else:
        for v in verdicts:
            mark = "READY" if v.ready else "wait "
            why = "" if v.ready else " — " + "; ".join(v.reasons)
            print(f"{mark} #{v.number} [{v.area or '-'}] {v.title}{why}")
            for note in v.notes:
                print(f"      note: {note}")
        print("start now: " + (", ".join(f"#{v.number}" for v in start) or "nothing"))
    return 0


def cmd_status(a) -> int:
    """Where the project stands, for the guided start (`skills/start`), with
    doctor's local gaps (#62): its local checks only, so no network call."""
    root = project_root()
    prof, error = _read_profile(root)
    issues = prs = None
    if a.fetch:
        if error:
            print("workflow status: the kit's profile has an error, so issues weren't read (see kit.profile)", file=sys.stderr)
        elif not prof:
            print("workflow status: the kit isn't set up here, so issues weren't read (--fetch needs the profile's project.repo)", file=sys.stderr)
        else:
            issues, prs = _fetch(prof.repo, "issues"), _fetch(prof.repo, "pulls")
    elif a.issues or a.prs:
        if not a.issues or not a.prs:
            raise SystemExit("give both --issues and --prs (JSON files, as the GitHub API returns them), or --fetch")
        issues, prs = _json(a.issues), _json(a.prs)
    experience = resolve_experience(root, prof.experience if prof else None)
    try:
        local = doctor_mod.report(
            doctor_mod.Inputs(root=root, kit_root=KIT_ROOT, profile=prof, profile_error=error, experience=experience, gaps_only=True),
            doctor_mod.LOCAL_CHECKS,
        )
    except KeyboardInterrupt:  # Ctrl-C while `python3` runs: a quiet stop, as doctor's
        print("workflow status: stopped", file=sys.stderr)
        return 130
    st = status_mod.snapshot(
        root,
        prof is not None or error is not None,
        issues,
        prs,
        repo=prof.repo if prof else None,
        areas=list(prof.areas) if prof else None,
        protected=list(prof.protected_paths) if prof else None,
        ruleset=prof.ruleset if prof else None,
        experience=experience,
        local_gaps=[ln.as_dict(local.wording) for ln in local.lines if ln.status == "gap"],
        profile_error=error is not None,
    )
    kit = updates_mod.check(root, KIT_ROOT) if a.fetch else {"installed": updates_mod.installed(root, KIT_ROOT)}
    if a.json:
        _out({**st.as_dict(), "kit": kit})
    else:
        print(status_mod.text(st))
        print(_kit_line(kit))
    return 0


def _given_file(path: str | None) -> Path | str | None:
    """A file given to doctor: absolute, as the current directory has it;
    `-` (standard input) and an empty path as they are."""
    return path if path in (None, "", "-") else Path(path).absolute()


def _read_profile(root: Path):
    """(the profile, None), or (None, `profile check`'s error) for one that
    can't be used, as doctor reads it; (None, None) with no profile."""
    try:
        if (root / PROFILE_PATH).exists() and not (root / PROFILE_PATH).is_file():
            raise ProfileError(f"{PROFILE_PATH} isn't a file")  # a directory, or a pipe that would block the read
        return load(root, required=False), None
    except ProfileError as e:
        return None, str(e)
    except UnicodeDecodeError:
        return None, f"{PROFILE_PATH} isn't UTF-8 text"
    except (OSError, ValueError) as e:
        return None, f"{PROFILE_PATH} can't be read ({type(e).__name__})"


def cmd_doctor(a) -> int:
    """What's set up and what isn't, each line with its fix (#34). Exits 0,
    or with --strict 1 on a gap or a line it couldn't check."""
    if [a.rulesets, a.repo, a.environments, a.runs, a.checks, a.prs].count("-") > 1:
        print("workflow doctor: only one of --rulesets, --repo, --environments, --runs, --checks and --prs can be standard input (-)", file=sys.stderr)
        return 2
    root = project_root()
    prof, error = _read_profile(root)
    try:
        r = doctor_mod.report(
            doctor_mod.Inputs(
                root=root,
                kit_root=KIT_ROOT,
                profile=prof,
                profile_error=error,
                experience=resolve_experience(root, prof.experience if prof else None),
                claude_version=a.claude_version,
                rulesets_file=_given_file(a.rulesets),
                repo_file=_given_file(a.repo),
                environments_file=_given_file(a.environments),
                runs_file=_given_file(a.runs),
                checks_file=_given_file(a.checks),
                prs_file=_given_file(a.prs),
            )
        )
    except KeyboardInterrupt:  # Ctrl-C: a quiet stop (what it ran is already killed)
        print("workflow doctor: stopped", file=sys.stderr)
        return 130
    _out(r.as_dict() if a.json else doctor_mod.text(r, min(100, shutil.get_terminal_size((100, 24)).columns)))
    return 1 if a.strict and not r.strict_ok() else 0


def cmd_protection(a) -> int:
    """The base branch's protection, from GitHub's JSON: the read-back, the
    requests to protect it or require checks, or the checks that ran. Builds and
    prints; sends nothing and writes nothing."""

    def given(path: str, what: str):
        if not path:
            raise protection_mod.ProtectionError(f"the {what} file was given no path")
        if path == "-" and sys.stdin is None:
            raise protection_mod.ProtectionError(f"the {what} file is standard input (-), and standard input is closed")
        try:
            return protection_mod.loads(_read(path))
        except OSError as e:
            raise protection_mod.ProtectionError(f"can't read the {what} file {path}: {e.strerror or e}") from e
        except (ValueError, RecursionError) as e:  # ValueError: bad JSON, NaN, bad UTF-8, a number too long
            why = "nested too deeply" if isinstance(e, RecursionError) else str(e)
            raise protection_mod.ProtectionError(f"the {what} file {path} isn't JSON ({why})") from e

    def base_branch() -> str:
        if a.base is not None:
            if not a.base.strip():
                raise protection_mod.ProtectionError("--base was given no branch")
            return a.base
        try:
            prof = load(required=False)
        except ProfileError as e:
            raise protection_mod.ProtectionError(f"{e}; give the base branch with --base") from e
        if not prof:
            raise protection_mod.ProtectionError("the kit isn't set up here, so give the base branch with --base")
        return prof.base_branch

    def settings_file():
        settings = given(a.repo, "repository's settings")
        if not isinstance(settings, dict):
            raise protection_mod.ProtectionError("the repository's settings must be a JSON object, as GET repos/<repo> returns it")
        return settings

    def read_back():
        if a.rulesets is None:
            raise protection_mod.ProtectionError("give the repository's rulesets with --rulesets (a JSON list; [] when there are none)")
        base = base_branch()
        rulesets = given(a.rulesets, "rulesets")
        return protection_mod.check(rulesets, base, settings_file() if a.repo is not None else None)

    def protect():
        if a.rulesets is not None:
            raise protection_mod.ProtectionError("--rulesets doesn't go with --protect")
        if a.repo is None:
            raise protection_mod.ProtectionError("--protect needs the repository's settings with --repo (GET repos/<repo>): its name and default branch")
        reqs = protection_mod.protect(base_branch(), settings_file(), a.check)
        return {"requests": [r.as_dict() for r in reqs]} if a.json else protection_mod.requests_text(reqs)

    def require():
        if a.rulesets is not None or a.repo is not None or a.base is not None:
            raise protection_mod.ProtectionError("--require-checks takes the ruleset alone, without --rulesets, --repo or --base: it names its repository, and targets what it targets")
        req = protection_mod.require_checks(given(a.require_checks, "ruleset"), a.check)
        return {"requests": [req.as_dict()]} if a.json else protection_mod.requests_text([req])

    def checks_ran():
        if a.repo is None:
            raise protection_mod.ProtectionError("--checks-ran needs the repository's settings with --repo, so a ruleset on ~DEFAULT_BRANCH counts as requiring its checks")
        runs = given(a.checks_ran, "check runs")
        statuses = given(a.statuses, "statuses") if a.statuses is not None else None
        rep = read_back()
        ran = protection_mod.checks_ran(runs, statuses, rep.required_checks)
        return {"checks": ran, "required": rep.required_checks} if a.json else protection_mod.ran_text(ran, rep.required_checks)

    try:
        files = [f for f in (a.rulesets, a.repo, a.require_checks, a.checks_ran, a.statuses) if f is not None]
        if files.count("-") > 1:
            raise protection_mod.ProtectionError("only one of the files can be read from standard input (-)")
        if a.check and not (a.protect or a.require_checks is not None):
            raise protection_mod.ProtectionError("--check goes with --protect or --require-checks")
        if a.statuses is not None and a.checks_ran is None:
            raise protection_mod.ProtectionError("--statuses goes with --checks-ran")
        if a.protect:
            out = protect()
        elif a.require_checks is not None:
            out = require()
        elif a.checks_ran is not None:
            out = checks_ran()
        else:
            rep = read_back()
            out = rep.as_dict() if a.json else protection_mod.text(rep)
        out = out if isinstance(out, str) else json.dumps(out, indent=2)
    except RecursionError:  # input JSON can parse yet be too deep to copy or print
        print("workflow protection: an input file is nested too deeply to be what GitHub returns", file=sys.stderr)
        return 2
    except protection_mod.ProtectionError as e:
        print(f"workflow protection: {e}", file=sys.stderr)
        return 2
    print(out)
    return 0


def _kit_line(kit: dict) -> str:
    have = kit.get("installed")
    if not have:
        here = "unknown (no readable kit_version in .claude/workflow/lock.json, or VERSION)"
        return f"Kit version: {here}" + (f"; the latest release is {kit['latest']}" if kit.get("latest") else "")
    if "latest" not in kit:
        return f"Kit version: {have}"
    if not kit.get("checked", True):
        return f"Kit version: {have} (the update check is off: WORKFLOW_UPDATE_CHECK)"
    if kit.get("update_available"):
        how = "type /plugin update" if kit.get("mode") == "plugin" else "offer the update first"
        return f"Kit version: {have}; {kit['latest']} is out ({how})"
    if kit.get("ahead"):
        return f"Kit version: {have}, ahead of the latest release ({kit['latest']})"
    if kit.get("latest"):
        return f"Kit version: {have} (the latest)"
    return f"Kit version: {have} (couldn't read the latest release)"


def cmd_version(a) -> int:
    """The kit's version here, and whether a newer release is out; or, with
    --repo, only the kit's home on GitHub (with --starter, the starter's), asking
    nothing over the network."""
    if a.repo:
        print(updates_mod.KIT_REPO)
        return 0
    if a.starter:
        print(updates_mod.STARTER_REPO)
        return 0
    prof = load(required=False)
    root = prof.root if prof else project_root()
    kit = updates_mod.check(root, KIT_ROOT, fresh=a.fresh)
    if a.json:
        _out(kit)
    else:
        print(_kit_line(kit))
    return 0


def cmd_charter(a) -> int:
    if a.action == "defaults":
        _out(charter_mod.defaults(profile=load(required=False), protected=_protected(a)))
        return 0
    if a.action == "questions":
        _out(charter_mod.questions(profile=load(required=False), protected=_protected(a)))
        return 0
    if a.action == "reuse":
        old = _json(a.file)
        if not isinstance(old, dict):
            print("workflow: the old charter must be a JSON object", file=sys.stderr)
            return 1
        _out(charter_mod.reuse(old))
        return 0
    if a.action == "pin-plan":
        c = _json(a.file)
        if not isinstance(c, dict):
            print("workflow: the charter must be a JSON object", file=sys.stderr)
            return 1
        plan = c.get("plan")
        if plan is not None and not (charter_mod._is_int_list(plan) and plan):
            print("workflow: plan must be a non-empty list of issue numbers", file=sys.stderr)
            return 1
        _out(charter_mod.pin_plan(c))
        return 0
    if a.action == "validate":
        c = _json(a.file)
        problems = charter_mod.validate(c, require_approval=a.approved)
        prof = load(required=False)
        # Against the profile only once the charter itself is sound.
        if prof is not None and not problems:
            problems += _against_profile(c, prof, who=a.approved, protected=_protected(a))
        if problems:
            print("The charter has problems:\n- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        if prof is None:
            print("note: no profile found: release steps and waived checks weren't checked, nor the merge mode, the review's explorer or the owner", file=sys.stderr)
        print("ok")
        return 0
    if a.action == "estimate":
        return _charter_estimate(a)
    if a.action == "markdown":
        c = _json(a.file)
        problems = charter_mod.validate(c)
        if problems:
            print("- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        try:
            plan = charter_mod.parse_tickets(a.tickets) if a.tickets else None
        except ValueError as e:
            print(f"workflow: {e}", file=sys.stderr)
            return 2
        try:
            page = charter_mod.to_markdown(c, plan, _page_profile(), _json(a.estimate) if a.estimate else None)
        except (ValueError, OSError) as e:  # a bad estimate, or its file missing
            print(f"workflow charter markdown: {e}", file=sys.stderr)
            return 1
        print(page)
        return 0
    if a.action == "splice":
        c = _json(a.charter)
        problems = charter_mod.validate(c)
        if problems:
            print("The charter has problems:\n- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        try:
            plan = charter_mod.parse_tickets(a.tickets) if a.tickets else None
            est = _json(a.estimate) if a.estimate else None
            new = charter_mod.splice(_read(a.body), charter_mod.to_markdown(c, plan, _page_profile(), est))
        except (ValueError, OSError) as e:
            print(f"workflow charter splice: {e}", file=sys.stderr)
            return 1
        if a.out:
            Path(a.out).write_text(new, encoding="utf-8")
        else:
            print(new)
        return 0
    if a.action == "diff":
        for line in charter_mod.diff(_json(a.file), _json(a.other)):
            print(line)
        return 0
    return 2


def _plan_size(tickets: str | None, c) -> int:
    """`--tickets`: a number, or the plan as `markdown` takes it ("13:area,143:-");
    without it, the charter's plan."""
    if tickets and tickets.strip().isdigit():
        return int(tickets)
    if tickets:
        return len(charter_mod.parse_tickets(tickets))
    plan = c.get("plan") if isinstance(c, dict) else None
    if charter_mod._is_int_list(plan) and plan:
        return len(plan)
    raise ValueError("give --tickets (the number of tickets in the plan, or the plan), or a charter with a plan")


def _charter_estimate(a) -> int:
    try:
        c = _json(a.file)
        now = None
        if a.now:
            now = charter_mod._time(a.now)
            if now is None:
                raise ValueError("--now must be an ISO time with its zone, e.g. 2026-10-13T03:30:00Z")
        security = sorted(issues_mod.parse_numbers(a.security))
        est = estimate_mod.estimate(c, _plan_size(a.tickets, c), _json(a.runs) if a.runs else None, security, _page_profile(), now)
    except (ValueError, OSError, RecursionError) as e:  # an EstimateError, a bad --tickets, a file missing, not JSON or nested too deep
        print(f"workflow charter estimate: {e}", file=sys.stderr)
        return 1
    for n in est["notes"]:
        print(f"note: {n}", file=sys.stderr)
    _out(est if a.json else estimate_mod.text(est))
    return 0


def _page_profile():
    """The profile for the one page's size and review, or None when it can't be
    read: a broken profile never stops the page from rendering."""
    try:
        return load(required=False)
    except (ValueError, OSError):  # ProfileError is a ValueError; so is a file that isn't UTF-8
        return None


def _protected(a) -> bool | None:
    """`--unprotected`: the conductor's read-back (`workflow protection`) found
    the base branch unprotected. Without it, the verdict isn't known here."""
    return False if getattr(a, "unprotected", False) else None


def _against_profile(c: dict, prof, who: bool = True, protected: bool | None = None) -> list[str]:
    """The charter against the profile: release steps, waived checks, auto-merge
    in solo mode and, with `who`, that the profile's project.owner approved and
    amended it."""
    return charter_mod.against_profile(c, prof, who=who, protected=protected)


def _charter_change_problems(old, new) -> list[str]:
    """A put or patch that changes the charter: the checks `charter validate
    --approved` runs against the profile on disk. Removed protection the old
    charter recorded can't be dropped, not even by clearing the charter
    (`charter.dropped_removed_protection`). A state whose charter is unchanged
    isn't checked; a charter that is otherwise unsound is left to `state.put`."""
    c = new.get("charter") if isinstance(new, dict) else None
    was = old.get("charter") if isinstance(old, dict) else None
    if c == was:
        return []
    # Before anything else, so clearing the charter can't drop it either.
    dropped = charter_mod.dropped_removed_protection(was, c)
    if dropped:
        return [dropped]
    if not isinstance(c, dict) or charter_mod.validate(c):
        return []
    try:
        prof = load(required=False)
    except (UnicodeDecodeError, OSError) as e:
        raise ProfileError(f"the profile can't be read ({e}), so the charter change can't be checked") from e
    if prof is None:
        print("note: no profile found: the charter change wasn't checked against it", file=sys.stderr)
        return []
    return _against_profile(c, prof)


def cmd_state(a) -> int:
    if a.action == "init":
        c = _json(a.charter)
        problems = charter_mod.validate(c, require_approval=True)
        if not problems:
            prof = load(required=False)
            if prof is not None:
                problems += _against_profile(c, prof)
        if problems:
            print("The charter isn't ready:\n- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        s = state_mod.empty(c)
        s["run_id"] = a.run_id
        s["by_hand_issue"] = a.by_hand
        s["comments_read_through"] = a.read_through
        if a.read_through is None:
            print(
                "warning: no --read-through given, so the first check-in will read every comment on the tracking issue "
                "as if new; pass the id of its newest comment (or 0 when it has none)",
                file=sys.stderr,
            )
        _out(s)
        return 0
    body = _read(a.body)
    if a.action == "get":
        s = state_mod.get(body)
        if s is None:
            print("no state block in this body", file=sys.stderr)
            return 1
        _out(s)
        return 0
    if a.action == "put":
        try:
            cur = state_mod.get(body)
        except state_mod.StateError:  # a block that isn't JSON: `put` replaces it
            cur = None
        s = _json(a.state)
    else:  # patch
        cur = state_mod.get(body)
        if cur is None:
            raise SystemExit("no state block to patch; use `state put` first")
        s = state_mod.patch(cur, _json(a.patch))
    # The body and the state's own problems first, then the charter against the profile.
    new = state_mod.put(body, s)
    problems = _charter_change_problems(cur, s)
    if problems:
        print("workflow state: refusing to write the state. The charter has problems:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1
    if a.out:
        Path(a.out).write_text(new, encoding="utf-8")
    else:
        print(new)
    return 0


def cmd_render(a) -> int:
    prof = load()
    vals = render_mod.values(prof, _json(a.ticket), _json(a.charter), _json(a.slots), a.tracking, a.by_hand)
    text = render_mod.seal(render_mod.render(_read(a.template), vals))
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    if a.print or not a.out:
        sys.stdout.write(text)
    return 0


def cmd_comments(a) -> int:
    owner = a.owner
    if not owner:
        prof = load(required=False)
        owner = prof.owner if prof else ""
    if not owner:
        print("workflow comments: give --owner (no project.owner in the profile)", file=sys.stderr)
        return 2
    try:
        _out(posts_mod.owner_words(posts_mod.load_comments(_read(a.file)), owner, since_id=a.since_id))
    except posts_mod.CommentsError as e:
        print(
            f"workflow comments: {e}. Give the issue's comments as GitHub returns them: "
            "`gh api --paginate --slurp repos/<repo>/issues/<n>/comments`, or every page of the MCP tool's comments",
            file=sys.stderr,
        )
        return 1
    return 0


def _pr_number(v: str) -> int:
    if not v.isdigit() or int(v) < 1:
        raise argparse.ArgumentTypeError(f"{v!r} isn't a pull request's number")
    return int(v)


def _review_rounds(v: str) -> int:
    if not (re.fullmatch(r"[0-9]{1,2}", v) and int(v) in merge_mod.REVIEW_ROUNDS):
        raise argparse.ArgumentTypeError(f"'{reviews_mod._shown(v, 20)}' isn't a whole number from 1 to 10 (the review rounds allowed, as the briefing or the profile's run.review_rounds gives them)")
    return int(v)


def _json_inputs(a, names, raw=()) -> dict:
    """Each of `names` given as a file (or - for standard input, once): its
    JSON, several values in a row read as a list, `(value, None)`; or
    `(None, why)` when it can't be read. The `raw` names keep their text."""
    inputs: dict = {}
    stdin_for = None
    for name in names:
        path = getattr(a, name, None)
        if path is None:
            continue
        if path == "-":
            if stdin_for is not None:
                inputs[name] = (None, f"standard input (-) is already --{stdin_for}'s: only one file can be read from it")
                continue
            stdin_for = name
        try:
            if path == "-" and sys.stdin is None:
                raise ValueError("standard input (-) is closed")
            text = _read(path).removeprefix("\ufeff")
            if name in raw:
                inputs[name] = (text, None)
                continue
            values = posts_mod.decode_values(text)
            inputs[name] = (values[0], None) if len(values) == 1 else (values, None) if values else (None, f"{path} is empty")
        except OSError as e:
            inputs[name] = (None, f"can't open {path}: {e.strerror or e}")
        except posts_mod.CommentsError as e:
            inputs[name] = (None, f"{path} isn't JSON ({e})")
        except UnicodeDecodeError:
            inputs[name] = (None, f"{path} isn't UTF-8 text")
        except ValueError as e:  # a closed standard input
            inputs[name] = (None, str(e) if path == "-" else f"can't read {path}")
    return inputs


def cmd_merge_check(a) -> int:
    """Whether the pull request may merge (flow §4), from the files given, and
    with --fetch the rest through `gh api`. Changes nothing, posts nothing, and
    exits 0 whatever it finds: anything it can't read is a reason of its own,
    never "ready"."""
    inputs = _json_inputs(a, [*merge_mod.INPUTS, "charter"], raw=("charter",))  # the charter: JSON, or the tracking issue's body, as merge.charter_from reads it
    prof, profile_error = None, None
    try:
        prof = load()  # its protected paths and required checks are rules: none found is a reason
    except ProfileError as e:
        profile_error = str(e)
    except (OSError, UnicodeDecodeError) as e:
        profile_error = f"can't read {PROFILE_PATH}: {getattr(e, 'strerror', None) or e}"
    root = prof.root if prof else project_root()
    charter = inputs.pop("charter", None)
    if a.fetch is not None:
        wanted = [n for n in merge_mod.INPUTS if n != "preview"]  # the preview is #41's reader's
        if prof is None:
            inputs.update({n: (None, f"not fetched: the profile couldn't be read, so its repository isn't known: give --{n} as a file") for n in wanted if n not in inputs})
        else:
            inputs.update(fetch_mod.merge_inputs(prof.repo, a.fetch, inputs, wanted, asker=None if prof.owner else a.asker))
        pr = inputs.get("pr", (None, None))[0]
        pr = pr[0] if isinstance(pr, list) and len(pr) == 1 else pr
        if isinstance(pr, dict) and pr.get("number") != a.fetch:
            # The other inputs are #<fetch>'s: a --pr file of another pull request, or one that
            # doesn't say which it is, can't go with them.
            said = f"it is #{merge_mod._clean(pr['number'])}" if pr.get("number") is not None else "it doesn't say its number"
            inputs["pr"] = (None, f"{said}, not #{a.fetch} (--fetch)")
        if prof is not None and prof.previews.on and "preview" not in inputs:
            # After the --pr check, so the preview reads the inputs merge-check will.
            inputs["preview"] = _fetched_preview(prof.repo, a.fetch, inputs)
    logs: dict = {}
    if a.check_logs:
        try:
            logs = {f.name: f.read_text(encoding="utf-8", errors="replace") for f in Path(a.check_logs).iterdir() if f.is_file()}
        except OSError as e:
            print(f"workflow merge-check: can't read --check-logs {a.check_logs}: {e.strerror or e}; no check's log was read", file=sys.stderr)
    role = roles.env_role() if not roles.unrecognised() else None  # waivers want a firm role: see merge.waivers
    level = resolve_experience(root, prof.experience if prof else None).wording_level
    res = merge_mod.evaluate(inputs, prof, profile_error, asker=a.asker, level=level, charter_input=charter, logs=logs, role=role, review_rounds=a.review_rounds)
    _out(res.as_dict() if a.json else merge_mod.text(res))
    return 0


_PREVIEW_NAMES = {"comments": "comments", "checks": "check runs", "sha": "head commit"}


def _fetched_preview(repo: str, number: int, inputs: dict) -> tuple:
    """#117: with previews on, `merge-check --fetch` reads the try-it link
    itself when no --preview is given, through #41's reader, so a check that
    left it out can't say "ready" over a link that didn't build. It reuses
    what merge-check already read (the head, the comments, the check runs)
    and fetches only the rest. Its answer as merge-check's `(value, None)`,
    or `(None, why)`."""
    ctx = merge_mod.Context(inputs, None, None)
    unread = []
    for n, read in (("comments", ctx.comments), ("checks", ctx.checks_ran)):
        try:
            read()  # as merge-check reads it: a file it can't open, or one in the wrong shape
        except merge_mod.Unreadable:
            unread.append(n)
    if unread:  # already merge-check's own reasons: neither fetched again nor read
        return None, f"its {' and '.join(_PREVIEW_NAMES[n] for n in unread)} couldn't be read, as said above"
    have = {n: inputs[n] for n in ("comments", "checks") if n in inputs}
    try:  # the head as merge-check reads it, in any shape its --pr takes
        have["sha"] = (merge_mod._pr(inputs["pr"][0]).head, None) if inputs.get("pr", (None, None))[0] is not None else None
    except merge_mod.Unreadable:
        have["sha"] = None
    if have["sha"] is None or not previews_mod.is_sha(have["sha"][0]):
        del have["sha"]
    got = {**have, **fetch_mod.preview_inputs(repo, number, have)}
    # Each fetch error without the hint `preview_inputs` adds: its flags are `workflow preview`'s.
    why = [f"its {_PREVIEW_NAMES[n]}: {e.removesuffix(', ' + fetch_mod._give(n))}" for n, (_, e) in got.items() if e is not None]
    if why:
        return None, "--fetch couldn't fetch " + "; ".join(why)
    try:
        return previews_mod.read(got["comments"][0], got["checks"][0], got["sha"][0]).as_dict(), None
    except previews_mod.PreviewError as e:
        return None, f"`workflow preview` said: {e}"


def _sha(v: str) -> str:
    if not previews_mod.is_sha(v):
        raise argparse.ArgumentTypeError(f"'{reviews_mod._shown(v, 50)}' isn't a commit's SHA (7 to 40 hex characters): give the pull request's head commit")
    return v.lower()


def cmd_preview(a) -> int:
    """`preview`: whether the pull request's try-it link is ready for its head
    commit (#41's reader), from the files given, and with --fetch the rest
    through `gh api`. Changes nothing, posts nothing. Exits 0 with an answer,
    1 when an input can't be read, 2 when one is missing."""
    inputs = _json_inputs(a, ("comments", "checks"))
    if a.sha is not None:
        inputs["sha"] = (a.sha, None)
    give = "give --comments F (the pull request's issue comments), --checks F (its head commit's check runs), as JSON from the GitHub API, and --sha SHA (its head commit)"

    def unread() -> bool:
        said = [(n, why) for n, (_, why) in inputs.items() if why is not None]
        for n, why in said:
            print(f"workflow preview: couldn't read --{n}: {why}", file=sys.stderr)
        return bool(said)

    if unread():  # before asking gh for the rest
        return 1
    missing = [n for n in fetch_mod.PREVIEW_INPUTS if n not in inputs]
    if a.fetch is not None and missing:
        try:
            prof = load(required=False)
        except ProfileError as e:
            prof, why = None, f"the profile can't be read ({e})"
        except (OSError, UnicodeDecodeError) as e:
            prof, why = None, f"{PROFILE_PATH} can't be read ({getattr(e, 'strerror', None) or e})"
        else:
            why = f"there's no profile ({PROFILE_PATH})"
        if prof is None:
            print(f"workflow preview: --fetch needs the profile's project.repo, and {why}: {give}", file=sys.stderr)
            return 2
        inputs.update(fetch_mod.preview_inputs(prof.repo, a.fetch, inputs))
        if unread():
            return 1
        missing = []
    if missing:
        print(f"workflow preview: missing {', '.join('--' + n for n in missing)}: {give}, or --fetch <PR> to read them with gh", file=sys.stderr)
        return 2
    sha = inputs["sha"][0]
    try:
        got = previews_mod.read(inputs["comments"][0], inputs["checks"][0], sha)
    except previews_mod.PreviewError as e:
        print(f"workflow preview: couldn't read --{e.name}: {e}", file=sys.stderr)
        return 1
    _out(got.as_dict() if a.json else previews_mod.text(got, sha))
    return 0


def cmd_briefing(a) -> int:
    """`briefing verify`: the session's copy of its briefing against its last line."""
    stated, got = render_mod.seal_of(_read(a.file))
    if stated is None:
        print("no Briefing line")
        return 1
    if stated != got:
        print(f"Briefing changed: expected {stated}, got {got}")
        return 1
    print(f"Briefing {stated} intact")
    return 0


def cmd_pr_template(a) -> int:
    """`pr-template`: the pull request template to write, on stdout, and a note on
    stderr. Changes nothing. Exits 3 for a folder of templates (nothing to write)."""
    if a.existing == "":
        print("workflow pr-template: --existing is empty: give the project's template, or leave the flag out", file=sys.stderr)
        return 1
    try:
        r = pr_template_mod.build(KIT_ROOT, Path(a.existing) if a.existing is not None else None)
    except OSError as e:
        print(f"workflow pr-template: can't read {e.filename}: {e.strerror or e}", file=sys.stderr)
        return 1
    except pr_template_mod.TemplateError as e:
        print(f"workflow pr-template: {e}", file=sys.stderr)
        return 1
    if r.note:
        print(r.note, file=sys.stderr)
    if r.text is None:
        return 3
    # Bytes, so the project's own line endings and encoding come through as they are.
    sys.stdout.flush()
    sys.stdout.buffer.write(r.text)
    sys.stdout.buffer.flush()
    return 0


def cmd_adopt(a) -> int:
    """`adopt`: rewrite a copy of the starter's names to the person's own, and
    say what changed. Refused in words (exit 1) with nothing written."""
    if a.project == "":
        print("workflow adopt: --project is empty: give the checkout, or leave the flag out", file=sys.stderr)
        return 1
    root = Path(a.project).resolve() if a.project is not None else project_root()
    try:
        r = adopt_mod.adopt(root, a.owner, a.repo, a.name)
    except adopt_mod.AdoptError as e:
        print(f"workflow adopt: {e}", file=sys.stderr)
        return 1
    print(r.text())
    return 0


def _spec_body(path: str) -> str:
    """The spec's body from --body's file, as the session publishes it; raises
    RecordError, in words, for a file that is missing, isn't text or is empty."""
    if not path:
        raise reviews_mod.RecordError("give --body a file: the spec's body, exactly as you publish it")
    shown = reviews_mod._shown(path, 80)
    p = Path(path)
    if not p.exists():
        raise reviews_mod.RecordError(f"--body names no file: `{shown}`")
    if not p.is_file():
        raise reviews_mod.RecordError(f"--body `{shown}` isn't a file: give the file holding the spec's body")
    try:
        text = p.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise reviews_mod.RecordError(f"--body `{shown}` isn't UTF-8 text: give the spec's body as you publish it") from None
    except OSError as e:
        raise reviews_mod.RecordError(f"--body `{shown}` can't be read: {e.strerror or e}") from None
    if not text.strip():
        raise reviews_mod.RecordError(f"--body `{shown}` is empty: give the spec's body as you publish it")
    return text


def cmd_review_record(a) -> int:
    """`review-record`: the comment a review round, a later Correctness pass, or
    a spec's review round (keyed to its body's SHA-256) posts."""
    # Each flag is a list (`append`), so a repeated one is refused rather than
    # the last silently winning; repeated --reviewers add up.
    for flag in ("kind", "round", "commit", "body"):
        if len(getattr(a, flag) or []) > 1:
            print(f"workflow review-record: give --{flag} once", file=sys.stderr)
            return 2
    one = {flag: (getattr(a, flag) or [None])[0] for flag in ("kind", "round", "commit")}
    path = (a.body or [None])[0]
    if path is not None and one["kind"] is None:
        one["kind"] = "spec"  # --body alone is a spec's review
    reviewers = ",".join(a.reviewers) if a.reviewers else None
    try:
        if path is not None and one["commit"] is not None:
            raise reviews_mod.RecordError("give --commit or --body, not both: --commit for a round or a pass, --body for a spec's review")
        body = None if path is None else _spec_body(path)
        text = reviews_mod.record(**one, reviewers=reviewers, clean=a.clean, body=body)
    except reviews_mod.RecordError as e:
        print(f"workflow review-record: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(text)
    return 0


def cmd_evidence(a) -> int:
    prof = load()
    root = prof.root
    if a.base_count is not None and a.base_ref:
        print("workflow: give --base-count or --base-ref, not both", file=sys.stderr)
        return 2
    if a.all and a.suite:
        print("workflow: give --all or --suite, not both", file=sys.stderr)
        return 2
    # A bad ref fails before anything runs.
    base_sha = evidence_mod.resolve_ref(root, a.base_ref) if a.base_ref else None
    dirty = evidence_mod.dirty_paths(root) if a.allow_dirty else []
    selection = evidence_mod.Selection(None)
    if base_sha and not a.suite and not a.all:
        selection = evidence_mod.select(prof, root, a.base_ref, base_sha)
    only = a.suite or selection.names
    if only == []:  # no suite needed: nothing runs here or on the base
        sha, results = evidence_mod.checked_head(root, a.allow_dirty), []
    else:
        sha, results = evidence_mod.collect(prof, root, only=only, fresh=a.fresh, allow_dirty=a.allow_dirty)
    base_count, label, problem, notes = a.base_count, "", "", []
    if a.base_ref and only != []:
        b = evidence_mod.base_count_from_ref(prof, root, a.base_ref, only=only, fresh=a.fresh, sha=base_sha)
        base_count, notes = b.count, b.notes
        label = f"`{a.base_ref}` at `{b.sha[:12]}`"
        if b.problem:
            problem = f"no usable base count from {a.base_ref}: {b.problem}"
    ok, md = evidence_mod.report(
        sha, prof, results, base_count, dirty=dirty, base_label=label, base_problem=problem, base_notes=notes,
        selection=selection,
    )
    print(md)
    return 0 if ok else 1


def cmd_repair(a) -> int:
    prof = load()
    set_up = repair_mod.setup(prof.setup, prof.setup_check, prof.root, repair_mod.HOOK_BUDGET)
    res = repair_mod.run(prof.repair, prof.root)
    text = "\n".join(x for x in (repair_mod.setup_summary(set_up), repair_mod.summary(res)) if x)
    print(text or "no [repair] commands in the profile, and the project's setup is in place")
    return 1 if set_up and set_up[1] else 0


def cmd_vendor(a) -> int:
    project = Path(a.project).resolve() if a.project else project_root()
    if a.action == "verify":
        r = vendor_mod.verify(project)
        _out(r)
        problems = []
        if r["missing"]:
            problems.append("missing: " + ", ".join(r["missing"]))
        if not r["hooks_ok"]:
            problems.append("the kit's hooks aren't all in .claude/settings.json; run `vendor update`")
        if r["plugin_also_enabled"]:
            problems.append(f"the {vendor_mod.PLUGIN_KEY} plugin is enabled too: pick one mode")
        if r["conflicts"]:
            problems.append(
                "unresolved conflicts (merge each <file>.new by hand, then `vendor resolve <file>`): " + ", ".join(r["conflicts"])
            )
        if a.strict and r["changed"]:
            problems.append(
                "changed since vendored (`vendor resolve --keep <file>` records a deliberate edit): " + ", ".join(r["changed"])
            )
        if a.strict and r["mattpocock"] == "not_vendored":
            problems.append(vendor_mod.MP_MISSING)
        for x in problems:
            print(f"workflow vendor verify: {x}", file=sys.stderr)
        return 1 if problems else 0
    if a.action == "resolve":
        _out(vendor_mod.resolve(project, a.path, keep=a.keep))
        return 0
    kit = Path(a.kit).resolve() if a.kit else KIT_ROOT
    mp = Path(a.mattpocock).resolve() if a.mattpocock else None
    r = vendor_mod.install(
        kit,
        project,
        mp,
        update=a.action == "update",
        adopt=a.adopt,
        strict_pin=a.strict_pin,
        no_mattpocock=a.no_mattpocock,
    )
    for w in r["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    # Counts for the routine lists; every path that needs a look in full, the
    # project's own edits kept over the kit's included.
    _out({k: (len(v) if k in ("written", "unchanged") else v) for k, v in r.items()})
    return 0


# ---------- hooks ----------


def _deny_json(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}))


def _is_restore(event) -> bool:
    """With the profile missing or invalid, a firm session may still run exactly
    the commands that put the kit back (the vendored hook command allows the
    same when the CLI itself is missing)."""
    if not isinstance(event, dict) or event.get("tool_name") != "Bash":
        return False
    inp = event.get("tool_input")
    cmd = inp.get("command") if isinstance(inp, dict) else None
    return isinstance(cmd, str) and " ".join(cmd.split()) in vendor_mod.RESTORE_COMMANDS


def _role_label(role: str) -> str:
    odd = roles.unrecognised()
    return f"{role} session (WORKFLOW_ROLE={odd!r} isn't a role, so treated as ticket)" if odd else f"{role} session"


# The guard's time budget, 5 seconds under the hook's 30-second timeout: a guard
# still deciding when it runs out is refused in ticket and conductor sessions
# with its own reason, and takes the can't-decide fallback in an attended one,
# with time left to read the event again. A hook that outlasts its timeout
# blocks too (`onFailure: "block"`, #57), but only on Claude Code 2.1.295 or
# later, and with no reason given.
GUARD_BUDGET = float(vendor_mod.GUARD_TIMEOUT - 5)


class _OverBudget(BaseException):
    """Raised when the guard runs out of time. A BaseException, so no
    `except Exception` inside the guard can swallow it."""


@contextlib.contextmanager
def _budget(seconds: float):
    """Raise _OverBudget in the main thread after `seconds` (where the platform has
    SIGALRM; a regex match is interrupted too, since `re` checks for signals)."""
    if not hasattr(signal, "setitimer") or threading.current_thread() is not threading.main_thread():
        yield
        return
    if seconds <= 0:
        raise _OverBudget()

    def over(signum, frame):
        raise _OverBudget()

    previous = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, over)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        finally:  # even when the alarm goes off here
            signal.signal(signal.SIGALRM, previous)


def _cant_decide(event, why: str, solo: bool | None = None, fixes: str = fallback.FIXES) -> int:
    """The can't-decide fallback (`fallback`, #53) in an attended session: a push
    or a merge is asked, or refused in solo mode or where nobody is asked;
    anything else is left alone. A missing profile (the kit isn't set up) is
    left alone too. Always 0, and never raises: a hook that exits non-zero
    would let the tool run, or, once the hook blocks on failure, block them all."""
    try:
        if solo is None:
            root = project_root()
            if not (root / PROFILE_PATH).exists():
                return 0
            solo = fallback.solo(root)
        d = fallback.decide(event, solo, why, fixes)
        if d:
            out = fallback.output(d[0], f"[workflow guard, {_role_label('attended')}] {d[1]}")
            print(json.dumps(out))
    except Exception:
        pass
    return 0


def _ticket_branch_without_the_kit(event: dict) -> bool:
    """With the profile unreadable, whether the branch matches its
    `run.ticket_branch`, read as the old-Python fallback reads it."""
    try:
        cwd = event.get("cwd")
        return _old_python._firm(os.environ, cwd if isinstance(cwd, str) and cwd else str(project_root()))
    except Exception:
        return False


def _hook_guard(event, raw: str = "") -> int:
    firm = roles.env_role()
    if not isinstance(event, dict):  # malformed: nothing can be checked
        if firm is None and _ticket_branch_without_the_kit({}):
            firm = "ticket"
        if firm in ("ticket", "conductor"):
            _deny_json(f"[workflow guard, {_role_label(firm)}] the hook's event wasn't a JSON object, so nothing could be checked and this was refused")
            return 0
        return _cant_decide(fallback.read_event(raw), "the hook's event couldn't be read as a JSON object")
    try:
        prof = load(required=False)
    except ProfileError as e:
        if firm is None and _ticket_branch_without_the_kit(event):
            firm = "ticket"
        if firm in ("ticket", "conductor"):
            if not _is_restore(event):
                _deny_json(f"[workflow guard, {_role_label(firm)}] the profile is invalid, so nothing can be checked: {e}. Fix .claude/workflow/profile.toml in a PR from an attended session, or restore it: git checkout -- .claude/workflow")
            return 0
        print(f"workflow guard hook: the profile is invalid, so the guard can't check anything: {e}", file=sys.stderr)
        return _cant_decide(event, f"the profile is invalid ({e})")
    if prof is None:
        if firm in ("ticket", "conductor") and not _is_restore(event):
            _deny_json(
                f"[workflow guard, {_role_label(firm)}] the workflow profile is missing; nothing can be checked, so this was refused. "
                "Restore it with: git checkout -- .claude/workflow"
            )
        return 0
    root = prof.root
    cwd = Path(event.get("cwd") or root)
    role: str | None = None
    try:
        with _budget(GUARD_BUDGET - (time.monotonic() - _STARTED)):
            # A cwd with no branch (outside the repository, e.g. /tmp) takes the project root's.
            role = roles.role(cwd, prof.ticket_branch, fallback=root)
            d = guard_mod.decide(event, prof, role, root, roles.current_branch(cwd), role_from_env=firm is not None, cwd=event.get("cwd") or None)
    except _OverBudget:
        role = role or firm or "ticket"  # a role not read in time: the strictest
        # Solo mode refuses what touches the base branch, so a check not finished in time is refused too.
        if role in ("ticket", "conductor") or (role == "attended" and prof.ruleset is False):
            _deny_json(f"[workflow guard, {_role_label(role)}] the guard ran out of time ({GUARD_BUDGET:g} seconds) checking this, so it was refused; split the command, or give it smaller files")
            return 0
        return _cant_decide(
            event,
            f"it ran out of time ({GUARD_BUDGET:g} seconds) checking this",
            prof.ruleset is False,
            "To have it checked, split the command, or give it smaller files.",
        )
    except Exception as e:  # fail closed where a person isn't there to notice
        if role in ("ticket", "conductor") or (role is None and firm in ("ticket", "conductor")):
            _deny_json(f"[workflow guard, {_role_label(role or firm)}] the guard failed ({type(e).__name__}: {e}), so this was refused; rephrase the command more simply")
            return 0
        return _cant_decide(event, f"it failed ({type(e).__name__}: {e})", prof.ruleset is False)
    if d.action == "allow":
        return 0  # never force "allow": the normal permission rules still apply
    reason = f"[workflow guard, {_role_label(role)}] {d.reason}"
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": d.action,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


def _hook_gate(event: dict) -> int:
    prof = load(required=False)
    if prof is None:
        return 0
    root = prof.root
    if roles.role(Path(event.get("cwd") or root), prof.ticket_branch, fallback=root) != "ticket":
        return 0
    reason = gate_mod.decide(event)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def _hook_context(event: dict) -> int:
    prof = load(required=False)
    root = prof.root if prof else project_root()
    files = context_mod.flow_files(root, KIT_ROOT, prof.flow_addendum if prof else "")
    prompt, session = event.get("prompt") or "", event.get("session_id") or ""
    ctx = context_mod.context_for(prompt, session, files)
    role: list[str] = []  # read once, and only when something would be added

    def attended() -> bool:
        if not role:
            role.append(roles.role(root, prof.ticket_branch))
        return role[0] == "attended"

    # The guided start at the first prompt (marked whatever it was), and its
    # reminder at each later one: attended sessions only, since ticket and
    # conductor sessions start from a briefing or a charter, never from a menu.
    if prof is not None and prof.guided_start:
        nudge = context_mod.start_for(prompt, session) or context_mod.reminder_for(prompt)
        if nudge and not ctx and attended():
            ctx = nudge
    # The glossary, beside whatever came above, at the first prompt of an
    # attended session for someone new to building (unknown counts as new).
    # Its own marker, set at the first prompt whatever it brings. A failure
    # here never costs the flow or the nudge.
    if prof is not None:
        try:
            if context_mod.first_glossary_prompt(session) and attended() and resolve_experience(root, prof.experience).wording_level == "new":
                ctx = context_mod.with_glossary(ctx, context_mod.glossary_file(root, KIT_ROOT))
        except Exception:
            pass
    if ctx:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
    return 0


def _hook_repair(event: dict) -> int:
    prof = load(required=False)
    if prof is None:
        return 0
    role = roles.role(prof.root, prof.ticket_branch)
    # A newer kit: offered in attended and conductor sessions, never in a
    # ticket session, which stays on the version its run started with. Asked
    # first, in a few seconds at most, so setup keeps the hook's budget.
    note = updates_mod.notice(updates_mod.check_within(prof.root, KIT_ROOT), role) if role != "ticket" else None
    start = time.monotonic()
    # Only in cloud sessions: a laptop's checkout is its owner's to set up.
    cloud = os.environ.get("CLAUDE_CODE_REMOTE") == "true"
    set_up = repair_mod.setup(prof.setup, prof.setup_check, prof.root, repair_mod.HOOK_BUDGET - 60) if cloud else None
    left = int(repair_mod.HOOK_BUDGET - (time.monotonic() - start))
    deadline = max(0, min(repair_mod.DEADLINE, left))
    text = repair_mod.summary(repair_mod.run(prof.repair, prof.root, deadline=deadline)) if prof.repair else ""
    text = "\n".join(x for x in (repair_mod.setup_summary(set_up), text) if x)
    firm = "set by WORKFLOW_ROLE" if roles.env_role() else "from the branch name"
    text = (text + "\n" if text else "") + f"Workflow role of this session: {role} ({firm})."
    if note:
        text += "\n" + note
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


HOOKS = {"guard": _hook_guard, "gate": _hook_gate, "context": _hook_context, "repair": _hook_repair}


def cmd_hook(a) -> int:
    raw = ""  # the input with undecodable bytes replaced, for the can't-decide fallback
    try:
        data = sys.stdin.buffer.read()
        raw = data.decode("utf-8", "replace")
        event = json.loads(data.decode("utf-8") or "{}")  # the event itself is read strictly
    except (ValueError, RecursionError, OSError, AttributeError):  # AttributeError: no stdin
        event = None
    if a.name != "guard" and not isinstance(event, dict):
        event = {}  # the guard decides what a malformed event means
    try:
        return _hook_guard(event, raw) if a.name == "guard" else HOOKS[a.name](event)
    except Exception as e:  # a bug in a hook must not stop the session; say so
        if a.name == "guard":
            firm = roles.env_role()
            if firm is None and _ticket_branch_without_the_kit(event if isinstance(event, dict) else {}):
                firm = "ticket"
            if firm in ("ticket", "conductor"):
                _deny_json(f"[workflow guard] the guard failed ({type(e).__name__}: {e}), so this was refused")
                return 0
            print(f"workflow guard hook failed ({type(e).__name__}: {e})", file=sys.stderr)
            why = f"the profile is invalid ({e})" if isinstance(e, ProfileError) else f"it failed ({type(e).__name__}: {e})"
            return _cant_decide(event if isinstance(event, dict) else fallback.read_event(raw), why)
        if isinstance(e, ProfileError):
            print(f"workflow {a.name} hook: the profile is invalid, so the hook did nothing: {e}", file=sys.stderr)
            return 1
        print(f"workflow {a.name} hook failed ({type(e).__name__}: {e}); it did nothing this time", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="workflow", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("profile")
    s.add_argument("action", choices=["check"])
    s.set_defaults(fn=cmd_profile)

    s = sub.add_parser("ready")
    s.add_argument("--issues")
    s.add_argument("--prs")
    s.add_argument("--fetch", action="store_true")
    s.add_argument("--exclude", help="tickets to leave out, e.g. 13,#143")
    s.add_argument("--only", help="consider only these tickets, e.g. 1,2,3")
    s.add_argument("--override", help="tickets that may share an area with a running one, e.g. 5,6")
    s.add_argument("--running-area", action="append")
    s.add_argument("--slots", type=int)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_ready)

    s = sub.add_parser("status", help="where the project stands: what the guided start offers")
    s.add_argument("--issues")
    s.add_argument("--prs")
    s.add_argument("--fetch", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("doctor", help="what's set up and what isn't, each line with a one-sentence fix; changes nothing, exits 0 (--strict: 1 on a gap or a line it couldn't check)")
    s.add_argument("--claude-version", metavar="VERSION", help="Claude Code's version, as `claude --version` prints it (wins over running it)")
    s.add_argument("--rulesets", metavar="F", help="the repository's rulesets, each in full (GET repos/<repo>/rulesets/<id>), as `workflow protection` takes them (or -); else read with `gh api`")
    s.add_argument("--repo", metavar="F", help="the repository's settings (GET repos/<repo>): the merge settings and default branch (or -); else read with `gh api`")
    s.add_argument("--environments", metavar="F", help="the account's environments, as list_environments returns them (or -); only a cloud session can list them, so without it the Cloud line can't be checked")
    s.add_argument("--runs", metavar="F", help="the issues labelled workflow:run, as the GitHub API returns them (or -), for whether a run has been made; else read with `gh api`")
    s.add_argument("--checks", metavar="F", help="the base branch's latest commit's check runs and statuses (GET repos/<repo>/commits/<ref>/check-runs and .../status, every page, in one file), as `workflow protection --checks-ran` reads them (or -), for the \"Require these checks\" offer; else read with `gh api`")
    s.add_argument("--prs", metavar="F", help="the open pull requests, as `workflow ready --prs` takes them (or -), for one that adds required checks to the profile; else read with `gh api`")
    s.add_argument("--json", action="store_true", help="every line's group, id, status, message, fix and offer, for skills")
    s.add_argument("--strict", action="store_true", help="exit 1 when any line is a gap or can't be checked; notes never fail it")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("protection", help="whether the base branch is protected, read back from GitHub's JSON, or the requests to protect it; changes nothing, sends nothing")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--protect", action="store_true", help="print the requests that protect the base branch: the ruleset to create, and the merge settings (needs --repo)")
    mode.add_argument("--require-checks", metavar="F", help="print the request that adds --check names to this ruleset (GET repos/<repo>/rulesets/<id>, in full)")
    mode.add_argument("--checks-ran", metavar="F", help="the checks that ran on a commit (GET repos/<repo>/commits/<ref>/check-runs), less those --rulesets require")
    s.add_argument("--statuses", metavar="F", help="with --checks-ran: the commit's statuses (GET repos/<repo>/commits/<ref>/statuses)")
    s.add_argument("--check", action="append", default=[], metavar="NAME", help="a check to require (repeat for each)")
    s.add_argument("--rulesets", help="the repository's rulesets, each in full (GET repos/<repo>/rulesets/<id>), as a JSON list (or -)")
    s.add_argument("--repo", help="the repository's settings (GET repos/<repo>): the merge settings, and the default branch that ~DEFAULT_BRANCH means")
    s.add_argument("--base", help="the base branch (default: the profile's project.base_branch)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_protection)

    s = sub.add_parser("version", help="the kit's version here, and whether a newer release is out")
    s.add_argument("--fresh", action="store_true", help="ask GitHub again rather than the last six hours' answer")
    alone = s.add_mutually_exclusive_group()
    alone.add_argument("--json", action="store_true")
    alone.add_argument("--repo", action="store_true", help="print only the kit's home on GitHub (owner/repo); no network, so --fresh doesn't apply")
    alone.add_argument("--starter", action="store_true", help="print only the starter template's home on GitHub (owner/repo); no network, so --fresh doesn't apply")
    s.set_defaults(fn=cmd_version)

    s = sub.add_parser("charter")
    s.add_argument("action", choices=["defaults", "questions", "validate", "markdown", "diff", "reuse", "pin-plan", "splice", "estimate"])
    s.add_argument("file", nargs="?")
    s.add_argument("other", nargs="?")
    s.add_argument("--approved", action="store_true", help="also require the owner's approval")
    s.add_argument(
        "--unprotected",
        action="store_true",
        help="defaults, questions, validate: the read-back found the base branch unprotected; with project.ruleset true, "
        "that counts as solo mode (removed protection), so auto-merge isn't offered",
    )
    s.add_argument(
        "--tickets",
        help='markdown, splice: the planned tickets in order with their areas, e.g. "13:messages,143:-"; '
        "estimate: that, or just their number (else the charter's plan)",
    )
    s.add_argument("--estimate", metavar="F", help="markdown, splice: `charter estimate --json`'s output, for the one page's Estimate line")
    s.add_argument("--runs", metavar="F", help="estimate: past runs' workflow:run issues, as JSON (as the GitHub API returns them)")
    s.add_argument("--security", help="estimate: the plan's tickets the review panel would give a security review, e.g. 13,143")
    s.add_argument("--now", metavar="ISO", help="estimate: the time to count from (else now)")
    s.add_argument("--json", action="store_true", help="estimate: as JSON")
    s.add_argument("--body", help="splice: the tracking issue's body (a file, or -)")
    s.add_argument("--charter", help="splice: the charter")
    s.add_argument("--out", help="splice: write the new body here (else print it)")
    s.set_defaults(fn=cmd_charter)

    s = sub.add_parser("state")
    s.add_argument("action", choices=["init", "get", "put", "patch"])
    s.add_argument("--body")
    s.add_argument("--charter")
    s.add_argument("--run-id")
    s.add_argument("--by-hand", type=int)
    s.add_argument("--read-through", type=int, help="init: the id of the tracking issue's newest comment (0 for none)")
    s.add_argument("--state")
    s.add_argument("--patch")
    s.add_argument("--out")
    s.set_defaults(fn=cmd_state)

    s = sub.add_parser("render")
    for f in ("--template", "--ticket", "--charter", "--slots"):
        s.add_argument(f, required=True)
    s.add_argument("--tracking", type=int, required=True)
    s.add_argument("--by-hand", type=int)
    s.add_argument("--out", help="write the briefing to this file")
    s.add_argument("--print", action="store_true", help="print the briefing (the default without --out), to pass to create_session as it is")
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("comments", help="the owner's own words: their comments without the agents' marker")
    s.add_argument("--file", required=True, help="the issue's comments, as JSON from the GitHub API (or -)")
    s.add_argument("--owner", help="the owner's GitHub login (default: the profile's project.owner)")
    s.add_argument("--since-id", type=int, help="only comments with a greater id (the state's comments_read_through)")
    s.set_defaults(fn=cmd_comments)

    s = sub.add_parser(
        "merge-check", allow_abbrev=False, help="whether a pull request may merge under the merge rule (flow §4), from JSON files; changes nothing, posts nothing, exits 0"
    )
    for name, what in merge_mod.INPUTS.items():
        source = {
            "preview": "#41's preview reader: state built, building, failed or none; url; commit",
            "pr": "as JSON from the GitHub API",
            "compare": "as JSON from the GitHub API",
            "threads": "GraphQL's reviewThreads, with totalCount and pageInfo, every page",
        }.get(name, "as JSON from the GitHub API, every page")
        s.add_argument(f"--{name}", metavar="F", help=f"{what} ({source}); a file, or - for standard input")
    s.add_argument("--fetch", metavar="N", type=_pr_number, help="fetch every input not given as a file for pull request N, through `gh api` (the profile's project.repo), and with [previews] on = true read its try-it link (`workflow preview`); a file given wins")
    s.add_argument("--charter", metavar="F", help="the run's approved charter, as JSON, or the tracking issue's body (its run state holds it): the checks it waives (flow §4.1); ignored in an attended session")
    s.add_argument("--check-logs", metavar="DIR", help="a waived check's log, one file per check, named by its check run's id on the head (<id>, <id>.log or <id>.txt; the id is its job's), as `gh run view --log-failed --job <id>` gives its tail")
    s.add_argument("--asker", metavar="LOGIN", help="the GitHub login of whoever asks (the owner gets \"Ready once you've read\" for kit and CI files)")
    s.add_argument("--review-rounds", metavar="N", type=_review_rounds, help="the review rounds allowed, 1 to 10 (default: the profile's run.review_rounds): after the last one, a clean Correctness pass on the head lifts its findings; a run passes the briefing's")
    s.add_argument("--json", action="store_true", help="the decision, its reasons and notes, and each check's name and state, as JSON")
    s.set_defaults(fn=cmd_merge_check)

    s = sub.add_parser(
        "preview", allow_abbrev=False, help="whether a pull request's try-it link is ready for its head commit: state, url and commit, from JSON files or --fetch; changes nothing, posts nothing"
    )
    s.add_argument("--comments", metavar="F", help="the pull request's issue comments, as JSON from the GitHub API or the MCP tools, every page; a file, or - for standard input")
    s.add_argument("--checks", metavar="F", help="the head commit's check runs, as JSON from the GitHub API (GET repos/<repo>/commits/<sha>/check-runs), every page; a file, or -")
    s.add_argument("--sha", metavar="SHA", type=_sha, help="the pull request's head commit")
    s.add_argument("--fetch", metavar="N", type=_pr_number, help="read every input not given for pull request N, through `gh api` (the profile's project.repo); a file given wins")
    s.add_argument("--json", action="store_true", help="state, url and commit as JSON: what `workflow merge-check --preview` takes")
    s.set_defaults(fn=cmd_preview)

    s = sub.add_parser("briefing", help="check a ticket session's copy of its briefing against its `Briefing <hash>` line")
    s.add_argument("action", choices=["verify"])
    s.add_argument("--file", required=True, help="the briefing as the session received it (or -)")
    s.set_defaults(fn=cmd_briefing)

    s = sub.add_parser("pr-template", help="print the pull request template to write, with \"In plain words\" at the top; changes nothing")
    s.add_argument("--existing", metavar="FILE", help="the project's template: the headings go above its content (or its .github/PULL_REQUEST_TEMPLATE/ folder)")
    s.set_defaults(fn=cmd_pr_template)

    s = sub.add_parser("adopt", help="make a copy of the starter yours: the profile's owner, name and repo, CODEOWNERS, the Worker's, package's and README's names")
    s.add_argument("--owner", required=True, metavar="LOGIN", help="your GitHub login, without the @")
    s.add_argument("--repo", required=True, metavar="OWNER/NAME", help="the copy's repository on GitHub")
    s.add_argument("--name", required=True, help="the project's name; the Worker and the package get it in lower case with dashes")
    s.add_argument("--project", metavar="DIR", help="the checkout (default: this one)")
    s.set_defaults(fn=cmd_adopt)

    s = sub.add_parser(
        "review-record", allow_abbrev=False, help="the record a review round or a later Correctness pass posts on the pull request, or a spec's review on the spec"
    )
    s.add_argument("--kind", action="append", help="`round`, `pass` for a Correctness pass after the last round, or `spec` for a spec's review (the default with --body)")
    s.add_argument("--round", action="append", help="the round's number; for a pass, the round it follows")
    s.add_argument("--commit", action="append", help="the full SHA the round covered (`git rev-parse HEAD`)")
    s.add_argument("--body", action="append", metavar="FILE", help="a spec's review: the file holding the spec's body as you publish it, in place of --commit; the record names its SHA-256")
    s.add_argument("--reviewers", action="append", help="those that ran, comma-separated: " + ",".join(reviews_mod.REVIEWERS))
    result = s.add_mutually_exclusive_group()
    result.add_argument("--clean", dest="clean", action="store_true", default=None, help="nothing left to fix")
    result.add_argument("--not-clean", dest="clean", action="store_false", help="the round found something to fix")
    s.set_defaults(fn=cmd_review_record)

    s = sub.add_parser("evidence")
    s.add_argument("--suite", action="append")
    s.add_argument("--all", action="store_true", help="every suite, whatever commands.select_suites says the files need")
    s.add_argument("--base-count", type=int)
    s.add_argument("--base-ref", help="run the same suites on a worktree of this branch for the base count")
    s.add_argument("--fresh", action="store_true")
    s.add_argument("--allow-dirty", action="store_true", help="run on a dirty tree to try a profile (not a proof of the commit)")
    s.set_defaults(fn=cmd_evidence)

    s = sub.add_parser("repair")
    s.set_defaults(fn=cmd_repair)

    # Each vendor action is its own parser, so options go before or after a path.
    s = sub.add_parser("vendor")
    vsub = s.add_subparsers(dest="action", required=True)
    for name in ("install", "update"):
        v = vsub.add_parser(name)
        v.add_argument("--kit")
        v.add_argument("--mattpocock", help="a checkout of mattpocock/skills, at the kit's pinned SHA")
        v.add_argument("--no-mattpocock", action="store_true", help="go without Matt Pocock's skills, deliberately")
        v.add_argument("--project")
        v.add_argument("--adopt", action="store_true")
        v.add_argument("--strict-pin", action="store_true", help="refuse a mattpocock checkout not at the kit's pinned SHA")
        v.set_defaults(fn=cmd_vendor)
    v = vsub.add_parser("verify")
    v.add_argument("--project")
    v.add_argument("--strict", action="store_true")
    v.set_defaults(fn=cmd_vendor)
    v = vsub.add_parser("resolve")
    v.add_argument("path", help="the hand-merged file (or, with --keep, the file with a deliberate local edit)")
    v.add_argument("--project")
    v.add_argument("--keep", action="store_true", help="record a deliberate local edit that has no conflict")
    v.set_defaults(fn=cmd_vendor)

    s = sub.add_parser("hook")
    s.add_argument("name", choices=sorted(HOOKS))
    s.set_defaults(fn=cmd_hook)

    a = p.parse_args(argv)
    if a.cmd == "charter" and a.action in {"validate", "markdown", "diff", "reuse", "pin-plan", "estimate"} and not a.file:
        p.error("give the charter file")
    if a.cmd == "charter" and a.action == "diff" and not a.other:
        p.error("charter diff needs OLD and NEW")
    if a.cmd == "charter" and a.action == "splice" and not (a.body and a.charter):
        p.error("charter splice needs --body and --charter")
    if a.cmd == "state" and a.action == "init" and not (a.charter and a.run_id):
        p.error("state init needs --charter and --run-id")
    if a.cmd == "state" and a.action != "init" and not a.body:
        p.error("give --body (the tracking issue's body, a file or -)")
    if a.cmd == "state" and a.action == "put" and not a.state:
        p.error("state put needs --state")
    if a.cmd == "state" and a.action == "patch" and not a.patch:
        p.error("state patch needs --patch")
    try:
        return a.fn(a)
    except (ProfileError, state_mod.StateError, render_mod.RenderError, evidence_mod.EvidenceError, vendor_mod.VendorError) as e:
        print(f"workflow: {e}", file=sys.stderr)
        return 1

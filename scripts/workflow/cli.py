"""`workflow`: the kit's command line. Python 3.11+, standard library only.

    workflow profile check
    workflow ready [--issues F --prs F | --fetch] [--exclude 1,2] [--only 1,2] [--override 3] [--running-area A ...] [--slots N] [--json]
    workflow charter defaults | validate F [--approved] | markdown F [--tickets 13:area,143:-] | diff OLD NEW | reuse OLD | pin-plan F | questions
    workflow state init --charter F --run-id ID [--by-hand N] [--read-through ID] | get --body F | put --body F --state F | patch --body F --patch F
    workflow render --template F --ticket F --charter F --slots F --tracking N [--by-hand N]
    workflow evidence [--suite NAME ...] [--base-count N | --base-ref BRANCH] [--fresh] [--allow-dirty]
    workflow repair
    workflow vendor install|update --kit DIR [--mattpocock DIR | --no-mattpocock] [--project DIR] [--adopt] [--strict-pin]
    workflow vendor verify [--project DIR] [--strict] | resolve [--keep] PATH [--project DIR]
    workflow hook guard|gate|context|repair      (reads the hook's JSON on stdin)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import charter as charter_mod
from . import context as context_mod
from . import evidence as evidence_mod
from . import gate as gate_mod
from . import guard as guard_mod
from . import issues as issues_mod
from . import render as render_mod
from . import repair as repair_mod
from . import roles
from . import state as state_mod
from . import vendor as vendor_mod
from .profile import ProfileError, load, project_root

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
        dec, text, i = json.JSONDecoder(), p.stdout, 0
        while True:
            while i < len(text) and text[i].isspace():
                i += 1
            if i >= len(text):
                break
            try:
                value, i = dec.raw_decode(text, i)
            except json.JSONDecodeError as e:
                raise SystemExit(f"gh api {path}: couldn't read its output ({e})")
            values.append(value)
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


def cmd_charter(a) -> int:
    if a.action == "defaults":
        _out(charter_mod.defaults(profile=load(required=False)))
        return 0
    if a.action == "questions":
        _out(charter_mod.questions(profile=load(required=False)))
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
            problems += _against_profile(c, prof, who=a.approved)
        if problems:
            print("The charter has problems:\n- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        if prof is None:
            print("note: no profile found: release steps and waived checks weren't checked", file=sys.stderr)
        print("ok")
        return 0
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
        print(charter_mod.to_markdown(c, plan))
        return 0
    if a.action == "diff":
        for line in charter_mod.diff(_json(a.file), _json(a.other)):
            print(line)
        return 0
    return 2


def _against_profile(c: dict, prof, who: bool = True) -> list[str]:
    """The charter against the profile: release steps, waived checks and, with
    `who`, that the profile's project.owner approved and amended it."""
    return charter_mod.check_against_profile(
        c,
        [st["name"] for st in prof.release_steps],
        prof.required_checks,
        ci_none=prof.ci_none,
        owner=prof.owner if who else "",
    )


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
        new = state_mod.put(body, _json(a.state))
    else:  # patch
        cur = state_mod.get(body)
        if cur is None:
            raise SystemExit("no state block to patch; use `state put` first")
        new = state_mod.put(body, state_mod.patch(cur, _json(a.patch)))
    if a.out:
        Path(a.out).write_text(new, encoding="utf-8")
    else:
        print(new)
    return 0


def cmd_render(a) -> int:
    prof = load()
    vals = render_mod.values(prof, _json(a.ticket), _json(a.charter), _json(a.slots), a.tracking, a.by_hand)
    print(render_mod.render(_read(a.template), vals))
    return 0


def cmd_evidence(a) -> int:
    prof = load()
    root = prof.root
    if a.base_count is not None and a.base_ref:
        print("workflow: give --base-count or --base-ref, not both", file=sys.stderr)
        return 2
    # A bad ref fails before anything runs.
    base_sha = evidence_mod.resolve_ref(root, a.base_ref) if a.base_ref else None
    dirty = evidence_mod.dirty_paths(root) if a.allow_dirty else []
    sha, results = evidence_mod.collect(prof, root, only=a.suite, fresh=a.fresh, allow_dirty=a.allow_dirty)
    base_count, label, problem, notes = a.base_count, "", "", []
    if a.base_ref:
        b = evidence_mod.base_count_from_ref(prof, root, a.base_ref, only=a.suite, fresh=a.fresh, sha=base_sha)
        base_count, notes = b.count, b.notes
        label = f"`{a.base_ref}` at `{b.sha[:12]}`"
        if b.problem:
            problem = f"no usable base count from {a.base_ref}: {b.problem}"
    ok, md = evidence_mod.report(
        sha, prof, results, base_count, dirty=dirty, base_label=label, base_problem=problem, base_notes=notes
    )
    print(md)
    return 0 if ok else 1


def cmd_repair(a) -> int:
    prof = load()
    res = repair_mod.run(prof.repair, prof.root)
    print(repair_mod.summary(res) or "no [repair] commands in the profile")
    return 0


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
    # Counts for the routine lists; every path that needs a look in full.
    _out({k: (len(v) if k in ("written", "unchanged", "kept") else v) for k, v in r.items()})
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


def _hook_guard(event) -> int:
    firm = roles.env_role()
    if not isinstance(event, dict):  # malformed: nothing can be checked
        if firm in ("ticket", "conductor"):
            _deny_json(f"[workflow guard, {_role_label(firm)}] the hook's event wasn't a JSON object, so nothing could be checked and this was refused")
        return 0
    try:
        prof = load(required=False)
    except ProfileError as e:
        if firm in ("ticket", "conductor"):
            if not _is_restore(event):
                _deny_json(f"[workflow guard, {_role_label(firm)}] the profile is invalid, so nothing can be checked: {e}. Fix .claude/workflow/profile.toml in a PR from an attended session, or restore it: git checkout -- .claude/workflow")
            return 0
        raise
    if prof is None:
        if firm in ("ticket", "conductor") and not _is_restore(event):
            _deny_json(
                f"[workflow guard, {_role_label(firm)}] the workflow profile is missing; nothing can be checked, so this was refused. "
                "Restore it with: git checkout -- .claude/workflow"
            )
        return 0
    root = prof.root
    cwd = Path(event.get("cwd") or root)
    # A cwd with no branch (outside the repository, e.g. /tmp) takes the project root's.
    role = roles.role(cwd, prof.ticket_branch, fallback=root)
    try:
        d = guard_mod.decide(event, prof, role, root, roles.current_branch(cwd), role_from_env=firm is not None, cwd=event.get("cwd") or None)
    except Exception as e:  # fail closed where a person isn't there to notice
        if role in ("ticket", "conductor"):
            _deny_json(f"[workflow guard, {_role_label(role)}] the guard failed ({type(e).__name__}: {e}), so this was refused; rephrase the command more simply")
            return 0
        raise
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
    ctx = context_mod.context_for(event.get("prompt") or "", event.get("session_id") or "", files)
    if ctx:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
    return 0


def _hook_repair(event: dict) -> int:
    prof = load(required=False)
    if prof is None:
        return 0
    text = repair_mod.summary(repair_mod.run(prof.repair, prof.root)) if prof.repair else ""
    role = roles.role(prof.root, prof.ticket_branch)
    firm = "set by WORKFLOW_ROLE" if roles.env_role() else "from the branch name"
    text = (text + "\n" if text else "") + f"Workflow role of this session: {role} ({firm})."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


HOOKS = {"guard": _hook_guard, "gate": _hook_gate, "context": _hook_context, "repair": _hook_repair}


def cmd_hook(a) -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        event = None
    if a.name != "guard" and not isinstance(event, dict):
        event = {}  # the guard decides what a malformed event means
    try:
        return HOOKS[a.name](event)
    except ProfileError as e:
        print(f"workflow {a.name} hook: the profile is invalid, so the hook did nothing: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # a bug in a hook must not stop the session; say so
        if a.name == "guard" and roles.env_role() in ("ticket", "conductor"):
            _deny_json(f"[workflow guard] the guard failed ({type(e).__name__}: {e}), so this was refused")
            return 0
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

    s = sub.add_parser("charter")
    s.add_argument("action", choices=["defaults", "questions", "validate", "markdown", "diff", "reuse", "pin-plan"])
    s.add_argument("file", nargs="?")
    s.add_argument("other", nargs="?")
    s.add_argument("--approved", action="store_true", help="also require the owner's approval")
    s.add_argument("--tickets", help='markdown: the planned tickets in order with their areas, e.g. "13:messages,143:-"')
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
    s.set_defaults(fn=cmd_render)

    s = sub.add_parser("evidence")
    s.add_argument("--suite", action="append")
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
    if a.cmd == "charter" and a.action in {"validate", "markdown", "diff", "reuse", "pin-plan"} and not a.file:
        p.error("give the charter file")
    if a.cmd == "charter" and a.action == "diff" and not a.other:
        p.error("charter diff needs OLD and NEW")
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

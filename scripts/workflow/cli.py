"""`workflow`: the kit's command line. Python 3.11+, standard library only.

    workflow profile check
    workflow ready [--issues F --prs F | --fetch] [--exclude 1,2] [--running-area A ...] [--slots N] [--json]
    workflow charter defaults | validate F [--approved] | markdown F | diff OLD NEW | questions
    workflow state init --charter F --run-id ID [--by-hand N] | get --body F | put --body F --state F | patch --body F --patch F
    workflow render --template F --ticket F --charter F --slots F --tracking N [--by-hand N]
    workflow evidence [--suite NAME ...] [--base-count N] [--fresh]
    workflow repair
    workflow vendor install|update --kit DIR [--mattpocock DIR] [--project DIR] [--adopt] | verify [--project DIR]
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
    """Through `gh api` (the GitHub CLI, or Claude Code's built-in client)."""
    path = f"repos/{repo}/issues?state=all&per_page=100" if what == "issues" else f"repos/{repo}/pulls?state=open&per_page=100"
    p = subprocess.run(["gh", "api", "--paginate", path], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"gh api {path} failed: {p.stderr.strip()[:300]}\nFetch with the GitHub MCP tools instead and pass --issues/--prs files.")
    text = p.stdout.strip().replace("][", ",")
    return json.loads(text or "[]")


# ---------- commands ----------


def cmd_profile(a) -> int:
    prof = load()
    _out({"ok": True, "name": prof.name, "repo": prof.repo, "suites": [s.name for s in prof.suites], "explorer": prof.explorer})
    return 0


def cmd_ready(a) -> int:
    prof = load(required=False)
    if a.fetch:
        if not prof:
            raise SystemExit("--fetch needs a profile (project.repo)")
        issues, prs = _fetch(prof.repo, "issues"), _fetch(prof.repo, "pulls")
    else:
        if not a.issues or not a.prs:
            raise SystemExit("give --issues and --prs (JSON files, as the GitHub API returns them), or --fetch")
        issues, prs = _json(a.issues), _json(a.prs)
    exclude = {int(x) for x in (a.exclude or "").split(",") if x.strip()}
    verdicts = issues_mod.readiness(issues, prs, exclude=exclude)
    slots = a.slots if a.slots is not None else (prof.max_parallel if prof else 2)
    start = issues_mod.startable(verdicts, a.running_area or [], max(0, slots))
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
        print("start now: " + (", ".join(f"#{v.number}" for v in start) or "nothing"))
    return 0


def cmd_charter(a) -> int:
    if a.action == "defaults":
        _out(charter_mod.defaults())
        return 0
    if a.action == "questions":
        _out(charter_mod.QUESTIONS)
        return 0
    if a.action == "validate":
        c = _json(a.file)
        problems = charter_mod.validate(c, require_approval=a.approved)
        prof = load(required=False)
        if prof is not None and isinstance(c, dict):
            problems += charter_mod.check_against_profile(c, [s["name"] for s in prof.release_steps])
        if problems:
            print("The charter has problems:\n- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        print("ok")
        return 0
    if a.action == "markdown":
        c = _json(a.file)
        problems = charter_mod.validate(c)
        if problems:
            print("- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        print(charter_mod.to_markdown(c))
        return 0
    if a.action == "diff":
        for line in charter_mod.diff(_json(a.file), _json(a.other)):
            print(line)
        return 0
    return 2


def cmd_state(a) -> int:
    if a.action == "init":
        c = _json(a.charter)
        problems = charter_mod.validate(c, require_approval=True)
        if problems:
            print("The charter isn't ready:\n- " + "\n- ".join(problems), file=sys.stderr)
            return 1
        s = state_mod.empty(c)
        s["run_id"] = a.run_id
        s["by_hand_issue"] = a.by_hand
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
        new = state_mod.put(body, state_mod.merge_patch(cur, _json(a.patch)))
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
    sha, results = evidence_mod.collect(prof, root, only=a.suite, fresh=a.fresh)
    ok, md = evidence_mod.report(sha, prof, results, a.base_count)
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
        bad = r["missing"] or not r["hooks_ok"] or r["plugin_also_enabled"] or (a.strict and r["changed"])
        return 1 if bad else 0
    kit = Path(a.kit).resolve() if a.kit else KIT_ROOT
    mp = Path(a.mattpocock).resolve() if a.mattpocock else None
    r = vendor_mod.install(kit, project, mp, update=a.action == "update", adopt=a.adopt)
    _out({k: (len(v) if isinstance(v, list) and k in ("written", "unchanged", "adopted") else v) for k, v in r.items()})
    return 0


# ---------- hooks ----------


def _hook_guard(event: dict) -> int:
    prof = load(required=False)
    if prof is None:
        return 0
    root = prof.root
    role = roles.role(Path(event.get("cwd") or root), prof.ticket_branch)
    d = guard_mod.decide(event, prof, role, root, roles.current_branch(Path(event.get("cwd") or root)))
    if d.action == "allow":
        return 0  # never force "allow": the normal permission rules still apply
    reason = f"[workflow guard, {role} session] {d.reason}"
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
    if roles.role(Path(event.get("cwd") or root), prof.ticket_branch) != "ticket":
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
    if prof is None or not prof.repair:
        return 0
    text = repair_mod.summary(repair_mod.run(prof.repair, prof.root))
    role = roles.role(prof.root, prof.ticket_branch)
    text += f"\nWorkflow role of this session: {role}."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


HOOKS = {"guard": _hook_guard, "gate": _hook_gate, "context": _hook_context, "repair": _hook_repair}


def cmd_hook(a) -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        event = {}
    try:
        return HOOKS[a.name](event)
    except ProfileError as e:
        print(f"workflow {a.name} hook: the profile is invalid, so the hook did nothing: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # a bug in a hook must not stop the session; say so
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
    s.add_argument("--exclude")
    s.add_argument("--running-area", action="append")
    s.add_argument("--slots", type=int)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_ready)

    s = sub.add_parser("charter")
    s.add_argument("action", choices=["defaults", "questions", "validate", "markdown", "diff"])
    s.add_argument("file", nargs="?")
    s.add_argument("other", nargs="?")
    s.add_argument("--approved", action="store_true", help="also require the owner's approval")
    s.set_defaults(fn=cmd_charter)

    s = sub.add_parser("state")
    s.add_argument("action", choices=["init", "get", "put", "patch"])
    s.add_argument("--body")
    s.add_argument("--charter")
    s.add_argument("--run-id")
    s.add_argument("--by-hand", type=int)
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
    s.add_argument("--fresh", action="store_true")
    s.set_defaults(fn=cmd_evidence)

    s = sub.add_parser("repair")
    s.set_defaults(fn=cmd_repair)

    s = sub.add_parser("vendor")
    s.add_argument("action", choices=["install", "update", "verify"])
    s.add_argument("--kit")
    s.add_argument("--mattpocock")
    s.add_argument("--project")
    s.add_argument("--adopt", action="store_true")
    s.add_argument("--strict", action="store_true")
    s.set_defaults(fn=cmd_vendor)

    s = sub.add_parser("hook")
    s.add_argument("name", choices=sorted(HOOKS))
    s.set_defaults(fn=cmd_hook)

    a = p.parse_args(argv)
    if a.cmd == "charter" and a.action in {"validate", "markdown", "diff"} and not a.file:
        p.error("give the charter file")
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

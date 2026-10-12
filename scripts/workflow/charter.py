"""The run charter: what the owner approved for an unattended run, asked once
before it starts (the conductor's kick-off) and recorded on the tracking issue.

A charter is JSON. `validate` returns the problems (empty when valid);
`to_markdown` renders the one page the owner says "go" to; `diff` shows what a
new charter changes from the last run's, so a later run asks only that; `reuse`
starts a new charter from an old one, unapproved and without an end time.

`limits.ends_at` has no default: the owner always gives the end time.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

MERGE_MODES = {"auto-merge", "session", "owner"}
RELEASE_WHEN = {"never", "end", "each-merge"}
OPEN_DECISIONS = {"decide-and-record", "set-aside"}
NOTIFY = {"issue", "push"}

# The kick-off questions, in the order asked, with their recommended defaults.
QUESTIONS: list[dict[str, Any]] = [
    {
        "key": "scope",
        "ask": "Which tickets? Any to exclude? Also build tickets that get unblocked during the run?",
        "default": {"tickets": "all-ready", "exclude": [], "follow_unblocked": True},
    },
    {
        "key": "limits",
        "ask": "When does the run end (required: there is no default end time)? How many sessions at once, and retries per ticket?",
        "note": "limits.ends_at must be given by the owner: an ISO time with its zone, e.g. 2026-10-13T03:30:00Z",
        "default": {"ends_at": None, "max_parallel": 2, "max_sessions": 40, "max_retries": 1, "check_in_minutes": 20},
    },
    {
        "key": "merge",
        "ask": "Merge automatically when a ticket passes the merge rule? Which CI checks, if any, may be waived when killed (not failed)?",
        "default": {"mode": "auto-merge", "waived_checks": []},
    },
    {
        "key": "release",
        "ask": "Deploy and build after merges? Never, after each merge, or once at the end? Which steps?",
        "default": {"when": "end", "steps": [], "smoke_test": True},
    },
    {
        "key": "outward",
        "ask": "May it change anything outside the repo (cloud settings, secrets, accounts, DNS, payments)? Which, exactly?",
        "default": {"allowed": []},
    },
    {
        "key": "conductor_fixes",
        "ask": "May the conductor open its own PRs for test, CI or deploy-script problems (each reviewed and logged)?",
        "default": True,
    },
    {
        "key": "open_decisions",
        "ask": "When a ticket leaves a product decision open: take the safest choice and record it, or set the ticket aside for you?",
        "default": "decide-and-record",
    },
    {
        "key": "stop_run_on",
        "ask": "Anything that should stop the whole run, rather than be set aside and reported?",
        "default": [],
    },
    {
        "key": "notify",
        "ask": "How to reach you: the tracking issue only, or also a phone notification for a failure or the final report?",
        "default": {"failures": "issue", "final_report": "push"},
    },
]


def defaults(release_steps: list[str] | None = None) -> dict:
    """The recommended answers. Releases default to "never" without release steps,
    else to "end" with the first. limits.ends_at stays null: the owner gives it."""
    out: dict[str, Any] = {"version": 1}
    for q in QUESTIONS:
        out[q["key"]] = json.loads(json.dumps(q["default"]))
    if release_steps:
        out["release"]["when"] = "end"
        out["release"]["steps"] = [release_steps[0]]
    else:
        out["release"]["when"] = "never"
        out["release"]["steps"] = []
    out["accepted_gaps"] = []
    out["approved"] = None
    out["amendments"] = []
    return out


def reuse(old: dict) -> dict:
    """A new charter from an earlier run's: the same answers, not approved, no
    amendments, and no end time (the owner gives a new one)."""
    c = json.loads(json.dumps(old))
    c["approved"] = None
    c["amendments"] = []
    if isinstance(c.get("limits"), dict):
        c["limits"]["ends_at"] = None
    c.setdefault("accepted_gaps", [])
    return c


def _is_int_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in v)


def _pos_int(v, lo=1, hi=1000) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _time(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _iso(v) -> bool:
    return _time(v) is not None


def _strings(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


APPROVAL_SKEW = timedelta(minutes=10)


def validate(c: Any, require_approval: bool = False, now: datetime | None = None) -> list[str]:
    """The charter's problems, empty when valid. With require_approval it must be
    approved and its end time still ahead (as at `now`, default the clock)."""
    now = now or datetime.now(timezone.utc)
    p: list[str] = []
    if not isinstance(c, dict):
        return ["the charter must be a JSON object"]
    if c.get("version") != 1:
        p.append("version must be 1")
    s = c.get("scope")
    if not isinstance(s, dict):
        p.append("scope must be an object")
    else:
        t = s.get("tickets")
        if t != "all-ready" and not (_is_int_list(t) and t):
            p.append('scope.tickets must be "all-ready" or a non-empty list of issue numbers')
        if not _is_int_list(s.get("exclude", [])):
            p.append("scope.exclude must be a list of issue numbers")
        if not isinstance(s.get("follow_unblocked"), bool):
            p.append("scope.follow_unblocked must be true or false")
        if _is_int_list(t) and t and _is_int_list(s.get("exclude", [])) and not set(t) - set(s.get("exclude") or []):
            p.append("scope.tickets minus scope.exclude leaves nothing to build")
    lim = c.get("limits")
    if not isinstance(lim, dict):
        p.append("limits must be an object")
    else:
        if not _iso(lim.get("ends_at")):
            p.append("limits.ends_at must be an ISO time with its zone, e.g. 2026-10-13T03:30:00Z")
        for k, lo, hi in (("max_parallel", 1, 16), ("max_sessions", 1, 500), ("max_retries", 0, 5), ("check_in_minutes", 5, 240)):
            if not _pos_int(lim.get(k), lo, hi):
                p.append(f"limits.{k} must be a whole number from {lo} to {hi}")
        if _pos_int(lim.get("max_parallel"), 1, 16) and _pos_int(lim.get("max_sessions"), 1, 500):
            if lim["max_parallel"] > lim["max_sessions"]:
                p.append("limits.max_parallel can't be more than limits.max_sessions")
        ends = _time(lim.get("ends_at"))
        if ends and require_approval and ends <= now:
            p.append(f"limits.ends_at ({lim['ends_at']}) has passed: give a new end time")
    m = c.get("merge")
    if not isinstance(m, dict):
        p.append("merge must be an object")
    else:
        if m.get("mode") not in MERGE_MODES:
            p.append(f"merge.mode must be one of {sorted(MERGE_MODES)}")
        w = m.get("waived_checks", [])
        if not (isinstance(w, list) and all(isinstance(x, str) and x for x in w)):
            p.append("merge.waived_checks must be a list of check names")
        elif w and m.get("mode") == "auto-merge":
            p.append(
                "merge.waived_checks with merge.mode auto-merge: Auto-merge can't tell killed from failed; "
                "use mode session, where the session checks the killed markers before merging."
            )
    r = c.get("release")
    if not isinstance(r, dict):
        p.append("release must be an object")
    else:
        if r.get("when") not in RELEASE_WHEN:
            p.append(f"release.when must be one of {sorted(RELEASE_WHEN)}")
        st = r.get("steps", [])
        if not (isinstance(st, list) and all(isinstance(x, str) and x for x in st)):
            p.append("release.steps must be a list of the profile's release step names")
        if r.get("when") != "never" and not st:
            p.append('release.steps must name at least one step unless release.when is "never"')
        if not isinstance(r.get("smoke_test", True), bool):
            p.append("release.smoke_test must be true or false")
    o = c.get("outward")
    if not isinstance(o, dict) or not (
        isinstance(o.get("allowed"), list) and all(isinstance(x, str) and x for x in o["allowed"])
    ):
        p.append("outward.allowed must be a list of the outside changes allowed, each in words")
    if not isinstance(c.get("conductor_fixes"), bool):
        p.append("conductor_fixes must be true or false")
    if c.get("open_decisions") not in OPEN_DECISIONS:
        p.append(f"open_decisions must be one of {sorted(OPEN_DECISIONS)}")
    sr = c.get("stop_run_on")
    if not (isinstance(sr, list) and all(isinstance(x, str) and x for x in sr)):
        p.append("stop_run_on must be a list of conditions in words")
    n = c.get("notify")
    if not isinstance(n, dict) or n.get("failures") not in NOTIFY or n.get("final_report") not in NOTIFY:
        p.append(f"notify.failures and notify.final_report must each be one of {sorted(NOTIFY)}")
    if not _strings(c.get("accepted_gaps", [])):
        p.append("accepted_gaps must be a list of the safety setup the owner chose to go ahead without, each in words")
    a = c.get("approved")
    if a is not None:
        if not isinstance(a, dict) or not a.get("by") or not _iso(a.get("at")) or not a.get("source"):
            p.append("approved must have by, at (ISO time) and source (a comment URL or the owner's quoted words)")
        else:
            at = _time(a["at"])
            if at > now + APPROVAL_SKEW:
                p.append(f"approved.at ({a['at']}) is in the future")
            ends = _time((lim or {}).get("ends_at")) if isinstance(lim, dict) else None
            if ends and ends <= at:
                p.append(f"limits.ends_at ({lim['ends_at']}) must be after approved.at ({a['at']})")
    elif require_approval:
        p.append("the charter has not been approved: the owner's go is needed, with its source")
    am = c.get("amendments", [])
    if not isinstance(am, list):
        p.append("amendments must be a list")
    else:
        for i, x in enumerate(am):
            if not isinstance(x, dict) or not x.get("change") or not x.get("source") or not _iso(x.get("at")):
                p.append(f"amendments[{i}] needs change, source and at")
    return p


def check_against_profile(c: dict, release_step_names: list[str], required_checks: list[str]) -> list[str]:
    p: list[str] = []
    r = c.get("release") or {}
    for s in r.get("steps") or []:
        if s not in release_step_names:
            p.append(f"release step {s!r} is not in the profile's [release] steps {release_step_names}")
    for w in (c.get("merge") or {}).get("waived_checks") or []:
        if w not in required_checks:
            p.append(f"waived check {w!r} is not one of the profile's ci.required_checks {required_checks}")
    return p


def _yn(b) -> str:
    return "yes" if b else "no"


def parse_tickets(spec: str) -> list[tuple[int, str | None]]:
    """ "13:messages,143:-" -> [(13, "messages"), (143, None)]: the plan, in order."""
    out: list[tuple[int, str | None]] = []
    for part in [x.strip() for x in (spec or "").split(",") if x.strip()]:
        num, _, area = part.partition(":")
        num = num.strip().lstrip("#")
        if not num.isdigit():
            raise ValueError(f"--tickets: {part!r} should be <issue number>:<area or ->")
        area = area.strip()
        out.append((int(num), None if area in ("", "-") else area))
    return out


def to_markdown(c: dict, plan: list[tuple[int, str | None]] | None = None) -> str:
    s, lim, m, r, o, n = c["scope"], c["limits"], c["merge"], c["release"], c["outward"], c["notify"]
    tickets = "every ready ticket" if s["tickets"] == "all-ready" else ", ".join(f"#{t}" for t in s["tickets"])
    excl = ", ".join(f"#{t}" for t in s.get("exclude") or []) or "none"
    lines = [
        "## Run charter",
        "",
        f"- **Scope:** {tickets}; excluded: {excl}; tickets unblocked during the run: {_yn(s['follow_unblocked'])}.",
        f"- **Limits:** ends {lim['ends_at']}; {lim['max_parallel']} sessions at once, {lim['max_sessions']} in all; "
        f"{lim['max_retries']} retry per ticket, then `needs-human`; check-ins every {lim['check_in_minutes']} minutes.",
        f"- **Merging:** {m['mode']}"
        + (f"; checks that may be waived when killed (not failed): {', '.join(m['waived_checks'])}" if m.get("waived_checks") else "; no CI waivers")
        + ".",
        f"- **Release:** {r['when']}"
        + (f" ({', '.join(r['steps'])}{', with smoke test' if r.get('smoke_test', True) else ''})" if r["when"] != "never" else "")
        + ".",
        f"- **Changes outside the repo allowed:** {'; '.join(o['allowed']) if o['allowed'] else 'none (listed as owner tasks instead)'}.",
        f"- **Conductor's own fix PRs:** {_yn(c['conductor_fixes'])}.",
        f"- **Open product decisions:** {'take the safest choice and record it in the PR' if c['open_decisions'] == 'decide-and-record' else 'set the ticket aside for the owner'}.",
        f"- **Stops the whole run:** {'; '.join(c['stop_run_on']) if c['stop_run_on'] else 'nothing (problems are set aside and reported)'}.",
        f"- **Reaching the owner:** failures by {n['failures']}, the final report by {n['final_report']}.",
        "- **Safety setup gone without (the owner's choice):** "
        + ("; ".join(c.get("accepted_gaps") or []) or "none")
        + ".",
        "- **Kill switch:** the `workflow:stop` label on this issue stops the run at the next check-in.",
    ]
    if plan:
        lines += ["", "### Plan", ""]
        lines += [f"{i}. #{n} ({area or 'no area'})" for i, (n, area) in enumerate(plan, 1)]
    a = c.get("approved")
    lines.append("")
    lines.append(f"**Approved** by {a['by']} at {a['at']}: {a['source']}" if a else "**Not yet approved.** Reply \"go\" to approve.")
    for x in c.get("amendments") or []:
        lines.append(f"- Amended {x['at']}: {x['change']} ({x['source']})")
    return "\n".join(lines)


def diff(old: dict, new: dict) -> list[str]:
    """What a new charter changes from an earlier one, key by key."""
    out = []
    for k in [q["key"] for q in QUESTIONS] + ["accepted_gaps", "approved"]:
        empty = [] if k == "accepted_gaps" else None
        if old.get(k, empty) != new.get(k, empty):
            out.append(f"{k}: {json.dumps(old.get(k))} -> {json.dumps(new.get(k))}")
    return out

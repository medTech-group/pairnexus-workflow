"""The run charter: what the owner approved for an unattended run, asked once
before it starts (the conductor's kick-off) and recorded on the tracking issue.

A charter is JSON. `validate` returns the problems (empty when valid);
`to_markdown` renders the one page the owner says "go" to; `diff` shows what a
new charter changes from the last run's, so a later run asks only that; `reuse`
starts a new charter from an old one, unapproved and without an end time.

`limits.ends_at` has no default: the owner always gives the end time.

`plan` (optional) is the list of ticket numbers the owner approved, in order:
the one page shows it. At approval the conductor sets `scope.tickets` to that
list when `scope.follow_unblocked` is false (`pin_plan`), so the run builds
exactly what was approved; with follow_unblocked true the scope stays as
given and tickets unblocked during the run join it. A plan's tickets must be in
the scope and not excluded.

Every amendment is `{at, by, change, source}`: when, who (the owner's login),
what changed, and the comment URL or quoted words it came from.
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
        "ask": "When does the run end (ends_at; required: there is no default end time)? How many sessions at once "
        "(max_parallel), how many in all (max_sessions), how many retries per ticket (max_retries), and how often "
        "to check in (check_in_minutes)?",
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


def defaults(release_steps: list[str] | None = None, profile: Any = None) -> dict:
    """The recommended answers, fitted to the profile when given. Releases default
    to "never" without release steps, else to "end" with the first. The limits'
    max_parallel, max_retries and check_in_minutes come from the profile's [run].
    Merging defaults to "session" when the profile has no CI (ci.none) or no
    required checks, since auto-merge would merge with nothing checked.
    limits.ends_at stays null: the owner gives it."""
    if release_steps is None and profile is not None:
        release_steps = [st["name"] for st in getattr(profile, "release_steps", []) or []]
    out: dict[str, Any] = {"version": 1}
    for q in QUESTIONS:
        out[q["key"]] = json.loads(json.dumps(q["default"]))
    if release_steps:
        out["release"]["when"] = "end"
        out["release"]["steps"] = [release_steps[0]]
    else:
        out["release"]["when"] = "never"
        out["release"]["steps"] = []
    if profile is not None:
        lim = out["limits"]
        for k in ("max_parallel", "max_retries", "check_in_minutes"):
            v = getattr(profile, k, None)
            if isinstance(v, int) and not isinstance(v, bool):
                lim[k] = v
        lim["check_in_minutes"] = min(max(lim["check_in_minutes"], 5), 240)
        lim["max_sessions"] = max(lim["max_sessions"], lim["max_parallel"])
        if getattr(profile, "ci_none", False) or not getattr(profile, "required_checks", None):
            out["merge"]["mode"] = "session"
    out["accepted_gaps"] = []
    out["approved"] = None
    out["amendments"] = []
    return out


def questions(release_steps: list[str] | None = None, profile: Any = None) -> list[dict]:
    """The kick-off questions with defaults fitted to the profile, as `defaults` gives them."""
    d = defaults(release_steps, profile)
    out = json.loads(json.dumps(QUESTIONS))
    for q in out:
        q["default"] = d[q["key"]]
    return out


def reuse(old: dict) -> dict:
    """A new charter from an earlier run's: the same answers, not approved, no
    amendments, no accepted gaps (they are asked again), no plan (the tickets
    have changed), and no end time (the owner gives a new one). A ticket list in
    `scope.tickets` that came from the old plan is reset to "all-ready"."""
    c = json.loads(json.dumps(old))
    c["approved"] = None
    c["amendments"] = []
    c["accepted_gaps"] = []
    old_plan = c.pop("plan", None)
    scope = c.get("scope")
    if isinstance(scope, dict) and old_plan is not None and scope.get("tickets") == old_plan:
        scope["tickets"] = "all-ready"
    if isinstance(c.get("limits"), dict):
        c["limits"]["ends_at"] = None
    return c


def pin_plan(c: dict) -> dict:
    """At approval: with follow_unblocked false, scope.tickets becomes the plan
    (`workflow charter pin-plan F`)."""
    out = json.loads(json.dumps(c))
    plan, scope = out.get("plan"), out.get("scope")
    if plan and isinstance(scope, dict) and scope.get("follow_unblocked") is False:
        scope["tickets"] = list(plan)
    return out


def _is_int_list(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in v)


def _pos_int(v, lo=1, hi=1000) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _time(v) -> datetime | None:
    if not isinstance(v, str):
        return None
    if v[-1:] in ("Z", "z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _iso(v) -> bool:
    return _time(v) is not None


def _strings(v) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def _one_of(v, allowed: set[str]) -> bool:
    """A string in `allowed`: never raises on a list or an object, which can't be hashed."""
    return isinstance(v, str) and v in allowed


def _login(v: str) -> str:
    return v.strip().lstrip("@").casefold()


APPROVAL_SKEW = timedelta(minutes=10)

# Every key a charter may hold, so a typo ("max_paralel") is refused rather than ignored.
KEYS = {
    "version", "scope", "limits", "merge", "release", "outward", "conductor_fixes", "open_decisions",
    "stop_run_on", "notify", "accepted_gaps", "approved", "amendments", "plan",
}
SUBKEYS = {
    "scope": {"tickets", "exclude", "follow_unblocked"},
    "limits": {"ends_at", "max_parallel", "max_sessions", "max_retries", "check_in_minutes"},
    "merge": {"mode", "waived_checks"},
    "release": {"when", "steps", "smoke_test"},
    "outward": {"allowed"},
    "notify": {"failures", "final_report"},
    "approved": {"by", "at", "source"},
}
AMENDMENT_KEYS = {"at", "by", "change", "source"}


def _unknown(keys, allowed: set[str], where: str) -> list[str]:
    bad = sorted(str(k) for k in keys if k not in allowed)
    if not bad:
        return []
    return [f"{where}: unknown key{'s' if len(bad) > 1 else ''} {', '.join(repr(k) for k in bad)}; allowed: {', '.join(sorted(allowed))}"]


def validate(c: Any, require_approval: bool = False, now: datetime | None = None) -> list[str]:
    """The charter's problems, empty when valid. With require_approval it must be
    approved and its end time still ahead (as at `now`, default the clock)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    p: list[str] = []
    if not isinstance(c, dict):
        return ["the charter must be a JSON object"]
    p += _unknown(c, KEYS, "the charter")
    for k, allowed in SUBKEYS.items():
        if isinstance(c.get(k), dict):
            p += _unknown(c[k], allowed, k)
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
        if not _one_of(m.get("mode"), MERGE_MODES):
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
        if not _one_of(r.get("when"), RELEASE_WHEN):
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
    if not _one_of(c.get("open_decisions"), OPEN_DECISIONS):
        p.append(f"open_decisions must be one of {sorted(OPEN_DECISIONS)}")
    sr = c.get("stop_run_on")
    if not (isinstance(sr, list) and all(isinstance(x, str) and x for x in sr)):
        p.append("stop_run_on must be a list of conditions in words")
    n = c.get("notify")
    if not isinstance(n, dict) or not _one_of(n.get("failures"), NOTIFY) or not _one_of(n.get("final_report"), NOTIFY):
        p.append(f"notify.failures and notify.final_report must each be one of {sorted(NOTIFY)}")
    if not _strings(c.get("accepted_gaps", [])):
        p.append("accepted_gaps must be a list of the safety setup the owner chose to go ahead without, each in words")
    a = c.get("approved")
    if a is not None:
        if not isinstance(a, dict) or not _strings([a.get("by"), a.get("source")]) or not _iso(a.get("at")):
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
    p += validate_amendments(c.get("amendments", []))
    plan = c.get("plan")
    if plan is not None:
        if not (_is_int_list(plan) and plan):
            p.append("plan must be a non-empty list of issue numbers (the tickets the owner approved), or absent")
        elif isinstance(s, dict):
            t = s.get("tickets")
            if _is_int_list(t):
                out = [n for n in plan if n not in t]
                if out:
                    p.append(f"plan tickets {', '.join(f'#{n}' for n in out)} aren't in scope.tickets")
            ex = s.get("exclude") or []
            if _is_int_list(ex):
                both = [n for n in plan if n in ex]
                if both:
                    p.append(f"plan tickets {', '.join(f'#{n}' for n in both)} are in scope.exclude")
    return p


def validate_amendments(am: Any, owner: str = "", structure: bool = True) -> list[str]:
    """The amendments' problems: each `{at, by, change, source}`; with `owner`
    (the profile's project.owner), each made by the owner. Without `structure`,
    only the owner check."""
    p: list[str] = []
    if not isinstance(am, list):
        return ["amendments must be a list"] if structure else []
    for i, x in enumerate(am):
        if not isinstance(x, dict):
            if structure:
                p.append(f"amendments[{i}] must be an object with at, by, change and source")
            continue
        if structure:
            p += _unknown(x, AMENDMENT_KEYS, f"amendments[{i}]")
            if not all(isinstance(x.get(k), str) and x[k].strip() for k in ("by", "change", "source")) or not _iso(x.get("at")):
                p.append(f"amendments[{i}] needs at (ISO time), by (who), change and source")
        by = x.get("by")
        if owner and isinstance(by, str) and by.strip() and _login(by) != _login(owner):
            p.append(f"amendments[{i}].by ({by}) isn't the profile's project.owner ({owner}): only the owner amends a run")
    return p


def check_against_profile(
    c: dict,
    release_step_names: list[str],
    required_checks: list[str],
    ci_none: bool = False,
    owner: str = "",
) -> list[str]:
    """The charter against the profile: release steps and waived checks it names,
    auto-merge with nothing checked, and (with `owner`, the profile's
    project.owner) who approved it."""
    p: list[str] = []
    if not isinstance(c, dict):
        return p

    def obj(k: str) -> dict:
        v = c.get(k)
        return v if isinstance(v, dict) else {}

    def strs(v) -> list[str]:
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []

    r, m = obj("release"), obj("merge")
    for s in strs(r.get("steps")):
        if s not in release_step_names:
            p.append(f"release step {s!r} is not in the profile's [release] steps {release_step_names}")
    for w in strs(m.get("waived_checks")):
        if w not in required_checks:
            p.append(f"waived check {w!r} is not one of the profile's ci.required_checks {required_checks}")
    if m.get("mode") == "auto-merge" and (ci_none or not required_checks):
        why = "ci.none is true" if ci_none else "the profile has no ci.required_checks"
        p.append(f"merge.mode auto-merge: {why}, so auto-merge would merge at once with nothing checked; use session")
    a = c.get("approved")
    if owner and isinstance(a, dict) and isinstance(a.get("by"), str):
        if _login(a["by"]) != _login(owner):
            p.append(f"approved.by ({a['by']}) isn't the profile's project.owner ({owner}): only the owner approves a run")
    p += validate_amendments(c.get("amendments", []), owner, structure=False)
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
    if plan is None and c.get("plan"):
        plan = [(n, None) for n in c["plan"]]
        areas_known = False
    else:
        areas_known = True
    if plan:
        lines += ["", "### Plan", ""]
        lines += [
            f"{i}. #{n} ({area or ('no area' if areas_known else 'area not given')})" for i, (n, area) in enumerate(plan, 1)
        ]
    else:
        lines += ["", "Plan: not given (pass --tickets)"]
    a = c.get("approved")
    lines.append("")
    lines.append(f"**Approved** by {a['by']} at {a['at']}: {a['source']}" if a else "**Not yet approved.** Reply \"go\" to approve.")
    for x in c.get("amendments") or []:
        by = f" by {x['by']}" if x.get("by") else ""
        lines.append(f"- Amended {x['at']}{by}: {x['change']} ({x['source']})")
    return "\n".join(lines)


SECTION_BEGIN = "<!-- workflow-charter:begin -->"
SECTION_END = "<!-- workflow-charter:end -->"


class SpliceError(ValueError):
    pass


def splice(body: str, markdown: str) -> str:
    """The tracking issue's body with its charter section (between the two
    markers) replaced by `markdown`; the rest of the body as it was."""
    body = body or ""
    begins, ends = body.count(SECTION_BEGIN), body.count(SECTION_END)
    if begins != 1 or ends != 1:
        raise SpliceError(
            f"the body needs exactly one {SECTION_BEGIN} and one {SECTION_END} around its charter section "
            f"(it has {begins} and {ends}); add them around the charter, as templates/tracking-issue.md has them"
        )
    start, end = body.index(SECTION_BEGIN) + len(SECTION_BEGIN), body.index(SECTION_END)
    if end < start:
        raise SpliceError(f"{SECTION_END} comes before {SECTION_BEGIN}; put the charter section between them")
    return body[:start] + "\n" + markdown.strip("\n") + "\n" + body[end:]


def diff(old: dict, new: dict) -> list[str]:
    """What a new charter changes from an earlier one, key by key."""
    old = old if isinstance(old, dict) else {}
    new = new if isinstance(new, dict) else {}
    out = []
    for k in [q["key"] for q in QUESTIONS] + ["plan", "accepted_gaps", "amendments", "approved"]:
        empty = [] if k in ("accepted_gaps", "amendments") else None
        if old.get(k, empty) != new.get(k, empty):
            out.append(f"{k}: {json.dumps(old.get(k))} -> {json.dumps(new.get(k))}")
    return out

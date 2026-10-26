"""Roughly what a run will use, before it starts (#123, part of #42; decided in #31).

In sessions and hours, never money: the kit can't read the account's usage or
prices. `workflow charter estimate` feeds it the charter (unapproved is fine),
the number of tickets in the plan and, optionally, past runs' tracking issues
as the GitHub API returns them (`workflow:run` issues, their bodies holding the
run state), as `workflow ready --issues` takes issues.

- **Sessions:** tickets × (1 + `max_retries`), the worst case. With two or more
  past runs, tickets × their average sessions per ticket (the sum of `attempts`
  over the tickets they started), never below one per ticket.
- **Hours:** ceil(sessions ÷ `max_parallel`) waves × one hour, or, with two or
  more past runs, × their average wall time per merged ticket (`started_at` to
  `merged_at`). Rounded to the hour.
- **Past runs:** the five most recent closed `workflow:run` issues with at
  least one merged ticket. A body whose run state can't be read is skipped
  with a note, never a crash.
- **Warnings,** in words, never blocking: the end time cuts the run short,
  `max_sessions` is below the tickets' first tries plus retries, or the review
  is lighter than the project's default while the plan holds a ticket the
  review panel would give a security review (`security`, named by the caller).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from . import charter as charter_mod
from . import presets as presets_mod
from . import state as state_mod

MAX_RUNS = 5  # past runs read at most
MIN_RUNS = 2  # fewer than this means the defaults
DEFAULT_BASIS = "assuming about an hour a session"
RUN_LABEL = "workflow:run"


class EstimateError(ValueError):
    pass


_int = state_mod._int


def _num(v: float) -> str:
    """1.0 -> "1", 1.25 -> "1.2": a figure said roughly."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _duration(h: float) -> str:
    """0.75 -> "45 minutes", 1.5 -> "1.5 hours"."""
    if round(h * 60) < 60:
        return presets_mod.plural(max(1, round(h * 60)), "minute", "minutes")
    return f"{_num(h)} {'hour' if _num(h) == '1' else 'hours'}"


def _round_hours(h: float) -> int:
    return max(1, math.floor(h + 0.5))


def _labels(issue: dict) -> set[str]:
    labels = issue.get("labels")
    if not isinstance(labels, list):
        return set()
    names = [x.get("name") if isinstance(x, dict) else x for x in labels]
    return {x for x in names if isinstance(x, str)}


def _run_of(issue: dict) -> tuple[dict | None, str | None]:
    """A past run's figures from its tracking issue, or a note saying why it was skipped."""
    who = f"#{issue['number']}"  # past_runs passes only issues with a number
    body = issue.get("body")
    if body is not None and not isinstance(body, str):
        return None, f"{who} skipped: its body isn't text"
    try:
        s = state_mod.get(body or "")
    except state_mod.StateError as e:
        # Without the repair advice: that is for the run in progress, not a past one.
        why = str(e).replace(f"; {state_mod.RECOVER}", "").replace(f": {state_mod.RECOVER}", "")
        return None, f"{who} skipped: its run state can't be read ({why})"
    if s is None:
        return None, None  # no run state: a kick-off abandoned before the go, never a run
    tickets = s.get("tickets") if isinstance(s, dict) else None
    if not isinstance(tickets, dict):
        return None, f"{who} skipped: its run state has no tickets"
    attempts = started = merged = 0
    hours: list[float] = []
    for k, t in tickets.items():
        if not isinstance(t, dict) or not isinstance(t.get("status"), str) or t["status"] not in state_mod.TICKET_STATUSES:
            return None, f"{who} skipped: ticket {k} has no status the kit knows"
        for f in ("attempts", "started_at", "merged_at"):
            ok, what = state_mod.TICKET_FIELDS[f]
            if t.get(f) is not None and not ok(t[f]):
                return None, f"{who} skipped: ticket {k}'s {f} isn't {what}"
        a = t.get("attempts")
        if a is None and t["status"] == "merged":
            a = 1  # an older state without attempts: a merged ticket had at least one
        if _int(a) and a > 0:
            attempts += a
            started += 1
        if t["status"] == "merged":
            merged += 1
            st, mt = charter_mod._time(t.get("started_at")), charter_mod._time(t.get("merged_at"))
            if st and mt and mt > st:
                hours.append((mt - st).total_seconds() / 3600)
    if not merged:
        return None, None  # merged nothing: not counted, and nothing wrong with it
    return {"who": who, "attempts": attempts, "started": started, "hours": hours}, None


def _closed_at(issue: dict) -> datetime:
    # `closed_at` from the REST API (`gh api`), `closedAt` from the GitHub MCP tools.
    return charter_mod._time(issue.get("closed_at") or issue.get("closedAt")) or datetime.min.replace(tzinfo=timezone.utc)


def _closed(issue: dict) -> bool:
    """Closed, or no state given; "CLOSED" as the GitHub MCP tools say it."""
    v = issue.get("state")
    return v is None or (isinstance(v, str) and v.lower() == "closed")


def _flatten(v: Any) -> list:
    """Issues from a list, the GitHub MCP tools' wrapped list (`{"issues": […]}`),
    search's (`{"items": […]}`), or pages of any of them (`gh api --paginate
    --slurp`, or MCP pages saved together)."""
    if isinstance(v, list):
        return [y for x in v for y in _flatten(x)]
    if isinstance(v, dict) and any(isinstance(v.get(k), list) for k in ("issues", "items")):
        return [y for k in ("issues", "items") if isinstance(v.get(k), list) for y in _flatten(v[k])]
    return [v]


def past_runs(issues: Any) -> tuple[list[dict], list[str]]:
    """The five most recent closed `workflow:run` issues with a merged ticket,
    newest first, and the notes on the ones skipped."""
    if not isinstance(issues, (list, dict)):
        raise EstimateError("the past runs must be a JSON list of issues, as the GitHub API returns them")
    issues = _flatten(issues)
    candidates = [
        x
        for x in issues
        if isinstance(x, dict)
        and _int(x.get("number"))
        and "pull_request" not in x
        and _closed(x)
        and ("labels" not in x or RUN_LABEL in _labels(x))
    ]
    candidates.sort(key=lambda x: (_closed_at(x), x["number"]), reverse=True)
    runs: list[dict] = []
    notes: list[str] = [
        f"an entry that isn't an issue was skipped ({' '.join(x['message'].split())[:200]})"
        if isinstance(x, dict) and isinstance(x.get("message"), str)
        else "an entry that isn't an issue was skipped"
        for x in issues
        if not (isinstance(x, dict) and _int(x.get("number")))
    ]
    for x in candidates:
        if len(runs) == MAX_RUNS:
            break
        run, note = _run_of(x)
        if note:
            notes.append(note)
        if run:
            runs.append(run)
    return runs, notes


def _limits(c: Any) -> dict:
    lim = c.get("limits") if isinstance(c, dict) else None
    if not isinstance(lim, dict):
        raise EstimateError("the charter has no limits")
    for key, lo in (("max_parallel", 1), ("max_sessions", 1), ("max_retries", 0)):
        if not (_int(lim.get(key)) and lim[key] >= lo):
            raise EstimateError(f"limits.{key} must be a whole number, {lo} or more")
    return lim


def _review(c: dict, profile: Any) -> dict | None:
    """The run's review, or None when the charter's `review` or `preset` isn't
    well formed (an unvalidated charter): then nothing is said about it."""
    r = c.get("review")
    if "review" in c and not (isinstance(r, dict) and _int(r.get("rounds")) and 1 <= r["rounds"] <= 10 and isinstance(r.get("explorer"), bool)):
        return None
    if "preset" in c and c["preset"] not in presets_mod.PRESETS:
        return None
    return presets_mod.review_of(c, profile)


def _runs_explorer(rv: dict, profile: Any) -> bool:
    """The review runs the UI explorer, and the profile, when it reads, has one
    (as `presets.small_reviewers` says, #296)."""
    return presets_mod.runs_explorer(rv) and (profile is None or presets_mod.has_explorer(profile))


def _review_words(rv: dict, profile: Any) -> str:
    return f"up to {presets_mod.plural(rv['rounds'], 'round', 'rounds')}, " + (
        "UI explorer on" if _runs_explorer(rv, profile) else "no UI explorer"
    )


def estimate(
    c: dict,
    tickets: int,
    issues: Any = None,
    security: list[int] | None = None,
    profile: Any = None,
    now: datetime | None = None,
) -> dict:
    """The estimate: `sessions`, `hours`, `basis`, `runs_used`, `warnings`, plus
    `line` (the plain sentence), `tickets` and `notes` (past runs skipped)."""
    if not (_int(tickets) and tickets >= 1):
        raise EstimateError("the plan needs at least one ticket")
    lim = _limits(c)
    retries, parallel = lim["max_retries"], lim["max_parallel"]
    runs, notes = past_runs(issues) if issues is not None else ([], [])
    if len(runs) >= MIN_RUNS:
        # Never below one session a ticket, nor above the tries the charter allows.
        average = sum(r["attempts"] for r in runs) / max(1, sum(r["started"] for r in runs))
        per_ticket = min(max(1.0, average), float(1 + retries))
        hours_each = [h for r in runs for h in r["hours"]]
        # A ticket's `started_at` is its latest session's start, so this is a session's wall time.
        hours_a_ticket = sum(hours_each) / len(hours_each) if hours_each else 1.0
        sessions = math.ceil(tickets * per_ticket - 1e-9)
        a_ticket = f"about {_num(per_ticket)} {'session' if _num(per_ticket) == '1' else 'sessions'}"
        took = f"{_duration(hours_a_ticket)} a ticket" if hours_each else "an hour a ticket (no merge times over zero to go on)"
        basis = f"from your last {len(runs)} runs: {a_ticket} and {took}"
        each = f"{a_ticket} each"
        runs_used = len(runs)
    else:
        if len(runs) == 1:
            notes.append(f"only 1 past run merged anything ({runs[0]['who']}): the defaults until there are {MIN_RUNS}")
        per_ticket, hours_a_ticket = float(1 + retries), 1.0
        sessions = tickets * (1 + retries)
        basis = DEFAULT_BASIS
        each = f"up to {presets_mod.plural(retries, 'retry', 'retries')} each" if retries else "no retries"
        runs_used = 0
    waves = math.ceil(sessions / parallel)
    hours = _round_hours(waves * hours_a_ticket)
    line = (
        f"About {presets_mod.plural(sessions, 'ticket session', 'ticket sessions')} over roughly "
        f"{presets_mod.plural(hours, 'hour', 'hours')} ({presets_mod.plural(tickets, 'ticket', 'tickets')}, {each}), "
        "plus the conductor's check-ins"
    )

    warnings: list[str] = []
    ends = charter_mod._time(lim.get("ends_at"))
    if ends is None and lim.get("ends_at") is not None:
        notes.append("limits.ends_at isn't an ISO time with its zone, so the end time wasn't checked")
    if ends is not None:
        left = (ends - (now or datetime.now(timezone.utc))).total_seconds() / 3600
        fit = math.floor(left / hours_a_ticket + 1e-9) if left > 0 else 0
        if fit < waves:
            done = min(tickets - 1, math.floor(fit * parallel / per_ticket + 1e-9))
            if left <= 0:
                away = f"{lim['ends_at']} has passed"
            elif left < 1:
                away = f"{lim['ends_at']} is less than an hour away"
            else:
                away = f"{lim['ends_at']} is about {presets_mod.plural(math.floor(left), 'hour', 'hours')} away"
            if done:
                stops = f"after about {done} of {tickets} tickets"
            else:
                stops = "before its ticket is done" if tickets == 1 else f"before any of its {tickets} tickets is done"
            warnings.append(f"The end time stops it {stops}: {away}, and the run needs roughly {presets_mod.plural(hours, 'hour', 'hours')}. Move the end time or drop tickets.")
    need = tickets * (1 + retries)
    if lim["max_sessions"] < need:
        have = lim["max_sessions"]
        covers = (
            f"{tickets} tickets with {presets_mod.plural(have - tickets, 'retry', 'retries') if have > tickets else 'no retries'}"
            if have >= tickets
            else f"only {have} of the {tickets} tickets, with no retries"
        )
        wanted = f"up to {presets_mod.plural(retries, 'retry', 'retries')} each" if retries else "one try each"
        warnings.append(f"{have} sessions in all covers {covers}; {wanted} needs {need}.")
    rv = _review(c, profile) if security else None
    if security and rv is None:
        notes.append("the charter's review or preset isn't well formed, so the review wasn't compared with the project's default")
    if rv is not None:
        usual = presets_mod.numbers("normal", profile)["review"]
        if rv["rounds"] < usual["rounds"] or (_runs_explorer(usual, profile) and not _runs_explorer(rv, profile)):
            named = ", ".join(f"#{n}" for n in security)
            warnings.append(
                f"The review ({_review_words(rv, profile)}) is lighter than the project's default ({_review_words(usual, profile)}), "
                f"while the plan has {'a ticket' if len(security) == 1 else 'tickets'} the review panel would give a security review: {named}."
            )
    return {
        "sessions": sessions,
        "hours": hours,
        "basis": basis,
        "runs_used": runs_used,
        "warnings": warnings,
        "line": line,
        "tickets": tickets,
        "notes": notes,
    }


def text(est: dict) -> str:
    """The estimate as `charter estimate` prints it: the line, its basis, the warnings."""
    out = [f"{est['line']}.", f"Basis: {est['basis']}."]
    out += [f"Warning: {w}" for w in est["warnings"]]
    return "\n".join(out)


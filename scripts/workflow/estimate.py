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


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _num(v: float) -> str:
    """1.0 -> "1", 1.25 -> "1.2": a figure said roughly."""
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _duration(h: float) -> str:
    """0.75 -> "45 minutes", 1.5 -> "1.5 hours"."""
    if h < 1:
        return presets_mod.plural(max(1, round(h * 60)), "minute", "minutes")
    return f"{_num(h)} {'hour' if _num(h) == '1' else 'hours'}"


def _round_hours(h: float) -> int:
    return max(1, math.floor(h + 0.5))


def _labels(issue: dict) -> set[str]:
    return {(x.get("name") if isinstance(x, dict) else x) or "" for x in issue.get("labels") or []}


def _run_of(issue: dict) -> tuple[dict | None, str | None]:
    """A past run's figures from its tracking issue, or a note saying why it was skipped."""
    n = issue.get("number")
    who = f"#{n}" if _int(n) else "a run issue"
    try:
        s = state_mod.get(issue.get("body") or "")
    except state_mod.StateError as e:
        return None, f"{who} skipped: its run state can't be read ({e})"
    if s is None:
        return None, f"{who} skipped: its body has no run state"
    tickets = s.get("tickets") if isinstance(s, dict) else None
    if not isinstance(tickets, dict):
        return None, f"{who} skipped: its run state has no tickets"
    attempts = started = merged = 0
    hours: list[float] = []
    for k, t in tickets.items():
        if not isinstance(t, dict) or t.get("status") not in state_mod.TICKET_STATUSES:
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
            if st and mt and mt >= st:
                hours.append((mt - st).total_seconds() / 3600)
    if not merged:
        return None, None  # merged nothing: not counted, and nothing wrong with it
    return {"number": n, "attempts": attempts, "started": started, "hours": hours}, None


def _closed_at(issue: dict) -> datetime:
    return charter_mod._time(issue.get("closed_at")) or datetime.min.replace(tzinfo=timezone.utc)


def past_runs(issues: Any) -> tuple[list[dict], list[str]]:
    """The five most recent closed `workflow:run` issues with a merged ticket,
    newest first, and the notes on the ones skipped."""
    if isinstance(issues, dict):
        issues = [issues]
    if not isinstance(issues, list):
        raise EstimateError("the past runs must be a JSON list of issues, as the GitHub API returns them")
    candidates = [
        x
        for x in issues
        if isinstance(x, dict)
        and "pull_request" not in x
        and x.get("state", "closed") == "closed"
        and ("labels" not in x or RUN_LABEL in _labels(x))
    ]
    candidates.sort(key=lambda x: (_closed_at(x), x.get("number") if _int(x.get("number")) else 0), reverse=True)
    runs: list[dict] = []
    notes: list[str] = []
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


def _review_words(rv: dict) -> str:
    return f"up to {presets_mod.plural(rv['rounds'], 'round', 'rounds')}, " + (
        "UI explorer on" if presets_mod.runs_explorer(rv) else "no UI explorer"
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
        per_ticket = max(1.0, sum(r["attempts"] for r in runs) / max(1, sum(r["started"] for r in runs)))
        hours_each = [h for r in runs for h in r["hours"]]
        per_wave = sum(hours_each) / len(hours_each) if hours_each else 1.0
        sessions = math.ceil(tickets * per_ticket - 1e-9)
        a_ticket = f"about {_num(per_ticket)} {'session' if _num(per_ticket) == '1' else 'sessions'}"
        basis = f"from your last {len(runs)} runs: {a_ticket} and {_duration(per_wave)} a ticket"
        each = f"{a_ticket} each"
        runs_used = len(runs)
    else:
        if len(runs) == 1:
            notes.append(f"only 1 past run merged anything (#{runs[0]['number']}): the defaults until there are {MIN_RUNS}")
        per_ticket, per_wave = float(1 + retries), 1.0
        sessions = tickets * (1 + retries)
        basis = DEFAULT_BASIS
        each = f"up to {presets_mod.plural(retries, 'retry', 'retries')} each" if retries else "no retries"
        runs_used = 0
    waves = math.ceil(sessions / parallel)
    hours = _round_hours(waves * per_wave)
    line = (
        f"About {presets_mod.plural(sessions, 'ticket session', 'ticket sessions')} over roughly "
        f"{presets_mod.plural(hours, 'hour', 'hours')} ({presets_mod.plural(tickets, 'ticket', 'tickets')}, {each}), "
        "plus the conductor's check-ins"
    )

    warnings: list[str] = []
    ends = charter_mod._time(lim.get("ends_at"))
    if ends is not None:
        left = (ends - (now or datetime.now(timezone.utc))).total_seconds() / 3600
        fit = math.floor(left / per_wave + 1e-9) if left > 0 else 0
        if fit < waves:
            done = min(tickets - 1, math.floor(fit * parallel / per_ticket + 1e-9))
            away = f"{lim['ends_at']} is about {presets_mod.plural(max(0, math.floor(left)), 'hour', 'hours')} away" if left > 0 else f"{lim['ends_at']} has passed"
            stops = f"after about {done} of {tickets} tickets" if done else f"before any of its {presets_mod.plural(tickets, 'ticket', 'tickets')} is done"
            warnings.append(f"The end time stops it {stops}: {away}, and the run needs roughly {presets_mod.plural(hours, 'hour', 'hours')}. Move the end time or drop tickets.")
    need = tickets * (1 + retries)
    if lim["max_sessions"] < need:
        have = lim["max_sessions"]
        covers = (
            f"{tickets} tickets with {presets_mod.plural(have - tickets, 'retry', 'retries')}"
            if have >= tickets
            else f"only {have} of the {tickets} tickets, with no retries"
        )
        wanted = f"up to {presets_mod.plural(retries, 'retry', 'retries')} each" if retries else "one try each"
        warnings.append(f"{have} sessions in all covers {covers}; {wanted} needs {need}.")
    if security:
        rv, usual = presets_mod.review_of(c, profile), presets_mod.numbers("normal", profile)["review"]
        if rv["rounds"] < usual["rounds"] or (presets_mod.runs_explorer(usual) and not presets_mod.runs_explorer(rv)):
            named = ", ".join(f"#{n}" for n in security)
            warnings.append(
                f"The review ({_review_words(rv)}) is lighter than the project's default ({_review_words(usual)}), "
                f"while the plan has tickets the review panel would give a security review: {named}."
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


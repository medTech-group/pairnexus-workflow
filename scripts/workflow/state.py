"""The run's state: a small JSON block in the tracking issue's body.

The conductor is its only writer. Narrative goes in comments; the block holds
only what the conductor needs to resume: the charter, each ticket's status,
the outward-changes ledger and the owner's lists. `get` reads it out of a body;
`put` writes it back into the body (adding it when absent) after validating
it, and refuses a body over GitHub's limit. In the block, `<` and the backtick
are written as JSON \\u escapes, so no string can close the fence or comment; a
body with two blocks, or half of one, is refused rather than guessed at.

Optional: `wake_trigger`, the id of the poke-only routine that wakes the
conductor when a ticket session ends (`trig_…`), deleted when the run stops.
Optional: `estimate`, the estimate the owner approved (`charter estimate
--json`'s output), so a resumed conductor can splice the one page with it.
Optional: `merge_queue`, whether the ruleset required a merge queue on the base
when last seen (`state init --queue`, then `queue_seen` at each change), used
only to notice a change; null when not known.
Optional: `wind_down`, why the run winds down for good (#349: a session that
wasn't a ticket session, so every other would fail the same way).

A ledger entry naming a revert (`"what": "revert"`, or any entry with a
`revert` field) gives the reverted commit's full SHA in `revert`: the guard's
commit and push rule (#341) lets the conductor revert only a commit the ledger
records the owner allowing (#338, answer 40).

With the queue on, `drop` decides each answer GitHub gives to queueing a
ticket's pull request (#243), and keeps on the ticket what it needs: the heads
seen in the queue with their drops (`queue_heads`), the `failed` answers per
head (`queue_failed`), whether the base was merged in (`base_merged`) and the
last decision (`queue_result`).
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import charter as charter_mod

BEGIN = "<!-- workflow-state:begin (written by the conductor; edit only through `workflow state`) -->"
END = "<!-- workflow-state:end -->"
_BLOCK = re.compile(r"<!-- workflow-state:begin[^>]*-->\s*```json\s*(.*?)\s*```\s*<!-- workflow-state:end -->", re.S)

BODY_LIMIT = 65_536
TICKET_STATUSES = {"queued", "running", "in-review", "merged", "needs-human", "set-aside", "skipped"}
RUN_STATUSES = {"running", "stopping", "stopped"}


class StateError(ValueError):
    pass


def empty(charter: dict | None = None) -> dict:
    return {
        "version": 1,
        "run_id": None,
        "charter": charter,
        "tickets": {},
        "overrides": [],
        "ledger": [],
        "for_owner": [],
        "by_hand_issue": None,
        "stopped": None,
        # The newest tracking-issue comment the conductor has read (its id), or
        # None before the first check-in: the owner's comments after it are new.
        "comments_read_through": None,
        "kickoff_tickets": [],
        "ci_minutes_at_start": None,
        "merge_queue": None,
        "status": "running",
    }


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _iso(v) -> bool:
    return charter_mod._time(v) is not None


_HEAD = re.compile(r"[0-9a-f]{40}")  # as merge-check reads a head

# What `drop` takes: GitHub's answer to `PUT pulls/<n>/merge-async` with
# `merge_action: merge_queue`, as #243 names them, and what it prints.
DROP_ANSWERS = ("202-enqueued", "202-pending", "200-waiting", "200-merged", "409", "failed", "refused")
DROP_RESULTS = {"in_queue", "waiting", "merged", "retry", "requeued", "merge_base", "needs_human"}
FAILED_LIMIT = 3


def is_head(v) -> bool:
    """A full commit SHA in lower case."""
    return isinstance(v, str) and bool(_HEAD.fullmatch(v))


def _counts(v) -> bool:
    return isinstance(v, dict) and all(is_head(k) and _int(n) and n >= 0 for k, n in v.items())


# Optional ticket fields and their checks.
TICKET_FIELDS = {
    "pr": (lambda v: _int(v) and v > 0, "an issue number"),
    "rounds": (lambda v: _int(v) and v >= 0, "a whole number"),
    "attempts": (lambda v: _int(v) and v >= 0, "a whole number"),
    "stopped_head": (lambda v: isinstance(v, str) and bool(v.strip()), "a commit SHA"),
    "area": (lambda v: isinstance(v, str) and bool(v.strip()), "an area name"),
    "started_at": (_iso, "an ISO time with its zone"),
    "merged_at": (_iso, "an ISO time with its zone"),
    # When the conductor asked the owner a question on this needs-human ticket in this run.
    "asked_at": (_iso, "an ISO time with its zone"),
    # When the conductor saw its pull request at `passes_used_up` with its own profile unreadable, so
    # whether it is at the cap couldn't be told; step 2 looks again at each check-in until the profile reads.
    "cap_unknown_at": (_iso, "an ISO time with its zone"),
    # The hash on the last line of the briefing it was sent (`Briefing <hash>`).
    "briefing": (lambda v: isinstance(v, str) and bool(re.fullmatch(r"[0-9a-f]{12}", v)), "the briefing's 12-character hash"),
    # The merge queue (`drop`): each head seen in it, with its drops; `failed` answers per head.
    "queue_heads": (_counts, "an object of commit SHAs and whole numbers"),
    "queue_failed": (_counts, "an object of commit SHAs and whole numbers"),
    "base_merged": (lambda v: isinstance(v, bool), "true or false"),
    "queue_result": (lambda v: isinstance(v, str) and v in DROP_RESULTS, "one of " + ", ".join(sorted(DROP_RESULTS))),
    # The pull request's head when "also #<n>" requeued it for a code fix (#349): nothing merges or
    # settles it until its head moves.
    "requeued_head": (is_head, "a full commit SHA in lower case"),
}


def validate(s: Any) -> list[str]:
    p: list[str] = []
    if not isinstance(s, dict):
        return ["state must be a JSON object"]
    if s.get("version") != 1:
        p.append("version must be 1")
    if s.get("charter") is not None:
        p += [f"charter: {x}" for x in charter_mod.validate(s["charter"])]
    t = s.get("tickets")
    if not isinstance(t, dict):
        p.append("tickets must be an object keyed by issue number")
    else:
        for k, v in t.items():
            if not k.isdigit():
                p.append(f"tickets key {k!r} must be an issue number")
            if not isinstance(v, dict) or not isinstance(v.get("status"), str) or v["status"] not in TICKET_STATUSES:
                p.append(f"tickets[{k}].status must be one of {sorted(TICKET_STATUSES)}")
                continue
            for f, (ok, what) in TICKET_FIELDS.items():
                if f in v and v[f] is not None and not ok(v[f]):
                    p.append(f"tickets[{k}].{f} must be {what}")
    for key in ("overrides", "ledger", "for_owner", "kickoff_tickets"):
        if not isinstance(s.get(key, []), list):
            p.append(f"{key} must be a list")
    kt = s.get("kickoff_tickets") or []
    if isinstance(kt, list) and not all(_int(x) and x > 0 for x in kt):
        p.append("kickoff_tickets must be a list of issue numbers")
    crt = s.get("comments_read_through")
    if crt is not None and not (_int(crt) and crt >= 0):
        p.append("comments_read_through must be a comment id (a whole number) or null")
    ci = s.get("ci_minutes_at_start")
    if ci is not None and (isinstance(ci, bool) or not isinstance(ci, (int, float)) or ci < 0):
        p.append("ci_minutes_at_start must be a number of minutes or null")
    wt = s.get("wake_trigger")
    if wt is not None and not (isinstance(wt, str) and re.fullmatch(r"trig_\w+", wt.strip())):
        p.append("wake_trigger must be the wake routine's trigger id (trig_…) or null")
    est = s.get("estimate")
    if est is not None and not (isinstance(est, dict) and isinstance(est.get("line"), str) and isinstance(est.get("basis"), str)):
        p.append("estimate must be `workflow charter estimate --json`'s output or null")
    if s.get("merge_queue") is not None and not isinstance(s["merge_queue"], bool):
        p.append("merge_queue must be true, false or null")
    wd = s.get("wind_down")
    if wd is not None and not (isinstance(wd, str) and wd.strip()):
        p.append("wind_down must be why the run winds down (words) or null")
    if "status" in s and not (isinstance(s["status"], str) and s["status"] in RUN_STATUSES):
        p.append(f"status must be one of {sorted(RUN_STATUSES)}")
    for i, e in enumerate(s.get("ledger") or []):
        if not isinstance(e, dict) or not e.get("what") or not e.get("at") or not e.get("grant"):
            p.append(f"ledger[{i}] needs what, at and grant (the charter line or owner message allowing it)")
        if isinstance(e, dict) and (e.get("what") == "revert" or "revert" in e) and not is_head(e.get("revert")):
            p.append(f"ledger[{i}].revert must be the full commit SHA of the change reverted, in lower case")
    return p


RECOVER = (
    "edit the issue body so it has exactly one block between the markers, "
    "or delete both to start again from `state init`"
)
_BEGIN_MARK = "<!-- workflow-state:begin"
_END_MARK = "<!-- workflow-state:end -->"


def _find(body: str) -> re.Match | None:
    """The one state block, None when the body has none, a StateError when it's ambiguous."""
    body = body or ""
    begins, ends = body.count(_BEGIN_MARK), body.count(_END_MARK)
    if begins == 0 and ends == 0:
        return None
    if begins > 1 or ends > 1:
        raise StateError(f"the body has {max(begins, ends)} state blocks, so which one is current is unclear: {RECOVER}")
    if begins != ends:
        which = "a begin marker without an end" if begins else "an end marker without a begin"
        raise StateError(f"the body has {which}: {RECOVER}")
    m = _BLOCK.search(body)
    if not m:
        raise StateError(f"the body has state markers but no ```json block between them: {RECOVER}")
    return m


def _dump(state: dict) -> str:
    """JSON that can't close the code fence or the HTML comment around it: `<` and
    the backtick are written as \\u escapes (json.loads reads both forms)."""
    return json.dumps(state, indent=1, sort_keys=True).replace("<", "\\u003c").replace("`", "\\u0060")


def get(body: str) -> dict | None:
    m = _find(body)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise StateError(f"the state block is not valid JSON: {e}; {RECOVER}") from e


def put(body: str, state: dict) -> str:
    problems = validate(state)
    if problems:
        raise StateError("refusing to write an invalid state:\n- " + "\n- ".join(problems))
    block = f"{BEGIN}\n```json\n{_dump(state)}\n```\n{END}"
    body = body or ""
    m = _find(body)
    if m:
        new = body[: m.start()] + block + body[m.end() :]
    else:
        new = (body.rstrip() + "\n\n" + block + "\n").lstrip()
    if len(new) > BODY_LIMIT - 1024:
        raise StateError(
            f"the body would be {len(new)} characters, too close to GitHub's {BODY_LIMIT}; "
            "move narrative to comments and finished tickets to the run report"
        )
    return new


def drop(ticket: dict, head: str, answer: str) -> str:
    """What to do with one answer to queueing the ticket's pull request at
    `head` (a full SHA), recorded on `ticket`, which is changed in place:
    - `200-merged` is `merged`; `200-waiting` ("already in a merge queue") is
      `waiting`, never a drop;
    - a head is in the queue from the first answer that shows it there: its
      first `202-enqueued` (`in_queue`) or a `200-waiting`;
    - a later `202-enqueued` of a head in the queue is a drop: the first on that
      head `requeued`, a second `merge_base` (the base is then counted as merged
      in), and any once the base was merged in `needs_human`, whatever the head;
    - `202-pending`, `409`, `refused` and `failed` are `retry`, never drops; the
      third `failed` on one head is `needs_human`."""
    if not is_head(head):
        raise StateError(f"the head must be a full commit SHA in lower case, not {head!r}")
    if answer not in DROP_ANSWERS:
        raise StateError(f"the answer must be one of {', '.join(DROP_ANSWERS)}, not {answer!r}")
    heads = dict(ticket.get("queue_heads") or {})
    if answer == "200-merged":
        result = "merged"
    elif answer == "200-waiting":
        heads.setdefault(head, 0)
        result = "waiting"
    elif answer == "202-enqueued":
        if head not in heads:
            heads[head] = 0
            result = "in_queue"
        else:
            heads[head] += 1
            if ticket.get("base_merged"):
                result = "needs_human"
            elif heads[head] == 1:
                result = "requeued"
            else:
                result = "merge_base"
                ticket["base_merged"] = True
    elif answer == "failed":
        failed = dict(ticket.get("queue_failed") or {})
        failed[head] = failed.get(head, 0) + 1
        ticket["queue_failed"] = failed
        result = "needs_human" if failed[head] >= FAILED_LIMIT else "retry"
    else:
        result = "retry"
    if heads:
        ticket["queue_heads"] = heads
    ticket["queue_result"] = result
    return result


def queue_seen(state: dict, on: bool) -> str:
    """The merge queue's state seen now against the one recorded, in words that
    start `unchanged`, `changed` or `recorded` (when none was), and recorded on
    `state`, which is changed in place, so a change is reported once. When the
    charter waives checks, a change (or a first sighting) says whether they
    apply: not while the queue is on."""
    was = state.get("merge_queue")
    state["merge_queue"] = on
    word = {True: "on", False: "off"}
    if was == on:
        return f"unchanged: the merge queue is {word[on]}"
    if was is None:
        said = f"recorded: the merge queue is {word[on]}"
    else:
        said = f"changed: the merge queue is now {word[on]} (it was {word[was]})"
    c = state.get("charter")
    m = c.get("merge") if isinstance(c, dict) else None
    if isinstance(m, dict) and m.get("waived_checks"):
        if on:
            said += "; the charter's waived checks no longer apply"
        elif was is not None:
            said += "; the charter's waived checks apply again"
    return said


def _approved(state: Any) -> bool:
    c = state.get("charter") if isinstance(state, dict) else None
    return isinstance(c, dict) and c.get("approved") is not None


def patch(current: dict, change: Any) -> dict:
    """The state with a merge patch applied, its charter validated again. A
    charter that was approved must still be approved after the patch: a patch
    can't unapprove a running run (amendments change it instead)."""
    new = merge_patch(current, change)
    if _approved(current):
        if not _approved(new):
            raise StateError(
                "the patch would leave the run's charter unapproved; a running run's charter changes only by "
                "amendments, and stopping it is `status`"
            )
        problems = charter_mod.validate(new["charter"])
        if problems:
            raise StateError("the patched charter has problems:\n- " + "\n- ".join(problems))
    return new


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7386 JSON merge patch."""
    if not isinstance(patch, dict):
        return patch
    if not isinstance(target, dict):
        target = {}
    out = dict(target)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = merge_patch(out.get(k), v)
    return out

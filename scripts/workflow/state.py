"""The run's state: a small JSON block in the tracking issue's body.

The conductor is its only writer. Narrative goes in comments; the block holds
only what the conductor needs to resume: the charter, each ticket's status,
the outward-changes ledger and the owner's lists. `get` reads it out of a body;
`put` writes it back into the body (adding it when absent) after validating
it, and refuses a body over GitHub's limit. In the block, `<` and the backtick
are written as JSON \\u escapes, so no string can close the fence or comment; a
body with two blocks, or half of one, is refused rather than guessed at.
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
        "status": "running",
    }


def _int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _iso(v) -> bool:
    return charter_mod._time(v) is not None


# Optional ticket fields and their checks.
TICKET_FIELDS = {
    "pr": (lambda v: _int(v) and v > 0, "an issue number"),
    "rounds": (lambda v: _int(v) and v >= 0, "a whole number"),
    "attempts": (lambda v: _int(v) and v >= 0, "a whole number"),
    "stopped_head": (lambda v: isinstance(v, str) and bool(v.strip()), "a commit SHA"),
    "area": (lambda v: isinstance(v, str) and bool(v.strip()), "an area name"),
    "started_at": (_iso, "an ISO time with its zone"),
    "merged_at": (_iso, "an ISO time with its zone"),
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
            if not isinstance(v, dict) or v.get("status") not in TICKET_STATUSES:
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
    if "status" in s and s["status"] not in RUN_STATUSES:
        p.append(f"status must be one of {sorted(RUN_STATUSES)}")
    for i, e in enumerate(s.get("ledger") or []):
        if not isinstance(e, dict) or not e.get("what") or not e.get("at") or not e.get("grant"):
            p.append(f"ledger[{i}] needs what, at and grant (the charter line or owner message allowing it)")
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

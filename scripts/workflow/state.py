"""The run's state: a small JSON block in the tracking issue's body.

The conductor is its only writer. Narrative goes in comments; the block holds
only what the conductor needs to resume: the charter, each ticket's status,
the outward-changes ledger and the owner's lists. `get` reads it out of a body;
`put` writes it back into the body (adding it when absent) after validating
it, and refuses a body over GitHub's limit.
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
            att = v.get("attempts", 0)
            if not isinstance(att, int) or att < 0:
                p.append(f"tickets[{k}].attempts must be a whole number")
    for key in ("overrides", "ledger", "for_owner"):
        if not isinstance(s.get(key, []), list):
            p.append(f"{key} must be a list")
    for i, e in enumerate(s.get("ledger") or []):
        if not isinstance(e, dict) or not e.get("what") or not e.get("at") or not e.get("grant"):
            p.append(f"ledger[{i}] needs what, at and grant (the charter line or owner message allowing it)")
    return p


def get(body: str) -> dict | None:
    m = _BLOCK.search(body or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise StateError(f"the state block is not valid JSON: {e}") from e


def put(body: str, state: dict) -> str:
    problems = validate(state)
    if problems:
        raise StateError("refusing to write an invalid state:\n- " + "\n- ".join(problems))
    block = f"{BEGIN}\n```json\n{json.dumps(state, indent=1, sort_keys=True)}\n```\n{END}"
    body = body or ""
    if _BLOCK.search(body):
        new = _BLOCK.sub(lambda _m: block, body, count=1)
    else:
        new = (body.rstrip() + "\n\n" + block + "\n").lstrip()
    if len(new) > BODY_LIMIT - 1024:
        raise StateError(
            f"the body would be {len(new)} characters, too close to GitHub's {BODY_LIMIT}; "
            "move narrative to comments and finished tickets to the run report"
        )
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

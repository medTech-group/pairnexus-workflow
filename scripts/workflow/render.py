"""Render a ticket session's briefing from a template.

Placeholders are `{{name}}` or `{{group.name}}`. Values come from the ticket,
the profile, the charter and the conductor's slots. Rendering refuses when any
placeholder is left unfilled or a required slot is empty, so a session can never
be sent a briefing with a hole in it.
"""

from __future__ import annotations

import re

from .profile import Profile

PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")
# Filled by the conductor for each ticket. "none" is a valid answer; empty isn't.
REQUIRED_SLOTS = ("alongside", "read_first", "owner_decisions", "briefing")


class RenderError(ValueError):
    pass


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items) if items else "- none"


def values(profile: Profile, ticket: dict, charter: dict, slots: dict, tracking: int, by_hand: int | None) -> dict:
    merge = charter.get("merge") or {}
    waived = merge.get("waived_checks") or []
    v = {
        "ticket.number": str(ticket["number"]),
        "ticket.title": ticket.get("title") or "",
        "ticket.branch": profile.ticket_branch.replace("*", str(ticket["number"])),
        "project.name": profile.name,
        "project.repo": profile.repo,
        "project.base_branch": profile.base_branch,
        "project.rules": _bullets(profile.rules),
        "tracking.issue": str(tracking),
        "by_hand.issue": str(by_hand) if by_hand else "none yet: add by-hand checks to the tracking issue",
        "merge.mode": merge.get("mode", "auto-merge"),
        "merge.waived": ", ".join(waived) if waived else "none: every required check must be green",
        "run.review_rounds": str(profile.review_rounds),
        "run.check_in_minutes": str((charter.get("limits") or {}).get("check_in_minutes", profile.check_in_minutes)),
        "open_decisions": "take the choice most consistent with the spec, ADRs and the project's rules, and record it in the PR body"
        if charter.get("open_decisions", "decide-and-record") == "decide-and-record"
        else "label the ticket needs-human, say exactly what needs deciding, and stop",
        "commands.typecheck": profile.typecheck or "none",
        "commands.test_file": profile.test_file or "none",
        "commands.suites": _bullets([f"{s.name}: `{s.run}`" for s in profile.suites]),
        "ui.explorer": profile.explorer,
    }
    for k in REQUIRED_SLOTS:
        v[k] = slots.get(k, "")
    for k, val in slots.items():
        v.setdefault(k, val)
    return v


def render(template: str, vals: dict) -> str:
    missing_slots = [k for k in REQUIRED_SLOTS if f"{{{{{k}}}}}" in template.replace(" ", "") and not str(vals.get(k, "")).strip()]
    if missing_slots:
        raise RenderError(
            "required slots are empty: " + ", ".join(missing_slots) + ' (write "none" when there is nothing to say)'
        )
    unknown = sorted({m.group(1) for m in PLACEHOLDER.finditer(template) if m.group(1) not in vals})
    if unknown:
        raise RenderError("no value for: " + ", ".join(unknown))
    out = PLACEHOLDER.sub(lambda m: str(vals[m.group(1)]), template)
    left = PLACEHOLDER.findall(out)
    if left or re.search(r"\b(SEE_BELOW|TODO_FILL|<fill[^>]*>)\b", out):
        raise RenderError("the rendered briefing still has a placeholder: " + ", ".join(left or ["SEE_BELOW/TODO"]))
    return out

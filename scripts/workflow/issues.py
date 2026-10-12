"""Reading tickets: blockers, areas, readiness. Pure functions over issue JSON.

An issue is a dict as GitHub's REST API returns it (number, title, body, state,
state_reason, labels, assignees, pull_request). Labels may be dicts with a
"name" or plain strings; assignees dicts with a "login" or plain strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

READY_LABEL = "ready-for-agent"
CLAIM_LABEL = "workflow:in-progress"
HUMAN_LABELS = {"needs-human", "owner-task"}
NOT_BUILD_LABELS = {"wayfinder:map"}

_REF = re.compile(r"#(\d+)\b")
_CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.I)


def labels_of(issue: dict) -> set[str]:
    out = set()
    for l in issue.get("labels") or []:
        out.add(l["name"] if isinstance(l, dict) else str(l))
    return out


def assignees_of(issue: dict) -> list[str]:
    return [a["login"] if isinstance(a, dict) else str(a) for a in issue.get("assignees") or []]


def blockers_of(body: str | None) -> list[int]:
    """Blockers, in the two conventions the flow uses.

    - a line `Blocked by: #a, #b` (anywhere, usually the first line);
    - a `## Blocked by` heading whose section lists `#n` refs ("None" means none).
    """
    if not body:
        return []
    found: list[int] = []
    lines = body.splitlines()
    for line in lines:
        m = re.match(r"^\s*\**blocked by\**\s*:\s*(.*)$", line, re.I)
        if m:
            found += [int(n) for n in _REF.findall(m.group(1))]
    in_section = False
    for line in lines:
        if re.match(r"^\s*#{1,6}\s*blocked by\s*$", line, re.I):
            in_section = True
            continue
        if in_section:
            if re.match(r"^\s*#{1,6}\s", line):
                in_section = False
                continue
            # "- #192" or "- medTech-group/pair-drop#192" (same repo only)
            for m in re.finditer(r"(?:^|[\s(])(?:[\w.-]+/[\w.-]+)?#(\d+)\b", line):
                found.append(int(m.group(1)))
    seen, out = set(), []
    for n in found:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def area_of(body: str | None) -> str | None:
    if not body:
        return None
    for line in body.splitlines():
        m = re.match(r"^\s*\**area\**\s*:\s*([A-Za-z0-9_.-]+)\s*$", line, re.I)
        if m:
            return m.group(1).lower()
    return None


def closed_by_open_prs(prs: list[dict]) -> dict[int, int]:
    """Issue number -> the open PR whose body closes it (drafts included)."""
    out: dict[int, int] = {}
    for pr in prs:
        if (pr.get("state") or "open").lower() != "open":
            continue
        for n in _CLOSES.findall(pr.get("body") or ""):
            out.setdefault(int(n), pr["number"])
    return out


@dataclass
class Verdict:
    number: int
    title: str
    ready: bool
    area: str | None = None
    reasons: list[str] = field(default_factory=list)
    blockers: list[int] = field(default_factory=list)


def readiness(
    issues: list[dict],
    prs: list[dict],
    exclude: set[int] | frozenset = frozenset(),
    claimed_ok: set[int] | frozenset = frozenset(),
) -> list[Verdict]:
    """Every open `ready-for-agent` build ticket with whether it is ready and why not.

    Ready means: open; labelled ready-for-agent; not a map; not needs-human or
    owner-task; not claimed (the claim label) unless in `claimed_ok`; no open PR
    closes it; not excluded; and every blocker closed *as completed*. A blocker
    closed as not planned, or one missing from `issues`, still blocks.
    """
    by_num = {i["number"]: i for i in issues if "pull_request" not in i}
    pr_for = closed_by_open_prs(prs)
    out: list[Verdict] = []
    for num in sorted(by_num):
        issue = by_num[num]
        if (issue.get("state") or "").lower() != "open":
            continue
        labels = labels_of(issue)
        if READY_LABEL not in labels or labels & NOT_BUILD_LABELS:
            continue
        v = Verdict(number=num, title=issue.get("title") or "", ready=True, area=area_of(issue.get("body")))
        v.blockers = blockers_of(issue.get("body"))
        if num in exclude:
            v.reasons.append("excluded by the charter")
        for lab in sorted(labels & HUMAN_LABELS):
            v.reasons.append(f"labelled {lab}")
        if CLAIM_LABEL in labels and num not in claimed_ok:
            v.reasons.append("claimed (workflow:in-progress)")
        if num in pr_for:
            v.reasons.append(f"open PR #{pr_for[num]} closes it")
        for b in v.blockers:
            bi = by_num.get(b)
            if bi is None:
                v.reasons.append(f"blocker #{b} unknown (not in the issue list)")
            elif (bi.get("state") or "").lower() != "closed":
                v.reasons.append(f"blocked by open #{b}")
            elif (bi.get("state_reason") or "completed") != "completed":
                v.reasons.append(f"blocker #{b} closed as {bi.get('state_reason')}, not completed")
        v.ready = not v.reasons
        out.append(v)
    return out


def startable(
    verdicts: list[Verdict],
    running_areas: list[str | None],
    slots: int,
    overrides: set[int] | frozenset = frozenset(),
) -> list[Verdict]:
    """Ready tickets to start now: lowest number first, at most `slots`, one per area.

    A ticket with no area may run beside anything. `overrides` are tickets the
    run state allows to share an area.
    """
    taken = {a for a in running_areas if a}
    out: list[Verdict] = []
    for v in verdicts:
        if len(out) >= slots:
            break
        if not v.ready:
            continue
        if v.area and v.area in taken and v.number not in overrides:
            continue
        out.append(v)
        if v.area:
            taken.add(v.area)
    return out

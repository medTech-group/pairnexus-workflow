"""Where the project stands: what the guided start (`skills/start`) offers.

Pure functions over issue and PR JSON (as `issues.py`), plus a look at the
checkout: whether the kit is set up, and whether the project is brand new.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import issues as issues_mod
from . import proc as proc_mod
from .profile import EXPERIENCE_ENV, EXPERIENCE_FILE, Experience

# A request recorded by the guided start, one issue per item, so a plan made in
# one session is still there in the next: `<!-- workflow:item path=spec -->`.
ITEM = re.compile(r"<!--\s*workflow:item(?:\s+path=([\w-]+))?\s*-->")
PATHS = ("ticket", "diagnose", "spec", "map")
# The title update-workflow gives its pull request.
KIT_UPDATE_TITLE = "Update the workflow kit"
_WAITING = issues_mod.HUMAN_LABELS | {"needs-info"}
# The labels a claimed issue's line names.
_CLAIM_DETAIL = {"spec", "wayfinder:map", issues_mod.READY_LABEL, issues_mod.CARRY_ON_LABEL}

# Files a repository has before any of its own code: what set-up writes, and
# the usual first commit. A checkout with nothing else is brand new.
_BOILERPLATE_DIRS = (".claude/", ".github/", "docs/agents/", "docs/adr/", ".devcontainer/", ".vscode/")
_BOILERPLATE = re.compile(
    r"^(readme|license|licence|copying|changelog|contributing|code_of_conduct|security|claude|agents|glossary|context|codeowners)"
    r"(\.(md|markdown|txt|rst|adoc))?$|^\.(gitignore|gitattributes|editorconfig|env\.example)$",
    re.I,
)


@dataclass
class Item:
    number: int
    title: str
    detail: str = ""


@dataclass
class Status:
    set_up: bool
    brand_new: bool
    own_files: int
    issues_read: bool = False
    # The profile's project.ruleset: False is solo mode, so solo_mode is its
    # opposite; None is "not set (as before)".
    solo_mode: bool | None = None
    experience: Experience = field(default_factory=lambda: Experience(None, "unknown"))
    run: list[Item] = field(default_factory=list)
    in_progress: list[Item] = field(default_factory=list)
    # `workflow:carry-on` tickets no run has adopted and no person is asked about (#376).
    carry_on: list[Item] = field(default_factory=list)
    # Open issues labelled `research` (#514): a study under way, or a note to fix
    # (the `study` skill's section 5). Never to sort.
    research: list[Item] = field(default_factory=list)
    # Items whose `## Blocked by` names an open owner task (#514): skipped by
    # `next` and `start` while it's open. A map keeps its own section, and an
    # item already waiting on a person stays under waiting (#577).
    held: list[Item] = field(default_factory=list)
    prs: list[Item] = field(default_factory=list)
    planned: list[Item] = field(default_factory=list)
    maps: list[Item] = field(default_factory=list)
    specs: list[Item] = field(default_factory=list)
    ready: list[Item] = field(default_factory=list)
    waiting: list[Item] = field(default_factory=list)
    to_triage: list[Item] = field(default_factory=list)
    kit_update_pr: int | None = None
    # Doctor's local gaps (#62): its lines for its local checks that are gaps,
    # in its JSON shape; None when they weren't checked. `profile_error`: the
    # profile is there but can't be used (its gap is kit.profile).
    local_gaps: list[dict] | None = None
    profile_error: bool = False
    # Who writes code (#339), from the profile that counts (profile.code_rule):
    # "ticket", "any" or None (not answered), and whether this session may.
    code_writers: str | None = None
    writes_code: bool = True

    @property
    def local_gap(self) -> bool | None:
        return None if self.local_gaps is None else bool(self.local_gaps)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["experience"]["wording_level"] = self.experience.wording_level
        d["local_gap"] = self.local_gap
        return d


OWN_FILES_TIMEOUT = 20  # seconds, for `git ls-files`: a seam the Ctrl-C tests raise


def own_files(root: Path) -> int:
    """Tracked files that are the project's own, not set-up's or boilerplate."""
    tracked = proc_mod.output(["git", "ls-files", "-z"], cwd=root, timeout=OWN_FILES_TIMEOUT)
    if tracked is None:
        return -1
    n = 0
    for path in filter(None, tracked.split("\0")):
        if path.startswith(_BOILERPLATE_DIRS) or _BOILERPLATE.match(path):
            continue
        n += 1
    return n


def item_path(body: str | None) -> str | None:
    """The path a recorded item was given ("" when the marker names none), or None."""
    m = ITEM.search(body or "")
    return None if m is None else (m.group(1) or "")


# The text fields `snapshot` reads, on an issue or a pull request (#770).
_TEXTS = ("state", "state_reason", "title", "body")


def _whole(v) -> bool:
    return v is None or (isinstance(v, int) and not isinstance(v, bool))


def as_read(item: dict) -> dict:
    """The issue or pull request as `snapshot` reads it (#770): a copy with each
    field it reads that holds the wrong type left out, so the item reads as it
    would without that field, never a traceback. A label of the wrong type is
    left out of the list, the others kept; a `sub_issues_summary` or
    `issue_dependencies_summary` whose count isn't a whole number is left out
    whole (its sub-issues unknown); a `pull_request` of the wrong type still
    marks a pull request, read without its details. A null reads as missing,
    as before."""
    out = dict(item)
    for k in _TEXTS:
        if not isinstance(out.get(k), (str, type(None))):
            del out[k]
    labels = out.get("labels")
    if isinstance(labels, list):
        out["labels"] = [
            l for l in labels if isinstance(l, str) or (isinstance(l, dict) and isinstance(l.get("name"), (str, type(None))))
        ]
    elif labels is not None:
        del out["labels"]
    for k, counts in (("sub_issues_summary", ("total", "completed")), ("issue_dependencies_summary", ("blocked_by",))):
        v = out.get(k)
        if v is not None and not (isinstance(v, dict) and all(_whole(v.get(c)) for c in counts)):
            del out[k]
    if not isinstance(out.get("pull_request", {}), (dict, type(None))):
        out["pull_request"] = {}
    head = out.get("head")
    if isinstance(head, dict) and not isinstance(head.get("ref"), (str, type(None))):
        out["head"] = {k: v for k, v in head.items() if k != "ref"}
    elif not isinstance(head, (dict, type(None))):
        del out["head"]
    if not isinstance(out.get("draft"), (bool, type(None))):
        del out["draft"]
    return out


def _open(i: dict) -> bool:
    return (i.get("state") or "open").lower() == "open"


def _children(i: dict) -> tuple[int, int] | None:
    """(sub-issues, open ones), or None when the issue doesn't say (a fetch
    without `sub_issues_summary`)."""
    subs = i.get("sub_issues_summary")
    if not isinstance(subs, dict):
        return None
    total = subs.get("total") or 0
    return total, max(0, total - (subs.get("completed") or 0))


def owner_tasks_holding(issue: dict, by_num: dict[int, dict], repo: str | None = None) -> list[int]:
    """The open owner tasks among the issue's blockers, in the order its
    `## Blocked by` names them. A blocker missing from `by_num`, closed, in
    another repository or not an owner task holds nothing here, and nor does
    the issue itself (#577)."""
    out = []
    for b in issues_mod.blockers_of(issue.get("body"), repo):
        bi = by_num.get(b) if isinstance(b, int) and b != issue.get("number") else None
        if bi is not None and _open(bi) and issues_mod.labels_of(bi) & issues_mod.OWNER_TASK_LABELS:
            out.append(b)
    return out


def snapshot(
    root: Path,
    set_up: bool,
    issues: list[dict] | None = None,
    prs: list[dict] | None = None,
    repo: str | None = None,
    areas: list[str] | None = None,
    protected: list[str] | None = None,
    ruleset: bool | None = None,
    experience: Experience | None = None,
    local_gaps: list[dict] | None = None,
    profile_error: bool = False,
) -> Status:
    files = own_files(root)
    st = Status(set_up=set_up, brand_new=files == 0, own_files=files, local_gaps=local_gaps, profile_error=profile_error)
    st.solo_mode = None if ruleset is None else not ruleset
    if experience is not None:
        st.experience = experience
    if issues is None or prs is None:
        return st
    st.issues_read = True
    issues, prs = [as_read(i) for i in issues], [as_read(p) for p in prs]
    lab = issues_mod.labels_of
    by_num = {i["number"]: i for i in issues if "pull_request" not in i}
    for i in sorted((i for i in issues if "pull_request" not in i and _open(i)), key=lambda i: i["number"]):
        n, title, labels, body = i["number"], i.get("title") or "", lab(i), i.get("body") or ""
        kids = _children(i)
        if "workflow:run" in labels:
            st.run.append(Item(n, title))
            continue
        if issues_mod.CLAIM_LABEL in labels:
            st.in_progress.append(Item(n, title, ", ".join(sorted(labels & _CLAIM_DETAIL))))
        if issues_mod.RESEARCH_LABEL in labels:
            # The kit reads every issue carrying the label as research (`study` §5): under way, never to sort.
            st.research.append(Item(n, title))
            continue
        if "wayfinder:map" in labels:
            detail = "open decisions unknown (no sub_issues_summary)" if kids is None else f"{kids[1]} open decisions"
            st.maps.append(Item(n, title, detail))
            continue
        is_spec = issues_mod.is_spec(i)
        path = item_path(body)
        # The item's own section, then held over it (#514), unless it already waits on a person (#577).
        if is_spec or (kids and kids[0]):
            kind = "" if is_spec else "parent issue, "
            if kids is None:
                detail = "tickets unknown (no sub_issues_summary)"
            elif not kids[0]:
                detail = "no tickets yet"
            else:
                detail = f"{kids[1]} of {kids[0]} tickets open"
            where, item = st.specs, Item(n, title, kind + detail)
        elif path is not None:
            where, item = st.planned, Item(n, title, path)
        elif labels & _WAITING:
            where, item = st.waiting, Item(n, title, ", ".join(sorted(labels & _WAITING)))
        elif issues_mod.CARRY_ON_LABEL in labels:
            # Handed on, review not yet clean: `start` offers "Carry on" (#376). One claimed is listed
            # as claimed only (a run adopted it, #380).
            where, item = (None if issues_mod.CLAIM_LABEL in labels else st.carry_on), Item(n, title)
        elif issues_mod.READY_LABEL in labels:
            where, item = None, None  # a build ticket: readiness below
        elif "needs-triage" in labels or not labels:
            where, item = st.to_triage, Item(n, title)
        else:
            where, item = None, None  # listed nowhere of its own
        tasks = [] if where is st.waiting else owner_tasks_holding(i, by_num, repo)
        if tasks:
            # Held until the owner task closes (#514).
            word = "owner task" if len(tasks) == 1 else "owner tasks"
            st.held.append(Item(n, title, f"{word} " + ", ".join(f"#{t}" for t in tasks)))
        elif where is not None:
            where.append(item)
    for pr in sorted((p for p in prs if _open(p)), key=lambda p: p["number"]):
        draft = " (draft)" if pr.get("draft") else ""
        st.prs.append(Item(pr["number"], pr.get("title") or "", ((pr.get("head") or {}).get("ref") or "") + draft))
        if (pr.get("title") or "").casefold().startswith(KIT_UPDATE_TITLE.casefold()) and st.kit_update_pr is None:
            st.kit_update_pr = pr["number"]
    # A ticket handed on is never ready, whichever section lists it: carrying it on isn't a fresh build.
    # Nor is a research issue, which is under way (#514).
    never_ready = {i["number"] for i in issues if "pull_request" not in i and lab(i) & {issues_mod.CARRY_ON_LABEL, issues_mod.RESEARCH_LABEL}}
    for v in issues_mod.readiness(issues, prs, repo=repo, areas=areas, protected=protected):
        if v.ready and v.number not in never_ready:
            st.ready.append(Item(v.number, v.title, v.area or ""))
    return st


_SECTIONS = [
    ("run", "Unattended run in progress"),
    ("in_progress", "Claimed (being worked on)"),
    ("carry_on", "Carried on (handed on by an earlier session, review not yet clean)"),
    ("research", "Research under way"),
    ("prs", "Open pull requests"),
    ("planned", "Planned at an earlier start, not yet begun"),
    ("maps", "Maps"),
    ("specs", "Open specs (and parent issues)"),
    ("ready", "Ready build tickets"),
    ("held", "Held by an open owner task (skipped until it closes)"),
    ("waiting", "Waiting on a person (owner tasks, needs-human, needs-info)"),
    ("to_triage", "New issues to sort"),
]


_SOURCES = {
    "environment": f"the environment, {EXPERIENCE_ENV}",
    "local file": f"the local file, {EXPERIENCE_FILE.as_posix()}",
    "profile": "the profile, project.experience",
}


def experience_lines(exp: Experience) -> list[str]:
    if exp.level:
        first = f"Experience: {exp.level} (from {_SOURCES.get(exp.source, exp.source)})"
    else:
        first = "Experience: unknown (worded as new to building)"
    return [first, *(f"warning: {w}" for w in exp.warnings)]


def local_gap_lines(st: Status) -> list[str]:
    """One line naming doctor's local gaps by their ids, most serious first
    (none when they weren't checked)."""
    if st.local_gaps is None:
        return []
    if not st.local_gaps:
        return ["Local gaps: none"]
    n = len(st.local_gaps)
    ids = ", ".join(g["id"] for g in st.local_gaps)
    return [f"Local gaps: {n} ({ids}): `workflow doctor` says how to fix {'it' if n == 1 else 'each'}"]


def text(st: Status) -> str:
    if st.profile_error:
        kit, solo = "set up, but its profile has an error (kit.profile)", "unknown (the profile has an error)"
    else:
        kit = "set up" if st.set_up else "NOT set up here (no .claude/workflow/profile.toml)"
        solo = "not set (as before)" if st.solo_mode is None else "yes" if st.solo_mode else "no"
    lines = [
        "Kit: " + kit,
        "Project: "
        + ("brand new (no code of its own yet)" if st.brand_new else "unknown (not a git checkout)" if st.own_files < 0 else f"{st.own_files} files of its own"),
        "Solo mode: " + solo,
        *experience_lines(st.experience),
        *local_gap_lines(st),
    ]
    if not st.issues_read:
        lines.append("Issues: not read (pass --fetch, or --issues and --prs files)")
        return "\n".join(lines)
    for key, heading in _SECTIONS:
        items = getattr(st, key)
        if not items:
            continue
        lines.append(f"{heading}: {len(items)}")
        for it in items[:8]:
            lines.append(f"- #{it.number} {it.title}" + (f" [{it.detail}]" if it.detail else ""))
        if len(items) > 8:
            lines.append(f"- … and {len(items) - 8} more")
    if st.kit_update_pr:
        lines.append(f"Kit update pull request open: #{st.kit_update_pr} (offer it, not another update)")
    if not any(getattr(st, k) for k, _ in _SECTIONS):
        lines.append("Issues: nothing open")
    return "\n".join(lines)

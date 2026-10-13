"""Where the project stands: what the guided start (`skills/start`) offers.

Pure functions over issue and PR JSON (as `issues.py`), plus a look at the
checkout: whether the kit is set up, and whether the project is brand new.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import issues as issues_mod

# A request recorded by the guided start, one issue per item, so a plan made in
# one session is still there in the next: `<!-- workflow:item path=spec -->`.
ITEM = re.compile(r"<!--\s*workflow:item(?:\s+path=([\w-]+))?\s*-->")
PATHS = ("ticket", "diagnose", "spec", "map")
_WAITING = issues_mod.HUMAN_LABELS | {"needs-info"}

# Files a repository has before any of its own code: what set-up writes, and
# the usual first commit. A checkout with nothing else is brand new.
_BOILERPLATE_DIRS = (".claude/", ".github/", "docs/agents/", "docs/adr/", ".devcontainer/", ".vscode/")
_BOILERPLATE = re.compile(
    r"^(readme|license|licence|changelog|contributing|code_of_conduct|security|claude|agents|glossary|context|codeowners)"
    r"(\.[\w.]+)?$|^\.(gitignore|gitattributes|editorconfig|env\.example)$",
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
    run: list[Item] = field(default_factory=list)
    in_progress: list[Item] = field(default_factory=list)
    prs: list[Item] = field(default_factory=list)
    planned: list[Item] = field(default_factory=list)
    maps: list[Item] = field(default_factory=list)
    specs: list[Item] = field(default_factory=list)
    ready: list[Item] = field(default_factory=list)
    waiting: list[Item] = field(default_factory=list)
    to_triage: list[Item] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def own_files(root: Path) -> int:
    """Tracked files that are the project's own, not set-up's or boilerplate."""
    try:
        p = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return -1
    if p.returncode:
        return -1
    n = 0
    for path in filter(None, p.stdout.split("\0")):
        if path.startswith(_BOILERPLATE_DIRS) or _BOILERPLATE.match(path):
            continue
        n += 1
    return n


def item_path(body: str | None) -> str | None:
    """The path a recorded item was given ("" when the marker names none), or None."""
    m = ITEM.search(body or "")
    return None if m is None else (m.group(1) or "")


def _open(i: dict) -> bool:
    return (i.get("state") or "open").lower() == "open"


def _open_children(i: dict) -> int | None:
    subs = i.get("sub_issues_summary")
    if not isinstance(subs, dict) or not subs.get("total"):
        return None
    return max(0, (subs.get("total") or 0) - (subs.get("completed") or 0))


def snapshot(
    root: Path,
    set_up: bool,
    issues: list[dict] | None = None,
    prs: list[dict] | None = None,
    repo: str | None = None,
    areas: list[str] | None = None,
    protected: list[str] | None = None,
) -> Status:
    files = own_files(root)
    st = Status(set_up=set_up, brand_new=files == 0, own_files=files)
    if issues is None or prs is None:
        return st
    st.issues_read = True
    lab = issues_mod.labels_of
    for i in sorted((i for i in issues if "pull_request" not in i and _open(i)), key=lambda i: i["number"]):
        n, title, labels, body = i["number"], i.get("title") or "", lab(i), i.get("body") or ""
        children = _open_children(i)
        if "workflow:run" in labels:
            st.run.append(Item(n, title))
            continue
        if issues_mod.CLAIM_LABEL in labels:
            st.in_progress.append(Item(n, title, ", ".join(sorted(labels & {"spec", "wayfinder:map", "ready-for-agent"}))))
        if "wayfinder:map" in labels:
            st.maps.append(Item(n, title, f"{children} open" if children else "no open decisions"))
            continue
        if "spec" in labels or title.strip().casefold().startswith("spec:"):
            st.specs.append(Item(n, title, f"{children} open tickets" if children is not None else "no tickets yet"))
            continue
        path = item_path(body)
        if path is not None:
            st.planned.append(Item(n, title, path))
            continue
        if labels & _WAITING:
            st.waiting.append(Item(n, title, ", ".join(sorted(labels & _WAITING))))
            continue
        if "needs-triage" in labels or not labels:
            st.to_triage.append(Item(n, title))
    for pr in sorted((p for p in prs if _open(p)), key=lambda p: p["number"]):
        draft = " (draft)" if pr.get("draft") else ""
        st.prs.append(Item(pr["number"], pr.get("title") or "", ((pr.get("head") or {}).get("ref") or "") + draft))
    for v in issues_mod.readiness(issues, prs, repo=repo, areas=areas, protected=protected):
        if v.ready:
            st.ready.append(Item(v.number, v.title, v.area or ""))
    return st


_SECTIONS = [
    ("run", "Unattended run in progress"),
    ("in_progress", "Claimed (being worked on)"),
    ("prs", "Open pull requests"),
    ("planned", "Planned at an earlier start, not yet begun"),
    ("maps", "Maps"),
    ("specs", "Open specs"),
    ("ready", "Ready build tickets"),
    ("waiting", "Waiting on a person (owner tasks, needs-human, needs-info)"),
    ("to_triage", "New issues to sort"),
]


def text(st: Status) -> str:
    lines = [
        "Kit: " + ("set up" if st.set_up else "NOT set up here (no .claude/workflow/profile.toml)"),
        "Project: "
        + ("brand new (no code of its own yet)" if st.brand_new else "unknown (not a git checkout)" if st.own_files < 0 else f"{st.own_files} files of its own"),
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
    if not any(getattr(st, k) for k, _ in _SECTIONS):
        lines.append("Issues: nothing open")
    return "\n".join(lines)

"""Flow context: a UserPromptSubmit hook.

When a prompt is about the flow (`/next`, or a flow verb next to an issue
reference), add the kit's flow to the context: the whole file the first time in
a session, a one-line reminder after that. Anything else passes untouched.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_NEXT = re.compile(r"(^|\s)/(?:[\w-]+:)?next\b")
_VERB = re.compile(
    r"\b(implement\w*|build\w*|work(?:ing)?|spec\w*|tickets?|maps?|wayfinder|grill\w*|to-spec|to-tickets|frontier|conductor|unattended)\b",
    re.I,
)
_REF = re.compile(r"(?<![\w/])#\d+\b|/issues/\d+")


def wants_flow(prompt: str) -> bool:
    if _NEXT.search(prompt or ""):
        return True
    return bool(_VERB.search(prompt or "") and _REF.search(prompt or ""))


def flow_files(project: Path, kit_root: Path, addendum: str = "") -> list[Path]:
    out = []
    for cand in (project / ".claude/workflow/flow.md", kit_root / "docs/flow.md"):
        if cand.exists():
            out.append(cand)
            break
    if addendum and (project / addendum).exists():
        out.append(project / addendum)
    return out


def context_for(prompt: str, session_id: str, files: list[Path]) -> str | None:
    if not files or not wants_flow(prompt):
        return None
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id or "unknown")[:80]
    marker = Path(os.environ.get("TMPDIR") or tempfile.gettempdir()) / f"workflow-flow-{safe}"
    names = ", ".join(str(f) for f in files)
    if marker.exists():
        return f"Follow the workflow's flow ({names}) for this request, step by step, and end with its checklist. If it is no longer in your context, read it again first."
    try:
        marker.touch()
    except OSError:
        pass
    body = "\n\n".join(f.read_text(encoding="utf-8") for f in files)
    return f"This request is part of the project's workflow. Follow the flow below step by step: skip nothing, and end with its checklist.\n\n{body}"

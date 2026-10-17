"""#76: every string the context hook adds stays under Claude Code's 10,000
characters for a hook's added context, measured on its own: a longer one is
saved to a file and Claude sees only its first 2,000. The first flow context is
a short, fixed instruction with the flow's path, plus the sections that fit.
Driven through `workflow hook context`, as the other context-hook tests are."""

import re
import uuid

import pytest

from conftest import KIT
from test_hooks_cli import run_hook
from workflow.context import CONTEXT_LIMIT as LIMIT

FLOW = (KIT / "docs/flow.md").read_text(encoding="utf-8")
SHOWN = 2_000  # what Claude sees of a string over the limit


@pytest.fixture(autouse=True)
def _no_level(monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)


def _ctx(repo, prompt, session=None, env=None):
    ev = {"prompt": prompt, "session_id": session or uuid.uuid4().hex}
    code, out, err = run_hook("context", ev, repo, {"TMPDIR": str(repo.parent), **(env or {})})
    assert code == 0 and not err, err
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


def _headings(text):
    return [l[3:].strip() for l in text.splitlines() if l.startswith("## ")]


def _add_addendum(repo, text):
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs/our-flow.md").write_text(text)
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nflow_addendum = "docs/our-flow.md"'))


def test_the_kit_s_own_flow_is_longer_than_the_limit():
    # what makes this ticket real: if it ever fits, the tests below still hold
    assert len(FLOW) > LIMIT - 4_000


@pytest.mark.parametrize("env", [{}, {"WORKFLOW_EXPERIENCE": "developer"}], ids=["with the glossary", "developer"])
def test_the_kit_s_flow_stays_under_the_limit(repo, env):
    ctx = _ctx(repo, "implement #5", env=env)
    assert ctx and len(ctx) < LIMIT
    shown = ctx[:SHOWN]
    # the instruction comes first, where Claude sees it whatever happens
    assert "read" in shown.lower() and "all of it" in shown and str(KIT / "docs/flow.md") in shown
    assert "Follow the flow below" not in ctx  # never claims the whole flow is below when it isn't


def test_a_vendored_flow_stays_under_the_limit(repo):
    (repo / ".claude/workflow/flow.md").write_text(FLOW)
    ctx = _ctx(repo, "/next")
    assert len(ctx) < LIMIT and str(repo / ".claude/workflow/flow.md") in ctx[:SHOWN]


def test_sections_that_fit_come_whole_and_the_rest_are_named(repo):
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    sections = re.split(r"(?m)^(?=## )", FLOW)
    given = [s for s in sections[1:] if s.strip() in ctx]
    assert given, "at least one section fits"
    for s in sections[1:]:
        heading = s.splitlines()[0][3:].strip()
        assert s.strip() in ctx or heading in ctx, f"{heading!r} neither given nor named"
    # a section is given whole or not at all
    for heading in _headings(ctx):
        whole = next(s for s in sections if s.startswith(f"## {heading}\n"))
        assert whole.strip() in ctx


def test_a_long_addendum_stays_under_the_limit(repo):
    _add_addendum(repo, "# Our flow\n\n## Our rules\n\n" + "Always ask the shop's owner first.\n" * 600)
    ctx = _ctx(repo, "build #12")
    assert len(ctx) < LIMIT
    assert str(repo / "docs/our-flow.md") in ctx[:SHOWN] and "Our rules" in ctx
    assert "Always ask the shop's owner first." not in ctx


def test_a_long_flow_and_a_long_addendum_under_the_limit(repo):
    (repo / ".claude/workflow/flow.md").write_text(FLOW + "\n\n## Padding\n\n" + "More words.\n" * 2_000)
    _add_addendum(repo, "# Our flow\n\n" + "A long opening.\n" * 2_000)
    ctx = _ctx(repo, "work the doctor map")
    assert len(ctx) < LIMIT and "Padding" in ctx


def test_a_short_addendum_comes_beside_the_flow(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n## 1. Build\n\nTests first.\n")
    _add_addendum(repo, "# Our flow\n\n## Our rules\n\nThe notes app ships on Fridays.\n")
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "Tests first." in ctx and "The notes app ships on Fridays." in ctx and "left out" not in ctx


def test_a_short_flow_comes_whole(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n## 1. Build\n\nTests first.\n")
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "Tests first." in ctx and "left out" not in ctx


def test_a_heading_inside_a_code_block_is_not_a_section(repo):
    flow = "# The flow\n\n## 1. Build\n\n```\n## not a heading\n```\n\nTests first.\n"
    (repo / ".claude/workflow/flow.md").write_text(flow)
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "## 1. Build\n\n```\n## not a heading\n```\n\nTests first." in ctx


def test_the_reminder_after_the_first_is_short(repo):
    s = uuid.uuid4().hex
    _ctx(repo, "implement #5", session=s)
    again = _ctx(repo, "implement #6", session=s)
    assert again and len(again) < 1_000 and "read it again" in again

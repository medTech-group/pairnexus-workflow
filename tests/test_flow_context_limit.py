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
from workflow.context import CONTEXT_LIMIT as LIMIT, FLOW_BUDGET

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


def _add_addendum(repo, text=None):
    """Name docs/our-flow.md as the profile's addendum, writing `text` there unless None."""
    if text is not None:
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs/our-flow.md").write_text(text)
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nflow_addendum = "docs/our-flow.md"'))


def test_the_kit_s_own_flow_is_too_long_to_add_whole():
    # what makes this ticket real: if it ever fits, the tests below still hold
    assert len(FLOW) > FLOW_BUDGET


@pytest.mark.parametrize("env", [{}, {"WORKFLOW_EXPERIENCE": "developer"}], ids=["with the glossary", "developer"])
def test_the_kit_s_flow_stays_under_the_limit(repo, env):
    ctx = _ctx(repo, "implement #5", env=env)
    assert ctx and len(ctx) < LIMIT
    shown = ctx[:SHOWN]
    # the instruction comes first, where Claude sees it whatever happens
    assert "read it now, all of it" in shown.lower() and str(KIT / "docs/flow.md") in shown
    assert "Follow the flow below" not in ctx  # never claims the whole flow is below when it isn't
    if not env:
        assert "the first time you use it in this session" in shown  # the glossary's rule, beside it


def test_a_vendored_flow_stays_under_the_limit(repo):
    (repo / ".claude/workflow/flow.md").write_text(FLOW)
    ctx = _ctx(repo, "/next")
    assert len(ctx) < LIMIT and str(repo / ".claude/workflow/flow.md") in ctx[:SHOWN]


def test_the_start_comes_whole_and_where_it_stops_is_named(repo):
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    instruction, body = ctx.split("\n\n", 1)
    sections = re.split(r"(?m)^(?=## )", FLOW)
    given = [s for s in sections if s.strip() in body]
    assert len(given) >= 2 and given == sections[: len(given)], "a run of whole sections from the start"
    stop = sections[len(given)].splitlines()[0][3:].strip()
    assert f'stops before "{stop}" (flow.md)' in instruction
    assert body == "\n\n".join(s.strip() for s in given)


def test_a_long_addendum_stays_under_the_limit(repo):
    _add_addendum(repo, "# Our flow\n\n## Our rules\n\n" + "Always ask the shop's owner first.\n" * 600)
    ctx = _ctx(repo, "build #12")
    assert len(ctx) < LIMIT
    assert str(repo / "docs/our-flow.md") in ctx[:SHOWN]
    assert "Always ask the shop's owner first." not in ctx


def test_a_long_flow_and_a_long_addendum_under_the_limit(repo):
    (repo / ".claude/workflow/flow.md").write_text(FLOW + "\n\n## Padding\n\n" + "More words.\n" * 2_000)
    _add_addendum(repo, "# Our flow\n\n" + "A long opening.\n" * 2_000)
    ctx = _ctx(repo, "work the doctor map")
    assert len(ctx) < LIMIT and 'stops before "' in ctx


def test_an_addendum_of_many_sections_stays_under_the_limit(repo):
    _add_addendum(repo, "# Our flow\n\n" + "".join(f"## Rule {i}\n\n{'Ask the owner. ' * 40}\n\n" for i in range(600)))
    ctx = _ctx(repo, "implement #5")
    assert len(ctx) < LIMIT and str(repo / "docs/our-flow.md") in ctx[:SHOWN]


def test_a_huge_heading_stays_under_the_limit(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n## 1. Build\n\nTests first.\n")
    _add_addendum(repo, "# Our flow\n\n## " + "Rules " * 2_000 + "\n\nAsk first.\n")
    ctx = _ctx(repo, "implement #5")
    assert len(ctx) < LIMIT and str(repo / "docs/our-flow.md") in ctx[:SHOWN]
    assert "Tests first." in ctx and 'stops before "Rules Rules' in ctx and "…\" (our-flow.md)" in ctx


def test_the_budget_is_used(repo):
    # sections fill up to the budget: not reserved for names that are never written
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n" + "".join(f"## {i}\n\n{'x' * 900}\n\n" for i in range(20)))
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert FLOW_BUDGET - 1_000 < len(ctx) <= FLOW_BUDGET


def test_the_budget_counts_the_name_where_the_text_stops(tmp_path):
    # short and long headings in turn: the check must use the name the text would stop before
    from workflow import context

    long = "L" * 80
    flow = "# The flow\n\n" + "".join(f"## {'s' if i % 2 else long}{i}\n\n{'x' * 700}\n\n" for i in range(30))
    path = tmp_path / "flow.md"
    for pad in range(0, 1_700):  # move the cut across a whole cycle of short and long names
        path.write_text(flow.replace("# The flow", "# The flow" + "y" * pad, 1))
        ctx = context.first_flow([path])
        assert len(ctx) <= FLOW_BUDGET and "stops before" in ctx, pad
        # and the latest cut that fits: one more section, stopping before the next, would not
        pieces = [(path, p) for p in context._sections(path.read_text())]
        k = ctx.count("\n\n## ") + 1  # the opening and the sections given
        if k + 1 < len(pieces):
            more = "\n\n".join([f"{context.FLOW_HEAD}{context._READ}{path}." + context._stop(*pieces[k + 1]), *(q for _, q in pieces[: k + 1])])
            assert len(more) > FLOW_BUDGET, pad


def test_a_flow_that_fits_whole_is_never_cut(tmp_path):
    # exactly the budget in the whole form, which the cut form's longer instruction would pass
    from workflow import context

    path = tmp_path / "flow.md"
    whole_head = f"{context.FLOW_HEAD}{context._WHOLE}{path})."
    tail = "## Done\n\nShip it."
    opening = "# The flow\n\n"
    opening += "x" * (FLOW_BUDGET - len(whole_head) - len(opening) - 2 - len(tail) - 2)
    path.write_text(f"{opening}\n\n{tail}\n")
    ctx = context.first_flow([path])
    assert len(ctx) == FLOW_BUDGET and "All of it is below" in ctx and ctx.endswith("Ship it.")


def test_an_opening_too_long_for_the_budget_leaves_the_instruction_alone(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n" + "x" * 9_000 + "\n\n## 1. Build\n\nTests first.\n")
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "read it now, all of it" in ctx.lower() and "below" not in ctx and "\n" not in ctx


def test_a_short_addendum_comes_beside_the_flow(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n## 1. Build\n\nTests first.\n")
    _add_addendum(repo, "# Our flow\n\n## Our rules\n\nThe notes app ships on Fridays.\n")
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "Tests first." in ctx and "The notes app ships on Fridays." in ctx and "All of it is below" in ctx


def test_a_short_flow_comes_whole(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n\n## 1. Build\n\nTests first.\n")
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "Tests first." in ctx and "All of it is below" in ctx and "not included" not in ctx.lower()


def test_a_heading_inside_a_code_block_is_not_a_section(repo):
    flow = "# The flow\n\n## 1. Build\n\n```\n## not a heading\n```\n\nTests first.\n"
    (repo / ".claude/workflow/flow.md").write_text(flow)
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "## 1. Build\n\n```\n## not a heading\n```\n\nTests first." in ctx


def test_fences_of_each_kind(repo):
    flow = (
        "# The flow\n\n## 1. Build\n\n~~~\n## not a heading\n```\n## nor this\n~~~\n"
        "````\n```\n## nor this one\n````\n```\n```x\n## nor this, after a fence with words\n```\n"
        "```x``` is inline, not a fence\n## 2. Merge\n\nGreen first.\n"
    )
    (repo / ".claude/workflow/flow.md").write_text(flow)
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    body = ctx.split("\n\n", 1)[1]
    # only "## 2. Merge" starts a section: the join adds a blank line before it alone
    assert body == flow.strip().replace("not a fence\n## 2. Merge", "not a fence\n\n## 2. Merge")


def test_an_unreadable_flow_leaves_the_instruction_and_never_fails(repo):
    (repo / ".claude/workflow/flow.md").write_bytes(b"# The flow\n\xff\xfe broken\n")
    s = uuid.uuid4().hex
    ctx = _ctx(repo, "implement #5", session=s, env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "read it now, all of it" in ctx.lower() and str(repo / ".claude/workflow/flow.md") in ctx


def test_the_reminder_after_the_first_is_short(repo):
    s = uuid.uuid4().hex
    _ctx(repo, "implement #5", session=s)
    again = _ctx(repo, "implement #6", session=s)
    assert again and len(again) < 1_000 and "read it again" in again


@pytest.mark.parametrize("sections", [30, 60], ids=["all of it fits", "only its start fits"])
def test_long_paths_never_pass_the_limit(tmp_path, sections):
    from workflow import context

    glossary = tmp_path / "glossary.md"
    glossary.write_text("# Glossary\n\n### Pull request\n\nA proposed change.\n")
    long = "/" + "d" * 200
    flow = tmp_path / "flow.md"
    flow.write_text("# The flow\n\n" + "".join(f"## {i}\n\n{'x' * 200}\n\n" for i in range(sections)))
    ctx = context.first_flow([flow])
    assert ("All of it is below" in ctx) == (sections == 30)
    ctx = ctx.replace(str(flow), long * 20)  # paths as long as a deep checkout's, without making one
    out = context.with_glossary(ctx, glossary)
    assert len(out) < LIMIT
    assert "read it now, all of it" in out.lower() and long * 20 in out
    assert "below" not in out.split("read it now.", 1)[1].lower()  # nothing claimed below that isn't there


def test_a_byte_order_mark_is_left_out(repo):
    (repo / ".claude/workflow/flow.md").write_bytes("\ufeff# The flow\n\n## 1. Build\n\nTests first.\n".encode("utf-8"))
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert "\ufeff" not in ctx and "# The flow" in ctx


def test_a_directory_is_not_a_flow_file(repo):
    (repo / "docs/our-flow.md").mkdir(parents=True)
    _add_addendum(repo)
    ctx = _ctx(repo, "implement #5", env={"WORKFLOW_EXPERIENCE": "developer"})
    assert ctx and "our-flow.md" not in ctx


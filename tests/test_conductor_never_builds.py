"""#308: a conductor session never builds a ticket it's named. "build #12",
"implement #12" or "Let's work on #12" in a conductor session becomes a run
scoped to that ticket (or, during a run, the amendment "also #12"), named to a
ticket session. Seams: `workflow hook context`, as Claude Code runs it, and the
skills' own text."""

import re
import uuid

import pytest

from changelog_notes import since_0110
from conftest import KIT
from test_plan_first import _ctx, _later

# The conductor line's opening, as the hook adds it.
LINE = "This is a conductor session: the conductor never builds a ticket itself."

NAMED = [
    "build #12",
    "Build #12 please",
    "implement #12",
    "Let's work on #12",
    "Lets work on #12",
    "build 12",
    "implement ticket 12",
    "Lets work on 12",
    "can you fix #12?",
    "/next 12",
    "work on https://github.com/acme/demo/issues/12",
    # From the explorer's round 1.
    "build tickets 12 and 13",
    "build issues #12 and #13",
    "building #12",
    "implementing #12",
    "fix bug #12",
    "work on the #12",
    "build: #12",
    "build\n#12",
    "#12 please build it",
    "Let's get #12 built",
    "#12: implement",
    "start with #12",
    "pick up #12",
    "tackle #12",
    "do #12",
    "go ahead with #12",
    "/build-ticket 12",
    "build owner/repo#12",
    "build \uff0312",
]

# A conductor's own messages, and the owner's that name no ticket to build.
NOT_NAMED = [
    "run the backlog unattended",
    "why did the build fail?",
    "is anything still building?",
    "the build on #12 failed, why?",
    "the fix for #12 looks wrong",
    "fix the CI",
    "start with infra",
    "start on Monday 9am",
    "pick up where you left off",
    "work on the report tonight",
    "rebuild #12",
    "fix 2 typos in the README",
    "build 2 dashboards",
    "start on 1 March",
    "implement 3 retries",
    "work on 10 minutes",
    "conductor resume",
    "conductor: wake (a ticket session finished)\n\n#12 merged in #40",
    "also #140",
    "extend to Monday 9am",
    "why did #12 stop?",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """This session's own level and role never leak into the hook under test."""
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)


CONDUCTOR = {"WORKFLOW_ROLE": "conductor"}


@pytest.mark.parametrize("prompt", NAMED)
def test_a_ticket_named_to_the_conductor_brings_the_line_first(repo, prompt):
    first = _ctx(repo, prompt, uuid.uuid4().hex, CONDUCTOR)
    assert first.startswith(LINE), first[:200]
    assert LINE in _later(repo, prompt, CONDUCTOR, first="conductor resume")


def test_the_line_says_where_the_ticket_goes(repo):
    ctx = _ctx(repo, "build #12", uuid.uuid4().hex, CONDUCTOR)
    line = ctx.split("\n\n", 1)[0]
    for part in ("ticket session", "`conductor` skill", '"A ticket named in chat"', '"also #<n>"', "`next`", "`build-ticket`"):
        assert part in line, part


def test_the_line_is_conditional_so_a_refusal_never_reads_as_a_request(repo):
    # "don't build #13" brings the line too: it says what to do *if* a ticket is asked for, never that one was.
    line = _ctx(repo, "don't build #13", uuid.uuid4().hex, CONDUCTOR).split("\n\n", 1)[0]
    assert "If this message asks for a ticket to be built" in line


def test_the_line_and_the_whole_flow_budget_fit_under_the_limit():
    from workflow.context import CONDUCTOR_LINE, CONTEXT_LIMIT, FLOW_BUDGET

    assert len(CONDUCTOR_LINE) + 2 + FLOW_BUDGET < CONTEXT_LIMIT


def test_long_prompts_stay_quick(repo):
    import time

    for prompt in ("build" + " " * 50_000 + "x", "#1" + "x" * 50_000 + " build", "work on https://" + "a" * 50_000, "1" * 50_000 + "x"):
        began = time.monotonic()
        _ctx(repo, prompt, uuid.uuid4().hex, CONDUCTOR)
        assert time.monotonic() - began < 5, repr(prompt[:20])


def test_a_conductor_session_without_a_profile_still_gets_the_line(repo):
    (repo / ".claude/workflow/profile.toml").unlink()
    assert _ctx(repo, "build #12", uuid.uuid4().hex, CONDUCTOR).startswith(LINE)


def test_the_flow_still_comes_beside_it(repo):
    session = uuid.uuid4().hex
    first = _ctx(repo, "build #12", session, CONDUCTOR)
    assert "This request is part of the project's workflow." in first
    assert len(first) < 10_000  # Claude Code's limit, so nothing is saved to a file


@pytest.mark.parametrize("prompt", NOT_NAMED)
def test_the_conductors_own_messages_bring_no_line(repo, prompt):
    assert LINE not in (_ctx(repo, prompt, uuid.uuid4().hex, CONDUCTOR) or "")


@pytest.mark.parametrize("env", [{}, {"WORKFLOW_ROLE": "attended"}, {"WORKFLOW_ROLE": "ticket"}])
@pytest.mark.parametrize("prompt", NAMED)
def test_other_sessions_never_get_the_line(repo, prompt, env):
    assert LINE not in (_ctx(repo, prompt, uuid.uuid4().hex, env) or "")
    assert LINE not in (_later(repo, prompt, env) or "")


def _text(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text):
    return re.sub(r"\s+", " ", text)


def test_next_never_builds_in_a_conductor_session():
    text = _flat(_text("skills/next/SKILL.md"))
    assert "conductor session, the briefing or the charter" not in text
    assert "In a ticket or conductor session (" not in text
    assert "In a ticket session (" in text
    rule = (
        "**Never in a conductor session.** In a conductor session (`WORKFLOW_ROLE=conductor`), never build: follow "
        'the `conductor` skill\'s "A ticket named in chat" with the ticket, or, with none named, offer a run of the '
        'ready tickets as its "Start a run" says.'
    )
    assert rule in text
    # Before anything is picked or claimed.
    assert text.index(rule) < text.index("## 1. Find what is ready")


def test_build_ticket_stops_in_a_conductor_session():
    text = _flat(_text("skills/build-ticket/SKILL.md"))
    assert (
        "**Never in a conductor session.** With `WORKFLOW_ROLE=conductor`, stop here, before the claim or any "
        'other write: the conductor never builds a ticket. Follow the `conductor` skill\'s "A ticket named in chat" '
        "with it instead."
    ) in text
    # Before the claim.
    assert text.index("**Never in a conductor session.**") < text.index("## 1. Claim it")
    description = _text("skills/build-ticket/SKILL.md").split("\n---", 1)[0]
    assert "Never in a conductor session" in description


def test_the_conductor_says_what_a_named_ticket_becomes():
    text = _flat(_text("skills/conductor/SKILL.md"))
    assert "## A ticket named in chat" in text
    section = text.split("## A ticket named in chat", 1)[1].split(" ## ", 1)[0]
    for part in (
        "You never build it yourself",
        "never claim it, branch for it, write its code",
        "`next` or `build-ticket`",
        "**No run in progress** (no open `workflow:run` issue)",
        "`scope.tickets` is `[<n>]`",
        "`follow_unblocked` false",
        "open `workflow:infra` tickets and leftovers adopted at the kick-off still run",
        "**A run in progress that this session conducts**",
        'the amendment "also #<n>"',
        'with "all-ready", only to `plan`',
        "takes it out of `scope.exclude`",
        "**A run in progress that another session conducts:** write nothing to its tracking issue",
        "**`/next` with no ticket**",
        "`conductor_fixes`",
    ):
        assert part in section, part
    description = _text("skills/conductor/SKILL.md").split("\n---", 1)[0]
    assert '"build #N"' in description and '"implement #N"' in description and '"work on #N"' in description


def test_flow_section_5_says_so():
    text = _flat(_text("docs/flow.md"))
    assert (
        'A ticket named to the conductor ("build #12", "implement #12", "let\'s work on #12") becomes a run '
        'scoped to it, or during a run the amendment "also #12": a ticket session builds it.'
    ) in text


def test_the_changelog_notes_it():
    assert "(#308)" in since_0110()

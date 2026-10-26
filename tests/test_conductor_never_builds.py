"""#308: a conductor session never builds a ticket it's handed. "build #12",
"implement #12" or "Let's work on #12" in a conductor session becomes a run
scoped to that ticket (or, during a run, the amendment "also #12"), handed to a
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

HANDED = [
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
]

# A conductor's own messages that name no ticket to build.
NOT_HANDED = [
    "run the backlog unattended",
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


@pytest.mark.parametrize("prompt", HANDED)
def test_a_ticket_handed_to_the_conductor_brings_the_line_first(repo, prompt):
    first = _ctx(repo, prompt, uuid.uuid4().hex, CONDUCTOR)
    assert first.startswith(LINE), first[:200]
    assert LINE in _later(repo, prompt, CONDUCTOR, first="conductor resume")


def test_the_line_says_where_the_ticket_goes(repo):
    ctx = _ctx(repo, "build #12", uuid.uuid4().hex, CONDUCTOR)
    line = ctx.split("\n\n", 1)[0]
    for part in ("ticket session", "`conductor` skill", '"A ticket named in chat"', '"also #<n>"', "`next`", "`build-ticket`"):
        assert part in line, part


def test_the_flow_still_comes_beside_it(repo):
    session = uuid.uuid4().hex
    first = _ctx(repo, "build #12", session, CONDUCTOR)
    assert "This request is part of the project's workflow." in first
    assert len(first) < 10_000  # Claude Code's limit, so nothing is saved to a file


@pytest.mark.parametrize("prompt", NOT_HANDED)
def test_the_conductors_own_messages_bring_no_line(repo, prompt):
    assert LINE not in (_ctx(repo, prompt, uuid.uuid4().hex, CONDUCTOR) or "")


@pytest.mark.parametrize("env", [{}, {"WORKFLOW_ROLE": "attended"}, {"WORKFLOW_ROLE": "ticket"}])
@pytest.mark.parametrize("prompt", HANDED)
def test_other_sessions_never_get_the_line(repo, prompt, env):
    assert LINE not in (_ctx(repo, prompt, uuid.uuid4().hex, env) or "")
    assert LINE not in (_later(repo, prompt, env) or "")


def _text(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text):
    return re.sub(r"\s+", " ", text)


def test_next_never_builds_in_a_conductor_session():
    text = _flat(_text("skills/next/SKILL.md"))
    assert "In a ticket or conductor session (" not in text
    assert "In a ticket session (" in text
    assert (
        "In a conductor session (`WORKFLOW_ROLE=conductor`), never build: follow the `conductor` skill's "
        '"A ticket named in chat" with the ticket.'
    ) in text


def test_build_ticket_stops_in_a_conductor_session():
    text = _flat(_text("skills/build-ticket/SKILL.md"))
    assert (
        "**Never in a conductor session.** With `WORKFLOW_ROLE=conductor`, stop here, before the claim or any "
        'other write: the conductor never builds a ticket. Follow the `conductor` skill\'s "A ticket named in chat" '
        "with it instead."
    ) in text
    # Before the claim.
    assert text.index("**Never in a conductor session.**") < text.index("## 1. Claim it")


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
        "**A run in progress:**",
        'the amendment "also #<n>"',
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

"""#223: a message that only mentions the conductor gets the guided start (or,
later, the reminder), not the flow; asking to run, resume or stop a run or the
conductor, and working on a named map, still bring the flow (spec #221,
decision 4 on #220). Seam: `workflow hook context`, as Claude Code runs it."""

import uuid

import pytest

from conftest import KIT
from test_plan_first import REMINDER, _ctx, _later

START = "This is the first message of the session."
FLOW = "This request is part of the project's workflow."

MENTIONS = [
    "the conductor left a label on the ticket after it merged",
    "Why did the conductor stop?",
    "the conductor's check-in table is hard to read",
    "the conductor run on Friday never woke up",
    "can you explain what the conductor does",
    "the conductor skipped #12",
]

ASKS = [
    "run the backlog unattended",
    "Run the backlog unattended this weekend",
    "conductor resume",
    "Conductor: stop",
    "stop the run",
    "resume the run",
    "start an unattended run",
    "stop the conductor",
    "start the conductor",
    "work the doctor map",
    "let's keep working on the doctor map",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """This session's own level and role never leak into the hook under test."""
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)


@pytest.mark.parametrize("prompt", MENTIONS)
def test_a_first_message_that_mentions_the_conductor_gets_the_guided_start(repo, prompt):
    ctx = _ctx(repo, prompt, uuid.uuid4().hex)
    assert START in ctx, ctx[:200]
    assert FLOW not in ctx


@pytest.mark.parametrize("prompt", MENTIONS)
def test_a_later_message_that_mentions_the_conductor_gets_the_reminder(repo, prompt):
    assert _later(repo, prompt) == REMINDER


@pytest.mark.parametrize("prompt", ASKS)
def test_asking_to_run_resume_or_stop_or_working_a_map_still_gets_the_flow(repo, prompt):
    first = _ctx(repo, prompt, uuid.uuid4().hex)
    assert FLOW in first and START not in first, first[:200]
    later = _later(repo, prompt)
    assert FLOW in later and REMINDER not in later


def test_the_changelog_notes_it_under_unreleased():
    unreleased = (KIT / "CHANGELOG.md").read_text(encoding="utf-8").split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "(#223, part of #221)" in unreleased and "conductor" in unreleased

"""#223: a message that only mentions the conductor gets the guided start (or,
later, the reminder), not the flow; asking to run, resume or stop a run or the
conductor, and working on a named map, still bring the flow (spec #221,
decision 4 on #220). Seam: `workflow hook context`, as Claude Code runs it."""

import time
import uuid

import pytest

from changelog_notes import since_0110
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
    # A run or the conductor named as a thing, not asked for.
    "Conductor run on Friday never woke up",
    "Conductor start time is wrong in the report",
    "conductor: stop button does nothing",
    "Conductor run's log is empty",
    "Conductor run\u2019s report skipped #12",
    "Conductor wake-up never fired",
    "Conductor start-up is slow",
    "Conductor stop/start buttons do nothing",
    "Conductor run this morning never woke up",
    "Conductor run now takes 3 hours",
    "the ticket sessions didn't start\nthe conductor log is attached",
    "Conductor run: hangs after the first ticket",
    "conductor run - it failed on Friday",
    "conductor start, then nothing happens",
    "Conductor stop (the button) does nothing",
    "Conductor: run the backlog failed at #12",
    "conductor: wake (a ticket session finished) shows up in my session, why?",
    # Running unattended asked about, not asked for.
    "can ticket sessions run unattended?",
    "the hooks don't work unattended",
    "why won't my session run unattended?",
    "sessions start asking for permission when unattended",
    "can the conductor run unattended overnight?",
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
    "restart the conductor",
    "OK conductor resume",
    "conductor, please resume",
    "Morning.\nconductor resume",
    "conductor resume #12",
    "conductor resume 2026-10-12-run",
    "conductor resume 45",
    "conductor resume please",
    "conductor stop now",
    "Hi, conductor resume",
    "run all the open tickets unattended",
    "/conductor",
    "/pairnexus-workflow:conductor resume",
]

# What the conductor's wake routine sends its session (skills/conductor/SKILL.md, set-up step 12).
WAKE = "conductor: wake (a ticket session finished)"


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


@pytest.mark.parametrize("wake", [WAKE, WAKE + "\n\n#12 merged in #40"])
def test_the_conductors_wake_still_brings_the_flow_to_its_session(repo, wake):
    env, session = {"WORKFLOW_ROLE": "conductor"}, uuid.uuid4().hex
    assert FLOW in _ctx(repo, wake, session, env)
    # At a later wake, the flow's one-line reminder.
    assert _ctx(repo, wake, session, env).startswith("Follow the workflow's flow")


def test_a_long_run_of_whitespace_after_conductor_is_quick(repo):
    for prompt in ("conductor" + " " * 50_000 + "x", "Conductor:" + "\n" * 50_000 + "x", "\n" * 50_000 + "x"):
        began = time.monotonic()
        _ctx(repo, prompt, uuid.uuid4().hex, {"WORKFLOW_ROLE": "conductor"})
        assert time.monotonic() - began < 5, repr(prompt[:12])


def test_the_changelog_notes_it():
    assert "(#223, part of #221)" in since_0110()

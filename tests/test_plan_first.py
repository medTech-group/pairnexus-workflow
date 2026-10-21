"""#222: the guided start's narrower first-message text, and a reminder on every
later message of an attended session (spec #221, decisions on #220). Seam:
`workflow hook context`, with a prompt event on stdin, as Claude Code runs it."""

import uuid

import pytest

from conftest import KIT, git
from test_hooks_cli import run_hook
from workflow.context import CONTEXT_LIMIT as LIMIT

# Agreed word for word on #220 (decision 5).
EXCEPTIONS = (
    "Act on this message straight away only when it is a question, names an issue, or asks for one small change "
    "with an obvious place (on its own branch, with a pull request)."
)
PLAN_FIRST = (
    "If it asks for any other work (a feature, a change, a fix whose cause isn't known, or more than one thing), "
    "don't start on it: split it into items with a path for each and agree the plan first."
)
RESUMED = "If the conversation was already under way (a resumed session), follow the reminder below instead."
REMINDER = (
    "Workflow: if this message asks for new work that isn't part of the plan or ticket already agreed in this "
    "session, don't start on it: split it into items with a path for each and agree the plan first (the `start` "
    "skill, step 2). A question, a named issue or one small change with an obvious place may go ahead (on its own "
    "branch, with a pull request). Replies to your own questions carry on."
)
FEATURE = "add a dark mode toggle to the settings page"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """This session's own level and role never leak into the hook under test."""
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)


def _ctx(repo, prompt, session, env=None):
    ev = {"prompt": prompt, "session_id": session}
    code, out, err = run_hook("context", ev, repo, {"TMPDIR": str(repo.parent), **(env or {})})
    assert code == 0 and not err, err
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


def _later(repo, prompt, env=None, first="hi"):
    """What `prompt` brings as a session's second message, after `first`."""
    session = uuid.uuid4().hex
    _ctx(repo, first, session, env)
    return _ctx(repo, prompt, session, env)


def _developer(repo):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nexperience = "developer"'))


def test_a_feature_request_first_gets_the_three_exceptions_and_plan_first(repo):
    _developer(repo)
    ctx = _ctx(repo, FEATURE, uuid.uuid4().hex)
    assert ctx.startswith("This is the first message of the session. Follow the kit's guided start, the `start` skill")
    assert "first, when `workflow status` finds no experience level, ask it as the skill says." in ctx
    assert EXCEPTIONS in ctx and PLAN_FIRST in ctx
    assert 'Otherwise ask "What are we working on?" with choices.' in ctx
    # The old "one clear thing, just do it" is gone.
    assert "one clear thing" not in ctx and "just do it" not in ctx


def test_the_second_and_third_prompts_get_the_reminder(repo):
    session = uuid.uuid4().hex
    first = _ctx(repo, FEATURE, session)
    assert first and "This is the first message" in first
    for prompt in ("now also add payments to checkout", "yes"):
        ctx = _ctx(repo, prompt, session)
        assert ctx == REMINDER, prompt  # the reminder alone: no first-message text, no glossary again


def test_no_reminder_in_ticket_or_conductor_sessions(repo):
    for role in ("ticket", "conductor"):
        assert _later(repo, "now also add payments", env={"WORKFLOW_ROLE": role}) == "", role
    git(repo, "checkout", "-qb", "claude/build-7")
    assert _later(repo, "now also add payments") == ""


def test_no_reminder_with_the_guided_start_off(repo):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nguided_start = false'))
    assert _later(repo, "now also add payments") == ""


def test_no_reminder_on_a_later_slash_command(repo):
    for prompt in ("/compact", "/review the branch", "  /grill-me"):
        assert _later(repo, prompt) == "", prompt
    # A path isn't a command: it gets the reminder.
    assert _later(repo, "/home/user/app.py crashes") == REMINDER


@pytest.mark.parametrize("prompt", ["/next", "implement #5"])
def test_a_later_flow_prompt_gets_the_flow_only(repo, prompt):
    ctx = _later(repo, prompt)
    assert "This request is part of the project's workflow." in ctx
    assert REMINDER not in ctx and "Workflow: if this message" not in ctx
    # And again, once the flow's own context is its reminder line.
    session = uuid.uuid4().hex
    for p in ("hi", prompt):
        _ctx(repo, p, session)
    again = _ctx(repo, prompt, session)
    assert again.startswith("Follow the workflow's flow") and REMINDER not in again


def test_the_first_message_text_says_a_resumed_session_follows_the_reminder(repo):
    _developer(repo)
    ctx = _ctx(repo, "hi", uuid.uuid4().hex)
    assert RESUMED in ctx and "ignore this" not in ctx.lower()
    # The reminder comes whole, below the first-message text.
    assert ctx.endswith("\n\n" + REMINDER)
    assert ctx.index(RESUMED) < ctx.index(REMINDER)


def test_new_to_building_the_first_text_and_glossary_stay_under_the_limit(repo):
    ctx = _ctx(repo, FEATURE, uuid.uuid4().hex)  # no level anywhere: counts as new
    assert "new to building" in ctx  # the glossary's rule is beside it
    assert len(ctx) < LIMIT
    assert REMINDER in ctx and EXCEPTIONS in ctx and RESUMED in ctx


# The skill, the docs and the changelog say what later messages get


def _text(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def test_the_start_skill_follows_the_reminder_in_a_resumed_session():
    step0 = _text("skills/start/SKILL.md").split("## 0. Read the first message", 1)[1].split("## 1. ", 1)[0]
    row = next(x for x in step0.splitlines() if "(a resumed session)" in x)
    assert "Follow the hook's reminder" in row and "Ignore the hook" not in row
    assert "**Later messages.**" in step0 and "one-line reminder" in step0
    # The "one clear request" row keeps its three cases.
    assert "a question, a named issue" in step0 and "one small change with an obvious place" in step0


def test_the_readme_and_the_flow_say_what_later_messages_get():
    first = _text("README.md").split("**What happens with your first message:**", 1)[1].split("**Looking around.**", 1)[0]
    assert "**Your later messages:**" in first and "plan new work before starting on it" in first
    assert "the first-message menu and the later messages' reminder off" in first
    starting = next(x for x in _text("docs/flow.md").splitlines() if x.startswith("**Starting.**"))
    assert "At each later message of an attended session" in starting and "reminder" in starting
    assert "the reminder at each later message" in _text("docs/profile.md")


def test_the_changelog_notes_it_under_unreleased():
    unreleased = _text("CHANGELOG.md").split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "(#222, part of #221)" in unreleased and "reminder" in unreleased

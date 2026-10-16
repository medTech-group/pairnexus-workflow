"""#74: the context hook adds the glossary for someone new to building, part of
the quickstart and the glossary (#35). Seam 2: `workflow hook context` with a
prompt event on stdin, as the other context-hook tests drive it."""

import os
import shutil
import subprocess
import sys
import uuid

import pytest

from conftest import KIT, git
from test_hooks_cli import run_hook

GLOSSARY = (KIT / "docs/glossary.md").read_text(encoding="utf-8")
RULE = "the first time you use it in this session"
LIMIT = 10_000  # Claude Code's cap on a hook's added context, per string


@pytest.fixture(autouse=True)
def _no_level(monkeypatch):
    """This session's own level and role never leak into the hook under test."""
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)


def _ctx(repo, prompt, session=None, env=None):
    ev = {"prompt": prompt, "session_id": session or uuid.uuid4().hex}
    _, out, _ = run_hook("context", ev, repo, {"TMPDIR": str(repo.parent), **(env or {})})
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


def _set_profile_level(repo, level):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', f'repo = "acme/demo"\nexperience = "{level}"'))


def _set_file_level(repo, level):
    (repo / ".workflow").mkdir(exist_ok=True)
    (repo / ".workflow/experience").write_text(level + "\n")


def _whole(ctx):
    return GLOSSARY.strip() in ctx and RULE in ctx


def _none(ctx):
    return RULE not in ctx and "### Pull request" not in ctx


# Who gets it


def test_unknown_level_counts_as_new(repo):
    ctx = _ctx(repo, "hi")
    assert _whole(ctx)
    assert "never" in ctx and "GitHub" in ctx  # never in PRs, comments, reports


@pytest.mark.parametrize("source", ["environment", "local file", "profile"])
def test_new_from_each_source(repo, source):
    env = {}
    if source == "environment":
        env = {"WORKFLOW_EXPERIENCE": "new"}
    elif source == "local file":
        _set_file_level(repo, "new")
    else:
        _set_profile_level(repo, "new")
    assert _whole(_ctx(repo, "hi", env=env))


@pytest.mark.parametrize("source", ["environment", "local file", "profile"])
def test_never_for_a_developer(repo, source):
    env = {}
    if source == "environment":
        env = {"WORKFLOW_EXPERIENCE": "developer"}
    elif source == "local file":
        _set_file_level(repo, "developer")
    else:
        _set_profile_level(repo, "developer")
    ctx = _ctx(repo, "hi", env=env)
    assert _none(ctx) and "guided start" in ctx  # the nudge still comes


def test_a_developer_file_beats_a_new_profile(repo):
    _set_profile_level(repo, "new")
    _set_file_level(repo, "developer")
    assert _none(_ctx(repo, "hi"))


@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_never_in_ticket_or_conductor_sessions(repo, role):
    assert _ctx(repo, "hi", env={"WORKFLOW_ROLE": role, "WORKFLOW_EXPERIENCE": "new"}) == ""


def test_never_on_a_ticket_branch(repo):
    git(repo, "checkout", "-qb", "claude/build-7")
    assert _ctx(repo, "hi") == ""


def test_never_after_the_first_prompt(repo):
    session = uuid.uuid4().hex
    assert _whole(_ctx(repo, "hi", session))
    assert _ctx(repo, "what is a branch?", session) == ""
    assert _ctx(repo, "hello again", session) == ""


def test_never_after_a_first_prompt_that_carried_none(repo):
    session = uuid.uuid4().hex
    assert _none(_ctx(repo, "hi", session, env={"WORKFLOW_EXPERIENCE": "developer"}))
    assert _ctx(repo, "hi", session, env={"WORKFLOW_EXPERIENCE": "new"}) == ""


def test_never_without_a_profile(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    assert _ctx(tmp_path, "hi") == ""
    assert RULE not in _ctx(tmp_path, "implement #5")  # the kit's flow may still come


# Beside, never instead


def test_beside_the_guided_start(repo):
    ctx = _ctx(repo, "hi")
    assert "guided start" in ctx.split(GLOSSARY.strip())[0]  # the nudge, then the glossary
    assert _whole(ctx)


def test_with_the_guided_start_off(repo):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nguided_start = false'))
    ctx = _ctx(repo, "hi")
    assert _whole(ctx) and "Follow the kit's guided start" not in ctx


@pytest.mark.parametrize("prompt", ["/grill-me my pitch", "/compact"])
def test_after_a_command_as_first_prompt(repo, prompt):
    assert _whole(_ctx(repo, prompt))


def test_beside_the_whole_flow_as_the_rule_and_its_path(repo):
    flow = KIT / "docs/flow.md"
    (repo / ".claude/workflow/flow.md").write_text(flow.read_text(encoding="utf-8"))
    ctx = _ctx(repo, "implement #5")
    assert "Follow the flow below" in ctx and "# The flow" in ctx
    assert RULE in ctx and "read it now" in ctx and str(KIT / "docs/glossary.md") in ctx
    assert "### Pull request" not in ctx
    # what the glossary adds is short: the flow is what passes the limit (#76)
    assert len(ctx) - len(flow.read_text(encoding="utf-8")) < 1_000


def test_beside_a_short_flow_still_only_the_path(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n")
    ctx = _ctx(repo, "build #12")
    assert "# The flow" in ctx and RULE in ctx and "read it now" in ctx and "### Pull request" not in ctx


# Where it reads the glossary


def test_vendored_mode_reads_the_vendored_glossary(repo):
    vendored = repo / ".claude/workflow/docs/glossary.md"
    vendored.parent.mkdir(parents=True)
    vendored.write_text("# Glossary\n\n### Widget\n\nA VENDORED WORD.\n")
    ctx = _ctx(repo, "hi")
    assert "A VENDORED WORD." in ctx and "### Pull request" not in ctx and RULE in ctx
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n")
    assert str(vendored) in _ctx(repo, "implement #5")


def test_plugin_mode_reads_the_kit_s_glossary(repo):
    assert not (repo / ".claude/workflow/docs/glossary.md").exists()
    assert _whole(_ctx(repo, "hi"))
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n")
    assert str(KIT / "docs/glossary.md") in _ctx(repo, "implement #5")


# Under Claude Code's limit


def test_under_the_limit_alone_and_with_the_nudge(repo):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nguided_start = false'))
    alone = _ctx(repo, "/compact")
    assert _whole(alone) and len(alone) < LIMIT
    p.write_text(p.read_text().replace("guided_start = false", ""))
    beside = _ctx(repo, "hi")
    assert _whole(beside) and "guided start" in beside and len(beside) < LIMIT


def test_a_glossary_too_long_to_add_whole_goes_by_its_path(repo):
    vendored = repo / ".claude/workflow/docs/glossary.md"
    vendored.parent.mkdir(parents=True)
    vendored.write_text("# Glossary\n\n" + "A long entry.\n" * 1_000)
    ctx = _ctx(repo, "hi")
    assert len(ctx) < LIMIT and RULE in ctx and "read it now" in ctx and str(vendored) in ctx


def test_a_missing_glossary_adds_nothing_and_never_fails(repo, tmp_path):
    # An older vendored copy without docs/glossary.md, run from a kit without one.
    kit = tmp_path / "oldkit"
    shutil.copytree(KIT / "scripts", kit / "scripts")
    ev = '{"prompt": "hi", "session_id": "%s"}' % uuid.uuid4().hex
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo), "TMPDIR": str(repo.parent)}
    p = subprocess.run([sys.executable, str(kit / "scripts/workflow.py"), "hook", "context"], input=ev, capture_output=True, text=True, cwd=repo, env=env)
    assert p.returncode == 0 and RULE not in p.stdout and "guided start" in p.stdout

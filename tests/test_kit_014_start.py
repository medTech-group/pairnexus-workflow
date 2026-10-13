"""Kit 0.1.4: the guided start (skills/start), `workflow status`, and the first-message hook."""

import json
import os
import subprocess
import sys
import uuid

import pytest

from conftest import KIT, BASE_PROFILE, git
from test_hooks_cli import CLI, run_hook
from workflow import context, status
from workflow.profile import ProfileError, parse


def _issue(n, title, labels=(), body="", state="open", **extra):
    return {"number": n, "title": title, "labels": [{"name": x} for x in labels], "body": body, "state": state, **extra}


ISSUES = [
    _issue(1, "Run 2026-10-13", ["workflow:run"]),
    _issue(2, "Doctor map", ["wayfinder:map"], sub_issues_summary={"total": 3, "completed": 1}),
    _issue(3, "Spec: export as PDF", ["spec", "ready-for-agent"], sub_issues_summary={"total": 0, "completed": 0}),
    _issue(4, "Export the PDF", ["ready-for-agent"], body="Area: messages\n\n## Blocked by\n\nNone"),
    _issue(5, "Claimed one", ["ready-for-agent", "workflow:in-progress"], body="Area: messages"),
    _issue(6, "Make an Auth0 tenant", ["owner-task"]),
    _issue(7, "What does OPD mean here?", ["needs-info"]),
    _issue(8, "The app crashes on upload", ["needs-triage"]),
    _issue(9, "Something someone filed"),
    _issue(10, "Rename Save to Done", body="what they said\n\n<!-- workflow:item path=ticket -->"),
    _issue(11, "Old and done", ["ready-for-agent"], state="closed"),
    _issue(12, "A PR, as the issues API lists it", pull_request={"merged_at": None}),
]
PRS = [{"number": 13, "title": "Export the PDF", "state": "open", "body": "Closes #99", "head": {"ref": "claude/build-99"}}]


def _nums(items):
    return [i.number for i in items]


def test_status_sorts_the_open_issues(repo):
    st = status.snapshot(repo, True, ISSUES, PRS, repo="acme/demo", areas=["messages"])
    assert st.issues_read and st.set_up
    assert _nums(st.run) == [1]
    assert _nums(st.maps) == [2] and st.maps[0].detail == "2 open decisions"
    assert _nums(st.specs) == [3] and st.specs[0].detail == "no tickets yet"
    assert _nums(st.ready) == [4]
    assert _nums(st.in_progress) == [5]
    assert _nums(st.waiting) == [6, 7]
    assert _nums(st.to_triage) == [8, 9]
    assert _nums(st.planned) == [10] and st.planned[0].detail == "ticket"
    assert _nums(st.prs) == [13] and "claude/build-99" in st.prs[0].detail


def test_brand_new_means_no_code_of_its_own(repo):
    # The repo fixture holds only the profile and a README.
    (repo / ".github/workflows").mkdir(parents=True)
    (repo / ".github/workflows/workflow-kit.yml").write_text("x")
    (repo / "docs/agents").mkdir(parents=True)
    (repo / "docs/agents/domain.md").write_text("x")
    (repo / "CLAUDE.md").write_text("x")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "set-up")
    assert status.snapshot(repo, True).brand_new
    (repo / "src").mkdir()
    (repo / "src/app.py").write_text("x")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "code")
    st = status.snapshot(repo, True)
    assert not st.brand_new and st.own_files == 1
    # A README in a subdirectory is the project's own.
    (repo / "src/README.md").write_text("x")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "doc")
    assert status.snapshot(repo, True).own_files == 2


def test_status_text_without_issues_says_so(repo):
    out = status.text(status.snapshot(repo, False))
    assert "NOT set up" in out and "brand new" in out and "not read" in out


def test_status_text_lists_each_group(repo):
    out = status.text(status.snapshot(repo, True, ISSUES, PRS, repo="acme/demo"))
    for words in ["Unattended run in progress: 1", "Maps: 1", "Ready build tickets: 1", "#10 Rename Save to Done [ticket]", "New issues to sort: 2"]:
        assert words in out, words


def test_status_cli_reads_files(repo, tmp_path):
    (tmp_path / "i.json").write_text(json.dumps(ISSUES))
    (tmp_path / "p.json").write_text(json.dumps(PRS))
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo)}
    p = subprocess.run(
        [sys.executable, str(CLI), "status", "--issues", str(tmp_path / "i.json"), "--prs", str(tmp_path / "p.json"), "--json"],
        cwd=repo, env=env, capture_output=True, text=True,
    )
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["set_up"] and [i["number"] for i in out["ready"]] == [4]


def test_status_says_unknown_when_github_gave_no_sub_issue_counts(repo):
    issues = [
        _issue(1, "A map", ["wayfinder:map"]),
        _issue(2, "Spec: one", ["spec"]),
        _issue(3, "Spec: two", ["spec"], sub_issues_summary={"total": 3, "completed": 3}),
    ]
    st = status.snapshot(repo, True, issues, [])
    assert "unknown" in st.maps[0].detail
    assert "unknown" in st.specs[0].detail
    assert st.specs[1].detail == "0 of 3 tickets open"


def test_a_parent_issue_is_listed_with_the_specs_not_to_sort(repo):
    issues = [_issue(1, "Epic", sub_issues_summary={"total": 2, "completed": 0}), _issue(2, "Epic two", ["enhancement"], sub_issues_summary={"total": 1, "completed": 0})]
    st = status.snapshot(repo, True, issues, [])
    assert _nums(st.specs) == [1, 2] and st.specs[0].detail.startswith("parent issue")
    assert st.to_triage == []


def test_a_ready_ticket_still_labelled_needs_triage_is_not_to_sort(repo):
    issues = [_issue(1, "Fix it", ["needs-triage", "ready-for-agent"], body="## Blocked by\n\nNone")]
    st = status.snapshot(repo, True, issues, [])
    assert _nums(st.ready) == [1] and st.to_triage == []


@pytest.mark.parametrize("name", ["agents.py", "context.ts", "security.js", "src/README.md"])
def test_code_named_like_boilerplate_is_the_project_s_own(repo, name):
    f = repo / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("x")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "code")
    assert status.snapshot(repo, True).own_files == 1


def test_status_text_outside_a_git_checkout(tmp_path):
    st = status.snapshot(tmp_path, False)
    assert st.own_files == -1 and not st.brand_new and "unknown" in status.text(st)


# The first-message hook ---------------------------------------------------


def _first(repo, prompt, session=None, env=None):
    ev = {"prompt": prompt, "session_id": session or uuid.uuid4().hex}
    _, out, _ = run_hook("context", ev, repo, {"TMPDIR": str(repo.parent), **(env or {})})
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


def test_first_message_of_an_attended_session_brings_the_guided_start(repo):
    session = uuid.uuid4().hex
    assert "guided start" in _first(repo, "hi", session)
    assert _first(repo, "let's add an export", session) == ""  # only the first message


def test_a_flow_request_as_first_message_still_counts_as_the_first(repo):
    (repo / ".claude/workflow/flow.md").write_text("# The flow\n")
    session = uuid.uuid4().hex
    assert "The flow" in _first(repo, "build #12", session)
    assert "guided start" not in _first(repo, "thanks, what next?", session)
    session = uuid.uuid4().hex
    _first(repo, "/next", session)
    assert "guided start" not in _first(repo, "hello", session)


def test_a_path_is_not_a_command(repo):
    assert "guided start" in _first(repo, "/home/user/app.py crashes on start")


@pytest.mark.parametrize("prompt", ["/grill-me my pitch", "/start", "/compact"])
def test_a_command_as_first_message_skips_it(repo, prompt):
    assert "guided start" not in _first(repo, prompt)


def test_a_flow_request_brings_the_flow_not_the_menu(repo):
    flow = repo / ".claude/workflow/flow.md"
    flow.write_text("# The flow\n")
    ctx = _first(repo, "build #12")
    assert "The flow" in ctx and "guided start" not in ctx


def test_never_in_ticket_or_conductor_sessions(repo):
    for role in ("ticket", "conductor"):
        assert _first(repo, "hi", env={"WORKFLOW_ROLE": role}) == ""
    git(repo, "checkout", "-qb", "claude/build-7")
    assert _first(repo, "hi") == ""


def test_the_profile_can_turn_it_off(repo):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text().replace('repo = "acme/demo"', 'repo = "acme/demo"\nguided_start = false'))
    assert _first(repo, "hi") == ""


def test_guided_start_must_be_a_boolean(tmp_path):
    data = json.loads(json.dumps(BASE_PROFILE))
    data["project"]["guided_start"] = "yes"
    with pytest.raises(ProfileError):
        parse(data, tmp_path)
    data["project"]["guided_start"] = False
    assert parse(data, tmp_path).guided_start is False


def test_start_for_once_per_session(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert context.start_for("hello", "s-1") == context.START
    assert context.start_for("hello", "s-1") is None
    assert context.start_for("/next", "s-2") is None
    assert context.start_for("hello", "s-2") is None  # the command was the first message


# The skill and the docs ---------------------------------------------------


def _skill():
    return (KIT / "skills/start/SKILL.md").read_text()


def test_the_start_skill_is_one_claude_may_start():
    text = _skill()
    head = text.split("---", 2)[1]
    assert "name: start" in head and "disable-model-invocation" not in head


def test_the_skill_uses_choices_and_the_status_command():
    text = _skill()
    assert "AskUserQuestion" in text and "WF status --fetch" in text
    for path in ("Quick ticket", "Find the cause first", "Spec", "Map", "Add to an existing issue"):
        assert f"**{path}**" in text, path


def test_the_skill_writes_the_marker_status_reads():
    text = _skill()
    line = next(x.strip() for x in text.splitlines() if "workflow:item" in x and "<!--" in x)
    for p in status.PATHS:
        assert status.item_path(line.replace("<ticket|diagnose|spec|map>", p)) == p


def test_the_flow_offers_handovers_and_commits_the_docs():
    flow = (KIT / "docs/flow.md").read_text()
    assert "`start` skill" in flow and "**Handovers.**" in flow
    assert "Commit what the session wrote" in flow and "**The gate.**" in flow
    assert "triaged to `ready-for-agent`" in flow

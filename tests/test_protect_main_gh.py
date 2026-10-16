"""#67: "Protect `main`" automatically on the owner's computer, with `gh`
(the `upgrade-setup` skill's local path, #38).

Seam 2: the guard's existing decisions on the exact commands the skill runs,
through `decide()` with the profile on disk, as the guard suites do. The
request bodies are the ones `workflow protection --protect` builds, written
where the skill writes them. Every command here is data passed to `decide`;
none is run, and nothing is sent to GitHub.

Seam 4: the skill's wording, read from its file as the kit-release tests read
skills, and the README's and `docs/enforcement.md`'s.
"""

import json
import os
import re
from pathlib import Path

import pytest

from workflow import protection
from workflow.guard import decide
from workflow.profile import load

KIT = Path(__file__).resolve().parents[1]
SKILL = KIT / "skills/upgrade-setup/SKILL.md"
REPO = {"full_name": "acme/demo", "default_branch": "main", "allow_merge_commit": False, "allow_auto_merge": False}
WF = "python3 -B .claude/workflow/bin/workflow.py"


def _toml(ruleset):
    line = "" if ruleset is None else f"ruleset = {'true' if ruleset else 'false'}\n"
    return f"""
[project]
name = "demo"
repo = "acme/demo"
base_branch = "main"
{line}
[guard]
deploy_commands = ["scripts/deploy.sh"]
"""


def on_disk(root: Path, ruleset):
    """The project with its profile, and the request bodies the skill writes."""
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(_toml(ruleset))
    (root / ".workflow").mkdir(exist_ok=True)
    ruleset_req, merge_req = protection.protect("main", REPO, ["test"])
    (root / ".workflow/ruleset-request.json").write_text(json.dumps(ruleset_req.body))
    (root / ".workflow/merge-request.json").write_text(json.dumps(merge_req.body))
    (root / ".workflow/repo.json").write_text(json.dumps(REPO))
    return load(root)


@pytest.fixture(autouse=True)
def _session_env(monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


# The profile as the skill meets it: solo mode, or outside it (`true`, or left out).
PROFILES = {"solo": False, "protected": True, "unset": None}


@pytest.fixture(params=list(PROFILES))
def prof(request, tmp_path):
    return on_disk(tmp_path, PROFILES[request.param])


@pytest.fixture
def solo(tmp_path):
    return on_disk(tmp_path, False)


def act(profile, cmd, role="attended", mode=None, branch="feature"):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(profile.root)}
    if mode is not None:
        ev["permission_mode"] = mode
    return decide(ev, profile, role, profile.root, branch)


# The commands, exactly as the skill gives them (with acme/demo and main filled in).
POST = "gh api -X POST repos/acme/demo/rulesets --input .workflow/ruleset-request.json"
PATCH = "gh api -X PATCH repos/acme/demo --input .workflow/merge-request.json"
READS = [
    "gh auth status",
    "gh api repos/acme/demo > .workflow/repo.json",
    "gh api --paginate --slurp 'repos/acme/demo/rulesets?includes_parents=true' > .workflow/ruleset-list.json",
    "gh api repos/acme/demo/rulesets/42 > .workflow/ruleset-42.json",
    "gh api --paginate --slurp 'repos/acme/demo/commits/main/check-runs?per_page=100' > .workflow/check-runs.json",
    "gh api --paginate --slurp 'repos/acme/demo/commits/main/status?per_page=100' > .workflow/status.json",
    f"{WF} protection --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base main --json",
    f"{WF} protection --checks-ran .workflow/check-runs.json --statuses .workflow/status.json"
    " --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base main --json",
    f"{WF} protection --protect --repo .workflow/repo.json --base main --check test --json > .workflow/protect.json",
]


def test_the_bodies_are_the_protect_requests_in_order():
    ruleset_req, merge_req = protection.protect("main", REPO, ["test"])
    assert (ruleset_req.method, ruleset_req.path) == ("POST", "repos/acme/demo/rulesets")
    assert (merge_req.method, merge_req.path) == ("PATCH", "repos/acme/demo")
    # The skill's commands send exactly these, and name them the same way.
    assert f"-X {ruleset_req.method} {ruleset_req.path} " in POST
    assert PATCH.startswith(f"gh api -X {merge_req.method} {merge_req.path} ")


# ---------- the ruleset POST: asked when someone is asked ----------


@pytest.mark.parametrize("mode", [None, "default", "acceptEdits", "auto"])
def test_the_ruleset_post_is_asked_in_an_attended_session(prof, mode):
    assert act(prof, POST, mode=mode).action == "ask"


# ---------- the merge settings and the reads: not refused ----------


@pytest.mark.parametrize("cmd", [PATCH, *READS])
def test_the_patch_and_the_reads_are_not_refused(prof, cmd):
    d = act(prof, cmd)
    assert d.action == "allow", (cmd, d.reason)


# ---------- the POST is refused where nobody is asked ----------


@pytest.mark.parametrize("mode", ["bypassPermissions", "dontAsk"])
def test_the_ruleset_post_is_refused_in_modes_that_never_ask_naming_the_mode(prof, mode):
    asked = act(prof, POST)
    d = act(prof, POST, mode=mode)
    assert d.action == "deny"
    assert d.reason.startswith(asked.reason)
    extra = d.reason[len(asked.reason):]
    assert f"`{mode}`" in extra and "would have asked" in extra
    assert "switch the permission mode" in extra


@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_the_ruleset_post_is_refused_in_ticket_and_conductor_sessions(prof, role):
    assert act(prof, POST, role=role, branch="claude/build-1").action == "deny"


# ---------- seam 4: the skill's wording ----------


def _text():
    return SKILL.read_text(encoding="utf-8")


def _protect_part():
    text = _text()
    return text[text.index("# Protect `main`"):text.index("# Set up unattended runs")]


def _section(title):
    m = re.search(rf"^## [^\n]*{re.escape(title)}[^\n]*\n(.*?)(?=^#{{1,2}} |\Z)", _text(), re.M | re.S)
    assert m, f"no section {title!r}"
    return m.group(1)


def test_the_automatic_path_no_longer_comes_later():
    where = _section("Where things are")
    assert "An automatic path with `gh` comes in a later release" not in _text()
    assert "the automatic path with `gh`, come in a later release" not in _text()
    assert "`gh`" in where and "automatic" in where.lower()


def test_the_local_paths_conditions_and_the_other_ways():
    which = _section("Which way")
    # The three conditions, each read before anything is tried.
    assert "`CLAUDE_CODE_REMOTE`" in which
    assert "`gh auth status`" in which
    assert "`permissions.admin`" in which
    # Cloud sessions always take the clicks, and never try the API.
    assert "A cloud session always takes the guided clicks" in which
    assert "never tries the API" in which
    # `gh` missing or signed out: the clicks, with how to sign in.
    assert "`gh auth login`" in which
    # Not an admin: the ready message, before anything is tried.
    assert "message for the owner" in which and "before anything is tried" in which
    text = _text()
    assert text.index("## 1. Admin first") < text.index("## Which way") < text.index("## 2. Read what is there")


def test_existing_rulesets_are_read_back_first_with_no_edit_in_solo_mode():
    auto = _section("The automatic path")
    assert "step 2" in auto and "first" in auto
    first = _section("Read what is there")
    assert "never edits an existing ruleset" in first
    assert "nothing is created" in first.lower()


def test_the_one_confirmation_by_experience_with_the_checks_that_ran():
    auto = _section("The automatic path")
    assert "Protect your main branch: GitHub will then refuse changes that skip a pull request or a failing test" in auto
    assert "**Do it now**" in auto and "**Not now**" in auto
    assert "developer" in auto.lower() and "merge settings" in auto
    # The checks that ran, for ticking, passing ones ticked by default.
    assert "--checks-ran" in auto and "--paginate --slurp" in auto
    assert "Passing ones are ticked by default" in auto
    assert "`ci.required_checks`" in auto and "ticked by default too" in auto
    assert "multiSelect" in auto
    # Claude Code's prompt, said up front as expected.
    assert "Claude Code will ask you to approve the GitHub command" in auto and "expected" in auto


def test_a_refusal_naming_the_mode_is_answered_with_the_mode_switch():
    auto = _section("The automatic path")
    assert "switch the permission mode and try again" in auto
    assert "never retry" in auto.lower()


def test_the_order_ruleset_merge_settings_read_back_flip_pull_request():
    auto = _section("The automatic path")
    order = [
        "1. **The requests:** `WF protection --protect",
        "2. **The ruleset:** `gh api -X POST repos/<repo>/rulesets --input .workflow/ruleset-request.json`",
        "3. **The merge settings:** `gh api -X PATCH repos/<repo> --input .workflow/merge-request.json`",
        "4. **The read-back:** step 4",
        "5. **The pull request that leaves solo mode:** step 5",
    ]
    at = [auto.index(s) for s in order]
    assert at == sorted(at), order
    flip = _section("Leave solo mode")
    assert "<!-- workflow:required-checks -->" in flip
    assert "never removing a name the profile already lists" in flip
    assert "`ci.required_checks`" in flip


def test_a_failure_says_what_was_done_and_left_and_gives_the_clicks_for_the_rest():
    auto = _section("The automatic path")
    assert "what was done and what's left" in auto
    assert "the clicks for the rest" in auto
    assert "Never retry an edit to the ruleset" in auto
    assert "only ever stricter" in auto


def test_the_skill_still_names_no_kit_issue_numbers():
    assert not re.search(r"#\d", _text())


# ---------- the docs ----------


def test_the_readme_says_the_kit_makes_the_ruleset_with_the_clicks_as_the_fallback():
    readme = (KIT / "README.md").read_text()
    m = re.search(r"^### Protect `main`\n(.*?)(?=^### )", readme, re.M | re.S)
    assert m
    section = m.group(1)
    assert "ask claude to protect `main`" in section.lower()
    assert "`gh`" in section and "own computer" in section and "makes the ruleset" in section
    assert "guided clicks" in section and "cloud" in section
    assert "fallback" in section


def test_enforcement_doc_section_one_says_the_kit_makes_the_ruleset():
    doc = (KIT / "docs/enforcement.md").read_text()
    m = re.search(r"^## 1\.[^\n]*\n(.*?)(?=^## )", doc, re.M | re.S)
    assert m
    one = m.group(1)
    assert "the kit makes this ruleset" in one
    assert "`gh`" in one

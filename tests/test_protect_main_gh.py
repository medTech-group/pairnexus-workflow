"""#67: "Protect `main`" automatically on the owner's computer, with `gh`
(the `upgrade-setup` skill's automatic path, #38), and #68's "Require these
checks", which adds checks to the ruleset with a `PUT`.

Seam 2: the guard's existing decisions on the exact commands the skill runs,
through `decide()` with the profile on disk, as the guard suites do. The
request bodies are the ones `workflow protection --protect` builds, written
where the skill writes them. Every command here is data passed to `decide`;
none is run, and nothing is sent to GitHub. The skill's wording is tested in
tests/test_upgrade_setup.py.
"""

import json
import os
import re
from pathlib import Path

import pytest

from conftest import KIT
from workflow import protection
from workflow.guard import decide
from workflow.profile import load

SKILL = KIT / "skills/upgrade-setup/SKILL.md"
REPO = {"full_name": "acme/demo", "default_branch": "main", "allow_merge_commit": False, "allow_auto_merge": False}
WF = "python3 -B .claude/workflow/bin/workflow.py"
# The kit's own ruleset on the base branch, as GET repos/<repo>/rulesets/<id> returns it.
KIT_RULESET = {
    **protection.protect("main", REPO)[0].body,
    "id": 42,
    "source_type": "Repository",
    "source": "acme/demo",
}


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
    # #68: the kit's ruleset as GET returns it, and the request adding the checks.
    (root / ".workflow/ruleset.json").write_text(json.dumps(KIT_RULESET))
    checks_req = protection.require_checks(KIT_RULESET, ["test"])
    (root / ".workflow/checks-request.json").write_text(json.dumps(checks_req.body))
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
# #68: "Require these checks" adds them to the ruleset protecting the base branch.
PUT = "gh api -X PUT repos/acme/demo/rulesets/42 --input .workflow/checks-request.json"
READS = [
    "gh auth status --hostname github.com",
    "gh api repos/acme/demo",
    "gh api repos/acme/demo > .workflow/repo.json",
    "gh api --paginate --slurp 'repos/acme/demo/rulesets?includes_parents=true' > .workflow/ruleset-list.json",
    "gh api repos/acme/demo/rulesets/42 > .workflow/ruleset-42.json",
    "gh api --paginate --slurp 'repos/acme/demo/commits/main/check-runs?per_page=100' > .workflow/check-runs.json",
    "gh api --paginate --slurp 'repos/acme/demo/commits/main/status?per_page=100' > .workflow/status.json",
    f"{WF} protection --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base main --json",
    f"{WF} protection --checks-ran .workflow/check-runs.json --statuses .workflow/status.json"
    " --rulesets .workflow/rulesets.json --repo .workflow/repo.json --base main --json",
    f"{WF} protection --protect --repo .workflow/repo.json --base main --check test --json > .workflow/protect.json",
    # #68's reads: the one ruleset in full, and the request built from it.
    "gh api repos/acme/demo/rulesets/42 > .workflow/ruleset.json",
    f"{WF} protection --require-checks .workflow/ruleset.json --check test --json > .workflow/checks.json",
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


# ---------- #68: the require-checks PUT ----------


def test_the_put_is_the_require_checks_request():
    req = protection.require_checks(KIT_RULESET, ["test"])
    assert (req.method, req.path) == ("PUT", "repos/acme/demo/rulesets/42")
    assert PUT.startswith(f"gh api -X {req.method} {req.path} ")
    rule = next(r for r in req.body["rules"] if r["type"] == "required_status_checks")
    assert rule["parameters"]["strict_required_status_checks_policy"] is True


@pytest.mark.parametrize("ruleset", [True, None], ids=["protected", "unset"])
@pytest.mark.parametrize("mode", [None, "default", "acceptEdits", "auto"])
def test_the_put_is_asked_in_an_attended_session_outside_solo_mode(tmp_path, ruleset, mode):
    assert act(on_disk(tmp_path, ruleset), PUT, mode=mode).action == "ask"


def test_the_put_is_refused_in_solo_mode(solo):
    assert act(solo, PUT).action == "deny"


@pytest.mark.parametrize("ruleset", [True, None], ids=["protected", "unset"])
@pytest.mark.parametrize("mode", ["bypassPermissions", "dontAsk"])
def test_the_put_is_refused_in_modes_that_never_ask_naming_the_mode(tmp_path, ruleset, mode):
    profile = on_disk(tmp_path, ruleset)
    asked = act(profile, PUT)
    d = act(profile, PUT, mode=mode)
    assert d.action == "deny"
    assert d.reason.startswith(asked.reason)
    extra = d.reason[len(asked.reason):]
    assert f"`{mode}`" in extra and "would have asked" in extra
    assert "switch the permission mode" in extra


@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_the_put_is_refused_in_ticket_and_conductor_sessions(prof, role):
    assert act(prof, PUT, role=role, branch="claude/build-1").action == "deny"


# ---------- the commands tested are the ones the skill gives ----------


def test_every_gh_command_the_skill_runs_is_one_tested_here():
    """Each `gh` command in the skill, with <repo> and <base> filled in, is one
    whose decision is tested above, so a changed command can't slip past."""
    text = SKILL.read_text(encoding="utf-8")
    given = re.findall(r"`(gh (?:api|auth status)[^`]*)`", text)
    tested = {POST, PATCH, PUT, *READS}
    # `gh api` alone names the tool, not a command.
    fill = {"<repo>": "acme/demo", "<base>": "main", "<id>": "42"}
    commands = [c for c in given if c != "gh api"]
    for k, v in fill.items():
        commands = [c.replace(k, v) for c in commands]
    assert POST.replace("acme/demo", "<repo>") in given and PATCH.replace("acme/demo", "<repo>") in given
    assert PUT.replace("acme/demo", "<repo>").replace("/42 ", "/<id> ") in given
    for c in commands:
        assert c in tested, c

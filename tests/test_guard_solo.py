"""Solo mode (#45): with `ruleset = false`, an attended session's git pushes that
touch the base branch are refused (deny, never ask), worded by experience.

Every command here is data passed to `decide` or the hook; none is run.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import BASE_PROFILE, git

from workflow.guard import decide
from workflow.profile import load

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
MAIN_LINE = "`main` is the project's main branch"


def bash(cmd, cwd=None):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if cwd is not None:
        ev["cwd"] = str(cwd)
    return ev


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
    """The profile written where a session reads it, then loaded as the hook does."""
    (root / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (root / ".claude/workflow/profile.toml").write_text(_toml(ruleset))
    return load(root)


@pytest.fixture(autouse=True)
def _session_env(monkeypatch):
    """No experience or role from the session running the suite."""
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)


@pytest.fixture
def solo(tmp_path):
    return on_disk(tmp_path, False)


def act(profile, cmd, role="attended", branch="feature", cwd=None):
    return decide(bash(cmd, cwd), profile, role, profile.root, branch)


# ---------- refused: they touch the base branch ----------

REFUSED = [
    "git push origin main",
    "git push origin HEAD:main",
    "git push origin feature:refs/heads/main",
    "git push -u origin main",
    "git -C . push origin main",
    "git push -f origin main",
    "git push --force origin main",
    "git push --force-with-lease origin main",
    "git push --force-with-lease=main:abc origin main",
    "git push --force-if-includes origin main",
    "git push -uf origin main",
    "git push origin +main",
    "git push origin +HEAD:main",
    "git push origin :main",
    "git push --delete origin main",
    "git push origin --delete main",
    "git push -d origin main",
    "git push --mirror origin",
    "git push --all origin",
    "git push --branches origin",
    "git push --prune origin feature",
    "git push origin :",
    "git push --mirr origin",
    "git -c remote.origin.mirror=true push origin feature",
    "git -c remote.pushdefault=backup push",
    "git config remote.origin.mirror true",
    "git config remote.pushDefault backup",
    "git remote add --mirror=push backup ../b.git",
    "git send-pack ../b.git",
    "cd sub && git push origin main",
    "echo hi; git push origin main",
    "sh -c 'git push origin main'",
]


@pytest.mark.parametrize("cmd", REFUSED)
def test_refused_in_solo_mode(cmd, solo):
    d = act(solo, cmd)
    assert d.action == "deny", cmd
    assert "Without GitHub's protection set up, the kit doesn't allow that" in d.reason, cmd


@pytest.mark.parametrize("cmd", ["git push", "git push origin", "git push origin HEAD", "git push origin @", "git push -f origin HEAD"])
def test_push_from_the_base_branch_itself(cmd, solo):
    assert act(solo, cmd, branch="main").action == "deny", cmd


@pytest.fixture
def tracking_main(tmp_path):
    """A repository on `feature`, whose upstream is the remote's `main`."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "t")
    (work / "README.md").write_text("x")
    git(work, "add", ".")
    git(work, "commit", "-qm", "init")
    git(work, "remote", "add", "origin", str(remote))
    git(work, "push", "-q", "origin", "main")
    git(work, "checkout", "-qb", "feature", "--track", "origin/main")
    return work


@pytest.mark.parametrize("cmd", ["git push", "git push -f"])
def test_bare_push_with_the_base_as_upstream(cmd, tracking_main):
    prof = on_disk(tracking_main, False)
    d = decide(bash(cmd, tracking_main), prof, "attended", tracking_main, "feature")
    assert d.action == "deny", cmd


# ---------- refused because it might be the base branch ----------

CANT_TELL = [
    ('git push origin "$BRANCH"', "feature"),
    ("git push origin HEAD:$TARGET", "feature"),
    ("git push origin @", None),
    ("git push origin HEAD", None),
    ("git push", None),
    ("git push -f origin @", None),
    ("git push origin @{u}", "feature"),
    ("git push origin 'refs/heads/*:refs/heads/*'", "feature"),
    ("git push origin {feature,main}", "feature"),
    ('cd "$X" && git push origin HEAD', "feature"),
    ("git --git-dir=../other/.git push origin HEAD", "feature"),
    ("git push --stdin origin", "feature"),
]


@pytest.mark.parametrize("cmd,branch", CANT_TELL)
def test_cant_tell_is_refused_and_says_push_by_name(cmd, branch, solo):
    d = act(solo, cmd, branch=branch)
    assert d.action == "deny", cmd
    assert "push the branch by name" in d.reason, cmd


# ---------- still asked, or allowed ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git push -f origin my-branch",
        "git push --force origin my-branch",
        "git push --force-with-lease origin my-branch",
        "git push origin +my-branch",
        "git push origin --delete my-branch",
        "git push --delete origin my-branch",
        "git push origin :my-branch",
    ],
)
def test_feature_branch_force_and_delete_still_asked(cmd, solo):
    assert act(solo, cmd).action == "ask", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin feature",
        "git push -u origin feature",
        "git push origin HEAD",
        "git push --dry-run origin main",
        "git push --tags",
        "git status",
        "git pull origin main",
    ],
)
def test_ordinary_work_still_allowed(cmd, solo):
    assert act(solo, cmd).action == "allow", cmd


# ---------- unchanged outside solo mode ----------

ALL_FORMS = REFUSED + [c for c, _ in CANT_TELL] + ["git push -f origin my-branch", "git push origin --delete my-branch", "git push origin feature"]


@pytest.mark.parametrize("cmd", ALL_FORMS)
def test_ruleset_true_and_unset_give_todays_decisions(cmd, tmp_path):
    protected = on_disk(tmp_path / "a", True)
    unset = on_disk(tmp_path / "b", None)
    a, b = act(protected, cmd), act(unset, cmd)
    assert (a.action, a.reason) == (b.action, b.reason), cmd
    assert a.action != "deny", cmd  # attended outside solo mode is never refused outright
    assert "Without GitHub's protection" not in a.reason


def test_ruleset_true_still_asks_for_the_base_branch(tmp_path):
    for ruleset in (True, None):
        prof = on_disk(tmp_path / str(ruleset), ruleset)
        for cmd in ("git push origin main", "git push -f origin main", "git push --mirror origin", "git push origin :main"):
            assert act(prof, cmd).action == "ask", (ruleset, cmd)


@pytest.mark.parametrize("role", ["ticket", "conductor"])
@pytest.mark.parametrize("cmd", ALL_FORMS)
def test_ticket_and_conductor_unchanged_in_solo_mode(role, cmd, tmp_path):
    solo = on_disk(tmp_path / "solo", False)
    unset = on_disk(tmp_path / "unset", None)
    branch = "claude/build-1"
    a = decide(bash(cmd), solo, role, solo.root, branch)
    b = decide(bash(cmd), unset, role, unset.root, branch)
    assert (a.action, a.reason) == (b.action, b.reason), cmd


# ---------- the reason's wording ----------


def _reason(profile, cmd="git push origin main"):
    d = act(profile, cmd)
    assert d.action == "deny"
    return d.reason


@pytest.mark.parametrize("cmd", ["git push origin main", 'git push origin "$B"'])
def test_reason_for_new_to_building(cmd, solo, monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "new")
    r = _reason(solo, cmd)
    assert MAIN_LINE in r
    assert f"run it yourself in your own terminal: `{cmd}`" in r
    assert 'Offer "Protect `main`" as a choice, with "Not now"' in r


def test_reason_for_a_developer(solo, monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    r = _reason(solo)
    assert MAIN_LINE not in r
    assert "This would change `main` directly" in r
    assert "run it yourself in your own terminal: `git push origin main`" in r
    assert 'Offer "Protect `main`" as a choice, with "Not now"' in r


def test_unknown_experience_is_worded_as_new(solo):
    assert MAIN_LINE in _reason(solo)


def test_experience_from_the_local_file_and_the_profile(tmp_path):
    prof = on_disk(tmp_path, False)
    (tmp_path / ".workflow").mkdir()
    (tmp_path / ".workflow/experience").write_text("developer\n")
    assert MAIN_LINE not in _reason(prof)
    (tmp_path / ".workflow/experience").unlink()
    text = (tmp_path / ".claude/workflow/profile.toml").read_text().replace("ruleset = false", 'ruleset = false\nexperience = "developer"')
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    assert MAIN_LINE not in _reason(load(tmp_path))


def test_wording_never_changes_what_is_refused(solo, monkeypatch):
    for level in ("new", "developer"):
        monkeypatch.setenv("WORKFLOW_EXPERIENCE", level)
        assert [act(solo, c).action for c in REFUSED] == ["deny"] * len(REFUSED), level
        assert act(solo, "git push -f origin my-branch").action == "ask", level


def test_hand_command_with_backticks_is_still_one_code_span(solo, monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXPERIENCE", "developer")
    cmd = "git push origin `git branch --show-current`:main"
    r = _reason(solo, cmd)
    assert f"`` {cmd} ``" in r


def test_another_base_branch_is_named(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(_toml(False).replace('"main"', '"trunk"'))
    prof = load(tmp_path)
    d = act(prof, "git push origin trunk")
    assert d.action == "deny" and "This would change `trunk` directly" in d.reason and 'Protect `trunk`' in d.reason
    assert act(prof, "git push origin main").action == "allow"


# ---------- end to end through the hook CLI ----------


def run_hook(event, cwd, env_extra):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd), **env_extra}
    for k in ("WORKFLOW_ROLE", "WORKFLOW_EXPERIENCE"):
        if k not in env_extra:
            env.pop(k, None)
    p = subprocess.run([sys.executable, str(CLI), "hook", "guard"], input=json.dumps(event), capture_output=True, text=True, cwd=cwd, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)["hookSpecificOutput"] if p.stdout.strip() else None


@pytest.fixture
def solo_repo(repo):
    """The conftest repo (on `main`), in solo mode."""
    (repo / ".claude/workflow/profile.toml").write_text(_toml(False))
    return repo


@pytest.mark.parametrize("cmd", ["git push origin main", "git push --force origin main", "git push --mirror origin", "git push", 'git push origin "$B"'])
def test_hook_denies_in_solo_mode(cmd, solo_repo):
    out = run_hook(bash(cmd, solo_repo), solo_repo, {"WORKFLOW_ROLE": "attended"})
    assert out["permissionDecision"] == "deny", cmd
    assert out["permissionDecisionReason"].startswith("[workflow guard, attended session] ")
    assert 'Protect `main`' in out["permissionDecisionReason"]


def test_hook_by_experience_and_role(solo_repo):
    ev = bash("git push origin main", solo_repo)
    dev = run_hook(ev, solo_repo, {"WORKFLOW_ROLE": "attended", "WORKFLOW_EXPERIENCE": "developer"})
    assert dev["permissionDecision"] == "deny" and MAIN_LINE not in dev["permissionDecisionReason"]
    # The branch fallback: on `main`, with no WORKFLOW_ROLE, the session is attended.
    new = run_hook(ev, solo_repo, {})
    assert new["permissionDecision"] == "deny" and MAIN_LINE in new["permissionDecisionReason"]
    ticket = run_hook(ev, solo_repo, {"WORKFLOW_ROLE": "ticket"})
    assert ticket["permissionDecision"] == "deny" and "Protect" not in ticket["permissionDecisionReason"]


def test_hook_still_asks_for_a_feature_branch_and_outside_solo_mode(solo_repo):
    out = run_hook(bash("git push -f origin my-branch", solo_repo), solo_repo, {"WORKFLOW_ROLE": "attended"})
    assert out["permissionDecision"] == "ask"
    (solo_repo / ".claude/workflow/profile.toml").write_text(_toml(True))
    out = run_hook(bash("git push origin main", solo_repo), solo_repo, {"WORKFLOW_ROLE": "attended"})
    assert out["permissionDecision"] == "ask"

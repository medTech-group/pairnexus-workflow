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
MAIN_LINE = "`main` is the branch the project's work comes together on"


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
    """No experience, role or git config from the machine running the suite
    (the guard reads push settings in every scope)."""
    monkeypatch.delenv("WORKFLOW_EXPERIENCE", raising=False)
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


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


# ---------- review round 1 ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git push -f origin my-branch && git push origin main",
        "scripts/deploy.sh; git push origin main",
        "git -c core.pager=less log; git push --mirror origin",
        "git push origin :old-branch; git push origin +main",
    ],
)
def test_an_earlier_ask_never_hides_a_later_refusal(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "M=true git --config-env=remote.origin.mirror=M push origin feature",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=remote.origin.mirror GIT_CONFIG_VALUE_0=true git push origin feature",
        "GIT_CONFIG_PARAMETERS=\"'remote.origin.mirror'='true'\" git push origin feature",
        "GIT_DIR=../other/.git git push origin HEAD",
        "export GIT_DIR=../other/.git; git push origin HEAD",
        "env GIT_WORK_TREE=../other git push origin HEAD",
        "git -c alias.p='push origin main' p",
        "git -c alias.p=push p origin main",
        "git config push.default matching",
        "git config remote.origin.push refs/heads/main:refs/heads/main",
        "git config --add remote.origin.push HEAD",
    ],
)
def test_config_from_the_environment_aliases_and_push_settings(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


@pytest.mark.parametrize("cmd", ["git config push.default simple", "git config user.name x", "git -c core.pager=less log"])
def test_harmless_config_still_as_before(cmd, solo, tmp_path):
    unset = on_disk(tmp_path / "unset", None)
    assert act(solo, cmd).action == act(unset, cmd).action, cmd


@pytest.fixture
def on_feature(tracking_main):
    """`feature`, tracking the remote's `feature` (not `main`)."""
    git(tracking_main, "push", "-q", "origin", "feature:feature")
    git(tracking_main, "branch", "-q", "-u", "origin/feature")
    return tracking_main


@pytest.mark.parametrize(
    "setting",
    [
        ("push.default", "matching"),
        ("remote.origin.mirror", "true"),
        ("remote.origin.push", "refs/heads/main:refs/heads/main"),
        ("remote.origin.push", "+refs/heads/*:refs/heads/*"),
    ],
)
@pytest.mark.parametrize("cmd", ["git push", "git push origin"])
def test_bare_push_reads_the_settings_on_disk(setting, cmd, on_feature):
    prof = on_disk(on_feature, False)
    assert decide(bash(cmd, on_feature), prof, "attended", on_feature, "feature").action == "allow"
    git(on_feature, "config", *setting)
    assert decide(bash(cmd, on_feature), prof, "attended", on_feature, "feature").action == "deny", setting


def test_bare_push_upstream_setting_naming_the_base(on_feature):
    prof = on_disk(on_feature, False)
    git(on_feature, "config", "push.default", "upstream")
    git(on_feature, "config", "branch.feature.merge", "refs/heads/main")
    git(on_feature, "update-ref", "-d", "refs/remotes/origin/main")
    assert decide(bash("git push", on_feature), prof, "attended", on_feature, "feature").action == "deny"


def test_persisted_alias_that_pushes(on_feature):
    prof = on_disk(on_feature, False)
    git(on_feature, "config", "alias.p", "push origin main")
    assert decide(bash("git p", on_feature), prof, "attended", on_feature, "feature").action == "deny"
    git(on_feature, "config", "alias.l", "log --oneline")
    assert decide(bash("git l", on_feature), prof, "attended", on_feature, "feature").action == "allow"


def test_forced_dry_run_is_still_asked(solo):
    assert act(solo, "git push -n -f origin main").action == "ask"


def test_reason_names_a_force_only_when_the_base_is_forced(solo):
    assert "force-push" not in act(solo, "git push origin +feature main").reason
    assert "force-push" in act(solo, "git push origin feature +main").reason
    assert "force-push" in act(solo, "git push -f origin main").reason


def test_reason_starts_with_the_plain_sentence(solo):
    first = act(solo, "git push origin main").reason.splitlines()[0]
    assert first == "This would change `main` directly. Without GitHub's protection set up, the kit doesn't allow that."


# ---------- the explorer, round 1 ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "printf main | xargs git push origin",
        "xargs -n1 git push origin < branches.txt",
        'alias gp="git push origin main"; gp',
        "git push --prune origin",
    ],
)
def test_destinations_from_stdin_shell_aliases_and_prune(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


@pytest.mark.parametrize("cmd", ["git push --forc origin feature", "git push --force-w origin feature", "git push --prune origin feature"])
def test_abbreviated_force_or_prune_of_a_feature_branch_still_asked(cmd, solo):
    assert act(solo, cmd).action == "ask", cmd


def test_abbreviated_force_of_the_base_branch_refused(solo):
    assert act(solo, "git push --forc origin main").action == "deny"


def test_bare_push_on_the_base_branch_never_advises_pushing_it(solo):
    r = act(solo, "git push", branch="main").reason
    assert "git push origin main`" not in r.split("run it yourself")[0]


@pytest.mark.parametrize(
    "cmd,secret",
    [
        ("git push https://u:ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/acme/demo.git main", "ghp_abcdefghijklmnopqrstuvwxyz0123456789"),
        ("GH_TOKEN=s3cr3tvalue git push origin main", "s3cr3tvalue"),
        ("GITHUB_TOKEN=abc123xyz git push origin main", "abc123xyz"),
    ],
)
def test_hand_command_hides_credentials(cmd, secret, solo):
    r = act(solo, cmd).reason
    assert secret not in r and "run it yourself in your own terminal" in r


def test_a_very_long_command_is_not_repeated(solo):
    cmd = "echo " + "x" * 5000 + "; git push origin main"
    r = act(solo, cmd).reason
    assert len(r) < 2000 and 'Protect `main`' in r


def test_multi_line_hand_command_has_no_trailing_space(solo):
    r = act(solo, "cd sub\ngit push origin main").reason
    assert all(line == line.rstrip() for line in r.splitlines())


@pytest.mark.parametrize(
    "cmd,word",
    [('git push origin "$B"', "variable"), ("git push origin 'feat*'", "glob"), ("git push origin {a,main}", "brace list"), ("git push origin @{u}", "`@`")],
)
def test_cant_tell_names_what_it_saw(cmd, word, solo):
    r = act(solo, cmd).reason
    assert word in r and "a variable, `@`, a glob or a brace list" not in r


@pytest.mark.parametrize("cmd", ["git config remote.origin.mirror true", "git config push.default matching", "git remote add --mirror=push b ../b.git"])
def test_settings_are_worded_as_setting_up_a_later_push(cmd, solo):
    first = act(solo, cmd).reason.splitlines()[0]
    assert "later push" in first and "directly" not in first


def test_matching_refspec_quoted_with_its_remote(solo):
    assert "git push origin :" in act(solo, "git push origin :").reason


# ---------- review round 2 ----------

TODAY = {  # attended, outside solo mode: today's decision, pinned
    "git push origin main": "ask",
    "git push -f origin main": "ask",
    "git push --mirror origin": "ask",
    "git push origin :main": "ask",
    "git config remote.origin.mirror true": "ask",
    "git push -f origin my-branch": "ask",
    "git push origin --delete my-branch": "ask",
    "git push origin feature": "allow",
    'git push origin "$BRANCH"': "allow",
    "git push origin @": "allow",
    "git config push.default matching": "allow",
    "printf main | xargs git push origin": "allow",
}


@pytest.mark.parametrize("cmd,expected", list(TODAY.items()))
def test_todays_attended_decisions_pinned(cmd, expected, tmp_path):
    for ruleset in (True, None):
        prof = on_disk(tmp_path / str(ruleset), ruleset)
        assert act(prof, cmd, branch=None if "@" in cmd else "feature").action == expected, (ruleset, cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "git -c include.path=/tmp/m.cfg push origin",
        "git -c includeIf.onbranch:feature.path=/tmp/m.cfg push",
        "git -c include.path=/tmp/a.cfg p",
        "HOME=/tmp/h git push",
        "export XDG_CONFIG_HOME=/tmp/x; git push origin feature",
        "P='push origin main' git --config-env=alias.p=P p",
        "P='push origin main' git --config-env alias.p=P p",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0='push origin main' git p",
        "git -c remote.pushdefault=backup push",
    ],
)
def test_config_from_includes_home_and_the_environment(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


@pytest.mark.parametrize("value", ["true", "yes", "on", "1", "push"])
def test_mirror_on_disk_for_a_remote_with_capitals(value, on_feature):
    prof = on_disk(on_feature, False)
    git(on_feature, "remote", "add", "Backup", str(on_feature.parent / "remote.git"))
    git(on_feature, "config", "remote.Backup.mirror", value)
    assert decide(bash("git push Backup", on_feature), prof, "attended", on_feature, "feature").action == "deny", value


def test_another_remotes_mirror_doesnt_refuse_a_bare_push_to_origin(on_feature):
    prof = on_disk(on_feature, False)
    git(on_feature, "remote", "add", "backup", str(on_feature.parent / "remote.git"))
    git(on_feature, "config", "remote.backup.mirror", "true")
    assert decide(bash("git push", on_feature), prof, "attended", on_feature, "feature").action == "allow"
    git(on_feature, "config", "remote.pushDefault", "backup")
    assert decide(bash("git push", on_feature), prof, "attended", on_feature, "feature").action == "deny"


def test_alias_chains_and_shell_aliases_on_disk(on_feature):
    prof = on_disk(on_feature, False)
    git(on_feature, "config", "alias.q", "push origin main")
    git(on_feature, "config", "alias.p", "q")
    git(on_feature, "config", "alias.s", "!f(){ git $1 origin main; }; f")
    for cmd in ("git p", "git s push"):
        assert decide(bash(cmd, on_feature), prof, "attended", on_feature, "feature").action == "deny", cmd


def test_bare_force_push_of_a_feature_branch_still_asked(on_feature):
    prof = on_disk(on_feature, False)
    assert decide(bash("git push -f", on_feature), prof, "attended", on_feature, "feature").action == "ask"


@pytest.mark.parametrize(
    "cmd",
    ["git config --unset push.default", "git config --unset-all remote.origin.push", "git config unset push.default", "git push origin user@fix"],
)
def test_safer_settings_and_at_signs_in_names_not_refused(cmd, solo):
    assert act(solo, cmd).action != "deny", cmd


def test_stdin_and_pushdefault_wording(solo):
    assert "pushes every branch" not in act(solo, "git push --s origin feature").reason
    assert "This would change `main` directly" not in act(solo, "git -c remote.pushdefault=backup push").reason


def test_authorization_header_masked(solo):
    cmd = 'git -c http.extraHeader="Authorization: Bearer tok_abcdef123456" push origin main'
    assert "tok_abcdef123456" not in act(solo, cmd).reason


# ---------- the explorer, round 2 ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git checkout main && git push",
        "git switch main; git push origin HEAD",
        "git checkout main && git push origin @",
        "git switch -C main && git push -u origin HEAD",
        "git checkout main && git push -f",
        "git checkout -q main && git push origin HEAD",
    ],
)
def test_switching_to_the_base_branch_then_pushing(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


@pytest.mark.parametrize("cmd", ["git checkout -b fix && git push -u origin HEAD", "git switch other && git push origin other", "git checkout main -- README.md && git push origin HEAD"])
def test_switching_to_another_branch_then_pushing_it(cmd, solo):
    assert act(solo, cmd).action == "allow", cmd


@pytest.mark.parametrize("cmd", ['git config alias.pm "push origin main" && git pm', "git config alias.pm '!git push origin main'"])
def test_writing_an_alias_that_pushes(cmd, solo):
    assert act(solo, cmd).action == "deny", cmd


def test_harmless_alias_write(solo):
    assert act(solo, "git config alias.st status").action == "allow"


def test_reason_wording_round_2(solo):
    r = act(solo, "git push origin HEAD", branch=None).reason
    assert "guard" not in r
    r = act(solo, "git config push.default matching").reason
    assert "base branch" not in r
    r = act(solo, "git push", branch="main").reason
    assert "bare push" not in r and "make a branch" not in r.split("\n")[1]
    r = act(solo, 'git push origin "$B"').reason
    assert "own directory" not in r and "name the branch" in r


def test_prune_of_tags_only_is_asked(solo):
    assert act(solo, "git push --prune --tags origin").action == "ask"


def test_many_bare_pushes_stay_within_the_budget(on_feature):
    import time

    prof = on_disk(on_feature, False)
    cmd = "; ".join(["git push"] * 400 + ["git zz"] * 400 + ["git push origin main"])
    t = time.monotonic()
    d = decide(bash(cmd, on_feature), prof, "attended", on_feature, "feature")
    assert d.action == "deny"
    assert time.monotonic() - t < 6  # the git lookups are made once per directory


def test_a_slow_guard_in_solo_mode_refuses(solo_repo, monkeypatch, capsys):
    import time

    from workflow import cli

    monkeypatch.setattr(cli, "GUARD_BUDGET", 0.2)
    monkeypatch.setattr(cli, "_STARTED", time.monotonic())  # so the timer itself runs out
    monkeypatch.setattr(cli.guard_mod, "decide", lambda *a, **k: time.sleep(5))
    monkeypatch.setenv("WORKFLOW_ROLE", "attended")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(solo_repo))
    monkeypatch.chdir(solo_repo)
    assert cli._hook_guard(bash("git push origin main", solo_repo)) == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "ran out of time" in out["permissionDecisionReason"]

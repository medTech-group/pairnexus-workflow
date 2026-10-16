"""The third review round's guard findings, each pinned (numbers are the findings').

Every command here is data passed to `decide`; none is run.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import BASE_PROFILE, git

from workflow import roles
from workflow.guard import decide, segments
from workflow.profile import parse

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def bash(cmd, cwd=None):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if cwd is not None:
        ev["cwd"] = str(cwd)
    return ev


def act(profile, root, cmd, role="ticket", branch="claude/build-1", cwd=None, from_env=True):
    return decide(bash(cmd, cwd), profile, role, root, branch, role_from_env=from_env).action


def each_role(profile, root, cmd, branch="claude/build-1"):
    return tuple(act(profile, root, cmd, role, branch) for role in ("ticket", "conductor", "attended"))


FIRM_DENY = ("deny", "deny", "ask")


# ---------- 1. push settings ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git -c remote.origin.mirror=true push origin claude/build-1",
        "git -c remote.pushdefault=backup push",
        "git -c remote.origin.skipDefaultUpdate=true push origin claude/build-1",
        "git config remote.origin.mirror true",
        "git config --add remote.backup.mirror true",
        "git config remote.pushDefault backup",
        "git config set remote.pushdefault backup",
        "git config remote.origin.skipdefaultupdate true",
        "git remote add --mirror=push backup ../b.git",
    ],
)
def test_push_settings_in_every_role(cmd, profile, tmp_path):
    assert each_role(profile, tmp_path, cmd) == FIRM_DENY, cmd


def test_reading_push_settings_and_other_config_is_fine(profile, tmp_path):
    for cmd in ("git config remote.origin.mirror", "git config --get remote.pushdefault", "git config user.name x", "git remote add backup ../b.git"):
        assert act(profile, tmp_path, cmd, role="attended", branch="main") == "allow", cmd
    assert act(profile, tmp_path, "git config user.name x", role="ticket") == "allow"


# ---------- 2. find's start paths are trees ----------


def test_find_start_paths_are_trees(profile, tmp_path):
    for cmd in (
        "find .github -name '*.yml' -exec sed -i 's/a/b/' {} +",
        "find .github -name ci.yml -delete",
        "find -L .claude -name '*.json' -delete",
        "find .github -name '*.yml' -exec sh -c 'cat {}' \\;",
        "cd .github && find . -delete",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    for cmd in (
        "find .github -name '*.yml' -exec grep -l foo {} +",
        "find .github -name '*.yml'",
        "find src -name '*.pyc' -delete",
        "find . -name '*.pyc' -delete",
        "find . -name '*.py' -exec rm {} +",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd


# ---------- 3. sensitive data by indirection ----------


def test_sensitive_data_read_by_indirection(profile, tmp_path):
    (tmp_path / "body.md").write_text("Patient MRN-123456 failed")
    (tmp_path / "ok.md").write_text("Record 77fc6d9d failed <!-- workflow:agent -->")
    for cmd in (
        "cat body.md | gh pr comment 12 --body-file -",
        "gh pr comment 12 --body-file - < body.md",
        'B=$(cat body.md); gh pr comment 12 --body "$B"',
        'B=$(<body.md); gh pr comment 12 --body "$B"',
        'gh pr comment 12 --body "$(cat body.md)"',
        "head -n 5 body.md | gh issue comment 3 --body-file -",
        "cat body.md | gh api repos/acme/demo/issues/3/comments -F body=@-",
    ):
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd
        assert act(profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd
        assert act(profile, tmp_path, cmd.replace("body.md", "ok.md"), role="conductor", branch="main") == "allow", cmd
    # Without a post, reading the file is nobody's business.
    assert act(profile, tmp_path, "cat body.md | wc -l", role="conductor", branch="main") == "allow"


# ---------- 4. GraphQL in a variable ----------


def test_ticket_graphql_query_from_a_variable_counts_as_a_file(profile, tmp_path):
    for cmd in (
        'gh api graphql -f query="$Q"',
        "gh api graphql -f query=\"`cat q.graphql`\"",
        'gh api graphql -f query="$(cat q.graphql)"',
        'gh api graphql -F query="${Q}"',
    ):
        d = decide(bash(cmd), profile, "ticket", tmp_path, "claude/build-1")
        assert d.action == "deny" and "GraphQL" in d.reason, cmd
    for cmd in (
        "gh api graphql -f query='query { viewer { login } }'",
        "gh api graphql -f query='mutation($id: ID!) { addComment(input: {subjectId: $id, body: \"x <!-- workflow:agent -->\"}) { clientMutationId } }' -f id=I_1",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd  # no GraphQL in ticket sessions (0.1.1)


def test_dangerous_mutation_found_in_the_whole_command_and_files_it_reads(profile, tmp_path):
    (tmp_path / "q.graphql").write_text('mutation { updateRef(input: {refId: "x", oid: "y", force: true}) { clientMutationId } }')
    (tmp_path / "ok.graphql").write_text("query { viewer { login } }")
    for cmd in (
        'Q=$(cat q.graphql); gh api graphql -f query="$Q"',
        "Q='mutation { deleteRef(input: {refId: \"x\"}) { clientMutationId } }'; gh api graphql -f query=\"$Q\"",
        'gh api graphql -f query="$(cat q.graphql)"',
    ):
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd
        assert act(profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd
    assert act(profile, tmp_path, 'Q=$(cat ok.graphql); gh api graphql -f query="$Q"', role="conductor", branch="main") == "allow"


# ---------- 5-6. deploys run by an interpreter; shell options ----------


@pytest.fixture
def deploy_profile(tmp_path):
    data = json.loads(json.dumps(BASE_PROFILE))
    data["guard"]["deploy_commands"] = ["scripts/deploy.sh", "scripts/deploy.py", "scripts/release.js", "scripts/deploy-poc.sh", "terraform apply"]
    return parse(data, tmp_path)


@pytest.mark.parametrize(
    "cmd",
    [
        "python3 scripts/deploy.py",
        "python scripts/deploy.py --stage poc",
        "python3.11 -u scripts/deploy.py",
        "node scripts/release.js",
        "uv run scripts/deploy.py",
        "uv run --with requests python scripts/deploy.py",
        "cd scripts && python3 deploy.py",
        "npx tsx scripts/release.js",
        "deno run -A scripts/release.js",
        "bun scripts/release.js",
        "bun run scripts/release.js",
        "bash -o pipefail scripts/deploy-poc.sh",
        "bash +o posix scripts/deploy-poc.sh",
        "sh -O extglob scripts/deploy.sh",
        "bash --rcfile x.rc scripts/deploy.sh",
        "bash --init-file x.rc -e ./scripts/deploy.sh poc",
    ],
)
def test_deploys_run_by_an_interpreter(cmd, deploy_profile, tmp_path):
    assert act(deploy_profile, tmp_path, cmd) == "deny", cmd
    assert act(deploy_profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd


def test_interpreters_running_other_scripts_are_fine(deploy_profile, tmp_path):
    for cmd in (
        "python3 scripts/check.py",
        "cat scripts/deploy.py",
        "python3 -m pytest tests/test_deploy.py",
        "uv pip install requests",
        "node -e 'console.log(1)'",
        "bash -o pipefail scripts/test.sh",
        "deno fmt scripts/release.js",
    ):
        assert act(deploy_profile, tmp_path, cmd) == "allow", cmd


# ---------- 7. branch switches when the role comes from the branch ----------


@pytest.fixture
def switch_repo(repo):
    """main, then claude/build-1 checked out (so @{-1} is main), with
    claude/build-2, develop, a tag, a second commit and an origin remote."""
    (repo / "a.txt").write_text("1")
    git(repo, "add", "a.txt")
    git(repo, "commit", "-qm", "two")
    git(repo, "branch", "claude/build-2")
    git(repo, "branch", "develop")
    git(repo, "tag", "v1")
    git(repo, "remote", "add", "origin", str(repo / "nowhere.git"))
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "update-ref", "refs/remotes/origin/feature-x", "HEAD")
    git(repo, "checkout", "-qb", "claude/build-1")
    return repo


def branch_role(profile, repo, cmd):
    return decide(bash(cmd, repo), profile, "ticket", repo, "claude/build-1", role_from_env=False)


def test_checkout_switches_out_of_the_pattern_are_denied(profile, switch_repo):
    sha = git(switch_repo, "rev-parse", "HEAD").strip()
    for cmd in (
        "git checkout main",
        "git checkout develop",
        "git checkout -",
        "git checkout @{-1}",
        "git checkout --detach",
        f"git checkout {sha}",
        "git checkout v1",
        "git checkout origin/main",
        "git checkout HEAD~1",
        "git checkout feature-x",  # git's guess from origin/feature-x
        "git checkout main --",
        "git switch -",
        "git switch --detach claude/build-2",
        "git checkout -t origin/main",
    ):
        d = branch_role(profile, switch_repo, cmd)
        assert d.action == "deny" and "stay on" in d.reason, cmd
    for cmd in (
        "git checkout claude/build-2",
        "git checkout HEAD",
        "git checkout README.md",
        "git checkout -- README.md",
        "git checkout .",
        "git checkout main -- a.txt",
        "git checkout -b claude/build-3 origin/main",
        "git switch claude/build-2",
    ):
        assert branch_role(profile, switch_repo, cmd).action == "allow", cmd
    # Only when the role comes from the branch name.
    assert decide(bash("git checkout main", switch_repo), profile, "ticket", switch_repo, "claude/build-1").action == "allow"


def test_branch_rename_out_of_the_pattern_is_denied(profile, switch_repo):
    for cmd in ("git branch -m main2", "git branch -M claude/build-1 develop2", "git branch --move x"):
        assert branch_role(profile, switch_repo, cmd).action == "deny", cmd
    for cmd in ("git branch -m claude/build-9", "git branch -M claude/build-1 claude/build-10", "git branch --list"):
        assert branch_role(profile, switch_repo, cmd).action == "allow", cmd


def test_upstream_must_have_the_branchs_own_name_in_ticket_role(profile, switch_repo):
    for from_env in (True, False):
        for cmd in ("git branch -u origin/main", "git branch --set-upstream-to=origin/claude/build-2", "git branch -uorigin/develop", "git branch --set-upstream-to main"):
            d = decide(bash(cmd, switch_repo), profile, "ticket", switch_repo, "claude/build-1", role_from_env=from_env)
            assert d.action == "deny" and "upstream" in d.reason, (cmd, from_env)
        for cmd in ("git branch -u origin/claude/build-1", "git branch --set-upstream-to=origin/claude/build-1", "git branch -u origin/claude/build-2 claude/build-2"):
            assert decide(bash(cmd, switch_repo), profile, "ticket", switch_repo, "claude/build-1", role_from_env=from_env).action == "allow", cmd
    assert decide(bash("git branch -u origin/main", switch_repo), profile, "attended", switch_repo, "claude/build-1").action == "allow"


# ---------- 8. the default branch ----------


def test_default_branch_changes_in_every_role(profile, tmp_path):
    (tmp_path / "repo.json").write_text('{"default_branch": "dev"}')
    (tmp_path / "desc.json").write_text('{"description": "x"}')
    for cmd in (
        "gh repo edit --default-branch dev",
        "gh repo edit acme/demo --default-branch=dev",
        "gh api -X PATCH repos/acme/demo --input repo.json",
        "gh api -X PATCH repos/acme/demo --input - <<'EOF'\n{\"default_branch\": \"dev\"}\nEOF",
    ):
        assert each_role(profile, tmp_path, cmd) == FIRM_DENY, cmd
    assert act(profile, tmp_path, "gh api -X PATCH repos/acme/demo --input desc.json", role="conductor", branch="main") == "allow"


# ---------- 9. more writers ----------


def test_more_writers_of_protected_paths(profile, tmp_path):
    (tmp_path / "bad.mbox").write_text(
        "From abc Mon Sep 17 00:00:00 2001\nSubject: x\n---\n"
        "diff --git a/.claude/settings.json b/.claude/settings.json\n--- a/.claude/settings.json\n+++ b/.claude/settings.json\n@@ -1 +1 @@\n-a\n+b\n"
    )
    (tmp_path / "good.mbox").write_text(
        "From abc Mon Sep 17 00:00:00 2001\nSubject: x\n---\ndiff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    for cmd in (
        "ed -s .claude/settings.json <<'EOF'\n1d\nw\nEOF",
        "ex -sc '%s/a/b/|x' .github/workflows/ci.yml",
        "vim -c '%s/a/b/' -c wq .claude/settings.json",
        "vi +wq .env",
        "nvim --cmd 'set x' -c wq .github/CODEOWNERS",
        "awk -i inplace '{print}' .github/workflows/ci.yml",
        "gawk -i inplace -v x=1 '{print}' .env",
        "git am bad.mbox",
        "git am < bad.mbox",
        "git am",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    for cmd in ("awk '{print}' .github/workflows/ci.yml", "git am good.mbox", "git am --abort", "git am --continue", "vim -c wq src/x.py", "awk -i inplace '{print}' src/x.py"):
        assert act(profile, tmp_path, cmd) == "allow", cmd


def test_in_place_edits_of_files_a_search_finds(profile, tmp_path):
    for cmd in (
        "grep -rl foo . | xargs sed -i 's/foo/bar/'",
        "grep -rl foo | xargs sed -i 's/foo/bar/'",
        "sed -i 's/foo/bar/' $(grep -rl foo .)",
        "sed -i 's/foo/bar/' `git ls-files`",
        "git ls-files | xargs sed -i s/a/b/",
        "git grep -l foo | xargs sed -i s/a/b/",
        "find . -name '*.yml' | xargs perl -pi -e 's/a/b/'",
        "rg -l foo | xargs sed -i s/a/b/",
        "grep -rl foo .github | xargs sed -i s/a/b/",
        "echo .github/workflows/ci.yml | xargs sed -i s/a/b/",
    ):
        d = decide(bash(cmd), profile, "ticket", tmp_path, "claude/build-1")
        assert d.action == "deny", cmd
    d = decide(bash("grep -rl foo . | xargs sed -i 's/foo/bar/'"), profile, "ticket", tmp_path, "claude/build-1")
    assert "name the files" in d.reason
    for cmd in (
        "grep -rl foo src | xargs sed -i 's/foo/bar/'",
        "sed -i 's/foo/bar/' $(grep -rl foo src/)",
        "git ls-files src | xargs sed -i s/a/b/",
        "git grep -l foo -- src | xargs sed -i s/a/b/",
        "cd src && grep -rl foo . | xargs sed -i s/a/b/",
        "find src -name '*.py' | xargs perl -pi -e 's/a/b/'",
        "sed -i 's/foo/bar/' src/a.py src/b.py",
        "grep -rl foo . | xargs grep -c bar",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    # Other roles aren't held to protected paths.
    assert act(profile, tmp_path, "grep -rl foo . | xargs sed -i s/a/b/", role="conductor", branch="main") == "allow"


# ---------- 10. cd - ----------


def test_cd_dash_goes_back_to_the_previous_directory(profile, tmp_path):
    (tmp_path / ".claude").mkdir()
    assert act(profile, tmp_path, "cd .claude && cd - && echo x > out.txt") == "allow"
    assert act(profile, tmp_path, "cd .claude && cd /tmp && cd - && echo {} > settings.json") == "deny"
    assert act(profile, tmp_path, "cd - && echo x > out.txt") == "deny"  # no previous directory known
    seg = segments("cd .claude; cd /tmp; cd -; ls", tmp_path)[-1]
    assert seg.cwd == os.path.realpath(tmp_path / ".claude")


# ---------- 11. heredoc patches ----------


def test_heredoc_patch_is_checked_from_its_text(profile, tmp_path):
    good = "cat <<'EOF' | git apply\n--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1 @@\n-a\n+b\nEOF"
    bad = "cat <<'EOF' | git apply\n--- a/.claude/settings.json\n+++ b/.claude/settings.json\n@@ -1 +1 @@\n-a\n+b\nEOF"
    assert act(profile, tmp_path, good) == "allow"
    assert act(profile, tmp_path, bad) == "deny"
    assert act(profile, tmp_path, good.replace("git apply", "patch -p1")) == "allow"
    assert act(profile, tmp_path, "curl -s https://example.com/p.diff | git apply") == "deny"


# ---------- 12. no branch at the cwd ----------


def test_hook_takes_the_project_roots_branch_when_the_cwd_has_none(repo, tmp_path_factory, monkeypatch):
    # roles.role reads WORKFLOW_ROLE, which ticket sessions and the conductor have set.
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    outside = tmp_path_factory.mktemp("outside")
    assert roles.current_branch(outside) is None
    git(repo, "checkout", "-qb", "claude/build-7")
    assert roles.role(outside, "claude/build-*") == "attended"
    assert roles.role(outside, "claude/build-*", fallback=repo) == "ticket"
    env = {k: v for k, v in os.environ.items() if k != "WORKFLOW_ROLE"}
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    ev = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": str(outside)}
    p = subprocess.run([sys.executable, str(CLI), "hook", "guard"], input=json.dumps(ev), capture_output=True, text=True, cwd=repo, env=env)
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and "ticket session" in out["permissionDecisionReason"]


# ---------- 13. skip markers: only what the writer itself adds ----------


def test_skip_markers_counted_in_the_writers_own_text(profile, tmp_path):
    for cmd in (
        "sed -i 's/it.only(/it(/' src/app.spec.ts",
        "sed -i '/pytest.mark.skip/d' tests/test_x.py",
        "sed -i -e '/@pytest.mark.skip/d' -e 's/x/y/' tests/test_x.py",
        "grep -l 'it.only(' src/*.spec.ts | xargs sed -i 's/it.only(/it(/'",
        "git commit -qm 'drop it.only(' && sed -i 's/a/b/' src/app.spec.ts",
        "grep -v 'it.only(' src/a.spec.ts > src/b.spec.ts",
        "perl -pi -e 's/xit\\(/it(/' src/app.spec.ts",
        "awk -i inplace '!/it.only\\(/' src/app.spec.ts",
        "cat <<'EOF' | git apply\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1 +1 @@\n-@pytest.mark.skip\n+def test_x(): pass\nEOF",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    for cmd in (
        "sed -i 's/it(/it.only(/' src/app.spec.ts",
        "sed -i '1i import pytest; pytest.skip(\"x\")' tests/test_x.py",
        "echo 'it.only(\"x\")' >> src/a.spec.ts",
        "printf 'xit(1)' | tee -a src/a.spec.ts",
        "perl -pi -e 's/it\\(/fit(/' src/app.spec.ts",
        "cat <<'EOF' | git apply\n--- a/tests/test_x.py\n+++ b/tests/test_x.py\n@@ -1 +1 @@\n-def test_x(): pass\n+@pytest.mark.skip\nEOF",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd


# ---------- 14. gh allow-list ----------


def test_gh_ticket_allow_list_additions(profile, tmp_path):
    for cmd in ("gh run download 5", "gh run cancel 5", "gh workflow list", "gh workflow view ci.yml", "gh status", "gh issue close 3", "gh issue reopen 3", "gh pr close 3"):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    for cmd in ("gh workflow run deploy.yml", "gh workflow enable ci.yml", "gh run delete 5"):
        assert act(profile, tmp_path, cmd) == "deny", cmd


# ---------- 15. the current branch by substitution ----------


def test_current_branch_by_substitution_is_the_current_branch(profile, tmp_path):
    for cmd in (
        "git push origin $(git branch --show-current)",
        "git push -u origin `git rev-parse --abbrev-ref HEAD`",
        'git push origin "$(git symbolic-ref --short HEAD)"',
        "git push origin HEAD:$(git branch --show-current)",
    ):
        assert act(profile, tmp_path, cmd) == "allow", cmd
        assert act(profile, tmp_path, cmd, role="ticket", branch="main") == "deny", cmd
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd
    assert act(profile, tmp_path, "git push origin $(git rev-parse HEAD)") == "deny"


# ---------- 16. git clean; paths outside the project ----------


def test_git_clean(profile, tmp_path):
    for cmd in ("git clean -n", "git clean --dry-run -d", "git clean -nfd .claude", "git clean -fd", "git clean -fd src/", "git clean -f -e .env"):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    for cmd in ("git clean -fd .claude", "git clean -fdx", "git clean -fX", "git clean -fd .github/workflows"):
        assert act(profile, tmp_path, cmd) == "deny", cmd


def test_paths_outside_the_project_are_never_protected(profile, tmp_path):
    for cmd in ("echo x > /tmp/x/.env", "cp a /tmp/y/.env", "echo x > ../sibling/.env", "mkdir -p /tmp/z/.claude"):
        assert act(profile, tmp_path, cmd) == "allow", cmd
    w = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x/.env", "content": "A=1"}}
    assert decide(w, profile, "ticket", tmp_path, "claude/build-1").action == "allow"
    w = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x/test_a.py", "content": "@pytest.mark.skip"}}
    assert decide(w, profile, "ticket", tmp_path, "claude/build-1").action == "allow"
    # A tree that holds the project still holds its protected paths.
    assert act(profile, tmp_path, "rm -rf ..") == "deny"


# ---------- 25. the global git config ----------


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    (h / ".config/git").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
    return h


def test_global_git_config_writes_are_denied(profile, tmp_path, home, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    cmds = [
        "echo '[alias] p = push' >> ~/.gitconfig",
        "echo x >> $HOME/.gitconfig",
        'echo x >> "${HOME}/.gitconfig"',
        "cp x ~/.config/git/config",
        "sed -i s/a/b/ ~/.config/git/config",
        "tee -a ~/.config/git/attributes",
        "ln -s ~/.gitconfig link",
        "rm -rf ~/.config",
        "python3 -c \"open('" + str(home / ".gitconfig") + "', 'a').write('x')\"",
    ]
    for cmd in cmds:
        for role in ("ticket", "conductor"):
            assert act(profile, root, cmd, role=role, branch="main") == "deny", (role, cmd)
        assert act(profile, root, cmd, role="attended", branch="main") == "allow", cmd
    xdg = tmp_path / "xdg"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    assert act(profile, root, 'echo x > "$XDG_CONFIG_HOME/git/config"', role="conductor", branch="main") == "deny"
    gc = tmp_path / "gc"
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gc))
    assert act(profile, root, f"echo x > {gc}", role="ticket") == "deny"
    for path in (home / ".gitconfig", home / ".config/git/config", gc):
        w = {"tool_name": "Write", "tool_input": {"file_path": str(path), "content": "[alias]"}}
        assert decide(w, profile, "conductor", root, "main").action == "deny", path
        assert decide(w, profile, "attended", root, "main").action == "allow", path
    # git config itself is judged by its key.
    assert act(profile, root, "git config --global user.name x", role="ticket") == "allow"
    assert act(profile, root, "git config --global alias.p push", role="ticket") == "deny"
    assert act(profile, root, "cat ~/.gitconfig", role="ticket") == "allow"
    # After `cd ~` the directory is unknown: a relative .gitconfig could be it.
    assert act(profile, root, "cd ~ && echo x >> .gitconfig", role="conductor", branch="main") == "deny"
    assert act(profile, root, "cd ~ && echo x >> notes.txt", role="conductor", branch="main") == "allow"

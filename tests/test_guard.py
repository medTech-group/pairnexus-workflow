"""The guard against the ways a session could break the never-list (bypass attempts included)."""

import pytest

from workflow.guard import decide


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


@pytest.mark.parametrize(
    "cmd",
    [
        "git push origin main",
        "git push origin HEAD:main",
        "git push origin feature:refs/heads/main",
        "git -C . push origin main",
        "git -c push.default=current push origin main",
        "git push --force origin claude/build-1",
        "git push -f",
        "git push -uf origin claude/build-1",
        "git push --force-with-lease origin claude/build-1",
        "git push origin +claude/build-1",
        "git push origin :claude/build-1",
        "git push --delete origin claude/build-1",
        "git push --mirror origin",
        "cd repo && git push origin main",
        "echo hi; git push origin main",
        "sh -c 'git push origin main'",
        "bash -c \"cd x && git push --force\"",
        "FOO=1 git push origin main",
        "sudo git push origin main",
        "timeout 60 git push origin main",
        "echo `git push origin main`",
        "x=$(git push --force origin y)",
        "eval git push origin main",
        "git push origin main 2>&1 | tail -3",
        "python3 -c \"import subprocess; subprocess.run('git push origin main', shell=True)\"",
        "gh api -X PATCH repos/acme/demo/git/refs/heads/main -f sha=abc",
        "gh api --method DELETE repos/acme/demo/branches/main/protection",
        "gh api -X POST repos/acme/demo/rulesets -f name=x",
    ],
)
def test_ticket_cannot_push_to_base_or_force(cmd, profile, tmp_path):
    d = decide(bash(cmd), profile, "ticket", tmp_path, "claude/build-1")
    assert d.action == "deny", cmd


def test_bare_push_on_base_branch_denied(profile, tmp_path):
    assert decide(bash("git push"), profile, "ticket", tmp_path, "main").action == "deny"
    assert decide(bash("git push"), profile, "ticket", tmp_path, "claude/build-1").action == "allow"


@pytest.mark.parametrize(
    "cmd",
    [
        "git push -u origin claude/build-1",
        "git push origin claude/build-1",
        "git status && git log --oneline -3",
        "gh api repos/acme/demo/pulls/3",
        "gh api -X PUT repos/acme/demo/pulls/3/merge -f merge_method=merge",
        "echo 'git push origin main' > notes.txt",
        "python -m pytest tests -q",
    ],
)
def test_ticket_allowed(cmd, profile, tmp_path):
    assert decide(bash(cmd), profile, "ticket", tmp_path, "claude/build-1").action == "allow", cmd


def test_attended_is_asked_not_denied(profile, tmp_path):
    assert decide(bash("git push origin main"), profile, "attended", tmp_path, "x").action == "ask"
    assert decide(bash("scripts/deploy.sh prod"), profile, "attended", tmp_path, "x").action == "ask"


def test_conductor_may_deploy_but_never_force(profile, tmp_path):
    assert decide(bash("scripts/deploy.sh staging"), profile, "conductor", tmp_path, "main").action == "allow"
    assert decide(bash("git push --force origin x"), profile, "conductor", tmp_path, "x").action == "deny"


@pytest.mark.parametrize(
    "cmd",
    ["scripts/deploy.sh staging", "./scripts/deploy.sh", "cd infra && terraform apply -auto-approve", "bash scripts/deploy.sh"],
)
def test_ticket_cannot_deploy(cmd, profile, tmp_path):
    assert decide(bash(cmd), profile, "ticket", tmp_path, "claude/build-1").action == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "rm .claude/settings.json",
        "sed -i 's/guard//' .claude/settings.json",
        "echo '{}' > .claude/settings.json",
        "cat x >> .github/workflows/ci.yml",
        "cp /tmp/x .claude/workflow/bin/workflow/guard.py",
        "git checkout -- .claude/settings.json",
        "tee .env < /tmp/secrets",
    ],
)
def test_ticket_cannot_write_protected_paths_by_shell(cmd, profile, tmp_path):
    assert decide(bash(cmd), profile, "ticket", tmp_path, "claude/build-1").action == "deny", cmd


def test_protected_paths_by_edit_tools(profile, tmp_path):
    for tool, inp in [
        ("Edit", {"file_path": str(tmp_path / ".claude/settings.json"), "old_string": "a", "new_string": "b"}),
        ("Write", {"file_path": ".github/workflows/ci.yml", "content": "x"}),
        ("MultiEdit", {"file_path": "./.claude/agents/x.md", "edits": []}),
        ("Write", {"file_path": "config/.env.production", "content": "x"}),
    ]:
        assert decide({"tool_name": tool, "tool_input": inp}, profile, "ticket", tmp_path, "b").action == "deny", inp
        assert decide({"tool_name": tool, "tool_input": inp}, profile, "attended", tmp_path, "b").action == "allow"
    ok = {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}}
    assert decide(ok, profile, "ticket", tmp_path, "b").action == "allow"


@pytest.mark.parametrize(
    "new",
    [
        "@pytest.mark.skip(reason='flaky')\ndef test_x(): pass",
        "def test_x():\n    pytest.skip('later')",
        "it.skip('works', () => {})",
        "xit('works', () => {})",
        "test('x', () {}, skip: true);",
        "t.Skip(\"later\")",
    ],
)
def test_adding_a_skip_marker_denied(new, profile, tmp_path):
    for path in ("tests/test_x.py", "src/x.test.ts", "test/x_test.dart", "pkg/x_test.go"):
        e = {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": "def test_x(): pass", "new_string": new}}
        assert decide(e, profile, "ticket", tmp_path, "b").action == "deny"


def test_skip_already_there_or_non_test_file_allowed(profile, tmp_path):
    e = {"tool_name": "Edit", "tool_input": {"file_path": "tests/test_x.py", "old_string": "@pytest.mark.skip\ndef a(): 1", "new_string": "@pytest.mark.skip\ndef a(): 2"}}
    assert decide(e, profile, "ticket", tmp_path, "b").action == "allow"
    e = {"tool_name": "Edit", "tool_input": {"file_path": "src/runner.py", "old_string": "", "new_string": "pytest.skip("}}
    assert decide(e, profile, "ticket", tmp_path, "b").action == "allow"
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_y.py").write_text("@pytest.mark.skip\ndef test_a(): 1\n")
    w = {"tool_name": "Write", "tool_input": {"file_path": "tests/test_y.py", "content": "@pytest.mark.skip\ndef test_a(): 2\n"}}
    assert decide(w, profile, "ticket", tmp_path, "b").action == "allow"
    w["tool_input"]["content"] += "@pytest.mark.skip\ndef test_b(): 2\n"
    assert decide(w, profile, "ticket", tmp_path, "b").action == "deny"


def test_github_mcp_writes(profile, tmp_path):
    base = {"tool_name": "mcp__github__create_or_update_file", "tool_input": {"owner": "a", "repo": "d", "path": "x.py", "branch": "main", "content": "x"}}
    assert decide(base, profile, "ticket", tmp_path, "b").action == "deny"
    assert decide(base, profile, "conductor", tmp_path, "b").action == "deny"
    assert decide(base, profile, "attended", tmp_path, "b").action == "ask"
    nobranch = {"tool_name": "mcp__github__push_files", "tool_input": {"files": [{"path": "x"}]}}
    assert decide(nobranch, profile, "ticket", tmp_path, "b").action == "deny"
    ok = {"tool_name": "mcp__github__push_files", "tool_input": {"branch": "claude/build-1", "files": [{"path": "src/x.py"}]}}
    assert decide(ok, profile, "ticket", tmp_path, "b").action == "allow"
    prot = {"tool_name": "mcp__github__push_files", "tool_input": {"branch": "claude/build-1", "files": [{"path": ".github/workflows/ci.yml"}]}}
    assert decide(prot, profile, "ticket", tmp_path, "b").action == "deny"
    merge = {"tool_name": "mcp__github__merge_pull_request", "tool_input": {"pullNumber": 3}}
    assert decide(merge, profile, "ticket", tmp_path, "b").action == "allow"


def test_sensitive_posts(profile, tmp_path):
    post = {"tool_name": "mcp__github__add_issue_comment", "tool_input": {"body": "Patient MRN-123456 failed"}}
    assert decide(post, profile, "ticket", tmp_path, "b").action == "deny"
    assert decide(post, profile, "attended", tmp_path, "b").action == "ask"
    nested = {"tool_name": "mcp__plugin_x_github__issue_write", "tool_input": {"method": "create", "title": "t", "body": "ok", "labels": ["MRN-654321"]}}
    assert decide(nested, profile, "conductor", tmp_path, "b").action == "deny"
    fine = {"tool_name": "mcp__github__add_issue_comment", "tool_input": {"body": "Record 77fc6d9d failed"}}
    assert decide(fine, profile, "ticket", tmp_path, "b").action == "allow"
    other = {"tool_name": "mcp__slack__post", "tool_input": {"body": "MRN-123456"}}
    assert decide(other, profile, "ticket", tmp_path, "b").action == "allow"

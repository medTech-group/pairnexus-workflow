"""The hooks end to end through the CLI, as Claude Code runs them."""

import json
import os
import subprocess
import sys
from pathlib import Path

from workflow import context, gate

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"


def run_hook(name, event, cwd, env_extra=None):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd), **(env_extra or {})}
    env.pop("WORKFLOW_ROLE", None) if "WORKFLOW_ROLE" not in (env_extra or {}) else None
    env.pop("WORKFLOW_EXPERIENCE", None) if "WORKFLOW_EXPERIENCE" not in (env_extra or {}) else None
    p = subprocess.run([sys.executable, str(CLI), "hook", name], input=json.dumps(event), capture_output=True, text=True, cwd=cwd, env=env)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None), p.stderr


def test_guard_hook_by_branch_role(repo):
    from conftest import git

    ev = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": str(repo)}
    code, out, _ = run_hook("guard", ev, repo)
    assert code == 0 and out["hookSpecificOutput"]["permissionDecision"] == "ask"  # on main: attended
    git(repo, "checkout", "-qb", "claude/build-7")
    code, out, _ = run_hook("guard", ev, repo)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "ticket session" in out["hookSpecificOutput"]["permissionDecisionReason"]
    ok = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(repo)}
    code, out, _ = run_hook("guard", ok, repo)
    assert code == 0 and out is None  # never forces "allow"


def test_guard_hook_env_role_wins(repo):
    ev = {"tool_name": "Bash", "tool_input": {"command": "scripts/deploy.sh"}, "cwd": str(repo)}
    _, out, _ = run_hook("guard", ev, repo, {"WORKFLOW_ROLE": "ticket"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    _, out, _ = run_hook("guard", ev, repo, {"WORKFLOW_ROLE": "conductor"})
    assert out is None


def test_hooks_do_nothing_without_a_profile(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    ev = {"tool_name": "Bash", "tool_input": {"command": "git push --force"}, "cwd": str(tmp_path)}
    assert run_hook("guard", ev, tmp_path)[:2] == (0, None)
    assert run_hook("gate", {"last_assistant_message": "hi"}, tmp_path, {"TMPDIR": str(tmp_path)})[:2] == (0, None)


def test_invalid_profile_is_reported_not_silent(repo):
    (repo / ".claude/workflow/profile.toml").write_text("[project]\nname=1\n")
    code, out, err = run_hook("guard", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, repo)
    # Reported, and the hook exits 0 in an attended session (#53): nothing to decide for an `ls`.
    assert code == 0 and out is None and "profile is invalid" in err


def test_gate_hook_only_for_ticket_sessions(repo, tmp_path):
    ev = {"session_id": "s-gate-1", "last_assistant_message": "All done.", "stop_hook_active": False, "cwd": str(repo)}
    iso = {"TMPDIR": str(tmp_path)}
    assert run_hook("gate", ev, repo, iso)[1] is None
    code, out, _ = run_hook("gate", ev, repo, {"WORKFLOW_ROLE": "ticket", **iso})
    assert out["decision"] == "block" and "WORKFLOW-STATUS" in out["reason"]


def test_gate_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    done = "Merged.\n- [x] a\n- [x] b\n- [ ] c because d\nWORKFLOW-STATUS: done"
    assert gate.decide({"session_id": "a", "last_assistant_message": done}) is None
    assert gate.decide({"session_id": "a", "last_assistant_message": "CI running.\nWORKFLOW-STATUS: waiting"}) is None
    assert gate.decide({"session_id": "a", "last_assistant_message": "WORKFLOW-STATUS: done"})  # no checklist
    assert gate.decide({"session_id": "a", "last_assistant_message": "x", "stop_hook_active": True}) is None
    # One nudge per turn (stop_hook_active), every turn, up to a generous safety cap.
    for _ in range(gate.MAX_BLOCKS):
        assert gate.decide({"session_id": "b", "last_assistant_message": "x"})
    assert gate.decide({"session_id": "b", "last_assistant_message": "x"}) is None


def test_gate_reads_the_transcript_when_no_last_message(tmp_path, monkeypatch):
    import json as _j

    monkeypatch.setenv("TMPDIR", str(tmp_path))
    t = tmp_path / "t.jsonl"
    t.write_text(
        _j.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}) + "\n"
        + _j.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "CI running.\nWORKFLOW-STATUS: waiting"}]}}) + "\n"
    )
    assert gate.decide({"session_id": "c", "transcript_path": str(t)}) is None


def test_context_trigger_and_once_per_session(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    flow = tmp_path / "flow.md"
    flow.write_text("THE FLOW")
    assert not context.wants_flow("what's the weather")
    assert not context.wants_flow("see #12")  # a ref without a flow verb
    assert context.wants_flow("implement #146")
    assert context.wants_flow("/next build")
    assert context.wants_flow("/pairnexus-workflow:next")
    assert context.wants_flow("work the doctor map")
    assert context.wants_flow("fix #262")
    assert context.wants_flow("start an unattended run")
    first = context.context_for("work the map #153", "s1", [flow])
    assert "THE FLOW" in first
    again = context.context_for("implement #146", "s1", [flow])
    assert "THE FLOW" not in again and "read it again" in again
    assert context.context_for("hello", "s2", [flow]) is None


def test_context_hook_reads_vendored_flow(repo, tmp_path, monkeypatch):
    (repo / ".claude/workflow/flow.md").write_text("VENDORED FLOW")
    _, out, _ = run_hook("context", {"prompt": "implement #5", "session_id": "ctx-vendored"}, repo, {"TMPDIR": str(tmp_path)})
    assert "VENDORED FLOW" in out["hookSpecificOutput"]["additionalContext"]


def test_repair_hook(repo):
    p = repo / ".claude/workflow/profile.toml"
    p.write_text(p.read_text() + '\n[repair]\ncommands = ["true", "false"]\n')
    _, out, _ = run_hook("repair", {}, repo)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "ok: `true`" in ctx and "exit 1: `false`" in ctx and "role of this session: attended" in ctx


# ---------- failing closed when the role is firm (review round 2, finding 18) ----------


def run_raw(name, raw, cwd, env_extra=None):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd), **(env_extra or {})}
    if "WORKFLOW_ROLE" not in (env_extra or {}):
        env.pop("WORKFLOW_ROLE", None)
    p = subprocess.run([sys.executable, str(CLI), "hook", name], input=raw, capture_output=True, text=True, cwd=cwd, env=env)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None), p.stderr


def test_firm_role_without_a_profile_denies(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    ev = {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(tmp_path)}
    for role in ("ticket", "conductor"):
        code, out, _ = run_hook("guard", ev, tmp_path, {"WORKFLOW_ROLE": role})
        assert code == 0 and out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "the workflow profile is missing" in out["hookSpecificOutput"]["permissionDecisionReason"]
    restore = {"tool_name": "Bash", "tool_input": {"command": "git checkout -- .claude/workflow"}}
    assert run_hook("guard", restore, tmp_path, {"WORKFLOW_ROLE": "ticket"})[:2] == (0, None)
    assert run_hook("guard", ev, tmp_path, {"WORKFLOW_ROLE": "attended"})[:2] == (0, None)


def test_unrecognised_role_is_treated_as_ticket(repo):
    ev = {"tool_name": "Bash", "tool_input": {"command": "scripts/deploy.sh"}, "cwd": str(repo)}
    _, out, _ = run_hook("guard", ev, repo, {"WORKFLOW_ROLE": "tikcet"})
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "ticket session" in reason and "'tikcet' isn't a role" in reason


def test_malformed_event_denied_when_the_role_is_firm(repo, tmp_path):
    for raw in ("not json", "[1, 2]", '"a string"'):
        for role in ("ticket", "conductor"):
            code, out, _ = run_raw("guard", raw, repo, {"WORKFLOW_ROLE": role})
            assert code == 0 and out["hookSpecificOutput"]["permissionDecision"] == "deny", (raw, role)
        assert run_raw("guard", raw, repo)[:2] == (0, None)  # attended: nothing to check, nothing said
    assert run_raw("gate", "not json", repo, {"TMPDIR": str(tmp_path)})[1] is None


def test_guard_hook_starts_from_the_events_cwd(repo):
    (repo / ".claude/x").mkdir()
    ev = {"tool_name": "Bash", "tool_input": {"command": "echo {} > settings.json"}, "cwd": str(repo / ".claude")}
    _, out, _ = run_hook("guard", ev, repo, {"WORKFLOW_ROLE": "ticket"})
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    ev["cwd"] = str(repo)
    assert run_hook("guard", ev, repo, {"WORKFLOW_ROLE": "ticket"})[1] is None


def _run_hook_command(sub, project, event_raw, role=None, tmpdir=None):
    from workflow import vendor

    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    if tmpdir is not None:
        env["TMPDIR"] = str(tmpdir)
    env.pop("WORKFLOW_ROLE", None)
    if role is not None:
        env["WORKFLOW_ROLE"] = role
    p = subprocess.run(["sh", "-c", vendor.hook_command(sub)], input=event_raw, capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip()


def test_missing_cli_fails_closed_for_firm_roles(tmp_path):
    from workflow import vendor

    ev = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    for role in ("ticket", "conductor", " Ticket ", "tikcet"):
        code, out = _run_hook_command("guard", tmp_path, ev, role)
        assert code == 0, role
        decision = json.loads(out)["hookSpecificOutput"]
        assert decision["permissionDecision"] == "deny" and decision["permissionDecisionReason"] == vendor.MISSING_KIT_REASON
    for role in (None, "", "attended", "ATTENDED"):
        assert _run_hook_command("guard", tmp_path, ev, role) == (0, ""), role
    for cmd in vendor.RESTORE_COMMANDS + ("git  checkout --  .claude/workflow",):
        restore = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert _run_hook_command("guard", tmp_path, restore, "ticket") == (0, ""), cmd
    for cmd in ("git checkout -- .claude/workflow; git push origin main", "git checkout -- .claude"):
        other = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
        assert json.loads(_run_hook_command("guard", tmp_path, other, "ticket")[1])["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert json.loads(_run_hook_command("guard", tmp_path, "garbage", "ticket")[1])["hookSpecificOutput"]["permissionDecision"] == "deny"
    for sub in ("gate", "context", "repair"):
        assert _run_hook_command(sub, tmp_path, ev, "ticket", tmpdir=tmp_path) == (0, ""), sub


def test_hook_command_writes_no_pycache(tmp_path):
    from workflow import vendor

    bin_dir = tmp_path / Path(vendor.HOOK_TAG).parent
    bin_dir.mkdir(parents=True)
    (bin_dir / "helper.py").write_text("X = 1\n")
    (bin_dir / "workflow.py").write_text("import sys\nsys.path.insert(0, __import__('os').path.dirname(__file__))\nimport helper\nprint('ran', sys.argv[1:])\n")
    assert "python3 -B" in vendor.hook_command("guard")
    code, out = _run_hook_command("gate", tmp_path, "{}", None, tmpdir=tmp_path)
    assert code == 0 and out == "ran ['hook', 'gate']"
    assert not (bin_dir / "__pycache__").exists()

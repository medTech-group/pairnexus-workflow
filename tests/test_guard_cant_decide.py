"""When the guard can't decide (#53): the can't-decide fallback.

Through the CLI's `hook guard` with an event on stdin (in-process, so the guard
can be made to raise), and through the old-Python fallback's own entry.
"""

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from workflow import _old_python, cli, fallback

KIT = Path(__file__).resolve().parents[1]

PUSH = {"tool_name": "Bash", "tool_input": {"command": "git push origin feature"}}
MERGE = {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 12 --merge"}}
MCP = [{"tool_name": f"mcp__github__{t}", "tool_input": {"owner": "acme", "repo": "demo"}} for t in ("push_files", "create_or_update_file", "merge_pull_request", "delete_file")]
OTHERS = [
    {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
    {"tool_name": "Edit", "tool_input": {"file_path": "a.py", "old_string": "a", "new_string": "b"}},
    {"tool_name": "mcp__github__issue_read", "tool_input": {"issue_number": 3}},
]
ASKING = [None, "default", "acceptEdits"]
NEVER_ASKING = ["bypassPermissions", "dontAsk", "someNewMode"]

VALID = '[project]\nname = "demo"\nrepo = "acme/demo"\n'
INVALID = "[project]\nname = 1\n"  # name must be a string
SOLO_LINE = "ruleset = false\n"
FAILURES = ["error", "invalid", "malformed"]


def _project(tmp_path, profile):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(profile)
    return tmp_path


def _profile(failure, solo):
    if failure == "invalid":
        return INVALID.replace("[project]\n", "[project]\n" + (SOLO_LINE if solo else ""))
    return VALID + (SOLO_LINE if solo else "")


def _with_mode(event, mode):
    e = dict(event)
    if mode is not None:
        e["permission_mode"] = mode
    return e


def _hook(monkeypatch, capsys, root, failure, event, role="attended"):
    """`workflow hook guard` with `event` on stdin, the guard failing as `failure` says."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_ROLE", role)
    monkeypatch.chdir(root)
    text = json.dumps(event)
    if failure == "malformed":
        text += " }trailing"  # not JSON: the event can't be read as a whole
    if failure == "error":
        def boom(*a, **k):
            raise RuntimeError("guard-broke-here")

        monkeypatch.setattr(cli.guard_mod, "decide", boom)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(text.encode()), encoding="utf-8"))
    code = cli.main(["hook", "guard"])
    out = capsys.readouterr().out
    return code, (json.loads(out)["hookSpecificOutput"] if out.strip() else None)


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("mode", ASKING)
def test_a_push_or_merge_is_asked_in_a_mode_that_asks(tmp_path, monkeypatch, capsys, failure, mode):
    root = _project(tmp_path, _profile(failure, False))
    for event in [PUSH, MERGE] + MCP:
        code, out = _hook(monkeypatch, capsys, root, failure, _with_mode(event, mode))
        assert code == 0 and out and out["permissionDecision"] == "ask", (event, out)


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("mode", NEVER_ASKING)
def test_a_push_or_merge_is_refused_where_nobody_is_asked(tmp_path, monkeypatch, capsys, failure, mode):
    root = _project(tmp_path, _profile(failure, False))
    for event in [PUSH, MERGE] + MCP:
        code, out = _hook(monkeypatch, capsys, root, failure, _with_mode(event, mode))
        assert code == 0 and out and out["permissionDecision"] == "deny", (event, out)
        reason = out["permissionDecisionReason"]
        assert mode in reason and "switch the permission mode" in reason
        hand = "Or run it yourself in your own terminal" if event["tool_name"] == "Bash" else "Or do it yourself on GitHub"
        assert hand in reason


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("mode", ASKING + NEVER_ASKING)
def test_a_push_or_merge_is_refused_in_solo_mode(tmp_path, monkeypatch, capsys, failure, mode):
    root = _project(tmp_path, _profile(failure, True))
    for event in [PUSH, MERGE] + MCP:
        code, out = _hook(monkeypatch, capsys, root, failure, _with_mode(event, mode))
        assert code == 0 and out and out["permissionDecision"] == "deny", (event, out)
        assert "solo mode" in out["permissionDecisionReason"]


@pytest.mark.parametrize("failure", FAILURES)
@pytest.mark.parametrize("solo", [False, True])
@pytest.mark.parametrize("mode", [None, "default", "bypassPermissions", "someNewMode"])
def test_anything_else_is_left_alone(tmp_path, monkeypatch, capsys, failure, solo, mode):
    root = _project(tmp_path, _profile(failure, solo))
    for event in OTHERS:
        assert _hook(monkeypatch, capsys, root, failure, _with_mode(event, mode)) == (0, None), event


@pytest.mark.parametrize(
    "failure,why",
    [("error", "RuntimeError: guard-broke-here"), ("invalid", "the profile is invalid (project.name"), ("malformed", "couldn't be read")],
)
def test_the_reason_says_the_guard_isnt_working_why_and_how_to_fix_it(tmp_path, monkeypatch, capsys, failure, why):
    root = _project(tmp_path, _profile(failure, False))
    code, out = _hook(monkeypatch, capsys, root, failure, PUSH)
    reason = out["permissionDecisionReason"]
    assert "guard isn't working" in reason and why in reason
    assert "profile check" in reason and "python3 --version" in reason and "3.11" in reason
    assert "report the error" in reason


def test_the_command_isnt_repeated_where_nothing_could_check_it(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, VALID)
    event = _with_mode({"tool_name": "Bash", "tool_input": {"command": "git push origin MRN-123456"}}, "dontAsk")
    _, out = _hook(monkeypatch, capsys, root, "error", event)
    assert out["permissionDecision"] == "deny" and "MRN-123456" not in out["permissionDecisionReason"]


def test_solo_mode_is_read_from_its_first_plain_line(tmp_path):
    assert fallback.solo_from_text("[project]\nname = 1\nruleset = false\n[[[broken")
    assert fallback.solo_from_text("  ruleset=false # solo\n")
    assert not fallback.solo_from_text("ruleset = true\nruleset = false\n")  # the first counts
    assert not fallback.solo_from_text("# ruleset = false\n")
    assert not fallback.solo_from_text("rulesets = false\n")
    assert not fallback.solo_from_text("")
    assert not fallback.solo(tmp_path / "nowhere")


def test_solo_mode_from_an_otherwise_invalid_profile_through_the_hook(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, "[project]\nruleset = false\nname = 1\n[[[ not toml")
    code, out = _hook(monkeypatch, capsys, root, "invalid", PUSH)
    assert code == 0 and out["permissionDecision"] == "deny" and "solo mode" in out["permissionDecisionReason"]


def test_a_missing_profile_is_left_alone(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for failure in ("error", "malformed"):
        assert _hook(monkeypatch, capsys, tmp_path, failure, _with_mode(PUSH, "dontAsk")) == (0, None)


def test_an_event_that_isnt_utf8_is_read_for_the_fallback(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, VALID)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.setenv("WORKFLOW_ROLE", "attended")
    monkeypatch.chdir(root)
    data = b'{"tool_name": "Bash", "tool_input": {"command": "git push origin \xff"}}'
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))
    assert cli.main(["hook", "guard"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "ask"


@pytest.mark.parametrize("role", ["ticket", "conductor"])
@pytest.mark.parametrize("failure", FAILURES)
def test_ticket_and_conductor_sessions_keep_refusing_every_tool(tmp_path, monkeypatch, capsys, role, failure):
    root = _project(tmp_path, _profile(failure, False))
    for event in [PUSH, MERGE] + MCP + OTHERS:
        code, out = _hook(monkeypatch, capsys, root, failure, _with_mode(event, "default"), role)
        assert code == 0 and out and out["permissionDecision"] == "deny", (event, out)
        assert "isn't working" not in out["permissionDecisionReason"]  # 0.1.8's own refusals, not the fallback's


@pytest.mark.parametrize("mode,want", [(None, "ask"), ("default", "ask"), ("dontAsk", "deny")])
def test_a_guard_out_of_time_takes_the_fallback(tmp_path, monkeypatch, capsys, mode, want):
    root = _project(tmp_path, VALID)
    monkeypatch.setattr(cli, "GUARD_BUDGET", 0.2)
    monkeypatch.setattr(cli, "_STARTED", time.monotonic())  # so the timer itself runs out
    monkeypatch.setattr(cli.guard_mod, "decide", lambda *a, **k: time.sleep(5))
    monkeypatch.setenv("WORKFLOW_ROLE", "attended")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.chdir(root)
    assert cli._hook_guard(_with_mode(PUSH, mode)) == 0
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == want and "ran out of time" in out["permissionDecisionReason"]


def test_a_failure_outside_the_guard_still_exits_0(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, VALID)

    def boom(*a, **k):
        raise OSError("disk-went-away")

    monkeypatch.setattr(cli, "load", boom)
    code, out = _hook(monkeypatch, capsys, root, None, PUSH)
    assert code == 0 and out["permissionDecision"] == "ask" and "disk-went-away" in out["permissionDecisionReason"]
    assert _hook(monkeypatch, capsys, root, None, OTHERS[0]) == (0, None)


# The old-Python fallback's own entry ------------------------------------------


def _old(capsys, event, env, cwd):
    code = _old_python.main(["hook", "guard"], stdin_text=json.dumps(event), env=env, version="3.9.6", cwd=cwd)
    out = capsys.readouterr().out
    return code, (json.loads(out)["hookSpecificOutput"] if out.strip() else None)


@pytest.mark.parametrize("solo", [False, True])
@pytest.mark.parametrize("mode", ASKING + NEVER_ASKING)
def test_old_python_attended_takes_the_fallback(tmp_path, capsys, solo, mode):
    root = _project(tmp_path, VALID + (SOLO_LINE if solo else ""))
    env = {"WORKFLOW_ROLE": "attended", "CLAUDE_PROJECT_DIR": str(root)}
    want = "deny" if solo or mode in NEVER_ASKING else "ask"
    for event in [PUSH, MERGE] + MCP:
        code, out = _old(capsys, _with_mode(event, mode), env, root)
        assert code == 0 and out["permissionDecision"] == want, (event, mode, solo)
        assert "3.9.6" in out["permissionDecisionReason"] and "3.11" in out["permissionDecisionReason"]
    for event in OTHERS:
        assert _old(capsys, _with_mode(event, mode), env, root) == (0, None)


def test_the_fallback_parses_as_python_3_7_and_imports_only_the_standard_library_and_modes():
    for f in ("fallback.py", "_old_python.py", "modes.py"):
        ast.parse((KIT / "scripts/workflow" / f).read_text(), feature_version=(3, 7))
    imported = set()
    for node in ast.walk(ast.parse((KIT / "scripts/workflow/fallback.py").read_text())):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {f"{'.' * node.level}{node.module or ''}:{a.name}" for a in node.names}
    assert imported == {"json", "os", "re", ".:modes"}


@pytest.mark.parametrize("text", [
    "", "[" * 100000, "\x00\xff", '{"tool_name": 3}', '{"tool_name": "Bash", "tool_input": 7}',
    '{"tool_name": "Bash", "tool_input": {"command": ["git push"]}}', '"tool_name": "\\ud800" "command": "\\x"',
    '{"tool_name": "Bash", "permission_mode": 5}', '[1, 2]',
])
def test_the_fallback_never_raises(text, capsys, tmp_path):
    event = fallback.read_event(text)
    d = fallback.decide(event, False, "x")
    assert d is None or fallback.push_or_merge(event)
    env = {"WORKFLOW_ROLE": "attended", "CLAUDE_PROJECT_DIR": str(tmp_path)}
    assert _old_python.main(["hook", "guard"], stdin_text=text, env=env, version="3.9.6", cwd=tmp_path) == 0
    capsys.readouterr()


def _old_python_binary():
    for cand in (os.environ.get("OLD_PYTHON"), shutil.which("python3.9")):
        if cand and Path(cand).exists():
            return cand
    found = sorted(Path.home().glob(".local/share/uv/python/cpython-3.9*/bin/python3.9"))
    return str(found[0]) if found else None


# Without a Python 3.9 (CI always has one), the same module runs as a
# subprocess on this Python instead, so the case still runs end to end.
_SHIM = "import sys; sys.path.insert(0, sys.argv.pop(1)); from workflow import _old_python; sys.exit(_old_python.main(sys.argv[1:]))"


@pytest.mark.parametrize("solo,mode,want", [
    (False, None, "ask"), (False, "default", "ask"), (False, "bypassPermissions", "deny"),
    (False, "someNewMode", "deny"), (True, "default", "deny"),
])
def test_the_entry_point_on_a_real_python_3_9_attended(tmp_path, solo, mode, want):
    py = _old_python_binary()
    assert py or not os.environ.get("CI"), "set OLD_PYTHON to a Python 3.9"
    root = _project(tmp_path, VALID + (SOLO_LINE if solo else ""))
    env = {"PATH": os.environ["PATH"], "WORKFLOW_ROLE": "attended", "CLAUDE_PROJECT_DIR": str(root)}
    argv = [py, "-B", str(KIT / "scripts/workflow.py")] if py else [sys.executable, "-B", "-c", _SHIM, str(KIT / "scripts")]

    def run(event):
        return subprocess.run(argv + ["hook", "guard"], input=json.dumps(event), capture_output=True, text=True, env=env, cwd=root)

    for event in (PUSH, MERGE, MCP[0]):
        p = run(_with_mode(event, mode))
        assert p.returncode == 0, p.stderr
        assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == want
    for event in OTHERS:
        p = run(_with_mode(event, mode))
        assert (p.returncode, p.stdout) == (0, ""), p.stderr


# Docs ---------------------------------------------------------------------------


def test_enforcement_md_describes_the_attended_fallback():
    text = (KIT / "docs/enforcement.md").read_text()
    section = text.split("When something is wrong", 1)[1]
    assert "the hooks report the error and stay out of the way" not in text
    for words in ("can't-decide fallback", "is asked", "solo mode", "permission mode", "exits 0", "ticket and conductor"):
        assert words in section, words


def test_security_md_covers_a_hook_failing_open_in_any_role():
    text = (KIT / "SECURITY.md").read_text()
    assert "failing open where `docs/enforcement.md` says it asks or refuses" in text
    assert "attended sessions included" in text


def test_the_fallback_reads_the_profile_where_the_kit_does():
    from workflow.profile import PROFILE_PATH

    assert Path(fallback.PROFILE) == PROFILE_PATH


def test_an_invalid_profile_on_a_ticket_branch_is_refused_without_a_role(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, '[project]\nname = 1\n[run]\nticket_branch = "agents/*"\n')
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"], check=True)
    subprocess.run(git + ["checkout", "-qb", "agents/t-1"], check=True)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.delenv("WORKFLOW_ROLE", raising=False)
    monkeypatch.chdir(root)
    for event in (PUSH, OTHERS[0]):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(event).encode()), encoding="utf-8"))
        assert cli.main(["hook", "guard"]) == 0
        out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny" and "ticket session" in out["permissionDecisionReason"]
    subprocess.run(git + ["checkout", "-qb", "feature"], check=True)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(OTHERS[0]).encode()), encoding="utf-8"))
    assert cli.main(["hook", "guard"]) == 0 and capsys.readouterr().out == ""


def _bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def test_a_push_or_merge_is_matched_within_one_part_of_the_command():
    for cmd, want in [
        ("git push origin main", "push"), ("cd x && git -C . push --force", "push"), ("gh pr merge 3 --admin", "merge"),
        ("git \\\npush origin main", "push"),  # a line continuation joins its lines
        ("gh pr view 3; git status", None), ("git status; echo push", None), ("gh api x | grep pr; merge", None),
        ("gitpush", None), ("echo git-push-notes", "push"),
    ]:
        assert fallback.push_or_merge(_bash(cmd)) == want, cmd


def test_matching_stays_fast_on_a_large_command():
    for cmd in ("gh pr " * 20000, "git " * 200000 + "\ngit push origin main", ("git " * 5000 + ";") * 40):
        t = time.monotonic()
        fallback.push_or_merge(_bash(cmd))
        assert time.monotonic() - t < 1, cmd[:20]


def test_a_long_error_is_cut_short_in_the_reason():
    action, reason = fallback.decide(PUSH, False, "x" * 5000)
    assert action == "ask" and "x" * 200 + "…" in reason and "x" * 201 not in reason


def test_a_timeout_says_how_to_have_it_checked_not_how_to_fix_the_kit(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, VALID)
    monkeypatch.setattr(cli, "GUARD_BUDGET", 0.2)
    monkeypatch.setattr(cli, "_STARTED", time.monotonic())
    monkeypatch.setattr(cli.guard_mod, "decide", lambda *a, **k: time.sleep(5))
    monkeypatch.setenv("WORKFLOW_ROLE", "attended")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.chdir(root)
    assert cli._hook_guard(PUSH) == 0
    reason = json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "split the command" in reason and "profile check" not in reason


def test_old_python_without_a_profile_keeps_asking_as_since_0_1_8(tmp_path, capsys):
    """Unlike the CLI, which leaves a project without the kit alone: on an old
    Python the plugin's hooks run with no profile, and 0.1.8 asked there."""
    env = {"WORKFLOW_ROLE": "attended", "CLAUDE_PROJECT_DIR": str(tmp_path)}
    assert _old(capsys, PUSH, env, tmp_path)[1]["permissionDecision"] == "ask"
    assert _old(capsys, _with_mode(PUSH, "dontAsk"), env, tmp_path)[1]["permissionDecision"] == "deny"

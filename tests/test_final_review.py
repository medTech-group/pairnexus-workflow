"""The final correctness pass after review round 3, each finding pinned.

Every command here is data passed to `decide`; none is run.
"""

import json

import pytest
from conftest import BASE_PROFILE

from workflow import gate
from workflow.guard import decide
from workflow.issues import blockers_of, readiness
from workflow.profile import parse


def act(profile, root, cmd, role="ticket", branch="claude/build-1"):
    ev = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    return decide(ev, profile, role, root, branch, role_from_env=True).action


@pytest.fixture
def deploy_profile(tmp_path):
    data = json.loads(json.dumps(BASE_PROFILE))
    data["guard"]["deploy_commands"] = ["scripts/deploy.sh"]
    return parse(data, tmp_path)


# ---------- 1. a deploy script run with `.` ----------


@pytest.mark.parametrize("cmd", [". scripts/deploy.sh poc", "cd scripts && . ./deploy.sh", "source scripts/deploy.sh"])
def test_dot_runs_a_deploy_script(cmd, deploy_profile, tmp_path):
    (tmp_path / "scripts").mkdir()
    assert act(deploy_profile, tmp_path, cmd) == "deny", cmd
    assert act(deploy_profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd


def test_dot_running_another_script_is_fine(deploy_profile, tmp_path):
    assert act(deploy_profile, tmp_path, ". .venv/bin/activate") == "allow"


# ---------- 2. the default branch through `--input -` from a file or a pipe ----------


def test_default_branch_on_stdin_from_a_file_or_pipe(profile, tmp_path):
    (tmp_path / "db.json").write_text('{"default_branch": "dev"}')
    (tmp_path / "desc.json").write_text('{"description": "x"}')
    for cmd in ("gh api -X PATCH repos/acme/demo --input - < db.json", "cat db.json | gh api -X PATCH repos/acme/demo --input -"):
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd
        assert act(profile, tmp_path, cmd, role="attended", branch="main") == "ask", cmd
    assert act(profile, tmp_path, "gh api -X PATCH repos/acme/demo --input - < desc.json", role="conductor", branch="main") == "allow"


# ---------- 3. a writing find from the root or above ----------


def test_find_from_the_root_is_checked_against_the_files_there(profile, tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.pyc").write_text("")
    for cmd in (
        "find . -delete",
        "find . -name '*.yml' -delete",
        "find . -iname '*.YML' -delete",
        "find . -name '*.yml' -exec sed -i s/a/b/ {} +",
        "find . -path './.github/*' -delete",
        "find . -name '*.pyc' -o -name '*.yml' -delete",
        "find .. -name '*.pyc' -delete",
        "find / -name ci.yml -delete",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    for cmd in ("find . -name '*.pyc' -delete", "find . -type d -name __pycache__ -exec rm -rf {} +", "find src -delete"):
        assert act(profile, tmp_path, cmd) == "allow", cmd


# ---------- 4. a pull request as a blocker ----------


def _issue(n, state="open", labels=("ready-for-agent",), body="", reason=None, **extra):
    return {"number": n, "state": state, "state_reason": reason, "labels": [{"name": l} for l in labels], "body": body, "title": f"t{n}", **extra}


def test_a_pr_blocker_resolves_once_merged():
    body = "Blocked by: https://github.com/acme/demo/pull/8"
    assert blockers_of(body, "acme/demo") == [8]
    merged = _issue(8, state="closed", labels=(), pull_request={"merged_at": "2026-10-12T00:00:00Z"})
    unmerged = _issue(8, state="closed", labels=(), pull_request={"merged_at": None})
    still_open = _issue(8, labels=(), pull_request={"merged_at": None})
    for pr, reasons in ((merged, []), (unmerged, ["blocker PR #8 closed without merging"]), (still_open, ["blocked by open PR #8"])):
        (v,) = readiness([_issue(10, body=body), pr], [], repo="acme/demo")
        assert v.reasons == reasons
    (v,) = readiness([_issue(10, body=body)], [], repo="acme/demo")
    assert not v.ready and "unknown" in v.reasons[0]


# ---------- 10. the gate's reasons ----------


def test_gate_reasons_are_words(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    done = "- [x] a\n- [x] b\n- [ ] {}\nWORKFLOW-STATUS: done"
    for ok in ("Docs — none changed", "Merged: not yet, because the owner merges", "Docs: none", "Browser check skipped because no UI"):
        assert gate.verdict(done.format(ok)) is None, ok
    for bare in ("Handle the cannot connect case", "Update the Why section", "Docs—x", "Merged under the merge rule (or left for the owner), notes posted", "PR opened with the owner's one-time steps"):
        v = gate.verdict(done.format(bare))
        assert v and gate.NEEDS_REASON in v, bare


# ---------- 11. contractions as negations ----------


def test_contracted_negations_are_not_blockers():
    for text in ("This doesn't get blocked by #4 any more.", "It won't be blocked by #4.", "We aren't blocked by #4."):
        assert blockers_of(text, "acme/demo") == [], text
    assert blockers_of("This is blocked by #4 for now.", "acme/demo") == [4]


# ---------- the pass on the fixes above ----------


def _project(root):
    (root / ".github" / "workflows").mkdir(parents=True)
    (root / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / ".env").write_text("X=1\n")
    (root / "src" / "a.pyc").write_text("")


def test_a_matched_directory_holding_protected_paths(profile, tmp_path):
    _project(tmp_path)
    for cmd in (
        "find . -name .github -exec rm -rf {} +",
        "find . -name '.git*' -exec rm -rf {} +",
        "find . -name pkg -exec rm -rf {} +",
        "find . -name '\\.env' -delete",
        "find . -name '[^x]env' -delete",
    ):
        assert act(profile, tmp_path, cmd) == "deny", cmd
    assert act(profile, tmp_path, "find . -name '*.pyc' -delete") == "allow"


def test_a_symlinked_root_is_walked_as_its_target(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    _project(real)
    link = tmp_path / "link"
    link.symlink_to(real)
    prof = parse(json.loads(json.dumps(BASE_PROFILE)), link)
    assert act(prof, link, "find . -name ci.yml -delete") == "deny"
    assert act(prof, link, "find . -name '*.pyc' -delete") == "allow"


def test_dependency_directories_are_not_walked_and_a_big_tree_says_so(profile, tmp_path, monkeypatch):
    from workflow import guard

    _project(tmp_path)
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    for k in range(30):
        (tmp_path / "node_modules" / "x" / f"f{k}.js").write_text("")
    monkeypatch.setattr(guard, "_WALK_LIMIT", 20)
    assert act(profile, tmp_path, "find . -name '*.pyc' -delete") == "allow"
    for k in range(30):
        (tmp_path / "src" / f"g{k}.py").write_text("")
    d = decide({"tool_name": "Bash", "tool_input": {"command": "find . -name '*.pyc' -delete"}}, profile, "ticket", tmp_path, "claude/build-1")
    assert d.action == "deny" and "too big" in d.reason


def test_a_pruned_find_from_the_root(profile, tmp_path):
    _project(tmp_path)
    assert act(profile, tmp_path, "find . -name node_modules -prune -o -name '*.pyc' -delete") == "allow"
    assert act(profile, tmp_path, "find . -name node_modules -prune -o -name '*.yml' -delete") == "deny"
    assert act(profile, tmp_path, "find . -name node_modules -prune -o -name '*.pyc' -o -name '*.yml' -delete") == "deny"


def test_default_branch_through_dev_stdin_and_escaped_keys(profile, tmp_path):
    (tmp_path / "db.json").write_text('{"default_branch": "dev"}')
    (tmp_path / "esc.json").write_text('{"default\\u005fbranch": "dev"}')
    for cmd in (
        "gh api -X PATCH repos/acme/demo --input /dev/stdin < db.json",
        "gh api -X PATCH repos/acme/demo --input esc.json",
        "gh api -X PATCH repos/acme/demo --input - < esc.json",
    ):
        assert act(profile, tmp_path, cmd, role="conductor", branch="main") == "deny", cmd

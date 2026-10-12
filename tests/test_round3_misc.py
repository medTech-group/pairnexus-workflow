"""The third review round's findings outside the guard (numbers are the findings')."""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import git
from test_evidence_review import _repo, parse_profile
from test_vendor_evidence import kit, mattpocock, proj  # noqa: F401  (fixtures)

from workflow import charter, evidence, gate, vendor
from workflow.issues import blockers_of, read_area, readiness
from workflow.profile import parse

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
PROFILE = '[project]\nname="d"\nrepo="a/d"\nowner="rajat-t"\n[ci]\nrequired_checks=["CI"]\n[[release.steps]]\nname="deploy staging"\nrun="x"\n'


def _cli(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=e)


def _project(tmp_path, text=PROFILE):
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


def good():
    c = charter.defaults(["deploy staging"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["merge"]["mode"] = "session"
    return c


def approved(by="rajat-t"):
    c = good()
    c["approved"] = {"by": by, "at": "2026-10-12T11:55:00Z", "source": "chat"}
    return c


# ---------- 17. malformed charters never raise ----------

ODD = [[], {}, 1, 2.5, True, None, "x", [1, "a"], {"a": []}, [[]], [{}]]
PATHS = [
    ("version",), ("scope",), ("scope", "tickets"), ("scope", "exclude"), ("scope", "follow_unblocked"),
    ("limits",), ("limits", "ends_at"), ("limits", "max_parallel"), ("merge",), ("merge", "mode"),
    ("merge", "waived_checks"), ("release",), ("release", "when"), ("release", "steps"), ("release", "smoke_test"),
    ("outward",), ("outward", "allowed"), ("conductor_fixes",), ("open_decisions",), ("stop_run_on",), ("notify",),
    ("notify", "failures"), ("notify", "final_report"), ("accepted_gaps",), ("approved",), ("approved", "by"),
    ("approved", "at"), ("approved", "source"), ("amendments",), ("plan",),
]  # fmt: skip


@pytest.mark.parametrize("path", PATHS, ids=lambda p: ".".join(p))
def test_validate_never_raises_on_malformed_types(path):
    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    for value in ODD:
        c = approved()
        c["amendments"] = [{"at": "2026-10-12T12:00:00Z", "by": "rajat-t", "change": "x", "source": "y"}]
        c["plan"] = [1]
        c["scope"]["tickets"] = [1, 2]
        target = c
        for k in path[:-1]:
            target = target[k]
        target[path[-1]] = value
        problems = charter.validate(c, require_approval=True, now=now)
        assert isinstance(problems, list)
        assert isinstance(charter.check_against_profile(c, ["deploy staging"], ["CI"], owner="rajat-t"), list)
        assert isinstance(charter.validate_amendments(value, owner="rajat-t"), list)
    for whole in ODD:
        assert charter.validate(whole) or isinstance(whole, dict)
        assert isinstance(charter.check_against_profile(whole, [], []), list)


def test_validate_cli_reports_malformed_charters_without_a_traceback(tmp_path):
    env = _project(tmp_path)
    c = approved()
    c["merge"]["mode"] = ["auto-merge"]
    c["release"] = ["deploy staging"]
    f = tmp_path / "c.json"
    f.write_text(json.dumps(c))
    p = _cli("charter", "validate", str(f), "--approved", env=env)
    assert p.returncode == 1 and "Traceback" not in p.stderr
    assert "merge.mode must be one of" in p.stderr and "release must be an object" in p.stderr
    # The profile isn't checked while the charter itself has problems.
    assert "profile's" not in p.stderr


# ---------- 21. the approver and the plan ----------


def test_amendments_by_someone_else_than_the_owner():
    c = approved()
    c["amendments"] = [
        {"at": "2026-10-12T12:00:00Z", "by": "@Rajat-T", "change": "also #140", "source": "chat"},
        {"at": "2026-10-12T12:05:00Z", "by": "someone", "change": "extend", "source": "chat"},
    ]
    assert charter.validate_amendments(c["amendments"]) == []
    p = charter.validate_amendments(c["amendments"], owner="rajat-t")
    assert p == ["amendments[1].by (someone) isn't the profile's project.owner (rajat-t): only the owner amends a run"]
    assert charter.check_against_profile(c, ["deploy staging"], ["CI"], owner="rajat-t") == p
    assert charter.check_against_profile(c, ["deploy staging"], ["CI"]) == []
    assert charter.validate(c) == []


def test_state_init_checks_the_charter_against_the_profile(tmp_path):
    env = _project(tmp_path)
    f = tmp_path / "c.json"
    for c, why in (
        (approved("someone"), "isn't the profile's project.owner"),
        ({**approved(), "release": {"when": "end", "steps": ["deploy prod"], "smoke_test": True}}, "release step 'deploy prod'"),
        ({**approved(), "merge": {"mode": "session", "waived_checks": ["Lint"]}}, "waived check 'Lint'"),
    ):
        f.write_text(json.dumps(c))
        p = _cli("state", "init", "--charter", str(f), "--run-id", "r", "--read-through", "0", env=env)
        assert p.returncode == 1 and why in p.stderr, p.stderr
    f.write_text(json.dumps(approved()))
    p = _cli("state", "init", "--charter", str(f), "--run-id", "r", "--read-through", "0", env=env)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["run_id"] == "r"


def test_charter_pin_plan_cli(tmp_path):
    env = _project(tmp_path)
    c = good()
    c["plan"] = [13, 143]
    c["scope"]["follow_unblocked"] = False
    f = tmp_path / "c.json"
    f.write_text(json.dumps(c))
    p = _cli("charter", "pin-plan", str(f), env=env)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["scope"]["tickets"] == [13, 143] and out["plan"] == [13, 143]
    assert charter.validate(out) == []
    c["scope"]["follow_unblocked"] = True
    f.write_text(json.dumps(c))
    assert json.loads(_cli("charter", "pin-plan", str(f), env=env).stdout)["scope"]["tickets"] == "all-ready"
    f.write_text(json.dumps({**c, "plan": "13"}))
    p = _cli("charter", "pin-plan", str(f), env=env)
    assert p.returncode == 1 and "plan must be" in p.stderr


def test_conductor_skill_pins_the_plan_with_the_cli():
    text = (KIT / "skills/conductor/SKILL.md").read_text()
    assert "WF charter pin-plan charter.json > charter.json.tmp && mv charter.json.tmp charter.json" in text


# ---------- 22. issues ----------


def issue(n, state="open", labels=("ready-for-agent",), body="", reason=None):
    return {"number": n, "state": state, "state_reason": reason, "labels": [{"name": name} for name in labels], "body": body, "title": f"t{n}"}


def test_pull_request_urls_of_the_same_repo_are_blockers():
    body = "Blocked by: https://github.com/acme/demo/pull/8 and https://github.com/other/x/pull/3"
    assert blockers_of(body, "acme/demo") == [8, "other/x#3"]


def test_blocked_by_in_the_middle_of_a_sentence():
    assert blockers_of("This can only start once it is blocked by #8 no more.", "acme/demo") == [8]
    assert blockers_of("Waits: this is blocked by #8, #9 and acme/demo#10, then free.", "acme/demo") == [8, 9, 10]
    assert blockers_of("Note: it's blocked by https://github.com/acme/demo/issues/12.", "acme/demo") == [12]
    assert blockers_of("This is no longer blocked by #8.", "acme/demo") == []
    assert blockers_of("This is not blocked by #8.", "acme/demo") == []
    assert blockers_of("Related to #8; see the blocked list.", "acme/demo") == []
    v = {x.number: x for x in readiness([issue(1), issue(2, body="We are blocked by #1 for now.")], [])}
    assert not v[2].ready and "blocked by open #1" in v[2].reasons


def test_an_area_line_naming_several_known_areas_takes_the_first():
    area, note = read_area("**Area:** messages, sharing", ["messages", "sharing", "readings"])
    assert area == "messages" and note and "messages, sharing" in note
    assert read_area("Area: messages module", ["messages", "sharing"]) == ("messages", None)
    assert read_area("Area: messages", ["messages", "sharing"]) == ("messages", None)


# ---------- 23. the gate ----------

CHECKLIST = "- [x] a\n- [x] b\n- [x] c\n"


def test_gate_reasons_need_words_not_a_link_or_a_colon(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    for reason in ("because CI is down", "why: no UI", "— the owner's", "- not this ticket", "n/a", "N/A for docs", "not needed"):
        assert gate.verdict(CHECKLIST + f"- [ ] by-hand check {reason}\nWORKFLOW-STATUS: done") is None, reason
    for bare in ("https://example.com/x", ": later", "see #12", "x—y"):
        v = gate.verdict(CHECKLIST + f"- [ ] by-hand check {bare}\nWORKFLOW-STATUS: done")
        assert v and gate.NEEDS_REASON in v, bare


def test_gate_block_cap_counts_per_day(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    day1 = datetime(2026, 10, 12, 23, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)
    ev = {"session_id": "long-ticket", "last_assistant_message": "x"}
    for _ in range(gate.MAX_BLOCKS):
        assert gate.decide(ev, now=day1)
    assert gate.decide(ev, now=day1) is None  # the cap, for today
    assert gate.decide(ev, now=day2)  # a new day: the gate again
    assert {p.name for p in tmp_path.iterdir()} == {"workflow-gate-long-ticket-2026-10-12", "workflow-gate-long-ticket-2026-10-13"}


# ---------- 18. vendor ----------

FLOW = ".claude/workflow/flow.md"


def test_stale_new_files_are_deleted_when_no_longer_a_conflict(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    flow, new = proj / FLOW, proj / (FLOW + ".new")
    original = (kit / "docs/flow.md").read_text()
    flow.write_text("local edit")
    (kit / "docs/flow.md").write_text("kit v2")
    assert vendor.install(kit, proj, mattpocock, update=True)["conflicts"] == [FLOW] and new.exists()
    # The kit goes back to the version the project's edit came from: no conflict, so no .new.
    (kit / "docs/flow.md").write_text(original)
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert FLOW in r["kept"] and not r["conflicts"] and not new.exists()
    assert not vendor.verify(proj)["conflicts"]
    # A .new beside a file that never had a conflict goes too.
    other = proj / ".claude/workflow/docs/install.md.new"
    other.write_text("left over")
    vendor.install(kit, proj, mattpocock, update=True)
    assert not other.exists()


def test_a_kept_file_stays_kept_through_being_orphaned(mattpocock, kit, proj):
    vendor.install(kit, proj, mattpocock)
    doc = ".claude/workflow/docs/charter.md"
    original = (kit / "docs/charter.md").read_text()
    (proj / doc).write_text("our notes")
    vendor.resolve(proj, doc, keep=True)
    (kit / "docs/charter.md").unlink()
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["orphaned"] == [doc] and vendor.read_lock(proj)["kept"][doc]
    # Re-added unchanged: still kept, and verify --strict passes for it.
    (kit / "docs/charter.md").write_text(original)
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert doc in r["kept"] and not r["conflicts"]
    v = vendor.verify(proj)
    assert doc in v["kept"] and doc not in v["changed"]
    # Dropped again and re-added changed: a conflict, and the keep is gone.
    (kit / "docs/charter.md").unlink()
    vendor.install(kit, proj, mattpocock, update=True)
    (kit / "docs/charter.md").write_text("changed in the kit")
    r = vendor.install(kit, proj, mattpocock, update=True)
    assert r["conflicts"] == [doc] and doc not in (vendor.read_lock(proj).get("kept") or {})


# ---------- 19. evidence: a suite cwd missing ----------


def test_a_suite_cwd_missing_on_the_base_counts_zero_with_a_note(tmp_path):
    web = '[[commands.suite]]\nname = "web"\nrun = "python3 ../run_tests.py {files}"\nfiles = "web/test_*.txt"\ncwd = "web"\n'
    root = _repo(tmp_path, {"tests/test_0.txt": "pass"}, extra_suites=[web])
    git(root, "branch", "base")
    (root / "web").mkdir()
    (root / "web/test_a.txt").write_text("pass")
    git(root, "add", ".")
    git(root, "commit", "-qm", "add web")
    b = evidence.base_count_from_ref(parse_profile(root), root, "base")
    assert b.count == 1 and not b.problem, b.problem
    assert b.notes == ["suite web: its cwd `web` doesn't exist here, so it counts 0"]


def test_run_shard_with_a_missing_cwd_is_a_failed_shard(tmp_path):
    prof = parse({"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [{"name": "u", "run": "true", "cwd": "gone"}]}}, tmp_path)
    r = evidence.run_shard(prof.suites[0], 0, [], tmp_path)
    assert not r.ok and r.exit != 0 and "`gone` doesn't exist here" in r.tail


def test_base_count_catches_os_errors(tmp_path, monkeypatch):
    root = _repo(tmp_path, {"tests/test_0.txt": "pass"})
    git(root, "branch", "base")

    def boom(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(evidence, "collect", boom)
    b = evidence.base_count_from_ref(parse_profile(root), root, "base")
    assert b.count is None and "PermissionError" in b.problem
    assert not (root / ".workflow" / f"base-{b.sha}").exists()


# ---------- 20. test isolation ----------


def test_every_gate_call_in_the_tests_sets_its_own_tmpdir():
    """Each test that runs the gate (gate.decide or the gate hook) sets TMPDIR."""
    import ast

    for f in sorted((KIT / "tests").glob("test_*.py")):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                src = ast.get_source_segment(f.read_text(), node) or ""
                calls_gate = "gate.decide(" in src or any(q + "gate" + q in src for q in ("'", '"'))
                if calls_gate and node.name != "test_every_gate_call_in_the_tests_sets_its_own_tmpdir":
                    assert "TMPDIR" in src or "tmpdir=" in src, f"{f.name}::{node.name} runs the gate without its own TMPDIR"


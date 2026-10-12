"""Charter, state, gate, profile and render: the review's findings."""

import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from workflow import charter, gate, state
from workflow.profile import ProfileError, check, parse
from workflow.render import values

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def _cli(*args, cwd=None, env=None, stdin=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=cwd, env=e, input=stdin)


def good():
    c = charter.defaults(["deploy staging"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    return c


def approved(by="owner"):
    c = good()
    c["approved"] = {"by": by, "at": "2026-10-12T11:55:00Z", "source": "chat"}
    return c


def _profile_dir(tmp_path, text):
    (tmp_path / ".claude/workflow").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


# ---------- 15. times ----------


def test_lowercase_z_and_a_naive_now():
    c = approved()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00z"
    c["approved"]["at"] = "2026-10-12t11:55:00z"
    assert charter.validate(c, require_approval=True, now=NOW) == []
    naive = datetime(2026, 10, 12, 12, 0)
    assert charter.validate(c, require_approval=True, now=naive) == []
    c["approved"]["at"] = "2026-10-12T12:30:00z"
    assert any("in the future" in p for p in charter.validate(c, now=naive))


# ---------- 16. unknown keys ----------


def test_unknown_keys_are_refused():
    c = good()
    c["scopee"] = {}
    c["limits"]["max_paralel"] = 3
    c["approved"] = {"by": "o", "at": "2026-10-12T11:55:00Z", "source": "chat", "when": "now"}
    problems = charter.validate(c, now=NOW)
    assert any("the charter: unknown key 'scopee'" in p for p in problems)
    assert any("limits: unknown key 'max_paralel'" in p for p in problems)
    assert any("approved: unknown key 'when'" in p for p in problems)


# ---------- 17. against the profile ----------


def test_auto_merge_needs_something_checked():
    c = good()
    assert c["merge"]["mode"] == "auto-merge"
    p = charter.check_against_profile(c, ["deploy staging"], [])
    assert p == ["merge.mode auto-merge: the profile has no ci.required_checks, so auto-merge would merge at once with nothing checked; use session"]
    p = charter.check_against_profile(c, ["deploy staging"], ["CI"], ci_none=True)
    assert any("ci.none is true" in x and "use session" in x for x in p)
    assert charter.check_against_profile(c, ["deploy staging"], ["CI"]) == []
    c["merge"]["mode"] = "session"
    assert charter.check_against_profile(c, ["deploy staging"], [], ci_none=True) == []


def test_approved_by_must_be_the_owner():
    assert charter.check_against_profile(approved("@Rajat-T"), ["deploy staging"], ["CI"], owner="rajat-t") == []
    p = charter.check_against_profile(approved("someone"), ["deploy staging"], ["CI"], owner="rajat-t")
    assert p == ["approved.by (someone) isn't the profile's project.owner (rajat-t): only the owner approves a run"]
    assert charter.check_against_profile(approved("someone"), ["deploy staging"], ["CI"]) == []  # no owner set


def test_validate_approved_cli_checks_the_owner(tmp_path):
    env = _profile_dir(
        tmp_path,
        '[project]\nname="d"\nrepo="a/d"\nowner="rajat-t"\n[ci]\nrequired_checks=["CI"]\n[[release.steps]]\nname="deploy staging"\nrun="x"\n',
    )
    f = tmp_path / "c.json"
    f.write_text(json.dumps(approved("someone")))
    p = _cli("charter", "validate", str(f), "--approved", env=env)
    assert p.returncode == 1 and "isn't the profile's project.owner (rajat-t)" in p.stderr
    assert _cli("charter", "validate", str(f), env=env).returncode == 0  # only --approved checks who
    f.write_text(json.dumps(approved("Rajat-T")))
    p = _cli("charter", "validate", str(f), "--approved", env=env)
    assert p.returncode == 0, p.stderr


# ---------- 18. reuse ----------


def test_reuse_clears_accepted_gaps_and_diff_shows_amendments():
    old = approved()
    old["accepted_gaps"] = ["no branch protection"]
    old["amendments"] = [{"at": "2026-10-12T12:00:00Z", "by": "owner", "change": "also #140", "source": "chat"}]
    new = charter.reuse(old)
    assert new["accepted_gaps"] == [] and new["amendments"] == []
    d = charter.diff(old, new)
    assert any(x.startswith("amendments: [") and x.endswith("-> []") for x in d)
    assert any(x.startswith("accepted_gaps:") for x in d)


# ---------- 19. amendments carry by ----------


def test_amendments_need_by():
    c = good()
    c["amendments"] = [{"at": "2026-10-12T12:00:00Z", "change": "also #140", "source": "chat"}]
    assert any("amendments[0] needs at (ISO time), by (who), change and source" in p for p in charter.validate(c))
    c["amendments"][0]["by"] = "owner"
    assert charter.validate(c) == []
    assert "Amended 2026-10-12T12:00:00Z by owner: also #140 (chat)" in charter.to_markdown(c)
    c["amendments"][0]["why"] = "x"
    assert any("amendments[0]: unknown key 'why'" in p for p in charter.validate(c))


# ---------- 20. the plan ----------


def test_plan_in_scope_and_not_excluded():
    c = good()
    c["plan"] = [13, 143]
    assert charter.validate(c) == []
    c["scope"]["exclude"] = [143]
    assert any("plan tickets #143 are in scope.exclude" in p for p in charter.validate(c))
    c["scope"].update(tickets=[13, 20], exclude=[])
    assert any("plan tickets #143 aren't in scope.tickets" in p for p in charter.validate(c))
    c["plan"] = []
    assert any(p.startswith("plan must be") for p in charter.validate(c))
    assert "pin_plan" in charter.__doc__ and "follow_unblocked" in charter.__doc__


def test_pin_plan_sets_scope_when_not_following_unblocked():
    c = good()
    c["plan"] = [13, 143]
    assert charter.pin_plan(c)["scope"]["tickets"] == "all-ready"  # follow_unblocked true: unchanged
    c["scope"]["follow_unblocked"] = False
    pinned = charter.pin_plan(c)
    assert pinned["scope"]["tickets"] == [13, 143] and c["scope"]["tickets"] == "all-ready"
    assert charter.validate(pinned) == []


# ---------- 21. questions fit the profile ----------


def test_questions_fit_the_profile(tmp_path):
    env = _profile_dir(
        tmp_path,
        '[project]\nname="d"\nrepo="a/d"\n[[release.steps]]\nname="ship"\nrun="x"\n'
        "[run]\ncheck_in_minutes=30\nmax_parallel=3\nmax_retries=2\n",
    )
    p = _cli("charter", "questions", env=env)
    q = {x["key"]: x for x in json.loads(p.stdout)}
    assert q["release"]["default"] == {"when": "end", "steps": ["ship"], "smoke_test": True}
    lim = q["limits"]
    for k in ("ends_at", "max_parallel", "max_sessions", "max_retries", "check_in_minutes"):
        assert k in lim["ask"]
    assert lim["default"] == {"ends_at": None, "max_parallel": 3, "max_sessions": 40, "max_retries": 2, "check_in_minutes": 30}
    assert q["merge"]["default"]["mode"] == "session"  # no required checks: auto-merge would check nothing
    d = json.loads(_cli("charter", "defaults", env=env).stdout)
    assert d["limits"] == lim["default"] and d["release"] == q["release"]["default"]
    # Without a profile: the plain defaults.
    q = {x["key"]: x for x in json.loads(_cli("charter", "questions", env={"CLAUDE_PROJECT_DIR": str(tmp_path / "none")}).stdout)}
    assert q["release"]["default"]["when"] == "never" and q["limits"]["default"]["max_parallel"] == 2


# ---------- 22. markdown without --tickets ----------


def test_markdown_says_when_the_plan_is_missing(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(good()))
    p = _cli("charter", "markdown", str(f))
    assert p.returncode == 0 and "Plan: not given (pass --tickets)" in p.stdout
    p = _cli("charter", "markdown", str(f), "--tickets", "13:messages")
    assert "Plan: not given" not in p.stdout and "1. #13 (messages)" in p.stdout
    c = good()
    c["plan"] = [13]
    assert "1. #13 (area not given)" in charter.to_markdown(c)


# ---------- 23-26. state ----------


def test_comments_read_through(tmp_path):
    s = state.empty(good())
    assert s["comments_read_through"] is None and state.validate(s) == []
    s["comments_read_through"] = "123"
    assert any("comments_read_through" in p for p in state.validate(s))
    s["comments_read_through"] = 0
    assert state.validate(s) == []
    f = tmp_path / "c.json"
    f.write_text(json.dumps(approved()))
    p = _cli("state", "init", "--charter", str(f), "--run-id", "r1", "--read-through", "987")
    assert p.returncode == 0 and json.loads(p.stdout)["comments_read_through"] == 987 and "warning" not in p.stderr
    p = _cli("state", "init", "--charter", str(f), "--run-id", "r1")
    assert p.returncode == 0 and json.loads(p.stdout)["comments_read_through"] is None
    assert "the first check-in will read every comment" in p.stderr


@pytest.mark.parametrize(
    "field,bad,good_value",
    [
        ("pr", "12", 12),
        ("stopped_head", 5, "abc123"),
        ("started_at", "yesterday", "2026-10-12T10:00:00Z"),
        ("merged_at", "2026-10-12T10:00:00", "2026-10-12T10:00:00+05:30"),
        ("rounds", -1, 2),
        ("area", ["x"], "messages"),
        ("attempts", 1.5, 1),
    ],
)
def test_ticket_fields_are_typed(field, bad, good_value):
    s = state.empty()
    s["tickets"]["7"] = {"status": "running", field: bad}
    assert any(f"tickets[7].{field}" in p for p in state.validate(s))
    s["tickets"]["7"][field] = good_value
    assert state.validate(s) == []


def test_run_level_fields():
    s = state.empty()
    assert s["kickoff_tickets"] == [] and s["ci_minutes_at_start"] is None and s["status"] == "running"
    s.update(kickoff_tickets=[13, 143], ci_minutes_at_start=1234.5, status="stopping")
    assert state.validate(s) == []
    for k, v in (("kickoff_tickets", ["13"]), ("ci_minutes_at_start", "lots"), ("status", "paused"), ("kickoff_tickets", 13)):
        bad = dict(s, **{k: v})
        assert any(k in p for p in state.validate(bad)), k
    old = state.empty()
    for k in ("kickoff_tickets", "ci_minutes_at_start", "status", "comments_read_through"):
        old.pop(k)
    assert state.validate(old) == []  # a state written before these fields still reads


def test_patch_cannot_unapprove_a_running_run(tmp_path):
    s = state.empty(approved())
    body = state.put("# Tracking\n", s)
    with pytest.raises(state.StateError, match="unapproved"):
        state.patch(s, {"charter": {"approved": None}})
    with pytest.raises(state.StateError, match="unapproved"):
        state.patch(s, {"charter": None})
    with pytest.raises(state.StateError, match="patched charter has problems"):
        state.patch(s, {"charter": {"limits": {"max_parallel": 0}}})
    assert state.patch(s, {"status": "stopping"})["status"] == "stopping"
    # An unapproved charter (before kick-off) may still be changed freely.
    assert state.patch(state.empty(good()), {"charter": {"approved": None}})["charter"].get("approved") is None

    b, pf = tmp_path / "body.md", tmp_path / "patch.json"
    b.write_text(body)
    pf.write_text(json.dumps({"charter": {"approved": None}}))
    p = _cli("state", "patch", "--body", str(b), "--patch", str(pf))
    assert p.returncode == 1 and "unapproved" in p.stderr
    pf.write_text(json.dumps({"comments_read_through": 55, "tickets": {"7": {"status": "running", "pr": 300}}}))
    p = _cli("state", "patch", "--body", str(b), "--patch", str(pf))
    assert p.returncode == 0, p.stderr
    got = state.get(p.stdout)
    assert got["comments_read_through"] == 55 and got["tickets"]["7"]["pr"] == 300


# ---------- 27-28. the gate ----------

CHECKLIST = "- [x] a\n- [x] b\n- [x] c\n"


def test_gate_ignores_fenced_text():
    quoted = "Here is the template:\n```\nWORKFLOW-STATUS: done\n- [x] a\n- [x] b\n- [x] c\n```\n"
    assert gate.verdict(quoted)  # the status line is only inside a fence
    assert gate.verdict(quoted + "WORKFLOW-STATUS: waiting") is None
    checklist_in_fence = "```md\n" + CHECKLIST + "```\nWORKFLOW-STATUS: done"
    assert "checklist" in gate.verdict(checklist_in_fence)
    assert gate.verdict("```\nx\n```\n" + CHECKLIST + "WORKFLOW-STATUS: done") is None


def test_gate_unchecked_lines_need_a_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    msg = CHECKLIST + "- [ ] by-hand check\nWORKFLOW-STATUS: done"
    v = gate.verdict(msg)
    assert v and gate.NEEDS_REASON in v and "by-hand check" in v
    for reason in ("because the owner does it", "— the owner's", "- not this ticket", "n/a for a docs change", "why: no UI"):
        assert gate.verdict(CHECKLIST + f"- [ ] by-hand check {reason}\nWORKFLOW-STATUS: done") is None, reason
    assert gate.verdict("  - [ ] indented\n" + CHECKLIST + "WORKFLOW-STATUS: done")  # its own " - " isn't a reason
    assert gate.verdict(CHECKLIST + "- [ ] x\nWORKFLOW-STATUS: waiting") is None  # only done asks
    assert gate.decide({"session_id": "g-unchecked", "last_assistant_message": msg}) == v


# ---------- 29-32. profile and render ----------

PACKAGES = {
    "project": {"name": "d", "repo": "a/d"},
    "commands": {
        "typecheck": "pyright",
        "test_file": "pytest {file} -q",
        "package": [
            {"name": "web", "path": "web/**", "typecheck": "npx tsc --noEmit", "test_file": "npx jest {file}", "cwd": "web"},
            {"name": "app", "path": "flutter/**", "test_file": "flutter test {file}"},
        ],
    },
}


def _slots():
    return {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none"}


def test_packages_parse_and_render(tmp_path):
    prof = parse(json.loads(json.dumps(PACKAGES)), tmp_path)
    assert [p.name for p in prof.packages] == ["web", "app"] and prof.packages[0].cwd == "web"
    v = values(prof, {"number": 1}, good(), _slots(), 1, None)
    assert v["commands.typecheck"] == "`pyright` for everything else; for `web/**` (package web, run in `web`): `npx tsc --noEmit`"
    assert v["commands.test_file"] == (
        "`pytest {file} -q` (replace {file} with the test file's path) for everything else; "
        "for `web/**` (package web, run in `web`): `npx jest {file}` (replace {file} with the test file's path); "
        "for `flutter/**` (package app): `flutter test {file}` (replace {file} with the test file's path)"
    )
    no_top = json.loads(json.dumps(PACKAGES))
    no_top["commands"].pop("typecheck")
    v = values(parse(no_top, tmp_path), {"number": 1}, good(), _slots(), 1, None)
    assert v["commands.typecheck"] == "for `web/**` (package web, run in `web`): `npx tsc --noEmit`"


@pytest.mark.parametrize(
    "change,needle",
    [
        ({"name": ""}, "needs name and path"),
        ({"path": ""}, "needs name and path"),
        ({"typecheck": "", "test_file": ""}, "give typecheck, test_file or both"),
        ({"cwd": "../x"}, "cwd must be a directory relative"),
        ({"path": "/abs/**"}, "path must be a glob relative"),
        ({"files": "x"}, "unknown key 'files'"),
        ({"typecheck": 3}, "typecheck must be a string"),
    ],
)
def test_packages_are_validated(tmp_path, change, needle):
    data = json.loads(json.dumps(PACKAGES))
    data["commands"]["package"][0].update(change)
    with pytest.raises(ProfileError, match=re.escape(needle)):
        parse(data, tmp_path)


def test_package_names_unique(tmp_path):
    data = json.loads(json.dumps(PACKAGES))
    data["commands"]["package"][1]["name"] = "web"
    with pytest.raises(ProfileError, match="unique"):
        parse(data, tmp_path)


def test_suite_glob_wording_is_relative_to_the_root(tmp_path):
    prof = parse(
        {"project": {"name": "d", "repo": "a/d"}, "commands": {"suite": [{"name": "app", "run": "t {files}", "files": "app/tests/*.txt", "cwd": "app"}]}},
        tmp_path,
    )
    line = values(prof, {"number": 1}, good(), _slots(), 1, None)["commands.suites"]
    assert "matching `app/tests/*.txt`, relative to the project root, each given relative to `app`" in line
    tpl = (KIT / "templates/profile.toml").read_text()
    assert "relative to the project root (even when cwd is set)" in tpl


def test_profile_check_warnings(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Project\n\n## Safety Constraints\n\n```\n## Not A Heading\n```\n")
    (tmp_path / "src/messages").mkdir(parents=True)
    (tmp_path / "src/messages/a.py").write_text("")
    (tmp_path / "tests").mkdir()
    prof = parse(
        {
            "project": {"name": "d", "repo": "a/d", "rules": ["CLAUDE.md#safety-constraints", "CLAUDE.md#Safety Rules", "CLAUDE.md#not-a-heading"]},
            "commands": {"suite": [{"name": "unit", "run": "t {files}", "files": "tests/test_*.py"}]},
            "areas": {"messages": ["src/messages/**", "src/messages/*.dart"], "clock": ["src/clock/**"]},
        },
        tmp_path,
    )
    w = check(prof)
    assert "project.owner is empty: approvals and the owner's comments can't be checked against a login" in w
    assert any(x.startswith("run.ticket_environment is empty") for x in w)
    assert any(x.startswith("run.conductor_environment is empty") for x in w)
    assert "project.rules: CLAUDE.md has no heading matching #Safety Rules (from 'CLAUDE.md#Safety Rules')" in w
    assert "project.rules: CLAUDE.md has no heading matching #not-a-heading (from 'CLAUDE.md#not-a-heading')" in w
    assert not any("#safety-constraints" in x for x in w)
    assert "commands.suite unit: files glob 'tests/test_*.py' matches no file (globs are relative to the project root)" in w
    assert "areas.clock: glob 'src/clock/**' matches no file" in w
    assert "areas.messages: glob 'src/messages/*.dart' matches no file" in w
    assert not any("src/messages/**" in x for x in w)

    prof.owner, prof.ticket_environment, prof.conductor_environment = "o", "t", "c"
    prof.rules = ["CLAUDE.md#safety-constraints"]
    (tmp_path / "tests/test_a.py").write_text("")
    prof.areas = {"messages": ["src/messages/**"]}
    assert check(prof) == []


def test_template_package_example_parses_when_uncommented():
    tpl = (KIT / "templates/profile.toml").read_text()
    assert "# [[commands.package]]" in tpl
    lines = tpl.splitlines()
    start = lines.index("# [[commands.package]]")
    block = []
    for l in lines[start:]:
        if not l.startswith("# "):
            break
        block.append(l[2:])
    text = "\n".join(lines[:start] + block + lines[start + len(block) :])
    prof = parse(tomllib.loads(text), Path("."))
    assert prof.packages and prof.packages[0].name == "web" and prof.packages[0].typecheck


def test_reuse_clears_the_plan_and_a_scope_built_from_it():
    from workflow import charter

    old = charter.defaults()
    old["plan"] = [3, 4]
    old["scope"]["tickets"] = [3, 4]
    old["scope"]["follow_unblocked"] = False
    new = charter.reuse(old)
    assert "plan" not in new and new["scope"]["tickets"] == "all-ready"
    old["scope"]["tickets"] = [7]
    assert charter.reuse(old)["scope"]["tickets"] == [7]


def test_owner_task_blocker_is_named():
    from workflow.issues import readiness

    issues = [
        {"number": 5, "state": "open", "labels": [{"name": "owner-task"}], "body": "", "title": "key"},
        {"number": 6, "state": "open", "labels": [{"name": "ready-for-agent"}], "body": "Blocked by: #5", "title": "t"},
    ]
    v = [x for x in readiness(issues, []) if x.number == 6][0]
    assert v.reasons == ["blocked by owner task #5"]

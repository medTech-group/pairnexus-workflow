import json

import pytest

from workflow import charter, state
from workflow.render import RenderError, render, values


def good_charter():
    c = charter.defaults(["deploy staging"])
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    return c


def test_defaults_need_an_end_time():
    problems = charter.validate(charter.defaults())
    assert any("ends_at" in p for p in problems)
    assert not any("release.steps" in p for p in problems)


def test_defaults_release_from_the_profiles_steps():
    assert charter.defaults()["release"] == {"when": "never", "steps": [], "smoke_test": True}
    assert charter.defaults(["deploy staging", "build app"])["release"] == {"when": "end", "steps": ["deploy staging"], "smoke_test": True}
    c = charter.defaults()
    assert c["limits"]["ends_at"] is None and c["accepted_gaps"] == []
    q = next(q for q in charter.QUESTIONS if q["key"] == "limits")
    assert "required" in q["ask"] and "ends_at" in q["note"]


def test_good_charter_valid_but_not_approved():
    c = good_charter()
    assert charter.validate(c) == []
    assert any("not been approved" in p for p in charter.validate(c, require_approval=True))
    c["approved"] = {"by": "owner", "at": "2026-10-11T10:00:00Z", "source": "https://github.com/acme/demo/issues/1#issuecomment-1"}
    assert charter.validate(c, require_approval=True) == []


@pytest.mark.parametrize(
    "path,value,needle",
    [
        (("merge", "mode"), "yolo", "merge.mode"),
        (("limits", "max_parallel"), 0, "max_parallel"),
        (("limits", "ends_at"), "2026-10-13T03:30:00", "ends_at"),
        (("scope", "tickets"), [], "scope.tickets"),
        (("open_decisions",), "guess", "open_decisions"),
        (("notify", "failures"), "email", "notify"),
    ],
)
def test_invalid_fields(path, value, needle):
    c = good_charter()
    t = c
    for k in path[:-1]:
        t = t[k]
    t[path[-1]] = value
    assert any(needle in p for p in charter.validate(c))


def test_release_steps_checked_against_profile():
    c = good_charter()
    c["release"]["steps"] = ["deploy prod"]
    assert charter.check_against_profile(c, ["deploy staging"], [])


def test_markdown_and_diff():
    c = good_charter()
    md = charter.to_markdown(c)
    assert "Run charter" in md and "Not yet approved" in md and "workflow:stop" in md
    d = json.loads(json.dumps(c))
    d["scope"]["exclude"] = [143]
    assert charter.diff(c, d) == ['scope: {"tickets": "all-ready", "exclude": [], "follow_unblocked": true} -> {"tickets": "all-ready", "exclude": [143], "follow_unblocked": true}']


def test_state_roundtrip_keeps_the_body():
    s = state.empty(good_charter())
    s["tickets"]["201"] = {"status": "running", "attempts": 1, "session": "s1"}
    body = "# Tracking\n\nNarrative stays.\n"
    b2 = state.put(body, s)
    assert "Narrative stays." in b2
    assert state.get(b2) == s
    s["tickets"]["201"]["status"] = "merged"
    b3 = state.put(b2, s)
    assert b3.count("workflow-state:begin") == 1
    assert state.get(b3)["tickets"]["201"]["status"] == "merged"


def test_state_refuses_invalid_and_oversize():
    s = state.empty()
    s["tickets"]["x"] = {"status": "dancing"}
    with pytest.raises(state.StateError):
        state.put("", s)
    s = state.empty()
    s["for_owner"] = ["y" * 70_000]
    with pytest.raises(state.StateError, match="too close"):
        state.put("", s)
    s = state.empty()
    s["ledger"] = [{"what": "deployed"}]
    with pytest.raises(state.StateError, match="grant"):
        state.put("", s)


def test_merge_patch():
    assert state.merge_patch({"a": {"b": 1, "c": 2}}, {"a": {"b": None, "d": 3}}) == {"a": {"c": 2, "d": 3}}


TEMPLATE = "Ticket #{{ticket.number}} on {{ticket.branch}}\nAlongside: {{alongside}}\nRead: {{read_first}}\nDecisions: {{owner_decisions}}\n{{briefing}}\nWaived: {{merge.waived}}"


def test_render_fills_everything(profile):
    slots = {"alongside": "#213 (readings writes)", "read_first": "#232 comment 5", "owner_decisions": "none", "briefing": "Build it."}
    out = render(TEMPLATE, values(profile, {"number": 201, "title": "t"}, good_charter(), slots, 232, 233))
    assert "Ticket #201 on claude/build-201" in out
    assert "every required check must be green" in out


def test_render_refuses_empty_slot(profile):
    slots = {"alongside": "", "read_first": "x", "owner_decisions": "none", "briefing": "b"}
    with pytest.raises(RenderError, match="alongside"):
        render(TEMPLATE, values(profile, {"number": 1}, good_charter(), slots, 1, None))


def test_render_refuses_unknown_and_leftover(profile):
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "SEE_BELOW"}
    with pytest.raises(RenderError):
        render(TEMPLATE, values(profile, {"number": 1}, good_charter(), slots, 1, None))
    with pytest.raises(RenderError, match="no value for: nope"):
        render("{{nope}}", values(profile, {"number": 1}, good_charter(), {}, 1, None))


def test_real_ticket_template_renders(profile):
    from pathlib import Path

    tpl = (Path(__file__).resolve().parents[1] / "templates/ticket-session-prompt.md").read_text()
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
    c = good_charter()
    c["merge"]["waived_checks"] = ["Backend tests"]
    out = render(tpl, values(profile, {"number": 7, "title": "Readings tab"}, c, slots, 232, 233))
    assert "issue **#7** (Readings tab)" in out and "`claude/build-7`" in out and "Backend tests" in out
    assert "`trig_01abc`" in out and "fire_trigger" in out and "<!-- workflow:agent -->" in out
    assert "{{" not in out


def test_state_init_cli(tmp_path):
    import os, subprocess, sys
    from pathlib import Path

    cli = Path(__file__).resolve().parents[1] / "scripts/workflow.py"
    # An empty project, so no profile is read (this repository has its own).
    run = {"capture_output": True, "text": True, "cwd": tmp_path, "env": {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}}
    c = good_charter()
    f = tmp_path / "c.json"
    f.write_text(json.dumps(c))
    p = subprocess.run([sys.executable, str(cli), "state", "init", "--charter", str(f), "--run-id", "r1"], **run)
    assert p.returncode == 1 and "not been approved" in p.stderr
    c["approved"] = {"by": "o", "at": "2026-10-11T10:00:00Z", "source": "chat 10:00"}
    f.write_text(json.dumps(c))
    p = subprocess.run([sys.executable, str(cli), "state", "init", "--charter", str(f), "--run-id", "r1", "--by-hand", "9"], **run)
    s = json.loads(p.stdout)
    assert s["run_id"] == "r1" and s["by_hand_issue"] == 9 and state.validate(s) == []


# ---------- charter: limits, profile, combinations, gaps, reuse, plan ----------

from datetime import datetime, timezone  # noqa: E402

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
APPROVAL = {"by": "owner", "at": "2026-10-12T11:55:00Z", "source": "chat"}


def _approved(**limits):
    c = good_charter()
    c["approved"] = dict(APPROVAL)
    c["limits"].update(limits)
    return c


def test_ends_at_must_be_ahead_and_after_approval():
    c = _approved(ends_at="2026-10-12T11:00:00Z")
    problems = charter.validate(c, require_approval=True, now=NOW)
    assert any("has passed" in p for p in problems)
    assert any("must be after approved.at" in p for p in problems)
    # Without require_approval (a state read back later), a past end is fine.
    c = _approved(ends_at="2026-10-12T11:59:00Z")
    c["approved"]["at"] = "2026-10-12T11:50:00Z"
    assert charter.validate(c, now=NOW) == []
    assert charter.validate(_approved(ends_at="2026-10-13T03:30:00Z"), require_approval=True, now=NOW) == []


def test_approval_not_in_the_future():
    c = _approved()
    c["approved"]["at"] = "2026-10-12T12:20:00Z"
    assert any("approved.at" in p and "future" in p for p in charter.validate(c, now=NOW))
    c["approved"]["at"] = "2026-10-12T12:05:00Z"  # clock skew within 10 minutes
    assert charter.validate(c, now=NOW) == []


def test_parallel_within_sessions_and_scope_not_empty():
    c = good_charter()
    c["limits"].update(max_parallel=4, max_sessions=3)
    assert any("max_parallel can't be more than" in p for p in charter.validate(c))
    c = good_charter()
    c["scope"].update(tickets=[13, 143], exclude=[13, 143])
    assert any("leaves nothing to build" in p for p in charter.validate(c))
    c["scope"]["exclude"] = [13]
    assert charter.validate(c) == []


def test_waivers_against_the_profile_and_the_merge_mode():
    c = good_charter()
    c["merge"].update(mode="session", waived_checks=["Backend tests", "Typo check"])
    assert charter.validate(c) == []
    p = charter.check_against_profile(c, ["deploy staging"], ["Backend tests"])
    assert p == ["waived check 'Typo check' is not one of the profile's ci.required_checks ['Backend tests']"]
    c["merge"]["mode"] = "auto-merge"
    assert any("Auto-merge can't tell killed from failed; use mode session" in x for x in charter.validate(c))


def test_accepted_gaps():
    c = good_charter()
    c["accepted_gaps"] = ["no branch protection on main"]
    assert charter.validate(c) == []
    assert "no branch protection on main" in charter.to_markdown(c)
    c["accepted_gaps"] = [""]
    assert any("accepted_gaps" in p for p in charter.validate(c))
    assert "Safety setup gone without (the owner's choice):** none" in charter.to_markdown(good_charter())


def test_reuse_and_diff_report_approval():
    old = _approved()
    old["amendments"] = [{"change": "also #140", "source": "chat", "at": "2026-10-12T12:00:00Z"}]
    new = charter.reuse(old)
    assert new["approved"] is None and new["amendments"] == [] and new["limits"]["ends_at"] is None
    assert new["scope"] == old["scope"] and old["approved"]  # the old one is untouched
    d = charter.diff(old, new)
    assert any(x.startswith("approved:") for x in d) and any(x.startswith("limits:") for x in d)


def test_markdown_plan():
    md = charter.to_markdown(good_charter(), charter.parse_tickets("13:messages, #143:-"))
    assert "### Plan" in md and "1. #13 (messages)\n2. #143 (no area)" in md
    with pytest.raises(ValueError):
        charter.parse_tickets("x:y")


def _cli(*args, cwd=None, env=None):
    import os
    import subprocess
    import sys
    from pathlib import Path

    cli = Path(__file__).resolve().parents[1] / "scripts/workflow.py"
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(cli), *args], capture_output=True, text=True, cwd=cwd, env=e)


def test_charter_cli_validate_defaults_reuse_markdown(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(good_charter()))
    p = _cli("charter", "validate", str(f), cwd=tmp_path, env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 0 and "no profile found: release steps and waived checks weren't checked" in p.stderr
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\n[ci]\nrequired_checks=["CI"]\n[[release.steps]]\nname="ship"\nrun="x"\n'
    )
    p = _cli("charter", "defaults", env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert json.loads(p.stdout)["release"] == {"when": "end", "steps": ["ship"], "smoke_test": True}
    p = _cli("charter", "validate", str(f), env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 1 and "'deploy staging' is not in the profile" in p.stderr
    p = _cli("charter", "reuse", str(f))
    assert json.loads(p.stdout)["limits"]["ends_at"] is None
    p = _cli("charter", "markdown", str(f), "--tickets", "13:messages,143:-")
    assert p.returncode == 0 and "2. #143 (no area)" in p.stdout


# ---------- state: escaping and ambiguous bodies ----------


def test_state_strings_cannot_break_the_block():
    s = state.empty(good_charter())
    nasty = "```\n<!-- workflow-state:end -->\n<!-- workflow-state:begin -->"
    s["for_owner"] = [nasty]
    body = state.put("intro", s)
    assert body.count("```") == 2 and body.count("<!-- workflow-state:end") == 1
    assert "\\u003c" in body and "\\u0060" in body
    assert state.get(body)["for_owner"] == [nasty]
    assert state.get(state.put(body, state.get(body)))["for_owner"] == [nasty]
    # Reading accepts the unescaped form too.
    s2 = state.empty()
    s2["for_owner"] = ["a<b`c"]
    raw = f"{state.BEGIN}\n```json\n{json.dumps(s2)}\n```\n{state.END}"
    assert state.get(raw)["for_owner"] == ["a<b`c"]


def test_state_refuses_ambiguous_bodies():
    one = state.put("", state.empty())
    with pytest.raises(state.StateError, match="exactly one block"):
        state.get(one + "\n" + one)
    begin_only = "x\n" + state.BEGIN + "\n```json\n{}\n"
    with pytest.raises(state.StateError, match="delete both to start again from `state init`"):
        state.get(begin_only)
    with pytest.raises(state.StateError, match="exactly one block"):
        state.put(begin_only, state.empty())  # never appends a second block
    no_json = state.BEGIN + "\nnothing\n" + state.END
    with pytest.raises(state.StateError):
        state.put(no_json, state.empty())
    assert state.get("no state here") is None


# ---------- render ----------


def _slots(**kw):
    return {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", **kw}


def test_render_values_with_braces(profile):
    out = render("{{briefing}} / {{alongside}}", values(profile, {"number": 1}, good_charter(), _slots(briefing="Fix {{x}} binding in `{ a }`", alongside="{{"), 1, None))
    assert out == "Fix {{x}} binding in `{ a }` / {{"


def test_render_names_the_hole(profile):
    v = values(profile, {"number": 1}, good_charter(), _slots(briefing="TODO_FILL"), 1, None)
    with pytest.raises(RenderError, match="briefing"):
        render("{{briefing}}", v)
    v = values(profile, {"number": 1}, good_charter(), _slots(), 1, None)
    with pytest.raises(RenderError, match=r"\{\{ticket number\}\}"):
        render("{{ticket number}} {{briefing}}", v)
    with pytest.raises(RenderError, match="SEE_BELOW"):
        render("{{briefing}}\nSEE_BELOW", v)


def test_render_values_read_well(tmp_path):
    from workflow.profile import parse

    prof = parse(
        {
            "project": {"name": "d", "repo": "a/d", "owner": "rajat-t"},
            "commands": {
                "test_file": "pytest {file} -q",
                "suite": [{"name": "unit", "run": "pytest {files} -q", "files": "tests/test_*.py"}, {"name": "web", "run": "npm test", "cwd": "web"}],
            },
        },
        tmp_path,
    )
    v = values(prof, {"number": 1}, good_charter(), _slots(), 232, 233)
    assert v["by_hand.issue"] == "#233" and v["project.owner"] == "@rajat-t"
    assert v["commands.test_file"] == "`pytest {file} -q` (replace {file} with the test file's path)"
    assert "where {files} is the test files to run" in v["commands.suites"] and "run in `web`" in v["commands.suites"]
    assert values(prof, {"number": 1}, good_charter(), _slots(), 232, None)["by_hand.issue"].startswith("none yet: ")


# ---------- profile ----------


def test_profile_rejects_unknown_keys_and_tables(tmp_path):
    from workflow.profile import ProfileError, parse

    base = {"project": {"name": "d", "repo": "a/d"}}
    with pytest.raises(ProfileError, match=r"'required_check'.*allowed: killed_markers, none, path_filtered, required_checks"):
        parse({**base, "ci": {"required_check": ["x"]}}, tmp_path)
    with pytest.raises(ProfileError, match=r"unknown table \[area\]"):
        parse({**base, "area": {"x": []}}, tmp_path)
    with pytest.raises(ProfileError, match="commands.suite"):
        parse({**base, "commands": {"suite": [{"name": "u", "run": "x", "file": "y"}]}}, tmp_path)
    with pytest.raises(ProfileError, match="project.owner"):
        parse({"project": {"name": "d", "repo": "a/d", "owner": "@me"}}, tmp_path)
    parse({**base, "areas": {"anything": ["a/**"]}}, tmp_path)  # area names are free


def test_profile_check_warns_and_summarises(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x")
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="a/d"\nrules=["CLAUDE.md#safety", "docs/missing.md"]\n'
        '[ci]\nrequired_checks=["Backend tests"]\n[areas]\nmessages=["src/messages/**"]\n'
        '[guard]\ndeploy_commands=["scripts/deploy.sh"]\n[[release.steps]]\nname="deploy staging"\nrun="x"\n'
    )
    p = _cli("profile", "check", env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 0
    out = json.loads(p.stdout)
    assert "project.rules: docs/missing.md doesn't exist (from 'docs/missing.md')" in out["warnings"]
    assert "docs/missing.md" in p.stderr
    assert out["required_checks"] == ["Backend tests"] and out["areas"] == {"messages": ["src/messages/**"]}
    assert out["deploy_commands"] == ["scripts/deploy.sh"] and out["release_steps"] == ["deploy staging"]


def test_profile_run_environments_and_ci_fields(tmp_path):
    from workflow.profile import ProfileError, parse

    p = parse(
        {
            "project": {"name": "x", "repo": "a/b"},
            "ci": {"none": True, "path_filtered": ["docs"]},
            "run": {"ticket_environment": "tickets", "conductor_environment": "conductor", "permission_mode": "acceptEdits"},
        },
        tmp_path,
    )
    assert p.ci_none and p.path_filtered == ["docs"] and p.ticket_environment == "tickets" and p.permission_mode == "acceptEdits"
    with pytest.raises(ProfileError, match="permission_mode"):
        parse({"project": {"name": "x", "repo": "a/b"}, "run": {"permission_mode": "default"}}, tmp_path)
    with pytest.raises(ProfileError, match="ci.none"):
        parse({"project": {"name": "x", "repo": "a/b"}, "ci": {"none": "yes"}}, tmp_path)

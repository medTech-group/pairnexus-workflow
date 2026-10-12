import json

import pytest

from workflow import charter, state
from workflow.render import RenderError, render, values


def good_charter():
    c = charter.defaults()
    c["limits"]["ends_at"] = "2026-10-13T03:30:00Z"
    c["release"]["steps"] = ["deploy staging"]
    return c


def test_defaults_need_an_end_time_and_release_steps():
    problems = charter.validate(charter.defaults())
    assert any("ends_at" in p for p in problems)
    assert any("release.steps" in p for p in problems)


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
    assert charter.check_against_profile(c, ["deploy staging"])


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
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none"}
    c = good_charter()
    c["merge"]["waived_checks"] = ["Backend tests"]
    out = render(tpl, values(profile, {"number": 7, "title": "Readings tab"}, c, slots, 232, 233))
    assert "issue **#7** (Readings tab)" in out and "`claude/build-7`" in out and "Backend tests" in out
    assert "{{" not in out


def test_state_init_cli(tmp_path):
    import subprocess, sys
    from pathlib import Path

    cli = Path(__file__).resolve().parents[1] / "scripts/workflow.py"
    c = good_charter()
    f = tmp_path / "c.json"
    f.write_text(json.dumps(c))
    p = subprocess.run([sys.executable, str(cli), "state", "init", "--charter", str(f), "--run-id", "r1"], capture_output=True, text=True)
    assert p.returncode == 1 and "not been approved" in p.stderr
    c["approved"] = {"by": "o", "at": "2026-10-11T10:00:00Z", "source": "chat 10:00"}
    f.write_text(json.dumps(c))
    p = subprocess.run([sys.executable, str(cli), "state", "init", "--charter", str(f), "--run-id", "r1", "--by-hand", "9"], capture_output=True, text=True)
    s = json.loads(p.stdout)
    assert s["run_id"] == "r1" and s["by_hand_issue"] == 9 and state.validate(s) == []

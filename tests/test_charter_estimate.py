"""#123: the estimate before a run (#42). Seam 3, `workflow charter estimate`
fed files: past runs are tracking issues as the GitHub API returns them, their
bodies shaped like a real run's (the charter section, then the run state block).
Plus the "**Estimate:**" line on the one page, and seam 4, the conductor's
wording."""

import json
import os
import subprocess
import sys

import pytest

from workflow import state

from conftest import KIT

CLI = KIT / "scripts/workflow.py"
NOW = "2026-10-17T00:00:00Z"


def _cli(*args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=e)


@pytest.fixture
def env(tmp_path):
    """A profile with the defaults: 2 at once, 1 retry, 3 rounds, an explorer."""
    text = '[project]\nname="d"\nrepo="a/d"\nowner="o"\n[ci]\nrequired_checks=["CI"]\n[ui]\nexplorer="browser"\n[run]\n'
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(text)
    return {"CLAUDE_PROJECT_DIR": str(tmp_path)}


def _charter(tmp_path, env, preset=None, **limits):
    args = ["charter", "defaults"]
    p = _cli(*args, env=env)
    assert p.returncode == 0, p.stderr
    c = json.loads(p.stdout)
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    if preset:
        q = json.loads(_cli("charter", "questions", env=env).stdout)
        nums = next(x for x in q if x["key"] == "limits")["presets"][preset]
        c["preset"], c["review"] = preset, nums["review"]
        c["limits"].update(nums["limits"])
    c["limits"].update(limits)
    f = tmp_path / "charter.json"
    f.write_text(json.dumps(c))
    return str(f)


def _ticket(status="merged", attempts=1, start="2026-10-16T10:00:00Z", minutes=60):
    t = {"status": status, "attempts": attempts, "area": "x", "started_at": start}
    if status == "merged":
        h, m = divmod(600 + minutes, 60)
        t["merged_at"] = f"2026-10-16T{h:02d}:{m:02d}:00Z"
        t["pr"] = 200
    return t


def _body(tickets, run_id="2026-10-16-weekend"):
    """A tracking issue's body as the conductor writes it."""
    s = {
        "version": 1,
        "run_id": run_id,
        "status": "stopped",
        "charter": None,
        "tickets": tickets,
        "ledger": [],
        "overrides": [],
        "for_owner": [],
        "kickoff_tickets": [],
    }
    head = (
        f"# Run: {run_id}\n\nAn unattended build run under the `conductor` skill.\n\n## Now\n\nDone.\n\n"
        "<!-- workflow-charter:begin -->\n## Run charter\n\n- **Scope:** every ready ticket.\n<!-- workflow-charter:end -->\n\n"
        "<!-- workflow:agent -->"
    )
    return state.put(head, s)


def _raw(tickets):
    """A state block the conductor would never write: `state put` refuses it."""
    return f"# Run\n\n{state.BEGIN}\n```json\n{json.dumps({'version': 1, 'tickets': tickets})}\n```\n{state.END}\n"


def _issue(n, tickets=None, closed="2026-10-10T00:00:00Z", body=None, issue_state="closed", labels=("workflow:run",)):
    return {
        "number": n,
        "state": issue_state,
        "closed_at": closed if issue_state == "closed" else None,
        "labels": [{"name": l} for l in labels],
        "body": body if body is not None else _body(tickets),
    }


def _runs(tmp_path, issues):
    f = tmp_path / "runs.json"
    f.write_text(json.dumps(issues))
    return str(f)


def _estimate(env, charter, *args):
    p = _cli("charter", "estimate", charter, "--now", NOW, *args, "--json", env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout), p.stderr


# Two runs: 6 attempts over 4 tickets started (1.5 a ticket); merged in 30, 90 and 60 minutes (1 hour).
RUN_A = {"1": _ticket(attempts=1, minutes=30), "2": _ticket(attempts=2, minutes=90)}
RUN_B = {"3": _ticket(attempts=1, minutes=60), "4": _ticket("needs-human", attempts=2), "5": _ticket("queued", attempts=0)}


def test_no_past_runs_is_the_worst_case_at_an_hour_a_session(tmp_path, env):
    est, _ = _estimate(env, _charter(tmp_path, env), "--tickets", "7")
    assert (est["sessions"], est["hours"], est["runs_used"]) == (14, 7, 0)
    assert est["basis"] == "assuming about an hour a session"
    assert est["line"] == "About 14 ticket sessions over roughly 7 hours (7 tickets, up to 1 retry each), plus the conductor's check-ins"
    assert est["warnings"] == []


def test_the_worst_case_follows_retries_and_sessions_at_once(tmp_path, env):
    est, _ = _estimate(env, _charter(tmp_path, env, max_retries=2, max_parallel=4), "--tickets", "5")
    assert (est["sessions"], est["hours"]) == (15, 4)  # 5 × 3; ceil(15 / 4) waves
    est, _ = _estimate(env, _charter(tmp_path, env, preset="light"), "--tickets", "1")
    assert est["line"] == "About 1 ticket session over roughly 1 hour (1 ticket, no retries), plus the conductor's check-ins"


def test_one_past_run_is_still_the_defaults(tmp_path, env):
    runs = _runs(tmp_path, [_issue(140, RUN_A)])
    est, err = _estimate(env, _charter(tmp_path, env), "--tickets", "7", "--runs", runs)
    assert (est["sessions"], est["hours"], est["runs_used"]) == (14, 7, 0)
    assert est["basis"] == "assuming about an hour a session"
    assert "only 1 past run" in err


def test_two_past_runs_give_their_averages(tmp_path, env):
    runs = _runs(tmp_path, [_issue(140, RUN_A), _issue(150, RUN_B, closed="2026-10-12T00:00:00Z")])
    est, _ = _estimate(env, _charter(tmp_path, env), "--tickets", "7", "--runs", runs)
    # 7 × 1.5 = 10.5, so 11 sessions; ceil(11 / 2) = 6 waves at an hour each.
    assert (est["sessions"], est["hours"], est["runs_used"]) == (11, 6, 2)
    assert est["basis"] == "from your last 2 runs: about 1.5 sessions and 1 hour a ticket"
    assert "(7 tickets, about 1.5 sessions each)" in est["line"]


def test_past_runs_never_give_less_than_one_session_a_ticket_and_say_minutes(tmp_path, env):
    fast = {"1": _ticket(minutes=20), "2": {"status": "merged", "merged_at": "2026-10-16T10:40:00Z", "started_at": "2026-10-16T10:00:00Z"}}
    runs = _runs(tmp_path, [_issue(140, fast), _issue(141, fast)])
    est, _ = _estimate(env, _charter(tmp_path, env), "--tickets", "4", "--runs", runs)
    assert est["sessions"] == 4
    assert est["hours"] == 1  # 2 waves of half an hour, rounded to the hour
    assert est["basis"] == "from your last 2 runs: about 1 session and 30 minutes a ticket"


def test_at_most_five_runs_the_most_recent_and_none_that_merged_nothing(tmp_path, env):
    issues = [_issue(100 + i, RUN_A, closed=f"2026-10-0{i + 1}T00:00:00Z") for i in range(5)]
    # The oldest, at 5 attempts a ticket, would change the average if it were read.
    slow = {"9": _ticket(attempts=5)}
    issues.append(_issue(90, slow, closed="2026-09-01T00:00:00Z"))
    # Newer, but merged nothing: skipped without counting towards the five.
    issues.append(_issue(160, {"8": _ticket("needs-human", attempts=2)}, closed="2026-10-15T00:00:00Z"))
    # Open (the run in progress) and a run issue's pull request: not past runs.
    issues.append(_issue(170, slow, issue_state="open"))
    issues.append({**_issue(171, slow), "pull_request": {}})
    issues.append(_issue(172, slow, labels=("bug",)))
    est, err = _estimate(env, _charter(tmp_path, env), "--tickets", "2", "--runs", _runs(tmp_path, issues))
    assert est["runs_used"] == 5
    assert est["basis"].startswith("from your last 5 runs: about 1.5 sessions")
    assert err == ""

    # With the oldest five only, the slow one is among them.
    issues = issues[1:6]
    est, _ = _estimate(env, _charter(tmp_path, env), "--tickets", "2", "--runs", _runs(tmp_path, issues))
    assert est["runs_used"] == 5
    assert "about 1.9 sessions" in est["basis"]  # (4 × 3 + 5) / (4 × 2 + 1)


def test_the_end_time_warning(tmp_path, env):
    c = _charter(tmp_path, env, ends_at="2026-10-17T05:00:00Z")
    est, _ = _estimate(env, c, "--tickets", "7")
    assert est["hours"] == 7
    assert len(est["warnings"]) == 1
    assert est["warnings"][0].startswith("The end time stops it after about 5 of 7 tickets")
    # With time enough, no warning.
    est, _ = _estimate(env, _charter(tmp_path, env, ends_at="2026-10-17T07:00:00Z"), "--tickets", "7")
    assert est["warnings"] == []
    # Already past: nothing gets done.
    est, _ = _estimate(env, _charter(tmp_path, env, ends_at="2026-10-16T07:00:00Z"), "--tickets", "7")
    assert est["warnings"][0].startswith("The end time stops it before any of its 7 tickets is done")


def test_the_max_sessions_warning(tmp_path, env):
    est, _ = _estimate(env, _charter(tmp_path, env, max_sessions=10), "--tickets", "7")
    assert est["warnings"] == ["10 sessions in all covers 7 tickets with 3 retries; up to 1 retry each needs 14."]
    est, _ = _estimate(env, _charter(tmp_path, env, max_sessions=5), "--tickets", "7")
    assert est["warnings"][0].startswith("5 sessions in all covers only 5 of the 7 tickets, with no retries")
    est, _ = _estimate(env, _charter(tmp_path, env, max_sessions=14), "--tickets", "7")
    assert est["warnings"] == []


def test_a_lighter_review_with_a_security_review_ticket(tmp_path, env):
    light = _charter(tmp_path, env, preset="light")
    est, _ = _estimate(env, light, "--tickets", "3", "--security", "12,#14")
    (w,) = est["warnings"]
    assert "lighter than the project's default" in w
    assert "#12, #14" in w and "security review" in w
    # No security-review ticket, or the project's own review: no warning.
    est, _ = _estimate(env, light, "--tickets", "3")
    assert est["warnings"] == []
    est, _ = _estimate(env, _charter(tmp_path, env), "--tickets", "3", "--security", "12")
    assert est["warnings"] == []
    est, _ = _estimate(env, _charter(tmp_path, env, preset="thorough"), "--tickets", "3", "--security", "12")
    assert est["warnings"] == []


def test_text_and_json_agree(tmp_path, env):
    c = _charter(tmp_path, env, max_sessions=10, ends_at="2026-10-17T05:00:00Z")
    runs = _runs(tmp_path, [_issue(140, RUN_A), _issue(150, RUN_B)])
    est, _ = _estimate(env, c, "--tickets", "7", "--runs", runs)
    p = _cli("charter", "estimate", c, "--now", NOW, "--tickets", "7", "--runs", runs, env=env)
    assert p.returncode == 0, p.stderr
    lines = p.stdout.strip().splitlines()
    assert lines[0] == est["line"] + "."
    assert f"{est['sessions']} ticket sessions" in lines[0] and f"{est['hours']} hours" in lines[0]
    assert lines[1] == f"Basis: {est['basis']}."
    assert lines[2:] == [f"Warning: {w}" for w in est["warnings"]]
    assert len(est["warnings"]) == 2
    for key in ("sessions", "hours", "basis", "runs_used", "warnings"):
        assert key in est


def test_a_malformed_past_body_is_skipped_with_a_note(tmp_path, env):
    good = [_issue(140, RUN_A), _issue(150, RUN_B)]
    bad = [
        _issue(141, body="# Run\n\nno state here"),
        _issue(142, body="<!-- workflow-state:begin -->\n```json\n{not json\n```\n<!-- workflow-state:end -->"),
        _issue(143, body=_raw({"1": {"status": "merged", "attempts": "two"}})),
        _issue(144, body=_raw({"1": {"status": "lost"}})),
        _issue(146, body=_raw([1, 2])),
        {**_issue(145, {}), "body": None},
    ]
    est, err = _estimate(env, _charter(tmp_path, env), "--tickets", "7", "--runs", _runs(tmp_path, good + bad))
    assert est["runs_used"] == 2 and est["sessions"] == 11
    for n in (141, 142, 143, 144, 145, 146):
        assert f"#{n} skipped" in err
    assert len(est["notes"]) == 6
    # Not even a list of issues: a clean error, not a crash.
    p = _cli("charter", "estimate", _charter(tmp_path, env), "--tickets", "7", "--runs", _runs(tmp_path, "nope"), env=env)
    assert p.returncode == 1 and "Traceback" not in p.stderr


def test_the_tickets_as_a_number_a_plan_or_the_charters_plan(tmp_path, env):
    c = _charter(tmp_path, env)
    est, _ = _estimate(env, c, "--tickets", "13:messages,143:-,150:-")
    assert est["tickets"] == 3
    p = _cli("charter", "estimate", c, env=env)
    assert p.returncode == 1 and "--tickets" in p.stderr
    data = json.loads(open(c).read())
    data["plan"] = [1, 2]
    open(c, "w").write(json.dumps(data))
    est, _ = _estimate(env, c)
    assert est["tickets"] == 2


def test_an_unapproved_charter_without_an_end_time_is_fine(tmp_path, env):
    c = _charter(tmp_path, env, ends_at=None)
    est, _ = _estimate(env, c, "--tickets", "2")
    assert est["sessions"] == 4 and est["warnings"] == []


def test_never_money(tmp_path, env):
    est, _ = _estimate(env, _charter(tmp_path, env, max_sessions=3, ends_at="2026-10-17T01:00:00Z"), "--tickets", "7", "--security", "1")
    text = json.dumps(est).lower()
    for word in ("$", "cost", "price", "usd", "dollar", "money"):
        assert word not in text


def _approvable(tmp_path, env):
    c = json.loads(open(_charter(tmp_path, env)).read())
    c["plan"] = [13, 143]
    f = tmp_path / "c2.json"
    f.write_text(json.dumps(c))
    return str(f)


def test_markdown_with_an_estimate_adds_its_line(tmp_path, env):
    c = _approvable(tmp_path, env)
    est = tmp_path / "est.json"
    p = _cli("charter", "estimate", c, "--tickets", "7", "--now", NOW, "--json", env={**env})
    est.write_text(p.stdout)
    page = _cli("charter", "markdown", c, "--estimate", str(est), env=env)
    assert page.returncode == 0, page.stderr
    want = "- **Estimate:** About 14 ticket sessions over roughly 7 hours (7 tickets, up to 1 retry each), plus the conductor's check-ins; assuming about an hour a session."
    assert want in page.stdout
    lines = page.stdout.splitlines()
    assert lines.index(want) == next(i for i, l in enumerate(lines) if l.startswith("- **Review:**")) + 1
    # Without one, no line.
    assert "**Estimate:**" not in _cli("charter", "markdown", c, env=env).stdout


def test_markdown_shows_the_estimates_warnings_under_it(tmp_path, env):
    c = json.loads(open(_approvable(tmp_path, env)).read())
    c["limits"]["max_sessions"] = 10
    f = tmp_path / "c3.json"
    f.write_text(json.dumps(c))
    est = tmp_path / "est.json"
    est.write_text(_cli("charter", "estimate", str(f), "--tickets", "7", "--json", env=env).stdout)
    page = _cli("charter", "markdown", str(f), "--estimate", str(est), env=env).stdout
    assert "  - 10 sessions in all covers 7 tickets with 3 retries; up to 1 retry each needs 14." in page


def test_splice_carries_the_estimate_and_a_bad_one_is_refused(tmp_path, env):
    c = _approvable(tmp_path, env)
    est = tmp_path / "est.json"
    est.write_text(_cli("charter", "estimate", c, "--tickets", "2", "--json", env=env).stdout)
    body = tmp_path / "body.md"
    body.write_text("# Run\n\n<!-- workflow-charter:begin -->\nold\n<!-- workflow-charter:end -->\n")
    p = _cli("charter", "splice", "--body", str(body), "--charter", c, "--estimate", str(est), env=env)
    assert p.returncode == 0, p.stderr
    assert "- **Estimate:** About 4 ticket sessions" in p.stdout
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"sessions": 4}))
    for args in (("markdown", c), ("splice", "--body", str(body), "--charter", c)):
        p = _cli("charter", *args, "--estimate", str(bad), env=env)
        assert p.returncode == 1 and "estimate --json" in p.stderr and "Traceback" not in p.stderr


# ---------- seam 4: the conductor's wording ----------


def _conductor() -> str:
    return (KIT / "skills/conductor/SKILL.md").read_text(encoding="utf-8")


def test_the_conductor_offers_the_presets_first_with_the_estimate():
    text = _conductor()
    kickoff = text.split("### 2. The kick-off", 1)[1].split("\n## Each check-in", 1)[0]
    assert "presets first" in kickoff
    assert "`run.preset`" in kickoff
    assert "WF charter estimate" in kickoff
    assert kickoff.index("presets first") < kickoff.index("WF charter estimate")
    assert "every change of preset or number" in kickoff
    assert "sessions and hours, never money" in kickoff


def test_the_conductor_puts_the_estimate_on_the_one_page():
    text = _conductor()
    splices = [l for l in text.splitlines() if "WF charter splice" in l]
    assert splices and all("--estimate estimate.json" in l for l in splices)


def test_the_capacity_line_is_unchanged_with_the_estimate_beside_it():
    cap = _conductor().split("**Capacity**", 1)[1].split("\n**", 1)[0]
    assert "You can't read the account's usage directly." in cap
    assert "the estimate" in cap

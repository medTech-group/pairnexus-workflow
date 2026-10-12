from workflow.issues import area_of, blockers_of, readiness, startable


def issue(n, state="open", labels=("ready-for-agent",), body="", reason=None, title=None):
    return {"number": n, "state": state, "state_reason": reason, "labels": [{"name": l} for l in labels], "body": body, "title": title or f"t{n}"}


def test_blockers_both_conventions_and_dedup():
    body = "Blocked by: #3, #4\n\n## What\nx\n\n## Blocked by\n\n- #4\n- #5 (spec)\n- acme/demo#6\n\n## Next\n- #9"
    assert blockers_of(body) == [3, 4, 5, 6]


def test_blockers_none():
    assert blockers_of("## Blocked by\n\nNone") == []
    assert blockers_of("") == []


def test_area():
    assert area_of("Part of #1\nArea: Messages\n") == "messages"
    assert area_of("no area here") is None


def test_ready_only_when_blockers_closed_as_completed():
    issues = [
        issue(1, state="closed", reason="completed", labels=()),
        issue(2, state="closed", reason="not_planned", labels=()),
        issue(10, body="Blocked by: #1"),
        issue(11, body="Blocked by: #2"),
        issue(12, body="Blocked by: #99"),
        issue(13, body="## Blocked by\n- #10"),
    ]
    v = {x.number: x for x in readiness(issues, [])}
    assert v[10].ready
    assert not v[11].ready and "not_planned" in v[11].reasons[0]
    assert not v[12].ready and "unknown" in v[12].reasons[0]
    assert not v[13].ready and "open #10" in v[13].reasons[0]


def test_not_ready_reasons():
    issues = [
        issue(20, labels=("ready-for-agent", "needs-human")),
        issue(21, labels=("ready-for-agent", "owner-task")),
        issue(22, labels=("ready-for-agent", "workflow:in-progress")),
        issue(23),
        issue(24),
        issue(25, labels=("needs-triage",)),
        issue(26, labels=("ready-for-agent", "wayfinder:map")),
        {"number": 27, "state": "open", "labels": ["ready-for-agent"], "pull_request": {}},
    ]
    prs = [{"number": 100, "state": "open", "body": "Closes #23"}, {"number": 101, "state": "closed", "body": "Fixes #24"}]
    v = {x.number: x for x in readiness(issues, prs, exclude={24})}
    assert set(v) == {20, 21, 22, 23, 24}
    assert "needs-human" in v[20].reasons[0]
    assert "owner-task" in v[21].reasons[0]
    assert "claimed" in v[22].reasons[0]
    assert "#100" in v[23].reasons[0]
    assert "excluded" in v[24].reasons[0]
    v2 = {x.number: x for x in readiness(issues, prs, claimed_ok={22})}
    assert v2[22].ready


def test_startable_one_per_area():
    issues = [issue(30, body="Area: a"), issue(31, body="Area: a"), issue(32, body="Area: b"), issue(33)]
    vs = readiness(issues, [])
    assert [v.number for v in startable(vs, [], 3)] == [30, 32, 33]
    assert [v.number for v in startable(vs, ["b"], 2)] == [30, 33]
    assert [v.number for v in startable(vs, ["a"], 2, overrides={31})] == [31, 32]
    assert startable(vs, [], 0) == []

import json

import pytest

from workflow import cli
from workflow.issues import area_of, blockers_of, closed_by_open_prs, parse_numbers, readiness, startable


def issue(n, state="open", labels=("ready-for-agent",), body="", reason=None, title=None, **extra):
    return {"number": n, "state": state, "state_reason": reason, "labels": [{"name": l} for l in labels], "body": body, "title": title or f"t{n}", **extra}


def test_blockers_both_conventions_and_dedup():
    body = "Blocked by: #3, #4\n\n## What\nx\n\n## Blocked by\n\n- #4\n- #5 (spec)\n- acme/demo#6\n\n## Next\n- #9"
    assert blockers_of(body, "acme/demo") == [3, 4, 5, 6]
    assert blockers_of(body, "ACME/Demo") == [3, 4, 5, 6]


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


# ---------- specs, maps and parents aren't build tickets ----------


def test_specs_maps_and_parents_are_not_build_tickets():
    issues = [
        issue(40, labels=("ready-for-agent", "spec")),
        issue(41, labels=("ready-for-agent", "Wayfinder:Map")),
        issue(42, title="Spec: sharing with my doctor"),
        issue(43, title="  SPEC: lowercase too"),
        issue(44, sub_issues_summary={"total": 3, "completed": 1}),
        issue(45, sub_issues_summary={"total": 0}),
        issue(46, title="Specify the thing"),
    ]
    assert [v.number for v in readiness(issues, [])] == [45, 46]


# ---------- labels ----------


def test_labels_case_insensitive_and_ready_for_human_blocks():
    issues = [
        issue(50, labels=("Ready-for-agent",)),
        issue(51, labels=("ready-for-agent", "ready-for-human")),
        issue(52, labels=("READY-FOR-AGENT", "Needs-Human")),
        issue(53, labels=("ready-for-agent", "Workflow:In-Progress")),
        {"number": 54, "state": "open", "labels": ["Ready-For-Agent"], "title": "plain strings"},
    ]
    v = {x.number: x for x in readiness(issues, [])}
    assert v[50].ready and v[54].ready
    assert v[51].reasons == ["labelled ready-for-human"]
    assert v[52].reasons == ["labelled needs-human"]
    assert "claimed" in v[53].reasons[0]


# ---------- blockers ----------


def test_blocked_by_without_colon():
    assert blockers_of("Blocked by #9") == [9]
    assert blockers_of("**Blocked by** #9 and #10") == [9, 10]
    assert blockers_of("**Blocked by:** #3") == [3]


def test_blocked_by_list_on_following_lines():
    body = "Blocked by:\n- #3\n- #4\n\nSee #99 for context\n"
    assert blockers_of(body) == [3, 4]
    body = "Blocked by:\n- #3\n## What\n- #7\n"
    assert blockers_of(body) == [3]
    assert blockers_of("Blocked by:\n- None\n- #5\n\nlater #6") == []


def test_blocked_by_section_none_with_refs():
    assert blockers_of("## Blocked by\n\nNone, but see #9\n\n## What\nx") == []
    assert blockers_of("## Blocked by\n- None (see #9)\n") == []
    assert blockers_of("Blocked by: None, but see #9") == []
    assert blockers_of("## Blocked by\n\n- #4\n- #5\n") == [4, 5]


def test_cross_repo_blockers():
    body = "Blocked by: other/lib#3, acme/demo#4, #5\n"
    assert blockers_of(body, "acme/demo") == ["other/lib#3", 4, 5]
    assert blockers_of(body, "Acme/Demo") == ["other/lib#3", 4, 5]
    assert blockers_of("Blocked by foo#3") == []
    issues = [
        issue(4, state="closed", reason="completed", labels=()),
        issue(5, state="closed", reason="completed", labels=()),
        issue(60, body=body),
        issue(61, body="## Blocked by\n- ACME/demo#4\n"),
    ]
    v = {x.number: x for x in readiness(issues, [], repo="acme/demo")}
    assert v[60].reasons == ["blocker other/lib#3 is in another repository"]
    assert v[61].ready


def test_github_native_dependencies_block():
    issues = [
        issue(62, issue_dependencies_summary={"blocked_by": 1, "total_blocked_by": 2, "blocking": 0}),
        issue(63, issue_dependencies_summary={"blocked_by": 0, "total_blocked_by": 2, "blocking": 1}),
    ]
    v = {x.number: x for x in readiness(issues, [])}
    assert v[62].reasons == ["blocked by a GitHub issue dependency"]
    assert v[63].ready


# ---------- closing PRs ----------


def test_closing_pr_forms():
    prs = [
        {"number": 200, "state": "open", "body": "closes:#8"},
        {"number": 201, "state": "open", "body": "Closes: #9"},
        {"number": 202, "state": "open", "body": "Fixes acme/demo#3", "draft": True},
        {"number": 203, "state": "open", "body": "Fixes other/lib#4"},
        {"number": 204, "state": "open", "body": "Resolves https://github.com/Acme/Demo/issues/12"},
        {"number": 205, "state": "open", "body": "Resolves https://github.com/other/lib/issues/13"},
        {"number": 206, "state": "open", "body": "prefixes #14"},
    ]
    assert closed_by_open_prs(prs, "acme/demo") == {8: 200, 9: 201, 3: 202, 12: 204}
    # Without the profile's repo, qualified refs can't be matched.
    assert closed_by_open_prs(prs) == {8: 200, 9: 201}


# ---------- areas ----------


@pytest.mark.parametrize(
    "body",
    [
        "Area: messages",
        "**Area:** messages",
        "**Area**: messages",
        "- Area: messages",
        "Area: `messages`",
        "Area: Messages (backend)",
        "## Area\n\nmessages\n",
        "## Area\n- `Messages`\n",
        "Part of #1\n\n## Area: messages\n",
    ],
)
def test_area_forms(body):
    assert area_of(body) == "messages"


def test_area_absent():
    assert area_of("## Areas of concern\nmessages") is None
    assert area_of("## Area\n\n## Next\nx") is None
    assert area_of("Areas: x") is None


def test_unknown_area_is_a_note_not_a_block():
    issues = [issue(70, body="Area: billing"), issue(71, body="Area: Messages"), issue(72)]
    v = {x.number: x for x in readiness(issues, [], areas=["messages"])}
    assert v[70].ready and "billing" in v[70].notes[0]
    assert v[71].ready and v[71].notes == []
    assert v[72].notes == []
    assert all(not x.notes for x in readiness(issues, []))


# ---------- startable ----------


def test_infra_tickets_start_first():
    issues = [issue(80), issue(81, labels=("ready-for-agent", "Workflow:Infra")), issue(82), issue(83, labels=("ready-for-agent", "workflow:infra"))]
    vs = readiness(issues, [])
    assert [v.number for v in vs] == [80, 81, 82, 83]
    assert [v.number for v in startable(vs, [], 3)] == [81, 83, 80]


def test_running_areas_casefolded():
    vs = readiness([issue(84, body="Area: messages"), issue(85)], [])
    assert [v.number for v in startable(vs, ["Messages"], 2)] == [85]


def test_parse_numbers():
    assert parse_numbers("13, #143") == {13, 143}
    assert parse_numbers(" # 7 ,, ") == {7}
    assert parse_numbers(None) == set()
    with pytest.raises(ValueError, match="x1"):
        parse_numbers("12, x1")


# ---------- the `ready` command ----------


@pytest.fixture
def ready_files(tmp_path, monkeypatch):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\n[areas]\nmessages = ["src/messages/**"]\nreadings = ["src/readings/**"]\n'
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    issues = [
        issue(1, body="Area: messages"),
        issue(2, body="Area: messages"),
        issue(3, body="Area: readings"),
        issue(4, body="Area: billing"),
        issue(5, body="Blocked by: other/lib#1"),
        issue(13),
        issue(143),
    ]
    prs = [{"number": 300, "state": "open", "body": "Fixes acme/demo#143"}]
    (tmp_path / "issues.json").write_text(json.dumps(issues))
    (tmp_path / "prs.json").write_text(json.dumps(prs))
    return ["ready", "--issues", str(tmp_path / "issues.json"), "--prs", str(tmp_path / "prs.json")]


def test_ready_cli_json(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--exclude", "13, #143", "--slots", "5"]) == 0
    out = json.loads(capsys.readouterr().out)
    not_ready = {v["number"]: v["reasons"] for v in out["not_ready"]}
    assert not_ready[13] == ["excluded"]
    assert "excluded" in not_ready[143] and "open PR #300 closes it" in not_ready[143]
    assert not_ready[5] == ["blocker other/lib#1 is in another repository"]
    assert out["start_now"] == [1, 3, 4]
    assert [v["notes"] for v in out["ready"] if v["number"] == 4][0]


def test_ready_cli_only_override_and_running_area(ready_files, capsys):
    assert cli.main([*ready_files, "--json", "--only", "1,2,3", "--running-area", "MESSAGES", "--slots", "5"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {v["number"] for v in out["ready"] + out["not_ready"]} == {1, 2, 3}
    assert out["start_now"] == [3]
    assert cli.main([*ready_files, "--json", "--only", "1,2,3", "--override", "#2", "--running-area", "messages", "--slots", "5"]) == 0
    assert json.loads(capsys.readouterr().out)["start_now"] == [2, 3]


def test_ready_cli_text_shows_notes(ready_files, capsys):
    assert cli.main([*ready_files, "--only", "4"]) == 0
    out = capsys.readouterr().out
    assert "READY #4 [billing]" in out and "note: area billing" in out


def test_ready_cli_bad_numbers_are_a_clean_error(ready_files, capsys):
    assert cli.main([*ready_files, "--exclude", "13, abc"]) == 2
    err = capsys.readouterr().err
    assert "abc" in err and "Traceback" not in err
    assert cli.main([*ready_files, "--only", "1;2"]) == 2


# ---------- fetching ----------


class _Done:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_fetch_slurps_pages_and_drops_prs(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        pages = [[{"number": 1, "body": "a ][ b"}, {"number": 2, "pull_request": {}}], [{"number": 3}]]
        return _Done(0, json.dumps(pages))

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert [i["number"] for i in cli._fetch("acme/demo", "issues")] == [1, 3]
    assert "--slurp" in calls[0]
    assert cli._fetch("acme/demo", "issues")[0]["body"] == "a ][ b"


def test_fetch_falls_back_without_slurp(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if "--slurp" in cmd:
            return _Done(1, err="unknown flag: --slurp")
        return _Done(0, json.dumps([{"number": 1, "body": "x][y"}]) + "\n" + json.dumps([{"number": 2}, {"number": 5, "pull_request": {}}]) + "\n")

    monkeypatch.setattr(cli.subprocess, "run", run)
    assert [i["number"] for i in cli._fetch("acme/demo", "issues")] == [1, 2]
    assert len(calls) == 2
    calls.clear()
    assert [i["number"] for i in cli._fetch("acme/demo", "pulls")] == [1, 2, 5]


def test_fetch_other_failure_is_a_clean_exit(monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: _Done(1, err="HTTP 404"))
    with pytest.raises(SystemExit, match="HTTP 404"):
        cli._fetch("acme/demo", "issues")


# ---------- review: URLs and quotes in blockers, --only "", one-word areas ----------


def test_blockers_read_issue_urls_and_quoted_lines():
    from workflow.issues import read_area  # noqa: F401

    body = (
        "> Blocked by: https://github.com/acme/demo/issues/12, #13\n\n"
        "## Blocked by\n"
        "- https://github.com/Acme/Demo/issues/14#issuecomment-5\n"
        "- https://github.com/other/lib/issues/3\n"
        "> - #15\n"
    )
    assert blockers_of(body, "acme/demo") == [12, 13, 14, "other/lib#3", 15]
    assert blockers_of("> > **Blocked by:**\n> > - #7\n> > - https://github.com/acme/demo/issues/8\n", "acme/demo") == [7, 8]
    assert blockers_of("> Blocked by: None (see https://github.com/acme/demo/issues/9)", "acme/demo") == []
    issues = [issue(12, state="closed", reason="completed", labels=()), issue(20, body="Blocked by https://github.com/acme/demo/issues/12")]
    v = {x.number: x for x in readiness(issues, [], repo="acme/demo")}
    assert v[20].ready and v[20].blockers == [12]


def test_ready_cli_only_empty_is_a_clean_error(ready_files, capsys):
    assert cli.main([*ready_files, "--only", ""]) == 2
    err = capsys.readouterr().err
    assert "--only was given no ticket numbers" in err and "Traceback" not in err
    assert cli.main([*ready_files, "--only", " , "]) == 2


def test_an_area_is_one_word():
    from workflow.issues import read_area

    areas = ["messages", "clock"]
    assert read_area("Area: messages and sharing", areas) == ("messages", None)
    area, note = read_area("Area: the clock module", areas)
    assert area == "the-clock-module" and note.startswith("Area should be one word from [clock, messages]")
    area, note = read_area("Area: Clock Module", None)
    assert area == "clock-module" and "Area should be one word" in note
    area, note = read_area("Area: mesages", areas)
    assert area == "mesages" and "isn't one of the profile's areas" in note and "treated as its own area" in note
    assert read_area("Area: Messages (backend)", areas) == ("messages", None)
    assert read_area("no area", areas) == (None, None)
    issues = [issue(90, body="Area: the clock module"), issue(91, body="Area: mesages")]
    v = {x.number: x for x in readiness(issues, [], areas=areas)}
    assert v[90].area == "the-clock-module" and "one word" in v[90].notes[0] and v[90].ready
    assert "treated as its own area" in v[91].notes[0]

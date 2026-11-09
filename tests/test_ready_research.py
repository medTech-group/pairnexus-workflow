"""#572: `workflow ready` never lists a research issue as a ready build
ticket. The kit reads every issue carrying the `research` label as research
(the `study` skill's section 5), as `workflow status` does (#514), so a
`ready-for-agent` one is not ready, with a reason naming the label, and never
"start now". Through `cli.main`, fed files."""

import json

import pytest

from workflow import cli
from workflow.issues import RESEARCH_LABEL, readiness

RESEARCH = {
    "number": 71,
    "labels": [{"name": "research"}, {"name": "ready-for-agent"}],
    "body": "Area: start\n\n## Blocked by\n\nNone",
    "state": "open",
    "title": "research note wrong",
}
TICKET = {
    "number": 72,
    "labels": [{"name": "ready-for-agent"}],
    "body": "Area: doctor\n\n## Blocked by\n\nNone",
    "state": "open",
    "title": "a build ticket",
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))  # no profile
    monkeypatch.chdir(tmp_path)
    return tmp_path


def ready(project, capsys, issues, *extra):
    (project / "issues.json").write_text(json.dumps(issues))
    (project / "prs.json").write_text("[]")
    capsys.readouterr()
    assert cli.main(["ready", "--issues", str(project / "issues.json"), "--prs", str(project / "prs.json"), *extra]) == 0
    return capsys.readouterr().out


def test_a_research_issue_is_not_ready_and_its_reason_names_the_label(project, capsys):
    out = json.loads(ready(project, capsys, [RESEARCH], "--json"))
    assert out["ready"] == []
    assert [v["number"] for v in out["not_ready"]] == [71]
    assert any("`research`" in r for r in out["not_ready"][0]["reasons"]), out["not_ready"][0]["reasons"]
    assert out["start_now"] == []


def test_the_text_says_wait_with_the_reason_and_starts_nothing(project, capsys):
    out = ready(project, capsys, [RESEARCH])
    line = next(l for l in out.splitlines() if "#71" in l and not l.startswith("start now"))
    assert line.startswith("wait ")
    assert "`research`" in line
    assert out.splitlines()[-1] == "start now: nothing"


def test_a_build_ticket_beside_it_still_starts(project, capsys):
    out = json.loads(ready(project, capsys, [RESEARCH, TICKET], "--json"))
    assert [v["number"] for v in out["ready"]] == [72]
    assert out["start_now"] == [72]


def test_the_label_is_matched_as_the_kit_names_it():
    (v,) = readiness([RESEARCH], [])
    assert not v.ready
    assert any(f"`{RESEARCH_LABEL}`" in r for r in v.reasons)

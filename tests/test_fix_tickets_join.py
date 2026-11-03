"""#378: tickets to fix old bugs, tickets to fix late findings and split tickets
join a run (spec #412, "Runs"). A ready ticket whose last machine line is
`<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`, from an account
with write access, naming a ticket of the run, joins the run's state and
starts once unblocked through `workflow ready --first` (#372); the charter's
one page says so; one whose source can't merge within the run is listed in the
report. Seams: the run's state (`state.join`, `state.joined`, `workflow state
join` and `workflow state joined`) and the rendered one page."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from changelog_notes import since_0110
from workflow import charter, state

KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "scripts/workflow.py"
OWNER = "owner-login"
WRITE = {OWNER: "admin", "writer": "write", "keeper": "maintain", "reader": "read", "triager": "triage", "outsider": "none"}


def _read(rel):
    return (KIT / rel).read_text(encoding="utf-8")


def _flat(text):
    return " ".join(text.split())


def _line(src=378, kind="split"):
    return f"<!-- workflow:fix-ticket from={src} kind={kind} -->"


def _issue(n, body="", labels=("ready-for-agent",), login=OWNER, st="open", **extra):
    return {"number": n, "title": f"Ticket {n}", "state": st, "body": body, "user": {"login": login},
            "labels": [{"name": x} for x in labels], **extra}


def _fix(n, src=378, kind="split", login=OWNER, labels=("ready-for-agent",), blocked="None", area="conductor", **extra):
    body = f"Area: {area}\n\n## What to build\n\nx\n\n## Blocked by\n\n{blocked}\n\n{_line(src, kind)}\n<!-- workflow:agent -->\n"
    return _issue(n, body, labels=labels, login=login, **extra)


def _state(tickets=None, exclude=()):
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["scope"]["exclude"] = list(exclude)
    s = state.empty(c)
    s["run_id"] = "2026-11-03-join"
    s["tickets"] = tickets if tickets is not None else {"378": {"status": "running", "attempts": 1}}
    return s


def _join(s, issues, perms=WRITE):
    return state.join(s, issues, perms)


# ---------- the run's state: who joins ----------


@pytest.mark.parametrize("kind", ["old", "late", "split"])
def test_a_ready_fix_ticket_naming_a_ticket_of_the_run_joins(kind):
    s = _state()
    out = _join(s, [_fix(501, kind=kind)])
    assert s["joined"] == {"501": {"from": 378, "kind": kind}}
    assert [j["number"] for j in out["joined"]] == [501]
    assert out["first"] == [501]
    assert state.validate(s) == []


def test_the_last_machine_line_in_a_body_counts():
    # A body may quote another ticket's line above its own: the last one is the ticket's.
    quoted_run = _issue(501, f"It quotes:\n\n> {_line(378)}\n\n{_line(999)}\n")
    quoted_other = _issue(502, f"It quotes:\n\n> {_line(999)}\n\n{_line(378, 'late')}\n")
    s = _state()
    out = _join(s, [quoted_run, quoted_other])
    assert s["joined"] == {"502": {"from": 378, "kind": "late"}}
    assert out["first"] == [502]


@pytest.mark.parametrize(
    "line",
    [
        "<!-- workflow:fix-ticket from=378 kind=other -->",
        "<!-- workflow:fix-ticket from=abc kind=split -->",
        "<!-- workflow:fix-ticket kind=split from=378 -->",
        "<!-- workflow:fix-ticket from=378 -->",
        "workflow:fix-ticket from=378 kind=split",
    ],
)
def test_a_line_not_in_the_exact_form_never_joins(line):
    s = _state()
    out = _join(s, [_issue(501, f"x\n{line}\n")])
    assert not s.get("joined") and out["first"] == [] and out["not_joined"] == []


@pytest.mark.parametrize("label", ["owner-task", "ready-for-human"])
def test_owner_tasks_carry_the_line_but_never_join(label):
    s = _state()
    out = _join(s, [_fix(501, labels=(label,)), _fix(502, labels=(label, "ready-for-agent"))])
    assert not s.get("joined") and out["first"] == []
    assert sorted(x["number"] for x in out["not_joined"]) == [501, 502]
    assert all(label in x["why"] for x in out["not_joined"])


def test_a_ticket_not_labelled_ready_never_joins():
    s = _state()
    out = _join(s, [_fix(501, labels=("needs-triage",))])
    assert not s.get("joined")
    assert [x["number"] for x in out["not_joined"]] == [501] and "ready-for-agent" in out["not_joined"][0]["why"]


@pytest.mark.parametrize("login", ["reader", "triager", "outsider", "stranger"])
def test_a_ticket_from_an_account_without_write_access_never_joins(login):
    s = _state()
    out = _join(s, [_fix(501, login=login)])
    assert not s.get("joined") and out["first"] == []
    assert out["not_joined"] == [{"number": 501, "from": 378, "kind": "split", "why": f"@{login} has no write access"}]


@pytest.mark.parametrize("login", ["writer", "keeper", "OWNER-LOGIN"])
def test_write_maintain_and_admin_all_count_and_logins_match_without_case(login):
    s = _state()
    _join(s, [_fix(501, login=login)])
    assert "501" in s["joined"]


def test_a_ticket_with_no_author_never_joins():
    s = _state()
    t = _fix(501)
    del t["user"]
    out = _join(s, [t])
    assert not s.get("joined") and out["not_joined"][0]["why"] == "its author can't be read"


def test_a_ticket_naming_a_ticket_outside_the_run_is_left_alone():
    # Another run's (or attended work's) fix ticket: not this run's to join, nor to report.
    s = _state()
    out = _join(s, [_fix(501, src=999, login="reader"), _fix(502, src=999)])
    assert not s.get("joined") and out == {"joined": [], "not_joined": [], "first": []}


def test_any_ticket_of_the_run_counts_as_a_source_whatever_its_status():
    s = _state({"378": {"status": "merged"}, "379": {"status": "needs-human"}, "380": {"status": "queued"}})
    _join(s, [_fix(501, src=378, kind="old"), _fix(502, src=379, kind="late"), _fix(503, src=380)])
    assert sorted(s["joined"]) == ["501", "502", "503"]


def test_a_fix_ticket_of_a_joined_ticket_joins_too_in_any_order():
    s = _state()
    # #502 comes first in the list but names #501, which joins only from #378.
    _join(s, [_fix(502, src=501, kind="late"), _fix(501)])
    assert s["joined"] == {"501": {"from": 378, "kind": "split"}, "502": {"from": 501, "kind": "late"}}


def test_an_excluded_ticket_never_joins():
    s = _state(exclude=[501])
    out = _join(s, [_fix(501)])
    assert not s.get("joined") and out["not_joined"][0]["why"] == "excluded by the charter's scope"


@pytest.mark.parametrize("extra", [{"state": "closed"}, {"pull_request": {"url": "x"}}])
def test_closed_issues_and_pull_requests_never_join(extra):
    s = _state()
    out = _join(s, [_fix(501, **{"st": extra.get("state", "open")}, **{k: v for k, v in extra.items() if k != "state"})])
    assert not s.get("joined") and out["not_joined"] == []


def test_joining_again_adds_nothing_and_first_leaves_out_started_tickets():
    s = _state()
    _join(s, [_fix(501), _fix(503, kind="old")])
    again = _join(s, [_fix(501), _fix(503, kind="old")])
    assert again["joined"] == [] and again["first"] == [501, 503]
    # #501 starts: it is in the state's tickets now, so `--first` no longer needs it.
    s["tickets"]["501"] = {"status": "running", "attempts": 1}
    assert _join(s, [_fix(501), _fix(503, kind="old")])["first"] == [503]


def test_a_joined_ticket_stays_joined_when_it_changes_later():
    # Readiness is `workflow ready`'s: a joined ticket relabelled or closed stays in the record.
    s = _state()
    _join(s, [_fix(501)])
    out = _join(s, [_fix(501, labels=("owner-task",))])
    assert s["joined"] == {"501": {"from": 378, "kind": "split"}} and out["first"] == [501] and out["not_joined"] == []


def test_a_ticket_already_of_the_run_isnt_joined():
    s = _state({"378": {"status": "running"}, "501": {"status": "queued"}})
    out = _join(s, [_fix(501)])
    assert not s.get("joined") and out == {"joined": [], "not_joined": [], "first": []}


def test_first_is_in_number_order():
    s = _state()
    assert _join(s, [_fix(510), _fix(502, kind="old"), _fix(507, kind="late")])["first"] == [502, 507, 510]


@pytest.mark.parametrize(
    "joined",
    [
        [],
        {"x": {"from": 378, "kind": "split"}},
        {"501": {"from": "378", "kind": "split"}},
        {"501": {"from": 0, "kind": "split"}},
        {"501": {"from": 378, "kind": "other"}},
        {"501": {"from": 378}},
        {"501": "split"},
    ],
)
def test_the_state_refuses_a_malformed_joined_record(joined):
    s = _state()
    s["joined"] = joined
    assert any(p.startswith("joined") for p in state.validate(s))


def test_join_refuses_a_state_that_isnt_valid():
    s = _state()
    s["joined"] = {"501": "split"}
    with pytest.raises(state.StateError):
        _join(s, [_fix(502)])


# ---------- the report: who didn't start ----------


def test_joined_tells_each_joined_tickets_fate_for_the_report():
    s = _state({"378": {"status": "needs-human"}, "380": {"status": "merged"}, "504": {"status": "merged", "pr": 9}})
    s["joined"] = {
        "501": {"from": 378, "kind": "split"},  # its source can't merge: listed
        "502": {"from": 380, "kind": "late"},  # its source merged, not started
        "503": {"from": 501, "kind": "late"},  # its source is a joined ticket that never started
        "504": {"from": 380, "kind": "old"},  # started and merged
    }
    out = {j["number"]: j for j in state.joined(s)}
    assert out[501] == {"number": 501, "from": 378, "kind": "split", "status": None, "source_status": "needs-human",
                        "waits_on_source": True}
    assert out[502]["status"] is None and out[502]["waits_on_source"] is False
    assert out[503]["source_status"] is None and out[503]["waits_on_source"] is True
    assert out[504]["status"] == "merged" and out[504]["waits_on_source"] is False
    assert [j["number"] for j in state.joined(s)] == [501, 502, 503, 504]


# ---------- the CLI ----------


def _project(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n\n[areas]\nconductor = []\nbuild = []\nstart = []\ndocs = []\n'
    )


def _cli(tmp_path, *args):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)}
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, cwd=tmp_path, env=env)


def _files(tmp_path, s, issues, perms=WRITE):
    _project(tmp_path)
    (tmp_path / "body.md").write_text(state.put("## Run\n", s))
    (tmp_path / "issues.json").write_text(json.dumps(issues))
    (tmp_path / "perms.json").write_text(json.dumps(perms))


def test_state_join_records_the_joined_tickets_in_the_body(tmp_path):
    _files(tmp_path, _state(), [_fix(501), _fix(502, login="reader", kind="old")])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == [
        "joined #501 (split, from #378)",
        "not joined #502 (old, from #378): @reader has no write access",
        "first: 501",
    ]
    s = state.get((tmp_path / "new.md").read_text())
    assert s["joined"] == {"501": {"from": 378, "kind": "split"}}


def test_state_join_json_gives_the_first_list(tmp_path):
    _files(tmp_path, _state(), [_fix(501)])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json",
             "--out", "new.md", "--json")
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["first"] == [501]


def test_state_join_with_nothing_to_join_prints_an_empty_first(tmp_path):
    _files(tmp_path, _state(), [])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == ["first:"]


@pytest.mark.parametrize(
    "args",
    [
        ["--issues", "issues.json", "--permissions", "perms.json"],  # no --out
        ["--permissions", "perms.json", "--out", "new.md"],  # no issues
        ["--issues", "issues.json", "--out", "new.md"],  # no permissions
    ],
)
def test_state_join_needs_its_inputs(tmp_path, args):
    _files(tmp_path, _state(), [_fix(501)])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", *args)
    assert p.returncode != 0 and not (tmp_path / "new.md").exists()


def test_state_join_refuses_permissions_it_cant_read(tmp_path):
    _files(tmp_path, _state(), [_fix(501)], perms=[{"login": OWNER}])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode != 0 and "permissions" in p.stderr and not (tmp_path / "new.md").exists()


def test_state_join_reads_the_permissions_as_github_gives_them(tmp_path):
    perms = [{"permission": "admin", "user": {"login": OWNER}}, {"permission": "read", "user": {"login": "reader"}}]
    _files(tmp_path, _state(), [_fix(501), _fix(502, login="reader")], perms=perms)
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert state.get((tmp_path / "new.md").read_text())["joined"] == {"501": {"from": 378, "kind": "split"}}


def test_state_join_fetch_reads_the_open_issues_and_their_authors_permissions(tmp_path, monkeypatch):
    import fake_gh

    issues = [_fix(501), _fix(502, login="reader", kind="old"), _fix(503, st="closed"), _issue(400, "no line", login="someone")]
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages(issues[:2], issues[2:]),
        f"repos/acme/demo/collaborators/{OWNER}/permission": {"permission": "admin", "user": {"login": OWNER}},
        "repos/acme/demo/collaborators/reader/permission": {"permission": "read", "user": {"login": "reader"}},
    })
    _files(tmp_path, _state(), [])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--fetch", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines()[-1] == "first: 501"
    assert state.get((tmp_path / "new.md").read_text())["joined"] == {"501": {"from": 378, "kind": "split"}}
    # Only the authors of open tickets with a machine line are asked about.
    assert sorted(x for x in gh.paths() if "collaborators" in x) == [
        f"repos/acme/demo/collaborators/{OWNER}/permission", "repos/acme/demo/collaborators/reader/permission"]


def test_state_joined_prints_the_report_lines(tmp_path):
    s = _state({"378": {"status": "needs-human"}, "380": {"status": "merged"}, "504": {"status": "running"}})
    s["joined"] = {"501": {"from": 378, "kind": "split"}, "502": {"from": 380, "kind": "late"}, "504": {"from": 380, "kind": "old"}}
    _files(tmp_path, s, [])
    p = _cli(tmp_path, "state", "joined", "--body", "body.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == [
        "#501 (split, from #378): not started; its source #378 didn't merge in this run",
        "#502 (late, from #380): not started",
        "#504 (old, from #380): running",
    ]


def test_a_joined_ticket_starts_once_unblocked_after_infra_through_ready_first(tmp_path):
    # The end to end: `state join`'s first list given to `ready --first`.
    infra = _issue(600, "Area: build\n\n## Blocked by\n\nNone\n", labels=("ready-for-agent", "workflow:infra"))
    other = _issue(400, "Area: docs\n\n## Blocked by\n\nNone\n")
    split = _fix(501, blocked="- #378")  # waits on its source's pull request
    old = _fix(502, kind="old", area="start")
    source = _issue(378, "Area: conductor\n", labels=("workflow:in-progress",))
    issues = [infra, other, split, old, source]
    _files(tmp_path, _state(), issues)
    (tmp_path / "prs.json").write_text("[]")
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json",
             "--out", "new.md", "--json")
    first = ",".join(str(n) for n in json.loads(p.stdout)["first"])
    assert first == "501,502"

    def start_now(issues):
        (tmp_path / "issues.json").write_text(json.dumps(issues))
        r = _cli(tmp_path, "ready", "--issues", "issues.json", "--prs", "prs.json", "--first", first, "--slots", "3", "--json")
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)["start_now"]

    # The split waits on #378; the old one starts after the infra ticket, ahead of the rest.
    assert start_now(issues) == [600, 502, 400]
    # #378 merged and closed: the split starts too, ahead of #400.
    closed = {**source, "state": "closed", "state_reason": "completed"}
    assert start_now([infra, other, split, old, closed]) == [600, 501, 502]


# ---------- the one page ----------


def _page(c):
    return charter.to_markdown(c, plan=[(378, "conductor")])


def _joining(page):
    return next(ln for ln in page.splitlines() if ln.startswith("- **Tickets filed during the run:**"))


@pytest.mark.parametrize("scope", ["all-ready", [378]])
def test_the_one_page_says_fix_and_split_tickets_join(scope):
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    c["scope"]["tickets"] = scope
    line = _joining(_page(c))
    for words in (
        "tickets to fix old bugs, tickets to fix late findings and split tickets",
        "join the run, whatever its scope",
        "`<!-- workflow:fix-ticket from=<n> kind=old|late|split -->`",
        "from an account with write access",
        "naming a ticket of the run",
        "labelled `ready-for-agent`",
        "start once unblocked, after infra tickets and ahead of the run's other tickets not yet started",
        "owner tasks and excluded tickets never join",
        "one whose source can't merge in this run is listed in the run report",
    ):
        assert words in line, words


def test_the_joining_line_comes_right_after_the_scope():
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    lines = _page(c).splitlines()
    i = next(i for i, ln in enumerate(lines) if ln.startswith("- **Scope:**"))
    assert lines[i + 1].startswith("- **Tickets filed during the run:**")


def test_the_spliced_one_page_carries_the_line(tmp_path):
    _project(tmp_path)
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    (tmp_path / "charter.json").write_text(json.dumps(c))
    (tmp_path / "body.md").write_text("<!-- workflow-charter:begin -->\nold\n<!-- workflow-charter:end -->\n")
    p = _cli(tmp_path, "charter", "splice", "--body", "body.md", "--charter", "charter.json", "--tickets", "378:conductor")
    assert p.returncode == 0, p.stderr
    assert "- **Tickets filed during the run:**" in p.stdout


# ---------- the kit's text ----------


def _conductor():
    return _flat(_read("skills/conductor/SKILL.md"))


def test_the_conductor_joins_them_before_starting_new_tickets():
    step = _flat(_read("skills/conductor/SKILL.md").split("**5. Start sessions,**", 1)[1].split("**6. Release**", 1)[0])
    assert "WF state join" in step
    assert "--first <its `first`>" in step
    # Added to `--only` too, as the infra tickets are, so a pinned scope still starts them.
    assert "plus every open workflow:infra ticket and every ticket in the state's `joined`" in step
    assert step.index("WF state join") < step.index("WF ready --fetch")


def test_the_conductor_names_them_at_the_go_and_in_the_report():
    text = _conductor()
    assert "Tickets filed during the run" in text
    assert "WF state joined" in text


def test_the_run_report_lists_those_whose_source_didnt_merge():
    report = _flat(_read("skills/run-report/SKILL.md"))
    assert "WF state joined" in report
    assert "its source" in report and "didn't merge in this run" in report


def test_the_charter_doc_describes_joining():
    doc = _flat(_read("docs/charter.md"))
    assert "`joined`" in doc and "workflow state join" in doc and "--first" in doc


def test_the_changelog_has_the_note():
    unreleased = since_0110(_read("CHANGELOG.md"))
    assert "(#378, part of spec #412)" in unreleased and "workflow state join" in unreleased

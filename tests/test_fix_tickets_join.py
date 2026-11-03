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


def test_a_line_naming_a_number_past_18_digits_is_no_machine_line_and_stops_nothing():
    # Anyone can open an issue: a `from=` too long for `int()` must never stop the others joining.
    s = _state()
    out = _join(s, [_issue(500, f"x\n<!-- workflow:fix-ticket from={'3' * 5000} kind=old -->\n", login="outsider"),
                    _issue(499, "x\n<!-- workflow:fix-ticket from=1234567890123456789 kind=old -->\n"), _fix(501)])
    assert s["joined"] == {"501": {"from": 378, "kind": "split"}} and out["not_joined"] == []
    assert state.authors(s, [_issue(500, f"<!-- workflow:fix-ticket from={'3' * 5000} kind=old -->")]) == []


def test_a_last_line_past_18_digits_never_lets_a_quoted_line_above_it_count():
    # The last line is the ticket's own: one too long is no machine line, and the quoted one above it never counts.
    body = f"Quoting:\n> {_line(378)}\n\n## Blocked by\n\nNone\n\n<!-- workflow:fix-ticket from=1234567890123456789 kind=old -->\n"
    s = _state()
    out = _join(s, [_issue(501, body)])
    assert not s.get("joined") and out == {"joined": [], "not_joined": [], "first": []}
    assert state.fix_line(body) is None


def test_eighteen_digits_still_count_as_a_ticket_number():
    # The accepting side of the limit: an 18-digit source (leading zeros aside) and an 18-digit issue number.
    big = 10**18 - 1
    s = _state({str(big): {"status": "running"}})
    t = _fix(big - 1, src=big)
    out = _join(s, [t, _issue(501, f"x\n<!-- workflow:fix-ticket from=000378 kind=old -->\n")])
    assert s["joined"] == {str(big - 1): {"from": big, "kind": "split"}} and out["first"] == [big - 1]
    s = _state()
    t = _fix(big)
    assert _join(s, [t, _issue(501, "x\n<!-- workflow:fix-ticket from=000378 kind=old -->\n")])["first"] == [501, big]
    assert state.validate(s) == []


def test_an_issue_numbered_past_18_digits_is_left_alone():
    s = _state()
    t = _fix(501)
    t["number"] = 10**18
    assert _join(s, [t])["first"] == [] and not s.get("joined")


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


@pytest.mark.parametrize("login", ["reader", "triager", "outsider"])
def test_a_ticket_from_an_account_without_write_access_never_joins(login):
    s = _state()
    out = _join(s, [_fix(501, login=login)])
    assert not s.get("joined") and out["first"] == []
    # The login in backticks, never an @-mention that would notify the account when the reason is posted.
    assert out["not_joined"] == [{"number": 501, "from": 378, "kind": "split", "why": f"`{login}` has no write access"}]


def test_a_ticket_whose_authors_permission_wasnt_given_never_joins():
    s = _state()
    out = _join(s, [_fix(501, login="stranger")])
    assert not s.get("joined") and out["not_joined"][0]["why"] == "`stranger`'s permission wasn't given"


def test_labels_are_read_without_case_as_workflow_ready_reads_them():
    s = _state()
    out = _join(s, [
        _fix(501, labels=("Ready-For-Agent",)),
        _fix(502, labels=("ready-for-agent", "Owner-Task")),
        _fix(503, labels=("READY-FOR-HUMAN", "ready-for-agent")),
    ])
    assert s["joined"] == {"501": {"from": 378, "kind": "split"}}
    assert [x["number"] for x in out["not_joined"]] == [502, 503]


@pytest.mark.parametrize("number", [0, -5, True, "501"])
def test_an_issue_without_a_real_number_is_left_alone(number):
    s = _state()
    t = _fix(501)
    t["number"] = number
    out = _join(s, [t, _fix(502)])
    assert s["joined"] == {"502": {"from": 378, "kind": "split"}} and out["not_joined"] == []


@pytest.mark.parametrize("st", [None, "", "OPEN "])
def test_an_issue_whose_state_isnt_open_is_left_alone(st):
    s = _state()
    t = _fix(501)
    if st is None:
        del t["state"]
    else:
        t["state"] = st
    assert _join(s, [t])["first"] == [] and not s.get("joined")


def test_a_ticket_blocked_by_its_source_is_recorded_as_waiting_on_it():
    s = _state({"378": {"status": "running"}, "377": {"status": "merged"}})
    _join(s, [
        _fix(501, blocked="- #378"),
        _fix(502, kind="late", blocked="#377, #400"),
        _fix(503, kind="late", blocked="- #400"),  # blocked, but not by its source
        _fix(504, kind="old"),
    ])
    assert s["joined"] == {
        "501": {"from": 378, "kind": "split", "waits": True},
        "502": {"from": 378, "kind": "late"},
        "503": {"from": 378, "kind": "late"},
        "504": {"from": 378, "kind": "old"},
    }


@pytest.mark.parametrize("ref", ["acme/demo#378", "ACME/Demo#378", "https://github.com/acme/demo/issues/378"])
def test_waits_reads_the_blockers_as_workflow_ready_does(ref):
    # This repository's own refs, written in full, name the source too; another repository's don't.
    s = _state()
    state.join(s, [_fix(501, kind="late", blocked=f"- {ref}"), _fix(502, kind="late", blocked="- other/demo#378")], WRITE, "acme/demo")
    assert s["joined"]["501"] == {"from": 378, "kind": "late", "waits": True}
    assert s["joined"]["502"] == {"from": 378, "kind": "late"}


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
    _join(s, [_fix(502, src=501, kind="late", blocked="- #501"), _fix(501)])
    assert s["joined"] == {"501": {"from": 378, "kind": "split"}, "502": {"from": 501, "kind": "late", "waits": True}}


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
        {"501": {"from": 378, "kind": "split", "waits": "yes"}},
        {"501": {"from": 378, "kind": "split", "extra": 1}},
        # Keys written one way only, so a ticket can never be recorded twice.
        {"²": {"from": 378, "kind": "old"}},
        {"0501": {"from": 378, "kind": "old"}},
        {"٥٠١": {"from": 378, "kind": "old"}},
        {"0": {"from": 378, "kind": "old"}},
        {"1" * 19: {"from": 378, "kind": "old"}},  # past 18 digits: the refusing side of the limit
    ],
)
def test_the_state_refuses_a_malformed_joined_record(joined):
    s = _state()
    s["joined"] = joined
    assert any(p.startswith("joined") for p in state.validate(s))


@pytest.mark.parametrize("bad", [{"501": "split"}, {"²": {"from": 378, "kind": "old"}}])
def test_join_and_joined_refuse_a_state_that_isnt_valid(bad):
    s = _state()
    s["joined"] = bad
    with pytest.raises(state.StateError):
        _join(s, [_fix(502)])
    with pytest.raises(state.StateError):
        state.joined(s)


# ---------- the report: who didn't start ----------


def test_joined_tells_each_joined_tickets_fate_for_the_report():
    s = _state({"378": {"status": "needs-human"}, "380": {"status": "merged"}, "504": {"status": "merged", "pr": 9}})
    s["joined"] = {
        "501": {"from": 378, "kind": "split", "waits": True},  # its source can't merge: listed
        "502": {"from": 380, "kind": "late", "waits": True},  # its source merged, not started
        "503": {"from": 501, "kind": "late", "waits": True},  # its source is a joined ticket that never started
        "504": {"from": 380, "kind": "old"},  # started and merged
        "505": {"from": 378, "kind": "old"},  # never waits on its source, which didn't merge
    }
    out = {j["number"]: j for j in state.joined(s)}
    assert out[501] == {"number": 501, "from": 378, "kind": "split", "status": None, "source_status": "needs-human",
                        "waits_on_source": True}
    assert out[502]["status"] is None and out[502]["waits_on_source"] is False
    assert out[503]["source_status"] is None and out[503]["waits_on_source"] is True
    assert out[504]["status"] == "merged" and out[504]["waits_on_source"] is False
    assert out[505]["status"] is None and out[505]["waits_on_source"] is False
    assert [j["number"] for j in state.joined(s)] == [501, 502, 503, 504, 505]


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
        "not joined #502 (old, from #378): `reader` has no write access",
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


def test_state_join_reads_mixed_pages_and_wrapped_lists(tmp_path):
    _files(tmp_path, _state(), {"issues": [[_fix(501)], _fix(502, kind="old")]})
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines()[-1] == "first: 501,502"


@pytest.mark.parametrize(
    "issues",
    [{"message": "Bad credentials", "documentation_url": "https://docs.github.com/rest"}, [[_fix(501)], {"message": "Not Found"}], 5, "hello", {}],
)
def test_state_join_refuses_issues_that_arent_issues(tmp_path, issues):
    # A saved GitHub error is never read as "nobody filed anything".
    _files(tmp_path, _state(), issues)
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 1 and "isn't an issue" in p.stderr and "Traceback" not in p.stderr
    assert not (tmp_path / "new.md").exists()
    if isinstance(issues, dict) and "message" in issues:
        assert "Bad credentials" in p.stderr


@pytest.mark.parametrize("name", ["issues", "permissions"])
def test_state_join_says_a_null_file_holds_null(tmp_path, name):
    _files(tmp_path, _state(), [_fix(501)])
    (tmp_path / f"{'perms' if name == 'permissions' else 'issues'}.json").write_text("null")
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 1 and f"--{name}: the file holds null" in p.stderr


def test_state_join_fetch_refuses_a_bad_state_before_fetching(tmp_path, monkeypatch):
    import fake_gh

    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.pages([_fix(501)])})
    _project(tmp_path)
    s = _state()
    s["joined"] = [{"from": 378, "kind": "old"}]
    (tmp_path / "body.md").write_text(state.put("x", _state()).replace(state._dump(_state()), state._dump(s)))
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--fetch", "--out", "new.md")
    assert p.returncode == 1 and "the state has problems" in p.stderr and "Traceback" not in p.stderr
    assert gh.paths() == [] and not (tmp_path / "new.md").exists()


def test_state_join_reads_blockers_with_the_profiles_repo(tmp_path):
    _files(tmp_path, _state(), [_fix(501, kind="late", blocked="- https://github.com/acme/demo/issues/378")])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert state.get((tmp_path / "new.md").read_text())["joined"]["501"] == {"from": 378, "kind": "late", "waits": True}


def test_state_join_refuses_fetch_with_files(tmp_path):
    _files(tmp_path, _state(), [_fix(501)])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--fetch", "--issues", "issues.json", "--out", "new.md")
    assert p.returncode != 0 and "not both" in p.stderr and not (tmp_path / "new.md").exists()


def test_state_join_reads_the_permissions_as_github_gives_them(tmp_path):
    perms = [{"permission": "admin", "user": {"login": OWNER}}, {"permission": "read", "user": {"login": "reader"}}]
    _files(tmp_path, _state(), [_fix(501), _fix(502, login="reader")], perms=perms)
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--issues", "issues.json", "--permissions", "perms.json", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert state.get((tmp_path / "new.md").read_text())["joined"] == {"501": {"from": 378, "kind": "split"}}


def test_state_join_fetch_reads_the_open_issues_and_their_authors_permissions(tmp_path, monkeypatch):
    import fake_gh

    issues = [_fix(501), _fix(502, login="reader", kind="old"), _fix(503, st="closed", login="closer"),
              _issue(400, "no line", login="someone"), _fix(504, src=999, login="elsewhere"),
              _fix(505, src=501, kind="late", login="chained")]  # names #501, which joins in the same check-in
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages(issues[:2], issues[2:]),
        f"repos/acme/demo/collaborators/{OWNER}/permission": {"permission": "admin", "user": {"login": OWNER}},
        "repos/acme/demo/collaborators/reader/permission": {"permission": "read", "user": {"login": "reader"}},
        "repos/acme/demo/collaborators/chained/permission": {"permission": "write", "user": {"login": "chained"}},
    })
    _files(tmp_path, _state(), [])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--fetch", "--out", "new.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines()[-1] == "first: 501,505"
    assert state.get((tmp_path / "new.md").read_text())["joined"] == {
        "501": {"from": 378, "kind": "split"}, "505": {"from": 501, "kind": "late"}}
    # Only the authors of open tickets whose machine line names a ticket of the run, or another such ticket, are asked about.
    assert sorted(x for x in gh.paths() if "collaborators" in x) == sorted([
        "repos/acme/demo/collaborators/chained/permission", f"repos/acme/demo/collaborators/{OWNER}/permission",
        "repos/acme/demo/collaborators/reader/permission"])


def test_state_join_fetch_says_which_flags_to_give_when_the_issues_cant_be_read(tmp_path, monkeypatch):
    import fake_gh

    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 500)")})
    _files(tmp_path, _state(), [])
    p = _cli(tmp_path, "state", "join", "--body", "body.md", "--fetch", "--out", "new.md")
    assert p.returncode != 0 and "--issues F and --permissions F" in p.stderr and "--prs" not in p.stderr
    assert not (tmp_path / "new.md").exists()


def test_state_joined_prints_the_report_lines(tmp_path):
    s = _state({"378": {"status": "needs-human"}, "380": {"status": "merged"}, "504": {"status": "running"}})
    s["joined"] = {"501": {"from": 378, "kind": "split", "waits": True}, "502": {"from": 380, "kind": "late", "waits": True},
                   "503": {"from": 378, "kind": "old"}, "504": {"from": 380, "kind": "old"}}
    _files(tmp_path, s, [])
    p = _cli(tmp_path, "state", "joined", "--body", "body.md")
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == [
        "#501 (split, from #378): not started; its source #378 didn't merge in this run",
        "#502 (late, from #380): not started",
        "#503 (old, from #378): not started",
        "#504 (old, from #380): running",
    ]


def test_state_joined_with_nothing_joined_says_so(tmp_path):
    _files(tmp_path, _state(), [])
    p = _cli(tmp_path, "state", "joined", "--body", "body.md")
    assert p.returncode == 0 and p.stdout == "nothing joined\n"


def test_state_joined_refuses_a_bad_state_without_a_traceback(tmp_path):
    _project(tmp_path)
    s = _state()
    s["joined"] = {"²": {"from": 378, "kind": "old"}}
    block = state.put("x", _state()).replace(state._dump(_state()), state._dump(s))
    (tmp_path / "body.md").write_text(block)
    p = _cli(tmp_path, "state", "joined", "--body", "body.md")
    assert p.returncode == 1 and "Traceback" not in p.stderr and "joined key" in p.stderr


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
        "posted by an account with write access",
        "naming a ticket of the run in its last",
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


def _checkin():
    return _read("skills/conductor/SKILL.md").split("## Each check-in", 1)[1].split("## A pull request that needs a code fix", 1)[0]


def test_the_conductor_joins_them_at_every_check_in_before_judging_done():
    # Before step 2 judges "Done" (and winding down too), so a ticket filed in a source's last review isn't missed.
    before = _flat(_checkin().split("**1. Read the state.**", 1)[1].split("**2. Stop or wind down?**", 1)[0])
    assert "WF state join --body .workflow/run/body.md --fetch --out .workflow/run/body.md --json" in before
    assert "At every check-in, winding down too, record who joined before judging step 2" in before
    assert "for step 2 and \"Done\" too" in before


def test_the_conductor_starts_them_through_ready_first():
    step = _flat(_checkin().split("**5. Start sessions,**", 1)[1].split("**6. Release**", 1)[0])
    assert "--first <join's first>" in step and "`--first` takes step 1's `first`" in step
    # Added to `--only` too, as the infra tickets are, so a pinned scope still starts them.
    assert "plus every open workflow:infra ticket and every ticket in the state's `joined`" in step
    assert "`" not in step.split("--first <", 1)[1].split(">", 1)[0]  # no code span nested in the command


def test_the_conductor_joins_once_more_before_the_report():
    report = _flat(_read("skills/conductor/SKILL.md").split("4. **The report.**", 1)[1].split("5. **Wind up.**", 1)[0])
    # First, with nothing else pending, its body written to the issue and the state read back, so the step's
    # later edits and its one state write keep `joined` (and the join never drops them).
    assert report.startswith("First, so a ticket filed since the last check-in joins too, run `WF state join` as check-in step 1 does: "
                             "write its body to the issue and read the state back from it")
    assert report.count("WF state join ") + report.count("WF state join`") == 1
    assert report.index("WF state join`") < report.index("look again at each revert still `opened`") < report.index("WF state joined")


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

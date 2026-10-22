"""#234: `workflow ready` notes a ticket whose parent spec has no clean review
for its current body, and `next`, `start` and the conductor's kick-off show
it. Through `cli.main`, fed issue JSON and the fake `gh` (#232's seam 2), and
the kit's text (seam 3)."""

import json
from datetime import date, timedelta

import pytest

import fake_gh
from changelog_notes import since_0110
from conftest import KIT
from workflow import cli
from workflow.issues import SPEC_REVIEW_SINCE
from workflow.reviews import record

SPEC_BODY = "## Problem Statement\r\n\r\nThe notes list shows the oldest note first.\r\n"
NOTE = "spec #10 has no clean review: check it before building"
UNREAD = "spec #10: couldn't read its reviews"
PERM = "repos/acme/demo/collaborators/{}/permission"


def _day(offset: int) -> str:
    return (date.fromisoformat(SPEC_REVIEW_SINCE) + timedelta(days=offset)).isoformat()


def spec(number=10, created=None, body=SPEC_BODY, comments=None, **kw) -> dict:
    out = {
        "number": number,
        "title": "Spec: newest note first",
        "state": "open",
        "labels": [{"name": "spec"}, {"name": "ready-for-agent"}],
        "body": body,
        "created_at": created or f"{SPEC_REVIEW_SINCE}T00:00:00Z",
        "sub_issues_summary": {"total": 1, "completed": 0},
        "comments": [] if comments is None else comments,
    }
    out.update(kw)
    return out


def ticket(number=11, section="## Parent\n\n#10 (newest note first)", labels=("ready-for-agent",), **kw) -> dict:
    out = {
        "number": number,
        "title": f"Ticket {number}",
        "state": "open",
        "labels": [{"name": l} for l in labels],
        "body": f"Area: notes\n\n{section}\n\n## Blocked by\n\nNone",
        "created_at": f"{SPEC_REVIEW_SINCE}T01:00:00Z",
        "comments": 0,
    }
    out.update(kw)
    return out


def comment(text: str, login="owner", cid=1, at="2026-12-01T10:00:00Z") -> dict:
    return {"id": cid, "user": {"login": login}, "body": text, "created_at": at}


def spec_record(clean=True, body=SPEC_BODY, round=1) -> str:
    return record(kind="spec", round=round, body=body, reviewers="spec,correctness", clean=clean)


def perm(login: str, permission: str) -> dict:
    return {"permission": permission, "user": {"login": login}}


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname = "demo"\nrepo = "acme/demo"\n[areas]\nnotes = ["src/notes/**"]\n'
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return tmp_path


def run_ready(project, capsys, issues, *extra) -> dict:
    (project / "issues.json").write_text(json.dumps(issues))
    (project / "prs.json").write_text("[]")
    assert cli.main(["ready", "--issues", str(project / "issues.json"), "--prs", str(project / "prs.json"), "--json", *extra]) == 0
    out = json.loads(capsys.readouterr().out)
    return {v["number"]: v for v in out["ready"] + out["not_ready"]}


def routes_asked(gh) -> list[str]:
    """The routes asked for, without their query strings."""
    return [p.split("?", 1)[0] for p in gh.paths()]


def owner_can_write(tmp_path, monkeypatch, extra=None):
    routes = {PERM.format("owner"): perm("owner", "admin"), PERM.format("visitor"): perm("visitor", "read")}
    routes.update(extra or {})
    return fake_gh.install(tmp_path, monkeypatch, routes)


# ---------- the note ----------


def test_a_post_cutoff_spec_with_no_record_notes_its_ticket_which_stays_ready(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(), ticket()])
    assert v[11]["ready"] is True and v[11]["reasons"] == []
    assert v[11]["notes"] == [NOTE]
    assert routes_asked(gh) == []  # comments carried, and no record to ask about


def test_a_clean_record_for_the_current_body_from_a_writer_gives_no_note(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    # Written from the body with `\n` endings; GitHub gives it back with `\r\n`.
    v = run_ready(project, capsys, [spec(comments=[comment(spec_record(body=SPEC_BODY.replace("\r\n", "\n")))]), ticket()])
    assert v[11]["ready"] is True and v[11]["notes"] == []


def test_only_a_not_clean_record_gives_the_note(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(comments=[comment(spec_record(clean=False))]), ticket()])
    assert v[11]["notes"] == [NOTE]


def test_the_latest_record_counts_oldest_first_whatever_order_they_come_in(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    clean = comment(spec_record(round=2), cid=2, at="2026-12-02T10:00:00Z")
    dirty = comment(spec_record(clean=False), cid=1, at="2026-12-01T10:00:00Z")
    assert run_ready(project, capsys, [spec(comments=[clean, dirty]), ticket()])[11]["notes"] == []
    later_dirty = comment(spec_record(clean=False, round=2), cid=3, at="2026-12-03T10:00:00Z")
    assert run_ready(project, capsys, [spec(comments=[later_dirty, clean]), ticket()])[11]["notes"] == [NOTE]


def test_a_clean_record_for_an_older_body_gives_the_note(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    old = comment(spec_record(body="## Problem Statement\n\nAn earlier draft.\n"))
    v = run_ready(project, capsys, [spec(comments=[old]), ticket()])
    assert v[11]["notes"] == [NOTE]


def test_a_clean_record_from_an_account_without_write_access_gives_the_note(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(comments=[comment(spec_record(), login="visitor")]), ticket()])
    assert v[11]["notes"] == [NOTE]
    assert routes_asked(gh) == [PERM.format("visitor")]


def test_an_account_github_doesnt_know_counts_as_without_write_access(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)  # no route for "stranger": gh answers 404
    v = run_ready(project, capsys, [spec(comments=[comment(spec_record(), login="stranger")]), ticket()])
    assert v[11]["notes"] == [NOTE]


def test_a_writers_clean_record_counts_beside_a_visitors_later_one(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    mine = comment(spec_record(), cid=1, at="2026-12-01T10:00:00Z")
    theirs = comment(spec_record(clean=False, round=2), login="visitor", cid=2, at="2026-12-02T10:00:00Z")
    assert run_ready(project, capsys, [spec(comments=[mine, theirs]), ticket()])[11]["notes"] == []


def test_a_spec_created_before_the_cutoff_gives_no_note(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(created=f"{_day(-1)}T23:59:59Z", comments=3), ticket()])
    assert v[11]["ready"] is True and v[11]["notes"] == []
    assert routes_asked(gh) == []  # never fetched


def test_a_ticket_with_no_parent_spec_gives_no_note(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch)
    plain = {**spec(), "labels": [{"name": "enhancement"}], "title": "Newest note first", "sub_issues_summary": None}
    v = run_ready(project, capsys, [ticket(section=""), ticket(12, section="## Parent\n\n#10"), plain])
    assert v[11]["notes"] == [] and v[12]["notes"] == []  # no parent; a parent that isn't a spec
    assert routes_asked(gh) == []


def test_the_sub_issue_link_names_the_parent_too(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    issues = [
        spec(),
        ticket(11, section="", parent_issue_url="https://api.github.com/repos/acme/demo/issues/10"),
        ticket(12, section="", parent={"number": 10, "repository": "acme/demo"}),
        ticket(13, section="", parent_issue_url="https://api.github.com/repos/other/lib/issues/10"),
    ]
    v = run_ready(project, capsys, issues)
    assert v[11]["notes"] == [NOTE] and v[12]["notes"] == [NOTE]
    assert v[13]["notes"] == []  # another repository's #10 isn't this spec


def test_the_note_never_changes_readiness_and_a_waiting_ticket_gets_none(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch, {"repos/acme/demo/issues/10/comments": fake_gh.pages([])})
    v = run_ready(project, capsys, [spec(comments=2), ticket(labels=("ready-for-agent", "needs-human"))])
    assert v[11]["ready"] is False and v[11]["notes"] == []
    assert routes_asked(gh) == []  # not fetched for a ticket that isn't ready


# ---------- where the comments come from ----------


def test_comments_in_the_issues_json_are_used_without_gh(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(comments=[comment(spec_record())]), ticket(), ticket(12)])
    assert v[11]["notes"] == [] and v[12]["notes"] == []
    assert routes_asked(gh) == [PERM.format("owner")]  # once, for both tickets: no comments fetched


def test_without_them_they_are_fetched_through_gh_once_per_spec(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch, {"repos/acme/demo/issues/10/comments": fake_gh.pages([comment(spec_record())])})
    v = run_ready(project, capsys, [spec(comments=1), ticket(), ticket(12)])
    assert v[11]["notes"] == [] and v[12]["notes"] == []
    assert routes_asked(gh) == ["repos/acme/demo/issues/10/comments", PERM.format("owner")]


def test_a_spec_with_no_comments_is_not_fetched(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(comments=0), ticket()])
    assert v[11]["notes"] == [NOTE]
    assert routes_asked(gh) == []


def test_only_parent_specs_of_ready_tickets_are_fetched(project, capsys, tmp_path, monkeypatch):
    routes = {
        "repos/acme/demo/issues/10/comments": fake_gh.pages([]),
        "repos/acme/demo/issues/20/comments": fake_gh.pages([]),
    }
    gh = owner_can_write(tmp_path, monkeypatch, routes)
    issues = [spec(comments=1), spec(20, comments=1), ticket(), ticket(21, section="## Parent\n\n#20", labels=("ready-for-agent", "owner-task"))]
    v = run_ready(project, capsys, issues)
    assert v[11]["notes"] == [NOTE] and v[21]["notes"] == []
    assert routes_asked(gh) == ["repos/acme/demo/issues/10/comments"]


def test_only_fetches_for_the_tickets_asked_about(project, capsys, tmp_path, monkeypatch):
    gh = owner_can_write(tmp_path, monkeypatch, {"repos/acme/demo/issues/20/comments": fake_gh.pages([])})
    issues = [spec(comments=1), spec(20, comments=1), ticket(), ticket(21, section="## Parent\n\n#20")]
    v = run_ready(project, capsys, issues, "--only", "21")
    assert set(v) == {21} and v[21]["notes"] == ["spec #20 has no clean review: check it before building"]
    assert routes_asked(gh) == ["repos/acme/demo/issues/20/comments"]


def test_permissions_given_as_a_file_need_no_gh(project, capsys, tmp_path, monkeypatch):
    fake_gh.without_gh(tmp_path, monkeypatch)
    (project / "perms.json").write_text(json.dumps({"owner": "write"}))
    issues = [spec(comments=[comment(spec_record())]), ticket()]
    assert run_ready(project, capsys, issues, "--permissions", str(project / "perms.json"))[11]["notes"] == []
    issues = [spec(comments=[comment(spec_record(), login="visitor")]), ticket()]
    assert run_ready(project, capsys, issues, "--permissions", str(project / "perms.json"))[11]["notes"] == [NOTE]


# ---------- what can't be read ----------


def test_comments_that_cant_be_fetched_say_so(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch, {"repos/acme/demo/issues/10/comments": fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 500)")})
    notes = run_ready(project, capsys, [spec(comments=2), ticket()])[11]["notes"]
    assert len(notes) == 1 and notes[0].startswith(UNREAD) and "HTTP 500" in notes[0]


def test_without_gh_unfetched_comments_say_so(project, capsys, tmp_path, monkeypatch):
    fake_gh.without_gh(tmp_path, monkeypatch)
    v = run_ready(project, capsys, [spec(comments=2), ticket()])
    assert v[11]["ready"] is True
    assert len(v[11]["notes"]) == 1 and v[11]["notes"][0].startswith(UNREAD)


def test_comments_in_a_shape_that_cant_be_read_say_so(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    notes = run_ready(project, capsys, [spec(comments=[{"nothing": "here"}]), ticket()])[11]["notes"]
    assert len(notes) == 1 and notes[0].startswith(UNREAD)


def test_permissions_that_cant_be_read_say_so(project, capsys, tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, {PERM.format("owner"): fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")})
    notes = run_ready(project, capsys, [spec(comments=[comment(spec_record())]), ticket()])[11]["notes"]
    assert len(notes) == 1 and notes[0].startswith(UNREAD) and "HTTP 502" in notes[0]
    fake_gh.without_gh(tmp_path, monkeypatch)
    notes = run_ready(project, capsys, [spec(comments=[comment(spec_record())]), ticket()])[11]["notes"]
    assert len(notes) == 1 and notes[0].startswith(UNREAD)


def test_a_proxy_that_refuses_the_route_gives_the_tokens_own_permission(project, capsys, tmp_path, monkeypatch):
    refused = fake_gh.reply(exit=1, stderr="gh: not permitted through this proxy (HTTP 403)")
    routes = {
        PERM.format("owner"): refused,
        PERM.format("visitor"): refused,
        "user": {"login": "owner"},
        "repos/acme/demo": {"permissions": {"admin": True, "push": True, "pull": True}},
    }
    fake_gh.install(tmp_path, monkeypatch, routes)
    assert run_ready(project, capsys, [spec(comments=[comment(spec_record())]), ticket()])[11]["notes"] == []
    v = run_ready(project, capsys, [spec(comments=[comment(spec_record(), login="visitor")]), ticket()])
    assert v[11]["notes"] == [NOTE]  # anyone else's can't be shown: no write access


def test_the_text_output_shows_the_note(project, capsys, tmp_path, monkeypatch):
    owner_can_write(tmp_path, monkeypatch)
    (project / "issues.json").write_text(json.dumps([spec(), ticket()]))
    (project / "prs.json").write_text("[]")
    assert cli.main(["ready", "--issues", str(project / "issues.json"), "--prs", str(project / "prs.json")]) == 0
    out = capsys.readouterr().out
    assert "READY #11 [notes]" in out and f"note: {NOTE}" in out


# ---------- the kit's text ----------


def _read(rel: str) -> str:
    return (KIT / rel).read_text(encoding="utf-8")


def test_next_shows_the_note_beside_the_ticket_it_offers():
    text = _read("skills/next/SKILL.md")
    assert "spec #<n> has no clean review: check it before building" in text
    assert "couldn't read its reviews" in text
    pick = text.split("## 2. Pick one", 1)[1].split("\n## 3.", 1)[0]
    assert "has no clean review" in pick and "never a block" in pick


def test_start_shows_the_note_beside_a_ready_ticket():
    text = _read("skills/start/SKILL.md")
    assert "spec #<n> has no clean review: check it before building" in text
    assert "WF ready --fetch --only <n>" in text


def test_the_conductors_kick_off_lists_tickets_of_unreviewed_specs():
    text = _read("skills/conductor/SKILL.md")
    work = text.split("**The work**", 1)[1].split("**Capacity**", 1)[0]
    assert "spec #<n> has no clean review: check it before building" in work
    plan = text.split("3. **The plan.**", 1)[1].split("\nThen:", 1)[0]
    assert "**Tickets of an unreviewed spec.**" in plan
    assert plan.index("**Tickets naming a protected path.**") < plan.index("**Tickets of an unreviewed spec.**")
    assert '"Keep it / Exclude it"' in plan.split("**Tickets of an unreviewed spec.**", 1)[1]


def test_the_changelog_notes_it_and_version_is_not_bumped():
    notes = since_0110()
    assert "#234" in notes and "has no clean review: check it before building" in notes
    assert "SPEC_REVIEW_SINCE" in notes
    assert _read("VERSION").strip() == "0.1.13"

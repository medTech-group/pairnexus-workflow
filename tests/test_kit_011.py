"""Kit 0.1.1: the findings of the sandbox run of 12 Oct 2026, each pinned.

Every command here is data passed to `decide`; none is run.
"""

import json
from pathlib import Path

import pytest

from conftest import pinned, ticket_checkout
from workflow import charter, cli, guard, posts, render, state
from workflow.guard import decide
from workflow.issues import named_paths, protected_named, readiness
from workflow.posts import AGENT_MARKER, is_agent, owner_words
from workflow.profile import DEFAULT_PROTECTED

KIT = Path(__file__).resolve().parents[1]
M = AGENT_MARKER


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def act(profile, root, cmd, role="ticket", branch="claude/build-1"):
    return decide(bash(cmd), profile, role, root, branch, role_from_env=True)


def mcp(profile, root, name, inp, role="ticket"):
    return decide({"tool_name": f"mcp__github__{name}", "tool_input": inp}, profile, role, root, "claude/build-1")


# ---------- 1. agents' posts carry the marker ----------


# (without the marker, with it)
POSTS = [
    ("gh pr comment 3 --body 'done'", f"gh pr comment 3 --body 'done {M}'"),
    ("gh issue comment 3 --body done", f"gh issue comment 3 --body 'done {M}'"),
    ("gh issue create --title t --body x", f"gh issue create --title t --body 'x {M}'"),
    ("gh pr create --title t --body x", f"gh pr create --title t --body 'x {M}'"),
    ("gh pr create --title t --fill", f"gh pr create --title t --body '{M}'"),
    ("gh pr edit 3 --body x", f"gh pr edit 3 --body 'x {M}'"),
    ("gh issue edit 3 --body=x", f"gh issue edit 3 '--body=x {M}'"),
    ("gh issue close 3 --comment 'why'", f"gh issue close 3 --comment 'why {M}'"),
    ("gh api repos/acme/demo/issues/3/comments -f body=x", f"gh api repos/acme/demo/issues/3/comments -f 'body=x {M}'"),
    ("gh api -X PATCH repos/acme/demo/issues/3 -f body=x", f"gh api -X PATCH repos/acme/demo/issues/3 -f 'body=x {M}'"),
    ("gh api -X PATCH repos/acme/demo/issues/comments/9 -f body=x", f"gh api -X PATCH repos/acme/demo/issues/comments/9 -f 'body=x {M}'"),
    ("gh api repos/acme/demo/pulls/3/reviews -f body=x -f event=COMMENT", f"gh api repos/acme/demo/pulls/3/reviews -f 'body=x {M}' -f event=COMMENT"),
    ("gh api repos/acme/demo/issues -f title=t", f"gh api repos/acme/demo/issues -f title=t -f 'body={M}'"),
    ("gh api repos/acme/demo/pulls -f title=t -f head=claude/build-1 -f base=main", f"gh api repos/acme/demo/pulls -f title=t -f head=claude/build-1 -f base=main -f 'body={M}'"),
    ("gh pr comment 3 --body-file - <<'EOF'\nok\nEOF", f"gh pr comment 3 --body-file - <<'EOF'\nok\n{M}\nEOF"),
    (
        "gh api graphql -f query='mutation{addComment(input:{subjectId:\"x\",body:\"ok\"}){clientMutationId}}'",
        f"gh api graphql -f query='mutation{{addComment(input:{{subjectId:\"x\",body:\"ok {M}\"}}){{clientMutationId}}}}'",
    ),
]


@pytest.mark.parametrize("bare, marked", POSTS)
@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_agent_posts_need_the_marker(bare, marked, role, profile, tmp_path):
    if role == "ticket" and bare.startswith("gh api graphql"):
        # Ticket sessions don't use GraphQL at all (the final review of 0.1.1).
        for cmd in (bare, marked):
            d = act(profile, tmp_path, cmd, role=role, branch="claude/build-1")
            assert d.action == "deny" and "GraphQL" in d.reason, cmd
        return
    d = act(profile, tmp_path, bare, role=role, branch="claude/build-1" if role == "ticket" else "main")
    assert d.action == "deny", bare
    assert M in d.reason and "at the end of the body" in d.reason
    assert act(profile, tmp_path, marked, role=role, branch="claude/build-1" if role == "ticket" else "main").action == "allow", marked


@pytest.mark.parametrize("bare, marked", POSTS)
def test_attended_posts_are_left_alone(bare, marked, profile, tmp_path):
    assert act(profile, tmp_path, bare, role="attended", branch="main").action == "allow", bare


def test_marker_found_in_body_files_and_reads(profile, tmp_path):
    (tmp_path / "marked.md").write_text(f"Notes for #201\n\n{M}\n")
    (tmp_path / "bare.md").write_text("Notes for #201\n")
    (tmp_path / "c.json").write_text(json.dumps({"body": f"x {M}"}))
    (tmp_path / "c-bare.json").write_text(json.dumps({"body": "x"}))
    for role, branch in (("ticket", "claude/build-1"), ("conductor", "main")):
        for cmd in (
            "gh pr comment 3 --body-file {f}",
            "gh issue comment 3 -F {f}",
            "gh api -X PATCH repos/acme/demo/issues/11 -F body=@{f}",
            "cat {f} | gh pr comment 3 --body-file -",
            'B=$(cat {f}); gh pr comment 3 --body "$B"',
        ):
            assert act(profile, tmp_path, cmd.format(f="marked.md"), role, branch).action == "allow", cmd
            assert act(profile, tmp_path, cmd.format(f="bare.md"), role, branch).action == "deny", cmd
        assert act(profile, tmp_path, "gh api repos/acme/demo/issues/3/comments --input c.json", role, branch).action == "allow"
        assert act(profile, tmp_path, "gh api repos/acme/demo/issues/3/comments --input c-bare.json", role, branch).action == "deny"
        assert act(profile, tmp_path, "gh api -X PATCH repos/acme/demo/issues/3 --input c-bare.json", role, branch).action == "deny"


NOT_POSTS = [
    "gh issue edit 3 --add-label x",
    "gh issue edit 3 --remove-label workflow:in-progress --remove-label ready-for-agent",
    "gh pr edit 3 --title 'Readings tab'",
    "gh api repos/acme/demo/issues/3/labels -f 'labels[]=needs-human'",
    "gh api -X DELETE repos/acme/demo/issues/3/labels/workflow:in-progress",
    "gh api -X PATCH repos/acme/demo/issues/3 -f state=closed -f state_reason=completed",
    "gh api -X PATCH repos/acme/demo/issues/3 --input state.json",
    "gh api repos/acme/demo/issues/3/labels --input labels.json",
    "gh api -X POST repos/acme/demo/issues/3/assignees -f 'assignees[]=owner-login'",
    "gh issue close 3",
    "gh pr ready 3",
    "gh pr merge 3 --merge --match-head-commit {sha}",
    "gh pr merge 3 --auto --merge --match-head-commit {sha}",
    "gh api -X PUT repos/acme/demo/pulls/3/merge -f merge_method=merge -f sha={sha}",
    "gh api -X PUT repos/acme/demo/pulls/3/update-branch",
    "gh api graphql -f query='mutation{enablePullRequestAutoMerge(input:{pullRequestId:\"x\"}){clientMutationId}}'",
    "gh api repos/acme/demo/issues/3/comments",
]


@pytest.mark.parametrize("cmd", NOT_POSTS)
@pytest.mark.parametrize("role", ["ticket", "conductor"])
def test_labels_state_and_merges_are_not_posts(cmd, role, profile, tmp_path):
    (tmp_path / "state.json").write_text('{"state": "closed"}')
    (tmp_path / "labels.json").write_text('{"labels": ["needs-human"]}')
    cmd = pinned(cmd, tmp_path)  # a ticket session's merge is pinned to its branch's head (#87)
    if role == "ticket" and cmd.startswith("gh api graphql"):
        assert act(profile, tmp_path, cmd, role=role, branch="claude/build-1").action == "deny", cmd
        return
    assert act(profile, tmp_path, cmd, role=role, branch="claude/build-1" if role == "ticket" else "main").action == "allow", cmd


def test_mcp_posts_need_the_marker(profile, tmp_path):
    cases = [
        ("add_issue_comment", {"issue_number": 3, "body": "done"}, {"issue_number": 3, "body": f"done {M}"}),
        ("issue_write", {"method": "create", "title": "t"}, {"method": "create", "title": "t", "body": f"x\n{M}"}),
        ("issue_write", {"method": "update", "issue_number": 11, "body": "state"}, {"method": "update", "issue_number": 11, "body": f"state {M}"}),
        ("create_pull_request", {"title": "t", "head": "claude/build-1", "base": "main"}, {"title": "t", "head": "claude/build-1", "base": "main", "body": M}),
        ("update_pull_request", {"pullNumber": 3, "body": "x"}, {"pullNumber": 3, "body": f"x {M}"}),
        ("pull_request_review_write", {"method": "create", "pullNumber": 3, "body": "x"}, {"method": "create", "pullNumber": 3, "body": f"x {M}"}),
        ("add_comment_to_pending_review", {"pullNumber": 3, "body": "x"}, {"pullNumber": 3, "body": f"x {M}"}),
        ("add_reply_to_pull_request_comment", {"commentId": 9, "body": "x"}, {"commentId": 9, "body": f"x {M}"}),
        ("update_issue_comment", {"comment_id": 9, "body": "x"}, {"comment_id": 9, "body": f"x {M}"}),
    ]
    for name, bare, marked in cases:
        for role in ("ticket", "conductor"):
            d = mcp(profile, tmp_path, name, bare, role)
            assert d.action == "deny" and M in d.reason, (name, role)
            assert mcp(profile, tmp_path, name, marked, role).action == "allow", (name, role)
        assert mcp(profile, tmp_path, name, bare, "attended").action == "allow", name


def test_mcp_labels_state_and_merges_are_not_posts(profile, tmp_path, monkeypatch):
    sha = ticket_checkout(tmp_path)  # a ticket session's merge is pinned to its branch's head (#87)
    monkeypatch.setattr(guard, "_pr_head", lambda repo, n: ("claude/build-1", sha))
    for name, inp in (
        ("issue_write", {"method": "update", "issue_number": 3, "labels": ["needs-human"]}),
        ("issue_write", {"method": "update", "issue_number": 3, "state": "closed", "state_reason": "completed"}),
        ("update_pull_request", {"pullNumber": 3, "title": "Readings tab"}),
        ("pull_request_review_write", {"method": "submit_pending", "pullNumber": 3, "event": "APPROVE"}),
        ("merge_pull_request", {"pullNumber": 3, "merge_method": "merge", "expectedHeadSha": sha}),
        ("enable_pr_auto_merge", {"pullNumber": 3, "mergeMethod": "MERGE"}),
        ("update_pull_request_branch", {"pullNumber": 3}),
        ("sub_issue_write", {"method": "add", "issue_number": 3, "sub_issue_id": 99}),
    ):
        for role in ("ticket", "conductor"):
            assert mcp(profile, tmp_path, name, inp, role).action == "allow", (name, role)


def test_the_sensitive_check_still_comes_first(profile, tmp_path):
    d = mcp(profile, tmp_path, "add_issue_comment", {"body": f"Patient MRN-123456 {M}"})
    assert d.action == "deny" and "sensitive" in d.reason
    d = act(profile, tmp_path, f"gh pr comment 3 --body 'Patient MRN-123456 {M}'")
    assert d.action == "deny" and "sensitive" in d.reason


# ---------- 1. the owner's own words ----------


def _comment(cid, login, body, **kw):
    return {"id": cid, "user": {"login": login}, "body": body, "created_at": f"2026-10-12T0{cid % 10}:00:00Z", "html_url": f"https://github.com/acme/demo/issues/11#issuecomment-{cid}", **kw}


COMMENTS = [
    _comment(101, "owner-login", "also #140"),
    _comment(102, "owner-login", f"#201 merged in #275 {M}"),
    _comment(103, "someone-else", "please also do #9"),
    _comment(104, "Owner-Login", "extend to Monday 9am"),
    _comment(105, "owner-login", f"Confirmed: stop releasing.\n\n{M}"),
]


def test_owner_words_are_the_owners_comments_without_the_marker():
    out = owner_words(COMMENTS, "owner-login")
    assert [c["id"] for c in out] == [101, 104]
    assert out[0] == {"id": 101, "created_at": "2026-10-12T01:00:00Z", "url": COMMENTS[0]["html_url"], "body": "also #140"}
    assert [c["id"] for c in owner_words(COMMENTS, "@owner-login", since_id=101)] == [104]
    assert owner_words(list(reversed(COMMENTS)), "owner-login")[0]["id"] == 101
    # A comment without a number, or something that isn't a comment, is an error, never dropped silently.
    for bad in ([{"id": "x", "user": {"login": "owner-login"}, "body": "?"}], ["junk"]):
        with pytest.raises(posts.CommentsError):
            owner_words(bad, "owner-login")
    assert is_agent(COMMENTS[1]["body"]) and not is_agent(None)
    with pytest.raises(ValueError):
        owner_words(COMMENTS, "")


def test_comments_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nowhere"))
    f = tmp_path / "comments.json"
    f.write_text(json.dumps(COMMENTS))
    assert cli.main(["comments", "--owner", "owner-login", "--file", str(f), "--since-id", "101"]) == 0
    assert [c["id"] for c in json.loads(capsys.readouterr().out)] == [104]
    assert cli.main(["comments", "--file", str(f)]) == 2  # no owner, no profile
    assert "--owner" in capsys.readouterr().err
    (tmp_path / "obj.json").write_text("{}")
    assert cli.main(["comments", "--owner", "owner-login", "--file", str(tmp_path / "obj.json")]) == 1


def test_comments_cli_takes_the_owner_from_the_profile(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    f = tmp_path / "comments.json"
    f.write_text(json.dumps(COMMENTS))
    assert cli.main(["comments", "--file", str(f)]) == 0
    assert [c["id"] for c in json.loads(capsys.readouterr().out)] == [101, 104]


# ---------- 3. tickets naming protected paths are owner tasks ----------


def _issue(n, body):
    return {"number": n, "state": "open", "labels": [{"name": "ready-for-agent"}], "body": body, "title": f"t{n}"}


def test_named_paths():
    body = (
        "Change `.github/workflows/ci.yml` and src/app.py, then run `git checkout -- .claude/workflow`.\n"
        "Also .env (not .env.example), see https://github.com/acme/demo/blob/main/.github/CODEOWNERS and acme/demo#3.\n"
        "Edit `CODEOWNERS`; and/or the [docs](docs/flow.md)."
    )
    paths = named_paths(body)
    for p in (".github/workflows/ci.yml", "src/app.py", ".claude/workflow", ".env", ".env.example", "CODEOWNERS", "docs/flow.md", "and/or"):
        assert p in paths, p
    assert not any(p.startswith("http") or "#" in p for p in paths)
    assert named_paths(None) == [] and named_paths("") == []


def test_protected_named_matches_as_the_guard_does():
    hits = dict(protected_named("Fix `.github/workflows/ci.yml`, .env and `CODEOWNERS`; not .env.example or src/x.py.", DEFAULT_PROTECTED))
    assert hits == {".github/workflows/ci.yml": ".github/workflows/**", ".env": "**/.env", "CODEOWNERS": "CODEOWNERS"}
    assert dict(protected_named("Edit the `.claude` folder", DEFAULT_PROTECTED)) == {".claude": ".claude/**"}
    assert dict(protected_named("Touch `.github/` only", DEFAULT_PROTECTED)) == {".github/": ".github/workflows/**"}
    assert protected_named("Edit `.github/workflows/ci.yml`", None) == []


def test_readiness_notes_tickets_naming_protected_paths():
    issues = [
        _issue(1, "Area: ci\n\nCache pip in `.github/workflows/ci.yml`."),
        _issue(2, "Area: readings\n\nAdd src/readings/chart.py."),
        _issue(3, "Rotate the key in .env"),
    ]
    v = {x.number: x for x in readiness(issues, [], protected=DEFAULT_PROTECTED)}
    assert all(x.ready and not x.reasons for x in v.values())  # a note, never a block
    assert v[1].notes == ["names protected path .github/workflows/ci.yml (.github/workflows/**): check it isn't an owner task"]
    assert v[2].notes == []
    assert v[3].notes == ["names protected path .env (**/.env): check it isn't an owner task"]
    assert all(x.ready and not x.notes for x in readiness(issues, []))  # without the patterns, nothing noted


def test_ready_cli_passes_the_profiles_protected_paths(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n[guard]\nprotected_paths = ["infra/**"]\n')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    (tmp_path / "issues.json").write_text(json.dumps([_issue(1, "Change infra/app.yaml"), _issue(2, "Change `.github/workflows/ci.yml`")]))
    (tmp_path / "prs.json").write_text("[]")
    assert cli.main(["ready", "--issues", str(tmp_path / "issues.json"), "--prs", str(tmp_path / "prs.json"), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["start_now"] == [1, 2] and out["not_ready"] == []
    assert out["ready"][0]["notes"] == ["names protected path infra/app.yaml (infra/**): check it isn't an owner task"]


# ---------- 9. briefings copied exactly ----------


def test_seal_ends_the_briefing_with_its_hash():
    text = render.seal("Build #7.\n\nMore.\n\n")
    body, last = text.rstrip("\n").rsplit("\n", 1)
    assert last.startswith("Briefing ") and len(last.split()[1]) == 12
    assert last == "Briefing " + render.briefing_hash("Build #7.\n\nMore.")
    assert render.sealed_intact(text)
    assert not render.sealed_intact(text.replace("#7", "#8"))
    assert not render.sealed_intact("Build #7.")
    assert render.seal(text.rsplit("\n\nBriefing", 1)[0]) == text


@pytest.fixture
def render_files(tmp_path, monkeypatch):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\nowner = "owner-login"\n')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    (tmp_path / "charter.json").write_text(json.dumps(c))
    (tmp_path / "ticket.json").write_text(json.dumps({"number": 7, "title": "Readings tab"}))
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": "trig_01abc"}
    (tmp_path / "slots.json").write_text(json.dumps(slots))
    args = ["render", "--template", str(KIT / "templates/ticket-session-prompt.md"), "--ticket", str(tmp_path / "ticket.json")]
    return args + ["--charter", str(tmp_path / "charter.json"), "--slots", str(tmp_path / "slots.json"), "--tracking", "11"]


def test_render_prints_the_sealed_briefing(render_files, tmp_path, capsys):
    assert cli.main([*render_files, "--print"]) == 0
    printed = capsys.readouterr().out
    assert render.sealed_intact(printed) and "`trig_01abc`" in printed
    assert cli.main(render_files) == 0
    assert capsys.readouterr().out == printed  # printing is the default
    out = tmp_path / "briefing.md"
    assert cli.main([*render_files, "--out", str(out)]) == 0
    assert capsys.readouterr().out == "" and out.read_text() == printed
    assert cli.main([*render_files, "--out", str(out), "--print"]) == 0
    assert capsys.readouterr().out == printed


def test_render_needs_the_wake_trigger(profile):
    slots = {"alongside": "none", "read_first": "none", "owner_decisions": "none", "briefing": "none", "wake_trigger": " "}
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    with pytest.raises(render.RenderError, match="wake_trigger"):
        render.render("{{wake_trigger}}", render.values(profile, {"number": 1}, c, slots, 1, None))


# ---------- 10. the charter section of the tracking issue ----------


def _charter():
    c = charter.defaults()
    c["limits"]["ends_at"] = "2099-10-13T03:30:00Z"
    return c


def test_splice_replaces_only_the_charter_section():
    s = state.empty()
    s["run_id"] = "2026-10-12-words"
    body = (KIT / "templates/tracking-issue.md").read_text().replace("CHARTER", "old charter")
    body = state.put(body, s)
    md = charter.to_markdown(_charter(), [(13, "messages")])
    new = charter.splice(body, md)
    assert "old charter" not in new and md in new
    assert state.get(new)["run_id"] == "2026-10-12-words"
    assert new.split(charter.SECTION_BEGIN)[0] == body.split(charter.SECTION_BEGIN)[0]
    assert new.split(charter.SECTION_END)[1] == body.split(charter.SECTION_END)[1]
    assert charter.splice(new, md) == new  # the same charter twice changes nothing


def test_splice_refuses_a_body_without_its_markers():
    for body in ("# Run\n\nno section", f"{charter.SECTION_BEGIN}\nx", f"{charter.SECTION_END}\nx\n{charter.SECTION_BEGIN}", f"{charter.SECTION_BEGIN}{charter.SECTION_BEGIN}{charter.SECTION_END}"):
        with pytest.raises(charter.SpliceError, match="workflow-charter"):
            charter.splice(body, "x")


def test_charter_splice_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nowhere"))
    (tmp_path / "charter.json").write_text(json.dumps(_charter()))
    (tmp_path / "body.md").write_text((KIT / "templates/tracking-issue.md").read_text())
    args = ["charter", "splice", "--body", str(tmp_path / "body.md"), "--charter", str(tmp_path / "charter.json")]
    assert cli.main([*args, "--tickets", "13:messages,143:-", "--out", str(tmp_path / "body.md")]) == 0
    body = (tmp_path / "body.md").read_text()
    assert "CHARTER" not in body and "1. #13 (messages)" in body and body.rstrip().endswith(M)
    (tmp_path / "plain.md").write_text("# Run\n")
    assert cli.main(["charter", "splice", "--body", str(tmp_path / "plain.md"), "--charter", str(tmp_path / "charter.json")]) == 1
    assert "workflow-charter:begin" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["charter", "splice", "--body", str(tmp_path / "body.md")])


# ---------- 13. the wake routine in the state ----------


def test_state_wake_trigger():
    s = state.empty()
    assert state.validate(s) == []
    for ok in ("trig_01ABCdef", None):
        s["wake_trigger"] = ok
        assert state.validate(s) == [], ok
    for bad in ("", "abc", 5, "trig_", ["trig_1"]):
        s["wake_trigger"] = bad
        assert any("wake_trigger" in p for p in state.validate(s)), bad
    s["wake_trigger"] = "trig_01abc"
    assert state.get(state.put("", s))["wake_trigger"] == "trig_01abc"


def test_state_ticket_briefing_hash():
    s = state.empty()
    h = render.briefing_hash("Build #7.")
    s["tickets"] = {"7": {"status": "running", "briefing": h}}
    assert state.validate(s) == []
    for bad in ("Briefing " + h, h.upper(), h[:8], 12):
        s["tickets"]["7"]["briefing"] = bad
        assert any("briefing" in p for p in state.validate(s)), bad


# ---------- templates, docs and the version ----------


def test_posted_templates_end_with_the_marker():
    for name in ("tracking-issue.md", "by-hand-issue.md"):
        assert (KIT / "templates" / name).read_text().rstrip().endswith(M), name
    tracking = (KIT / "templates/tracking-issue.md").read_text()
    assert tracking.index(charter.SECTION_BEGIN) < tracking.index("CHARTER") < tracking.index(charter.SECTION_END)
    assert M in (KIT / "skills/run-report/SKILL.md").read_text()


def test_skills_and_docs_carry_the_new_rules():
    conductor = (KIT / "skills/conductor/SKILL.md").read_text()
    for phrase in (M, "WF comments", "charter splice", "create_trigger", "wake_trigger", "permission_mode", "strict_required_status_checks_policy", "--print", "waiting on you", "60 minutes"):
        assert phrase in conductor, phrase
    build = (KIT / "skills/build-ticket/SKILL.md").read_text()
    for phrase in (M, "fire_trigger", "Briefing", "ready-for-agent"):
        assert phrase in build, phrase
    assert "Require review from Code Owners" in (KIT / "docs/enforcement.md").read_text()
    assert M in (KIT / "docs/charter.md").read_text() and "chat" in (KIT / "docs/charter.md").read_text()


def test_versions_agree():
    v = (KIT / "VERSION").read_text().strip()
    assert json.loads((KIT / ".claude-plugin/plugin.json").read_text())["version"] == v
    assert f"## {v}" in (KIT / "CHANGELOG.md").read_text()

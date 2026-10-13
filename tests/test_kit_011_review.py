"""Kit 0.1.1, the review's findings: each pinned.

Every command here is data passed to `decide`; none is run.
"""

import json
from pathlib import Path

import pytest

from workflow import cli, evidence, posts, render, state
from workflow.guard import decide
from workflow.issues import named_paths, protected_named, readiness
from workflow.posts import AGENT_MARKER
from workflow.profile import DEFAULT_PROTECTED

KIT = Path(__file__).resolve().parents[1]
M = AGENT_MARKER


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def act(profile, root, cmd, role="conductor"):
    branch = "claude/build-1" if role == "ticket" else "main"
    return decide(bash(cmd), profile, role, root, branch, role_from_env=True)


# ---------- 1. the owner's words, from every shape the conductor fetches ----------


def _rest(cid, login, body):
    return {
        "id": cid,
        "user": {"login": login},
        "body": body,
        "created_at": "2026-10-12T01:00:00Z",
        "html_url": f"https://github.com/acme/demo/issues/11#issuecomment-{cid}",
    }


def _view(cid, login, body):
    """`gh issue view --json comments`, and the GitHub MCP tools: `author`, node ids."""
    return {
        "id": f"IC_kwDOabc{cid}",
        "author": {"login": login},
        "body": body,
        "createdAt": "2026-10-12T01:00:00Z",
        "url": f"https://github.com/acme/demo/issues/11#issuecomment-{cid}",
    }


ROWS = [(101, "owner-login", "also #140"), (102, "owner-login", f"#7 merged in #9 {M}"), (103, "someone-else", "do #9"), (104, "Owner-Login", "extend to Monday")]
PAGE1 = [_rest(*r) for r in ROWS[:2]]
PAGE2 = [_rest(*r) for r in ROWS[2:]]
VIEW = [_view(*r) for r in ROWS]

SHAPES = {
    "one list": json.dumps(PAGE1 + PAGE2),
    "--paginate --slurp": json.dumps([PAGE1, PAGE2]),
    "--paginate, arrays one per line": json.dumps(PAGE1) + "\n" + json.dumps(PAGE2) + "\n",
    "--paginate, arrays back to back": json.dumps(PAGE1) + json.dumps(PAGE2),
    "gh issue view --json comments": json.dumps({"comments": VIEW}),
    "MCP get_comments, a list": json.dumps(VIEW),
    "ids as digit strings": json.dumps([{**c, "id": str(c["id"])} for c in PAGE1 + PAGE2]),
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_owner_words_from_every_shape(shape):
    comments = posts.load_comments(SHAPES[shape])
    out = posts.owner_words(comments, "owner-login")
    assert [c["id"] for c in out] == [101, 104], shape
    assert out[0]["url"].endswith("#issuecomment-101") and out[0]["created_at"] == "2026-10-12T01:00:00Z"
    assert [c["id"] for c in posts.owner_words(comments, "owner-login", since_id=101)] == [104], shape


def test_ids_are_compared_as_numbers():
    rows = [{**_rest(99, "owner-login", "a"), "id": "99"}, {**_rest(1000, "owner-login", "b"), "id": "1000"}]
    assert [c["id"] for c in posts.owner_words(rows, "owner-login", since_id=100)] == [1000]
    assert [c["id"] for c in posts.owner_words(rows, "owner-login")] == [99, 1000]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_comments_cli_reads_every_shape(shape, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nowhere"))
    f = tmp_path / "comments.json"
    f.write_text(SHAPES[shape])
    assert cli.main(["comments", "--owner", "owner-login", "--file", str(f), "--since-id", "101"]) == 0
    assert [c["id"] for c in json.loads(capsys.readouterr().out)] == [104]


@pytest.mark.parametrize(
    "text",
    ["", "not json", "42", '"text"', "[1, 2]", '{"foo": 1}', '{"data": {"x": 1}}', '[{"id": "IC_x", "user": {"login": "owner-login"}, "body": "no number"}]'],
)
def test_comments_cli_refuses_unknown_shapes_clearly(text, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "nowhere"))
    f = tmp_path / "comments.json"
    f.write_text(text)
    assert cli.main(["comments", "--owner", "owner-login", "--file", str(f)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("workflow comments:") and "Traceback" not in err


# ---------- 2. protected paths: a note, never a block ----------


def _issue(n, body):
    return {"number": n, "state": "open", "labels": [{"name": "ready-for-agent"}], "body": body, "title": f"t{n}"}


NOT_NAMED = {
    "a file the code reads": "Read the key from .env at startup.",
    "a fenced command": "Set it up locally:\n\n```bash\ncp .env.example .env\n```\n\nThen add src/config.py.",
    "a tilde fence": "~~~\nvi .github/workflows/ci.yml\n~~~\n",
    "don't touch": "Don't touch `.github/workflows/ci.yml`.",
    "do not edit": "Do not edit .env; read it.",
    "never change": "Never change `.claude/settings.json` here.",
    "the .github directory": "Document the .github directory's layout in docs/ci.md.",
}


@pytest.mark.parametrize("case", sorted(NOT_NAMED))
def test_protected_paths_the_body_doesnt_ask_to_change(case):
    assert protected_named(NOT_NAMED[case], DEFAULT_PROTECTED) == [], case


NAMED = {
    "a line anchor": ("Raise the timeout at `.github/workflows/ci.yml#L20`.", ".github/workflows/ci.yml"),
    "a bare line anchor": ("Raise the timeout at .github/workflows/ci.yml#L20-L24 too.", ".github/workflows/ci.yml"),
    "a blob URL": ("See https://github.com/acme/demo/blob/main/.github/workflows/ci.yml#L20 and cache pip.", ".github/workflows/ci.yml"),
    "a tree URL": ("Add a skill under https://github.com/acme/demo/tree/main/.claude/skills.", ".claude/skills"),
    "a markdown link": ("Change [the workflow](https://github.com/acme/demo/blob/main/.github/workflows/ci.yml).", ".github/workflows/ci.yml"),
    "a change after a read": ("Read the docs, then update .env with the new key.", ".env"),
    "still a change": ("Rotate the key in .env", ".env"),
}


@pytest.mark.parametrize("case", sorted(NAMED))
def test_protected_paths_the_review_found_missed(case):
    body, path = NAMED[case]
    assert [p for p, _ in protected_named(body, DEFAULT_PROTECTED, repo="acme/demo")] == [path], case


def test_another_repositorys_url_isnt_this_repo():
    body = "Like https://github.com/other/thing/blob/main/.github/workflows/ci.yml does."
    assert protected_named(body, DEFAULT_PROTECTED, repo="acme/demo") == []
    assert ".github/workflows/ci.yml" not in named_paths(body, repo="acme/demo")


def test_a_skill_path_is_noted():
    # "Follow .claude/skills/tdd" only reads the skill, but the words can't tell
    # reading a path under .claude/** from changing it. A note costs nothing: the
    # ticket stays ready and the conductor asks the owner at kick-off.
    assert dict(protected_named("Follow .claude/skills/tdd for the tests.", DEFAULT_PROTECTED)) == {".claude/skills/tdd": ".claude/**"}


def test_readiness_notes_protected_paths_and_keeps_the_ticket_ready():
    issues = [_issue(1, "Area: ci\n\nCache pip in `.github/workflows/ci.yml`."), _issue(2, "Area: readings\n\nAdd src/readings/chart.py.")]
    v = {x.number: x for x in readiness(issues, [], protected=DEFAULT_PROTECTED)}
    assert v[1].ready and v[1].reasons == []
    assert v[1].notes == ["names protected path .github/workflows/ci.yml (.github/workflows/**): check it isn't an owner task"]
    assert v[2].ready and v[2].notes == []


def test_ready_cli_prints_the_notes(tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname = "demo"\nrepo = "acme/demo"\n[guard]\nprotected_paths = ["infra/**"]\n')
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    (tmp_path / "issues.json").write_text(json.dumps([_issue(1, "Change infra/app.yaml"), _issue(2, "Change src/x.py")]))
    (tmp_path / "prs.json").write_text("[]")
    args = ["ready", "--issues", str(tmp_path / "issues.json"), "--prs", str(tmp_path / "prs.json")]
    assert cli.main(args) == 0
    out = capsys.readouterr().out
    assert "READY #1" in out and "note: names protected path infra/app.yaml (infra/**): check it isn't an owner task" in out
    assert cli.main([*args, "--json"]) == 0
    j = json.loads(capsys.readouterr().out)
    assert j["start_now"] == [1, 2] and j["not_ready"] == []


# ---------- 3. the briefing check ----------


def test_sealed_intact_tolerates_trailing_whitespace():
    text = render.seal("Build #7.\n\nMore.")
    for copy in (text, text + "\n\n  \n", text.rstrip("\n"), text.rstrip("\n") + "   \n", text.replace("\n", "\r\n")):
        assert render.sealed_intact(copy), repr(copy[-30:])
    assert not render.sealed_intact(text.replace("#7", "#8"))


def test_briefing_verify_cli(tmp_path, capsys):
    text = render.seal("Build #7.\n\nMore.")
    h = render.briefing_hash("Build #7.\n\nMore.")
    f = tmp_path / "briefing.md"
    f.write_text(text + "\n\n")
    assert cli.main(["briefing", "verify", "--file", str(f)]) == 0
    assert capsys.readouterr().out.strip() == f"Briefing {h} intact"
    f.write_text(text.replace("#7", "#8"))
    assert cli.main(["briefing", "verify", "--file", str(f)]) == 1
    got = render.briefing_hash("Build #8.\n\nMore.")
    assert capsys.readouterr().out.strip() == f"Briefing changed: expected {h}, got {got}"
    f.write_text("Build #7.\n")
    assert cli.main(["briefing", "verify", "--file", str(f)]) == 1
    assert capsys.readouterr().out.strip() == "no Briefing line"


# ---------- 4. the marker rule, refined ----------


POSTS = [
    ("ticket", "gh issue reopen 3 --comment 'again'", f"gh issue reopen 3 --comment 'again {M}'"),
    ("ticket", "gh issue reopen 3 -c again", f"gh issue reopen 3 -c 'again {M}'"),
    ("conductor", "gh issue reopen 3 --comment=again", f"gh issue reopen 3 '--comment=again {M}'"),
    ("conductor", "gh pr reopen 3 --comment again", f"gh pr reopen 3 --comment 'again {M}'"),
    ("conductor", "gh api repos/acme/demo/commits/abc123/comments -f body=x", f"gh api repos/acme/demo/commits/abc123/comments -f 'body=x {M}'"),
    ("conductor", "gh api -X PATCH repos/acme/demo/comments/9 -f body=x", f"gh api -X PATCH repos/acme/demo/comments/9 -f 'body=x {M}'"),
    (
        "conductor",
        "gh api -X PATCH repos/acme/demo/issues/3 --input - <<'EOF'\n{\"body\": \"x\"}\nEOF",
        f"gh api -X PATCH repos/acme/demo/issues/3 --input - <<'EOF'\n{{\"body\": \"x {M}\"}}\nEOF",
    ),
    (
        "conductor",
        "gh api graphql -f query='mutation{updateIssue(input:{id:\"x\",body:\"new\"}){issue{id}}}'",
        f"gh api graphql -f query='mutation{{updateIssue(input:{{id:\"x\",body:\"new {M}\"}}){{issue{{id}}}}}}'",
    ),
    (
        "conductor",
        "gh api graphql -f query='mutation($b:String!){updateIssue(input:{id:\"x\",body:$b}){issue{id}}}' -f b=hello",
        f"gh api graphql -f query='mutation($b:String!){{updateIssue(input:{{id:\"x\",body:$b}}){{issue{{id}}}}}}' -f 'b=hello {M}'",
    ),
]


@pytest.mark.parametrize("role, bare, marked", POSTS)
def test_more_posts_need_the_marker(role, bare, marked, profile, tmp_path):
    d = act(profile, tmp_path, bare, role)
    assert d.action == "deny" and M in d.reason, bare
    assert act(profile, tmp_path, marked, role).action == "allow", marked


def test_a_ticket_session_may_not_reopen_a_pr_or_comment_on_commits(profile, tmp_path):
    for cmd in (f"gh pr reopen 3 --comment 'x {M}'", f"gh api repos/acme/demo/commits/abc123/comments -f 'body=x {M}'"):
        assert act(profile, tmp_path, cmd, "ticket").action == "deny", cmd


NOT_POSTS = [
    ("both", "gh api -X PATCH repos/acme/demo/issues/3 --input - <<'EOF'\n{\"state\": \"closed\"}\nEOF"),
    ("both", "gh api -X PATCH repos/acme/demo/issues/3 --input - < state.json"),
    ("both", "cat state.json | gh api -X PATCH repos/acme/demo/issues/3 --input -"),
    ("both", "gh api -X PATCH repos/acme/demo/pulls/3 --input state.json"),
    ("both", "gh issue comment 3 --delete-last --yes"),
    ("both", "gh pr comment 3 --delete-last"),
    ("conductor", "gh api graphql -f query='mutation{updateIssue(input:{id:\"x\",state:CLOSED}){issue{body}}}'"),
    ("conductor", "gh api graphql --input closed.json"),
]


@pytest.mark.parametrize("roles, cmd", NOT_POSTS)
def test_state_changes_and_deletes_are_not_posts(roles, cmd, profile, tmp_path):
    (tmp_path / "state.json").write_text('{"state": "closed", "state_reason": "completed"}')
    q = "mutation($i:UpdateIssueInput!){updateIssue(input:$i){issue{body}}}"
    (tmp_path / "closed.json").write_text(json.dumps({"query": q, "variables": {"i": {"id": "x", "state": "CLOSED"}}}))
    for role in ("ticket", "conductor") if roles == "both" else (roles,):
        assert act(profile, tmp_path, cmd, role).action == "allow", (role, cmd)


def test_unreadable_stdin_still_counts_as_a_post(profile, tmp_path):
    for role in ("ticket", "conductor"):
        assert act(profile, tmp_path, "make_json | gh api -X PATCH repos/acme/demo/issues/3 --input -", role).action == "deny"


def test_conductor_graphql_from_a_file_or_stdin_is_read(profile, tmp_path):
    add = 'mutation{addComment(input:{subjectId:"x",body:"hi"}){clientMutationId}}'
    (tmp_path / "add.json").write_text(json.dumps({"query": add}))
    (tmp_path / "add-marked.json").write_text(json.dumps({"query": add.replace("hi", f"hi {M}")}))
    q = "mutation($i:UpdateIssueInput!){updateIssue(input:$i){issue{id}}}"
    (tmp_path / "body.json").write_text(json.dumps({"query": q, "variables": {"i": {"id": "x", "body": "new"}}}))
    assert act(profile, tmp_path, "gh api graphql --input add.json").action == "deny"
    assert act(profile, tmp_path, "gh api graphql --input add-marked.json").action == "allow"
    assert act(profile, tmp_path, "gh api graphql --input - < add.json").action == "deny"
    assert act(profile, tmp_path, "cat add.json | gh api graphql --input -").action == "deny"
    assert act(profile, tmp_path, f"gh api graphql --input - <<'EOF'\n{json.dumps({'query': add})}\nEOF").action == "deny"
    assert act(profile, tmp_path, "gh api graphql --input body.json").action == "deny"
    assert act(profile, tmp_path, "gh api graphql -f query='query{viewer{login}}'").action == "allow"
    (tmp_path / "add.graphql").write_text(add)
    assert act(profile, tmp_path, "gh api graphql -F query=@add.graphql").action == "deny"
    assert act(profile, tmp_path, "gh api graphql --input missing.json").action == "deny"  # can't be read: it counts


def test_enforcement_doc_says_the_marker_is_checked_in_the_whole_command():
    text = (KIT / "docs/enforcement.md").read_text()
    assert "as a whole" in text and "seatbelt" in text


# ---------- 5. the evidence report is an agent's post ----------


def test_evidence_report_ends_with_the_marker(profile):
    good = evidence.ShardResult("unit", 0, [], 0, 3, 0, 0, 0, 1.0, "3 passed")
    bad = evidence.ShardResult("unit", 0, [], 1, 2, 1, 0, 0, 1.0, "1 failed, 2 passed")
    for r in (good, bad):
        _, md = evidence.report("abc", profile, [r], base_count=3)
        assert md.rstrip().endswith(M)


# ---------- 12. a needs-human ticket the conductor asked the owner about ----------


def test_state_ticket_asked_at():
    s = state.empty()
    s["tickets"] = {"7": {"status": "needs-human", "asked_at": "2026-10-12T10:00:00Z", "attempts": 0}}
    assert state.validate(s) == []
    for bad in ("yesterday", "", 5):
        s["tickets"]["7"]["asked_at"] = bad
        assert any("asked_at" in p for p in state.validate(s)), bad


# ---------- the skills and docs ----------


def _text(rel):
    return (KIT / rel).read_text()


def test_conductor_skill_carries_the_review_fixes():
    c = _text("skills/conductor/SKILL.md")
    for phrase in (
        "gh api --paginate --slurp repos/<repo>/issues/<n>/comments",
        "Briefing changed",
        "A check-in is complete when",
        "run_once_at",
        "never counts",
        "wake_trigger: null",
        "already clean",
        "protected path",
        "no `permission_mode`",
        "workflow:infra",
        "check it isn't an owner task",
    ):
        assert phrase in c, phrase
    assert "can't merge without the owner" not in c
    assert "A check-in is done when" not in c


@pytest.mark.parametrize("rel", ["skills/build-ticket/SKILL.md", "templates/ticket-session-prompt.md"])
def test_ticket_instructions_carry_the_review_fixes(rel):
    t = _text(rel)
    for phrase in (".workflow/briefing.md", "briefing verify", "mcp__claude-code-remote__fire_trigger", "searching for `fire_trigger`", "ToolSearch", "never retry it in a loop"):
        assert phrase in t, (rel, phrase)


def test_wake_texts_are_the_same_everywhere():
    for rel in ("skills/build-ticket/SKILL.md", "templates/ticket-session-prompt.md", "skills/conductor/SKILL.md"):
        t = _text(rel)
        for word in ("merged in #", "needs-human", "stopped"):
            assert word in t, (rel, word)


def test_charter_and_flow_describe_waiting_on_the_owner():
    ch = _text("docs/charter.md")
    assert "nothing waits on the owner mid-run" not in ch
    assert "60 minutes" in ch
    assert "max_retries" in _text("skills/conductor/SKILL.md")


def test_spike_rows():
    s = _text("docs/spike.md")
    row11 = next(l for l in s.splitlines() if l.startswith("| 11 |"))
    assert "Partly" in row11 and "persistent_session_id" in row11
    assert "fire_trigger" in s and "permission_mode" in s

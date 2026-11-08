"""#510: the stakes and token records (spec #505). Seam 1, `workflow research
stakes` and `workflow research estimate` fed files (and `--fetch` through a fake
`gh`); seam 2, the fixtures and the per-agent figure tied to the text the
`study` skill shows."""

import json
import os
import re
import subprocess
import sys

import pytest

from conftest import KIT
from workflow import research_records

CLI = KIT / "scripts/workflow.py"
FIX = KIT / "tests/fixtures/research/records"
SKILL = KIT / "skills/study/SKILL.md"
STAKES = (FIX / "stakes-comment.md").read_text(encoding="utf-8")
FULL = (FIX / "tokens-full-comment.md").read_text(encoding="utf-8")
SECOND = (FIX / "tokens-second-comment.md").read_text(encoding="utf-8")
OWNER = "owner"
WRITE = {OWNER: "admin", "dev": "write", "reader": "read", "bot": "triage"}


def _cli(*args, cwd=None, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, "-B", str(CLI), "research", *map(str, args)], capture_output=True, text=True, cwd=cwd, env=e)


def _comment(cid, issue, body, login=OWNER, at="2026-11-07T10:00:00Z", pull=False):
    kind = "pull" if pull else "issues"
    return {
        "id": cid,
        "body": body,
        "user": {"login": login},
        "created_at": at,
        "html_url": f"https://github.com/acme/demo/{kind}/{issue}#issuecomment-{cid}",
        "issue_url": f"https://api.github.com/repos/acme/demo/issues/{issue}",
    }


def _tokens(study, agents, total, line="Tokens: so many."):
    return f"{line}\n\n<!-- workflow:tokens study={study} agents={agents} total={total} -->\n<!-- workflow:agent -->\n"


def _stakes(line):
    return f"{line}\n\n<!-- workflow:stakes -->\n<!-- workflow:agent -->\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text(
        '[project]\nname="d"\nrepo="acme/demo"\n[sensitive]\npatterns=[\'BOOKCODE-[0-9]{6}\']\n', encoding="utf-8"
    )
    return tmp_path


def _files(project, comments, perms=None, issues=None):
    (project / "comments.json").write_text(json.dumps(comments), encoding="utf-8")
    (project / "perms.json").write_text(json.dumps(WRITE if perms is None else perms), encoding="utf-8")
    args = ["--comments", "comments.json", "--permissions", "perms.json"]
    if issues is not None:
        (project / "issues.json").write_text(json.dumps(issues), encoding="utf-8")
        args += ["--issues", "issues.json"]
    return args


def _run(project, action, *args):
    return _cli(action, *args, cwd=project, env={"CLAUDE_PROJECT_DIR": str(project)})


# ---------- seam 1: `stakes` ----------


def test_stakes_lists_each_past_judgement_one_per_line_oldest_first_with_its_issue(project):
    comments = [
        _comment(2, 57, _stakes("Stakes: a new kind of user. Recommended: study. Owner chose: study."), at="2026-11-08T09:00:00Z"),
        _comment(1, 42, STAKES, at="2026-11-07T10:00:00Z"),
        _comment(3, 42, "Thanks, looks good."),
    ]
    issues = [{"number": 42, "title": "Deposits on bookings"}, {"number": 57, "title": "Waiting lists"}]
    p = _run(project, "stakes", *_files(project, comments, issues=issues))
    assert p.returncode == 0, p.stderr
    assert p.stdout.splitlines() == [
        '#42 2026-11-07 "Deposits on bookings": Stakes: touches payments. Recommended: study. Owner chose: skip, because the deposit is the fixed fee we already take.',
        '#57 2026-11-08 "Waiting lists": Stakes: a new kind of user. Recommended: study. Owner chose: study.',
    ]
    assert p.stderr == ""


def test_stakes_without_the_issues_lists_no_titles(project):
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, STAKES)]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == "#42 2026-11-07: Stakes: touches payments. Recommended: study. Owner chose: skip, because the deposit is the fixed fee we already take.\n"


def test_stakes_with_none_says_so(project):
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, "Just a comment.")]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == "No stakes records yet.\n"


def test_stakes_json(project):
    p = _run(project, "stakes", "--json", *_files(project, [_comment(9, 42, STAKES)], issues=[{"number": 42, "title": "Deposits"}]))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {
        "stakes": [{
            "issue": 42,
            "title": "Deposits",
            "date": "2026-11-07",
            "line": "Stakes: touches payments. Recommended: study. Owner chose: skip, because the deposit is the fixed fee we already take.",
            "url": "https://github.com/acme/demo/issues/42#issuecomment-9",
        }],
        "left_out": 0,
    }


@pytest.mark.parametrize("comment", [
    _comment(1, 42, STAKES.replace("<!-- workflow:agent -->\n", "")),  # the owner's own words
    _comment(1, 42, STAKES, login="reader"),  # an account without write access
    _comment(1, 42, STAKES, login="bot"),
    _comment(1, 42, STAKES, login="stranger"),  # not in the permissions at all
])
def test_stakes_counts_only_agents_comments_from_accounts_with_write_access(project, comment):
    p = _run(project, "stakes", *_files(project, [comment, _comment(2, 57, _stakes("Stakes: wording only. Recommended: skip."), login="dev")]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == "#57 2026-11-07: Stakes: wording only. Recommended: skip.\n"
    assert "left out 1 comment" in p.stderr and "write access" in p.stderr and "agents' marker" in p.stderr


def test_stakes_reads_write_access_whatever_the_logins_case(project):
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, STAKES, login="Owner")], perms={"owner": "admin"}))
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("#42 2026-11-07: Stakes: touches payments.") and p.stderr == ""


@pytest.mark.parametrize("body", [
    _stakes("Stakes: one.\nStakes: two."),  # two stakes lines
    "Stakes: one.\n\n<!-- workflow:stakes -->\n<!-- workflow:stakes -->\n<!-- workflow:agent -->\n",  # two markers
    "```\nStakes: one.\n```\n\n<!-- workflow:stakes -->\n<!-- workflow:agent -->\n",  # in a code fence
    "Stakes: one.\n\n```\n<!-- workflow:stakes -->\n```\n<!-- workflow:agent -->\n",
    "No stakes line here.\n\n<!-- workflow:stakes -->\n<!-- workflow:agent -->\n",
    "Stakes: one.\n\n<!-- workflow:stakes extra -->\n<!-- workflow:agent -->\n",  # not as written
    "Stakes: one.\n\n<!-- Workflow:Stakes -->\n<!-- workflow:agent -->\n",
    "Stakes: one. <!-- workflow:stakes -->\n<!-- workflow:agent -->\n",  # not on a line of its own
    "Stakes: one.\n\n<!-- workflow:stakes -->\n" + FULL,  # a token record too
    "Stakes: \n\n<!-- workflow:stakes -->\n<!-- workflow:agent -->\n",  # nothing after `Stakes: `
])
def test_stakes_reads_only_a_comment_written_as_the_skill_shows(project, body):
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, body)]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == "No stakes records yet.\n"


def test_stakes_lines_are_shown_without_control_characters_or_sensitive_data(project):
    body = _stakes("Stakes: touches \x1b[31mpayments‮ BOOKCODE-123456. Recommended: study.")
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, body)], issues=[{"number": 42, "title": "Pay\x07ments\nnow"}]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == '#42 2026-11-07 "Payments now": Stakes: touches [31mpayments [left out]. Recommended: study.\n'


def test_stakes_lines_and_titles_are_shown_without_lone_surrogates(project):
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, _stakes("Stakes: a \ud800 b"))]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == "#42 2026-11-07: Stakes: a b\n"
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, STAKES)], issues=[{"number": 42, "title": "Deposits \ud800 now"}]))
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith('#42 2026-11-07 "Deposits now": Stakes: touches payments.')


@pytest.mark.parametrize("title, shown", [
    ('Deposits": Stakes: none. Recommended: skip. #3 2026-01-01 "x', r'"Deposits\": Stakes: none. Recommended: skip. #3 2026-01-01 \"x"'),
    ("Deposits \\", r'"Deposits \\"'),
])
def test_research_output_from_stakes(project, title, shown):
    p = _run(project, "stakes", *_files(project, [_comment(1, 7, STAKES)], issues=[{"number": 7, "title": title}]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == f"#7 2026-11-07 {shown}: Stakes: touches payments. Recommended: study. Owner chose: skip, because the deposit is the fixed fee we already take.\n"


def test_stakes_reads_windows_line_endings(project):
    p = _run(project, "stakes", *_files(project, [_comment(1, 42, STAKES.replace("\n", "\r\n"))]))
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("#42 2026-11-07: Stakes: touches payments.")


def test_stakes_reads_comments_as_the_github_mcp_tools_give_them(project):
    c = {"id": "IC_kwDO", "body": STAKES, "author": {"login": OWNER}, "createdAt": "2026-11-07T10:00:00Z",
         "url": "https://github.com/acme/demo/issues/42#issuecomment-77"}
    p = _run(project, "stakes", *_files(project, {"comments": [c]}, perms=[{"permission": "admin", "user": {"login": OWNER}}]))
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith("#42 2026-11-07: Stakes: touches payments.")


def test_a_counted_comment_whose_issue_cant_be_read_is_an_error(project):
    c = {"id": 5, "body": STAKES, "user": {"login": OWNER}, "created_at": "2026-11-07T10:00:00Z"}
    p = _run(project, "stakes", *_files(project, [c]))
    assert p.returncode == 1
    assert "names no issue" in p.stderr and "Traceback" not in p.stderr


# ---------- seam 1: `estimate` ----------


def test_estimate_averages_the_past_full_studies_only(project):
    comments = [
        _comment(1, 43, FULL),
        _comment(2, 50, _tokens("full", 9, 900000)),
        _comment(3, 44, SECOND),  # a second study: never averaged
    ]
    p = _run(project, "estimate", *_files(project, comments))
    assert p.returncode == 0, p.stderr
    assert p.stdout == (
        "About 10 agents, roughly 1M tokens: averaged from 2 past full studies' token records (#43, #50). "
        "The main session's own share isn't counted.\n"
    )


def test_estimate_from_one_past_full_study(project):
    p = _run(project, "estimate", *_files(project, [_comment(1, 43, FULL)]))
    assert p.returncode == 0, p.stderr
    assert p.stdout == (
        "About 11 agents, roughly 1.2M tokens: averaged from 1 past full study's token record (#43). "
        "The main session's own share isn't counted.\n"
    )


def test_estimate_json(project):
    comments = [_comment(1, 43, FULL), _comment(2, 50, _tokens("full", 9, 900000)), _comment(3, 44, SECOND)]
    p = _run(project, "estimate", "--json", *_files(project, comments))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {
        "agents": 10,
        "tokens": 1040000,
        "learned": True,
        "per_agent": 104000,
        "studies": [{"issue": 43, "agents": 11, "total": 1180000}, {"issue": 50, "agents": 9, "total": 900000}],
        "left_out": 0,
    }


def test_estimate_scales_the_learned_figure_to_the_agents_given(project):
    comments = [_comment(1, 43, FULL), _comment(2, 50, _tokens("full", 9, 900000))]
    p = _run(project, "estimate", "--agents", "8", "--json", *_files(project, comments))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert (got["agents"], got["tokens"], got["learned"]) == (8, 832000, True)  # 8 x 2,080,000 / 20


def test_estimate_counts_one_record_per_research_issue_its_latest(project):
    comments = [_comment(1, 43, _tokens("full", 10, 500000)), _comment(2, 43, FULL)]
    p = _run(project, "estimate", "--json", *_files(project, comments))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert got["studies"] == [{"issue": 43, "agents": 11, "total": 1180000}]
    assert (got["agents"], got["tokens"]) == (11, 1180000)


def test_estimate_takes_the_latest_record_by_its_time_not_its_text(project):
    # 12:00 at +05:00 is 07:00 UTC, before 10:00 UTC.
    comments = [_comment(1, 43, FULL, at="2026-11-07T12:00:00+05:00"), _comment(2, 43, _tokens("full", 10, 500000), at="2026-11-07T10:00:00Z")]
    p = _run(project, "estimate", "--json", *_files(project, comments))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["studies"] == [{"issue": 43, "agents": 10, "total": 500000}]


def test_estimate_keeps_the_given_order_when_a_record_has_no_time(project):
    late = _comment(2, 43, _tokens("full", 10, 500000))
    del late["created_at"]
    p = _run(project, "estimate", "--json", *_files(project, [_comment(1, 43, FULL), late]))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["studies"] == [{"issue": 43, "agents": 10, "total": 500000}]


def test_estimate_with_no_past_full_study_uses_the_per_agent_figure_and_says_it_isnt_learned(project):
    p = _run(project, "estimate", *_files(project, [_comment(1, 44, SECOND)]))
    assert p.returncode == 0, p.stderr
    n, per = research_records.PANEL_AGENTS, research_records.PER_AGENT_TOKENS
    assert p.stdout == (
        f"About {n} agents, roughly {research_records.rough(n * per)} tokens: not learned yet, since no past full study has a token record; "
        f"from the per-agent figure, {per:,} tokens per agent.\n"
    )
    p = _run(project, "estimate", "--agents", "9", "--json", *_files(project, []))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == {"agents": 9, "tokens": 9 * per, "learned": False, "per_agent": per, "studies": [], "left_out": 0}


@pytest.mark.parametrize("comment", [
    _comment(1, 43, FULL.replace("<!-- workflow:agent -->\n", "")),
    _comment(1, 43, FULL, login="reader"),
    _comment(1, 43, FULL, login="stranger"),
])
def test_estimate_counts_only_agents_comments_from_accounts_with_write_access(project, comment):
    p = _run(project, "estimate", "--json", *_files(project, [comment]))
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert (got["learned"], got["studies"], got["left_out"]) == (False, [], 1)
    assert "left out 1 comment" in p.stderr


@pytest.mark.parametrize("marker", [
    "study=full agents=011 total=1180000",  # a leading zero
    "study=full agents=0 total=1180000",
    "study=full agents=11 total=0",
    "study=whole agents=11 total=1180000",
    "study=full agents=11",
    "study=full agents=11 total=1180000 extra=1",
    "agents=11 study=full total=1180000",  # not in the order written
    "study=full agents=11 total=1,180,000",
    "study=full  agents=11 total=1180000",
    "study=full agents=11 total=12345678901234",  # past what a study could use
])
def test_estimate_reads_only_a_token_marker_written_as_the_skill_shows(project, marker):
    body = f"Tokens: some.\n\n<!-- workflow:tokens {marker} -->\n<!-- workflow:agent -->\n"
    p = _run(project, "estimate", "--json", *_files(project, [_comment(1, 43, body)]))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["studies"] == []


def test_estimate_refuses_a_token_marker_in_a_code_fence_or_twice(project):
    fenced = "Tokens: some.\n\n```\n<!-- workflow:tokens study=full agents=11 total=1180000 -->\n```\n<!-- workflow:agent -->\n"
    twice = FULL.replace("<!-- workflow:agent -->", "<!-- workflow:tokens study=full agents=11 total=1180000 -->\n<!-- workflow:agent -->")
    p = _run(project, "estimate", "--json", *_files(project, [_comment(1, 43, fenced), _comment(2, 50, twice)]))
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["studies"] == []


@pytest.mark.parametrize("n", ["0", "-3", "x", "1000"])
def test_estimate_refuses_an_agent_count_that_isnt_a_whole_number_from_1_to_999(project, n):
    p = _run(project, "estimate", "--agents", n, *_files(project, []))
    assert p.returncode == 2 and "--agents" in p.stderr and "Traceback" not in p.stderr


@pytest.mark.parametrize("n, shown", [(0, "0"), (950, "950"), (1000, "1k"), (104000, "104k"), (999_499, "999k"), (999_500, "1M"),
                                      (1_000_000, "1M"), (1_180_000, "1.2M"), (12_340_000, "12.3M")])
def test_rough_token_counts(n, shown):
    assert research_records.rough(n) == shown


# ---------- inputs ----------


@pytest.mark.parametrize("action", ["stakes", "estimate"])
def test_missing_inputs_are_named(project, action):
    p = _run(project, action)
    assert p.returncode == 2 and "--comments" in p.stderr and "--permissions" in p.stderr and "--fetch" in p.stderr
    (project / "comments.json").write_text("[]")
    p = _run(project, action, "--comments", "comments.json")
    assert p.returncode == 2 and "--permissions" in p.stderr


@pytest.mark.parametrize("action", ["stakes", "estimate"])
def test_fetch_with_files_is_refused(project, action):
    p = _run(project, action, "--fetch", *_files(project, []))
    assert p.returncode == 2 and "not both" in p.stderr


@pytest.mark.parametrize("name, text", [("comments", "not json"), ("permissions", "[{\"login\": \"x\"}]"), ("issues", "{\"x\": 1}"),
                                        ("comments", "{\"x\": 1}"), ("comments", "")])
def test_an_unreadable_file_is_named(project, name, text):
    args = _files(project, [], issues=[])
    (project / f"{'perms' if name == 'permissions' else name}.json").write_text(text)
    p = _run(project, "stakes", *args)
    assert p.returncode == 1 and f"--{name}" in p.stderr and "Traceback" not in p.stderr


def test_a_missing_file_is_named(project):
    p = _run(project, "estimate", "--comments", "nowhere.json", "--permissions", "nowhere.json")
    assert p.returncode == 1 and "nowhere.json" in p.stderr and "Traceback" not in p.stderr


# ---------- --fetch, through a fake gh ----------


def test_fetch_reads_the_issues_their_comments_and_the_markers_authors_permissions(project, monkeypatch):
    import fake_gh

    gh = fake_gh.install(project, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages([{"number": 42, "title": "Deposits"}], [{"number": 43, "title": "Study: deposits"}]),
        "repos/acme/demo/issues/comments": fake_gh.pages(
            [_comment(1, 42, STAKES), _comment(2, 42, "Plain words from someone.", login="passer-by")],
            [_comment(3, 43, FULL, login="dev"), _comment(4, 43, FULL, login="reader")],
        ),
        "repos/acme/demo/collaborators/owner/permission": {"permission": "admin", "user": {"login": OWNER}},
        "repos/acme/demo/collaborators/dev/permission": {"permission": "write", "user": {"login": "dev"}},
        "repos/acme/demo/collaborators/reader/permission": {"permission": "read", "user": {"login": "reader"}},
    })
    p = _run(project, "stakes", "--fetch")
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith('#42 2026-11-07 "Deposits": Stakes: touches payments.')
    asked = gh.paths()
    assert asked[:2] == ["repos/acme/demo/issues?state=all&per_page=100", "repos/acme/demo/issues/comments?per_page=100"]
    # Only the authors of comments carrying a marker are asked about, each once.
    assert sorted(asked[2:]) == ["repos/acme/demo/collaborators/dev/permission", "repos/acme/demo/collaborators/owner/permission",
                                 "repos/acme/demo/collaborators/reader/permission"]
    p = _run(project, "estimate", "--fetch", "--json")
    assert p.returncode == 0, p.stderr
    got = json.loads(p.stdout)
    assert (got["studies"], got["left_out"]) == ([{"issue": 43, "agents": 11, "total": 1180000}], 1)


def test_fetch_asks_once_for_a_login_given_in_two_cases(project, monkeypatch):
    import fake_gh

    gh = fake_gh.install(project, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages([{"number": 43, "title": "Study: deposits"}]),
        "repos/acme/demo/issues/comments": fake_gh.pages([_comment(1, 43, FULL, login="Dev"), _comment(2, 43, FULL, login="dev")]),
        "repos/acme/demo/collaborators/Dev/permission": {"permission": "write", "user": {"login": "Dev"}},
        "repos/acme/demo/collaborators/dev/permission": {"permission": "write", "user": {"login": "dev"}},
    })
    p = _run(project, "estimate", "--fetch", "--json")
    assert p.returncode == 0, p.stderr
    assert [x for x in gh.paths() if x.endswith("/permission")] == ["repos/acme/demo/collaborators/Dev/permission"]
    assert (json.loads(p.stdout)["studies"], json.loads(p.stdout)["left_out"]) == ([{"issue": 43, "agents": 11, "total": 1180000}], 0)


def test_fetch_that_fails_says_what_to_give_instead(project, monkeypatch):
    import fake_gh

    fake_gh.install(project, monkeypatch, {"repos/acme/demo/issues": fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 500)")})
    p = _run(project, "stakes", "--fetch")
    assert p.returncode == 1 and "HTTP 500" in p.stderr and "--comments" in p.stderr and "Traceback" not in p.stderr


def test_fetch_needs_the_profiles_repo(tmp_path):
    p = _cli("estimate", "--fetch", cwd=tmp_path, env={"CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 2 and "project.repo" in p.stderr


# ---------- seam 2: the skill's text ----------


def _shown(start: str) -> str:
    """The fenced block the `study` skill shows that starts with `start`."""
    text = SKILL.read_text(encoding="utf-8")
    m = re.search(r"```markdown\n(" + re.escape(start) + r".*?)\n```", text, re.S)
    assert m, f"the study skill shows no example starting {start!r}"
    return m.group(1) + "\n"


@pytest.mark.parametrize("name, start", [("stakes-comment.md", "Stakes: "), ("tokens-full-comment.md", "Tokens: 1,180,000"),
                                         ("tokens-second-comment.md", "Tokens: 240,000")])
def test_the_fixtures_are_copied_from_the_records_the_study_skill_shows(name, start):
    assert (FIX / name).read_text(encoding="utf-8") == _shown(start)


def test_the_skills_examples_read_as_records():
    assert research_records.stakes_line(STAKES) == "Stakes: touches payments. Recommended: study. Owner chose: skip, because the deposit is the fixed fee we already take."
    assert research_records.token_record(FULL) == research_records.Tokens(study="full", agents=11, total=1180000)
    assert research_records.token_record(SECOND) == research_records.Tokens(study="second", agents=4, total=240000)
    assert research_records.stakes_line(FULL) is None and research_records.token_record(STAKES) is None


def test_the_study_skill_quotes_the_per_agent_figure_and_the_panels_size_from_the_constants():
    text = re.sub(r"\s+", " ", SKILL.read_text(encoding="utf-8"))
    m = re.search(r"it counts the panel at its largest, (\d+) agents, at the per-agent figure, ([0-9,]+) tokens per agent", text)
    assert m, "the study skill doesn't quote the per-agent figure"
    assert int(m.group(1)) == research_records.PANEL_AGENTS
    assert int(m.group(2).replace(",", "")) == research_records.PER_AGENT_TOKENS
    assert "That figure is a placeholder until a trial run of the panel's agents sets it." in text


def test_the_panels_size_is_the_panel_the_spec_names():
    # One evidence gatherer, one question writer, at most 8 personas, a synthesizer and a validator.
    assert research_records.PANEL_AGENTS == 1 + 1 + 8 + 1 + 1


def test_the_study_skill_says_which_comments_count_and_that_estimate_averages_full_studies_only():
    text = re.sub(r"\s+", " ", SKILL.read_text(encoding="utf-8"))
    assert "only comments carrying the agents' marker, posted by an account with write access, count" in text
    assert "never a second study's" in text and "the main session's own share isn't counted" in text
    assert "WF research stakes --fetch" in text and "WF research estimate --fetch" in text

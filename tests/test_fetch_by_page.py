"""#568: `gh api --paginate` fails after the first page in a Claude Code cloud
session, whose proxy refuses GitHub's next-page links (they name the
repository by number). Seam 1: the `workflow` CLI, and `fetch.api` under it,
fed a fake `gh` (tests/fake_gh.py) that fails `--paginate` as the proxy does
and answers each `page=N` on the `repos/<owner>/<repo>/` path."""

import json
import os
import subprocess
import sys

import pytest

import fake_gh
from conftest import KIT
from workflow import cli, fetch

CLI = KIT / "scripts/workflow.py"
STAKES = (KIT / "tests/fixtures/research/records/stakes-comment.md").read_text(encoding="utf-8")


def _comment(cid, issue, body="Plain words.", login="owner"):
    return {
        "id": cid,
        "body": body,
        "user": {"login": login},
        "created_at": "2026-11-07T10:00:00Z",
        "html_url": f"https://github.com/acme/demo/issues/{issue}#issuecomment-{cid}",
        "issue_url": f"https://api.github.com/repos/acme/demo/issues/{issue}",
    }


def _paged(gh) -> list[str]:
    """The paths asked for without `--paginate`, in order."""
    return [p for args, p in zip([c for c in gh.calls() if c[:1] == ["api"]], gh.paths()) if "--paginate" not in args]


FULL = [{"n": i} for i in range(100)]


# ---------- fetch.api ----------


def test_api_reads_every_page_one_at_a_time_when_the_proxy_refuses_the_next_page_link(tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues/comments": fake_gh.pages(FULL, FULL, [{"n": "last"}], numeric_refused=True),
    })
    got = fetch.api("repos/acme/demo/issues/comments?per_page=100", paginate=True)
    assert got == [FULL, FULL, [{"n": "last"}]]
    assert _paged(gh) == [
        "repos/acme/demo/issues/comments?per_page=100&page=1",
        "repos/acme/demo/issues/comments?per_page=100&page=2",
        "repos/acme/demo/issues/comments?per_page=100&page=3",
    ]


def test_api_page_by_page_keeps_the_query_and_its_page_size(tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages([1, 2], [3], numeric_refused=True),
    })
    assert fetch.api("repos/acme/demo/issues?state=all&per_page=2", paginate=True) == [[1, 2], [3]]
    assert _paged(gh) == ["repos/acme/demo/issues?state=all&per_page=2&page=1", "repos/acme/demo/issues?state=all&per_page=2&page=2"]


def test_api_page_by_page_without_a_page_size_asks_for_100(tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/pulls": fake_gh.pages(FULL, [], numeric_refused=True)})
    assert fetch.api("repos/acme/demo/pulls", paginate=True) == [FULL, []]
    assert _paged(gh) == ["repos/acme/demo/pulls?per_page=100&page=1", "repos/acme/demo/pulls?per_page=100&page=2"]


def test_api_page_by_page_measures_an_object_page_by_its_list(tmp_path, monkeypatch):
    """Check runs come as `{"total_count": …, "check_runs": […]}`."""
    first = {"total_count": 101, "check_runs": FULL}
    second = {"total_count": 101, "check_runs": [{"n": "last"}]}
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/commits/abc/check-runs": fake_gh.pages(first, second, numeric_refused=True)})
    assert fetch.api("repos/acme/demo/commits/abc/check-runs?per_page=100", paginate=True) == [first, second]


def test_api_page_by_page_with_an_old_gh_too(tmp_path, monkeypatch):
    """A gh too old for `--slurp` prints the first page, then fails the same way."""
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues/comments": fake_gh.pages(FULL, [{"n": "last"}], numeric_refused=True)}, slurp=False)
    assert fetch.api("repos/acme/demo/issues/comments?per_page=100", paginate=True) == [FULL, [{"n": "last"}]]


def test_a_page_that_can_t_be_read_fails_with_gh_s_words(monkeypatch):
    def run(args):
        if "--paginate" in args:
            return subprocess.CompletedProcess(args, 1, "", fake_gh.NUMERIC_REFUSED + "\n")
        if args[-1].endswith("page=2"):
            return subprocess.CompletedProcess(args, 1, "", "gh: Server Error (HTTP 502)\n")
        return subprocess.CompletedProcess(args, 0, json.dumps(FULL), "")

    monkeypatch.setattr(fetch, "_run", run)
    with pytest.raises(fetch.GhError, match="HTTP 502"):
        fetch.api("repos/acme/demo/issues/comments?per_page=100", paginate=True)


def test_page_by_page_stops_at_a_bound_rather_than_read_forever(monkeypatch):
    def run(args):
        if "--paginate" in args:
            return subprocess.CompletedProcess(args, 1, "", fake_gh.NUMERIC_REFUSED + "\n")
        return subprocess.CompletedProcess(args, 0, json.dumps(FULL), "")

    monkeypatch.setattr(fetch, "_run", run)
    monkeypatch.setattr(fetch, "MAX_PAGES", 5)
    with pytest.raises(fetch.GhError, match="more than 5 pages"):
        fetch.api("repos/acme/demo/issues/comments?per_page=100", paginate=True)


# ---------- any other failure fails as before ----------


@pytest.mark.parametrize("stderr", [
    "gh: Server Error (HTTP 500)",
    "gh: Resource not accessible by integration (HTTP 403)",
    "gh: not permitted through this proxy (HTTP 403)",
    "gh: API rate limit exceeded (HTTP 403)",
])
def test_any_other_paginate_failure_fails_as_before(tmp_path, monkeypatch, stderr):
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues/comments": fake_gh.reply(exit=1, stderr=stderr + "\n")})
    with pytest.raises(fetch.GhError) as e:
        fetch.api("repos/acme/demo/issues/comments?per_page=100", paginate=True)
    assert str(e.value) == f"gh api failed: {stderr}"
    assert len(gh.calls()) == 1  # nothing read page by page


QUOTING = [_comment(1, 7, f"The proxy said: {fake_gh.NUMERIC_REFUSED}")]


def _old_gh_page_quotes_the_refusal(args):
    """A gh without `--slurp` whose `--paginate` prints a page that quotes the
    proxy's refusal in a comment, then fails on something else; each
    `page=N` answers `[]`."""
    if "--slurp" in args:
        return subprocess.CompletedProcess(args, 1, "", "unknown flag: --slurp\n")
    if "--paginate" in args:
        return subprocess.CompletedProcess(args, 1, json.dumps(QUOTING) + "\n", "gh: Server Error (HTTP 502)\n")
    return subprocess.CompletedProcess(args, 0, "[]", "")


def test_the_refusal_quoted_in_a_page_s_output_fails_as_before(monkeypatch):
    calls = []

    def run(args):
        calls.append(args)
        return _old_gh_page_quotes_the_refusal(args)

    monkeypatch.setattr(fetch, "_run", run)
    with pytest.raises(fetch.GhError) as e:
        fetch.api("repos/acme/demo/issues/comments?per_page=100", paginate=True)
    assert str(e.value) == "gh api failed: gh: Server Error (HTTP 502)"
    assert len(calls) == 2  # nothing read page by page


def test_the_issues_and_pulls_fetch_fails_as_before_when_a_page_quotes_the_refusal(monkeypatch):
    calls = []

    def run(args, **kw):
        calls.append(args)
        return _old_gh_page_quotes_the_refusal(args[1:])

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(SystemExit) as e:
        cli._fetch("acme/demo", "issues")
    assert "HTTP 502" in str(e.value) and "--issues/--prs" in str(e.value)
    assert len(calls) == 2  # nothing read page by page


def test_the_refusal_on_a_path_not_under_repos_fails_as_before(tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, {"graphql": fake_gh.reply(exit=1, stderr=fake_gh.NUMERIC_REFUSED + "\n")})
    with pytest.raises(fetch.GhError, match="Numeric-ID repository paths"):
        fetch.api("graphql", paginate=True, fields=[("-f", "query=q")])
    assert len(gh.calls()) == 1


def test_a_read_without_paginate_is_unchanged(tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/pulls/12": fake_gh.reply(exit=1, stderr=fake_gh.NUMERIC_REFUSED + "\n")})
    with pytest.raises(fetch.GhError, match="Numeric-ID repository paths"):
        fetch.api("repos/acme/demo/pulls/12")
    assert gh.paths() == ["repos/acme/demo/pulls/12"]


# ---------- the callers ----------


def test_research_stakes_fetch_lists_a_record_on_the_second_page_of_the_comments(tmp_path, monkeypatch):
    (tmp_path / ".claude/workflow").mkdir(parents=True)
    (tmp_path / ".claude/workflow/profile.toml").write_text('[project]\nname="d"\nrepo="acme/demo"\n', encoding="utf-8")
    first = [_comment(i, 7) for i in range(1, 101)]
    gh = fake_gh.install(tmp_path, monkeypatch, {
        "repos/acme/demo/issues": fake_gh.pages([{"number": 42, "title": "Deposits"}]),
        "repos/acme/demo/issues/comments": fake_gh.pages(first, [_comment(101, 42, STAKES)], numeric_refused=True),
        "repos/acme/demo/collaborators/owner/permission": {"permission": "admin", "user": {"login": "owner"}},
    })
    p = subprocess.run([sys.executable, "-B", str(CLI), "research", "stakes", "--fetch"], capture_output=True, text=True, cwd=tmp_path,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith('#42 2026-11-07 "Deposits": Stakes: touches payments.'), p.stdout
    assert "repos/acme/demo/issues/comments?per_page=100&page=2" in gh.paths()


def test_the_issues_and_pulls_fetch_reads_every_page_too(tmp_path, monkeypatch):
    """`_fetch`, behind `ready --fetch` and `status --fetch`."""
    first = [{"number": i} for i in range(1, 101)]
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.pages(first, [{"number": 101}], numeric_refused=True)})
    assert [i["number"] for i in cli._fetch("acme/demo", "issues")] == list(range(1, 102))
    assert gh.paths()[-1] == "repos/acme/demo/issues?state=all&per_page=100&page=2"


def test_the_issues_and_pulls_fetch_reads_every_page_with_an_old_gh_too(tmp_path, monkeypatch):
    """A gh too old for `--slurp` prints the first page, then fails the same way."""
    first = [{"number": i} for i in range(1, 101)]
    gh = fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/issues": fake_gh.pages(first, [{"number": 101}], numeric_refused=True)}, slurp=False)
    assert [i["number"] for i in cli._fetch("acme/demo", "issues")] == list(range(1, 102))
    assert gh.paths()[-1] == "repos/acme/demo/issues?state=all&per_page=100&page=2"


def test_the_issues_and_pulls_fetch_fails_on_a_page_that_can_t_be_read_with_an_old_gh(monkeypatch):
    def run(args, **kw):
        if "--slurp" in args:
            return subprocess.CompletedProcess(args, 1, "", "unknown flag: --slurp\n")
        if "--paginate" in args:
            return subprocess.CompletedProcess(args, 1, json.dumps(FULL) + "\n", fake_gh.NUMERIC_REFUSED + "\n")
        if args[-1].endswith("page=2"):
            return subprocess.CompletedProcess(args, 1, "", "gh: Server Error (HTTP 502)\n")
        return subprocess.CompletedProcess(args, 0, json.dumps(FULL), "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(SystemExit) as e:
        cli._fetch("acme/demo", "issues")
    assert "HTTP 502" in str(e.value) and "--issues/--prs" in str(e.value)


def test_the_issues_and_pulls_fetch_fails_as_before_on_any_other_failure(tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, {"repos/acme/demo/pulls": fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 500)\n")})
    with pytest.raises(SystemExit) as e:
        cli._fetch("acme/demo", "pulls")
    assert "HTTP 500" in str(e.value) and "--issues/--prs" in str(e.value)

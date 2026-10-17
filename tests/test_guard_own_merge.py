"""A ticket session merges, or arms auto-merge on, only its own pull request (#87).

A merge must be pinned to the head commit of the session's ticket branch, in
the field GitHub checks: `gh pr merge --match-head-commit`, the REST merge's
`sha`, `merge_pull_request`'s `expectedHeadSha`. `enable_pr_auto_merge` and
the session route `pulls/<n>/ccr/auto_merge` take no pin GitHub is known to
check, so the guard always reads the pull request's head instead (faked
here). Conductor and attended sessions are unchanged.
"""

import json

import pytest

from conftest import git
from workflow import guard
from workflow.guard import decide
from workflow.profile import load

BRANCH = "claude/build-87"
OTHER = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def ticket(repo):
    """The repo fixture, on the session's ticket branch with a commit of its own."""
    git(repo, "checkout", "-qb", BRANCH)
    (repo / "x.txt").write_text("x")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-qm", "work")
    return repo


def head(root):
    return git(root, "rev-parse", "HEAD").strip()


def run(root, event, role="ticket"):
    return decide(event, load(root), role, root, BRANCH)


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def mcp(name, **inp):
    return {"tool_name": f"mcp__github__{name}", "tool_input": {"owner": "acme", "repo": "demo", **inp}}


# ---------- merges pinned to the branch's own head are allowed ----------


@pytest.mark.parametrize(
    "form",
    [
        "gh pr merge 12 --merge --match-head-commit {sha}",
        "gh pr merge 12 --merge --match-head-commit={sha}",
        "gh pr merge --match-head-commit {sha} --merge 12",
        "gh pr merge 12 --auto --merge --match-head-commit {sha}",
        "gh api -X PUT repos/acme/demo/pulls/12/merge -f merge_method=merge -f sha={sha}",
        "gh api --method PUT repos/acme/demo/pulls/12/merge -f sha={sha} -f merge_method=merge",
        "gh api -X PUT repos/acme/demo/pulls/12/merge -f sha={sha} -F sha={sha}",
        "gh pr merge 12 --merge -b 'Done: --disable-auto next' --match-head-commit {sha}",
        "gh pr merge 12 --disable-auto",
    ],
)
def test_a_merge_pinned_to_the_branch_head_is_allowed(ticket, form):
    d = run(ticket, bash(form.format(sha=head(ticket))))
    assert d.action == "allow", d.reason


def test_merge_pull_request_pinned_to_the_branch_head_is_allowed(ticket):
    d = run(ticket, mcp("merge_pull_request", pullNumber=12, merge_method="merge", expectedHeadSha=head(ticket)))
    assert d.action == "allow", d.reason


@pytest.mark.parametrize("key", ["sha", "expectedHeadOid"])
def test_merge_pull_request_pinned_only_by_a_field_the_tool_doesnt_send_is_refused(ticket, key):
    d = run(ticket, mcp("merge_pull_request", pullNumber=99, **{key: head(ticket)}))
    assert d.action == "deny" and "expectedHeadSha" in d.reason


def test_merge_pull_request_with_both_pins_needs_both_to_match(ticket):
    sha = head(ticket)
    assert run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha=sha, sha=sha)).action == "allow"
    d = run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha=sha, sha=OTHER))
    assert d.action == "deny" and OTHER in d.reason


def test_the_pin_is_read_case_insensitively(ticket):
    d = run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha=head(ticket).upper()))
    assert d.action == "allow", d.reason


# ---------- unpinned, or pinned to another commit, is refused with the fix ----------


@pytest.mark.parametrize(
    "event",
    [
        bash("gh pr merge 12 --merge"),
        bash("gh pr merge 12"),
        bash("gh pr merge --merge"),
        bash("gh pr merge 12 --auto --merge"),
        bash("gh pr merge 12 --squash --match-head-commit"),
        bash("gh api -X PUT repos/acme/demo/pulls/12/merge -f merge_method=merge"),
        mcp("merge_pull_request", pullNumber=12, merge_method="merge"),
        mcp("merge_pull_request", pullNumber=12, expectedHeadSha=""),
    ],
)
def test_an_unpinned_merge_is_refused_naming_the_fix(ticket, event):
    d = run(ticket, event)
    assert d.action == "deny"
    assert "its own pull request" in d.reason
    assert "--match-head-commit" in d.reason and "expectedHeadSha" in d.reason and "sha=" in d.reason
    assert "git rev-parse HEAD" in d.reason


@pytest.mark.parametrize(
    "event",
    [
        bash(f"gh pr merge 12 --merge --match-head-commit {OTHER}"),
        bash(f"gh pr merge 12 --auto --merge --match-head-commit={OTHER}"),
        bash(f"gh api -X PUT repos/acme/demo/pulls/12/merge -f merge_method=merge -f sha={OTHER}"),
        bash(f"gh api -X PUT repos/acme/demo/pulls/12/merge -f sha={{sha}} -f sha={OTHER}"),
        bash(f"gh api -X PUT repos/acme/demo/pulls/12/merge -f sha={{sha}} -F sha={OTHER}"),
        bash(f"gh pr merge 12 --merge --match-head-commit {{sha}} --match-head-commit={OTHER}"),
        mcp("merge_pull_request", pullNumber=12, expectedHeadSha=OTHER),
        mcp("merge_pull_request", pullNumber=12, expectedHeadSha="{sha}", sha=OTHER),
    ],
)
def test_a_merge_pinned_to_another_commit_is_refused(ticket, event):
    event = json.loads(json.dumps(event).replace("{sha}", head(ticket)))  # every pin is checked, not the first
    d = run(ticket, event)
    assert d.action == "deny"
    assert OTHER in d.reason and head(ticket) in d.reason and BRANCH in d.reason
    assert "git pull" in d.reason  # the fix when the pull request's head moved on GitHub


def test_an_abbreviated_pin_is_refused(ticket):
    d = run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha=head(ticket)[:7]))
    assert d.action == "deny" and "full" in d.reason


@pytest.mark.parametrize(
    "form",
    [
        "gh api -X PUT repos/acme/demo/pulls/12/merge -f sha={sha} --input body.json",
        "gh api -X PUT repos/acme/demo/pulls/12/merge -f sha={sha} --input -",
        "gh api -X PUT repos/acme/demo/pulls/12/merge -F sha=@pin.txt",
        "gh api -X PUT repos/acme/demo/pulls/12/merge --input body.json",
    ],
)
def test_a_rest_merge_with_a_body_the_guard_doesnt_read_is_refused(ticket, form):
    # With `--input`, gh sends the file as the body and the fields in the query string.
    d = run(ticket, bash(form.format(sha=head(ticket))))
    assert d.action == "deny" and "-f sha=" in d.reason


@pytest.mark.parametrize(
    "form",
    [
        "gh pr merge 99 --merge -t --disable-auto",
        "gh pr merge 99 --merge --subject --disable-auto",
        "gh pr merge 99 --merge -b --disable-auto",
        "gh pr merge 99 --merge -A --disable-auto",
        "gh pr merge 99 --merge -mb --disable-auto",
        "gh pr merge 99 --merge -b --match-head-commit={sha}",
        "gh pr merge 99 --disable-auto --merge",
        "gh pr merge 99 --disable-auto --auto --merge",
    ],
)
def test_gh_pr_merge_is_read_as_pflag_reads_it(ticket, form):
    d = run(ticket, bash(form.format(sha=head(ticket))))
    assert d.action == "deny", d.reason
    assert "--match-head-commit" in d.reason


def test_a_merge_word_the_shell_fills_in_is_refused_even_pinned(ticket):
    d = run(ticket, bash(f"gh pr merge 99 --merge --match-head-commit {head(ticket)} $X"))
    assert d.action == "deny" and "$X" in d.reason and "write this merge out" in d.reason


def test_an_upper_case_merge_path_is_a_merge(ticket):
    d = run(ticket, bash("gh api -X PUT repos/acme/demo/pulls/12/MERGE -f merge_method=merge"))
    assert d.action == "deny" and "pinned" in d.reason


@pytest.mark.parametrize("name", ["merge_pull_request", "enable_pr_auto_merge"])
def test_a_merge_in_another_repository_is_refused(ticket, name):
    event = {"tool_name": f"mcp__github__{name}", "tool_input": {"owner": "other", "repo": "x", "pullNumber": 3, "expectedHeadSha": head(ticket)}}
    d = run(ticket, event)
    assert d.action == "deny" and "acme/demo" in d.reason and "another repository" in d.reason


def test_a_pin_the_shell_fills_in_is_refused(ticket):
    d = run(ticket, bash('gh pr merge 12 --merge --match-head-commit "$(git rev-parse HEAD)"'))
    assert d.action == "deny" and "write this merge out" in d.reason
    d = run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha="$(git rev-parse HEAD)"))
    assert d.action == "deny" and "full commit sha" in d.reason  # no shell fills in an MCP tool's input


@pytest.mark.parametrize(
    "form",
    [
        # The lexer drops quoting, so any expansion counts, a heredoc's or a text value's too.
        "gh pr merge 99 --match-head-commit {sha} {--merge,--match-head-commit=}",
        "gh pr merge --merge --match-head-commit {sha} $(cat <<'EOF'\n99 --match-head-commit=x\nEOF\n)",
        "gh pr merge --merge --match-head-commit {sha} -t $(printf 'x 99 --match-head-commit=')",
        "gh pr merge 99 --merge --match-head-commit {sha} *",
        "gh pr merge 99 --merge --match-head-commit {sha} --subject \"$T\"",
        "gh pr merge 99 --merge --match-head-commit {sha} -b `cat b.txt`",
        "gh api -X PUT repos/acme/demo/pulls/99/merge -f sha={sha} {-f,sha=x}",
        "gh api -X PUT repos/acme/demo/pulls/99/merge -f sha={sha} $(printf -- '-f sha=X')",
        "gh api -X PUT repos/acme/demo/pulls/9?/merge -f sha={sha}",
        "printf '99 --match-head-commit=' | xargs gh pr merge --merge --match-head-commit {sha}",
        "echo '-f sha=x' | xargs gh api -X PUT repos/acme/demo/pulls/99/merge -f sha={sha}",
        "echo 12 | xargs -I N gh api -X PUT repos/acme/demo/pulls/N/ccr/auto_merge",
    ],
)
def test_a_merge_the_shell_could_add_words_to_is_refused(ticket, pr_heads, form):
    pr_heads[12] = (BRANCH, head(ticket))
    d = run(ticket, bash(form.replace("{sha}", head(ticket))))
    assert d.action == "deny", form
    assert "write this" in d.reason or "not `PUT" in d.reason, d.reason


@pytest.mark.parametrize(
    "form",
    [
        "gh pr merge 99 --merge --match-head-commit {sha} --match-head-commit ''",
        "gh pr merge 99 --merge --match-head-commit={sha} --match-head-commit=",
    ],
)
def test_an_empty_pin_beside_a_set_one_is_refused(ticket, form):
    # gh sends the last value: an empty one leaves the merge unpinned.
    d = run(ticket, bash(form.replace("{sha}", head(ticket))))
    assert d.action == "deny" and "full commit sha" in d.reason


@pytest.mark.parametrize(
    "form",
    [
        "gh pr merge 99 --disable-auto=false",
        "gh pr merge 99 --disable-auto=false --merge",
        "gh pr merge 99 --disable-auto $X",
        "gh pr merge 99 --disable-auto {--disable-auto=false,--auto,--merge}",
        "gh pr merge 99 --disable-auto *",
    ],
)
def test_disable_auto_with_a_value_is_no_disarm(ticket, form):
    d = run(ticket, bash(form))
    assert d.action == "deny" and ("--match-head-commit" in d.reason or "write this" in d.reason)


@pytest.mark.parametrize("number", ["\u0661\u0662", "12 ", True, 12.0, [12]])
def test_arming_needs_a_plain_pull_request_number(ticket, pr_heads, number):
    pr_heads[12] = (BRANCH, head(ticket))
    d = run(ticket, mcp("enable_pr_auto_merge", pullNumber=number))
    assert d.action == "deny" and "name its number" in d.reason
    assert pr_heads["calls"] == []


@pytest.mark.parametrize("inp", [{"owner": "acme"}, {"owner": ["acme"], "repo": "demo"}, {"owner": "acme", "repo": "other"}])
def test_an_mcp_merge_naming_another_repository_reads_plainly(ticket, inp):
    d = run(ticket, {"tool_name": "mcp__github__merge_pull_request", "tool_input": {"pullNumber": 3, "expectedHeadSha": head(ticket), **inp}})
    assert d.action == "deny" and "another repository" in d.reason and "None" not in d.reason and "[" not in d.reason


def test_a_pin_that_isnt_text_reads_plainly(ticket):
    d = run(ticket, mcp("merge_pull_request", pullNumber=3, expectedHeadSha={"a": "b"}))
    assert d.action == "deny" and "not a string" in d.reason and "{" not in d.reason


def test_the_pin_is_one_more_commit_behind_after_a_new_commit(ticket):
    old = head(ticket)
    (ticket / "y.txt").write_text("y")
    git(ticket, "add", "y.txt")
    git(ticket, "commit", "-qm", "more")
    assert run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha=old)).action == "deny"


def test_off_the_ticket_branch_a_merge_is_refused(ticket):
    sha = head(ticket)
    git(ticket, "checkout", "-q", "main")
    d = run(ticket, mcp("merge_pull_request", pullNumber=12, expectedHeadSha=sha))
    assert d.action == "deny" and "claude/build-*" in d.reason


def test_without_a_git_checkout_a_merge_is_refused(profile, tmp_path):
    d = decide(mcp("merge_pull_request", pullNumber=12, expectedHeadSha=OTHER), profile, "ticket", tmp_path, BRANCH)
    assert d.action == "deny"


def test_disarming_and_reading_need_no_pin(ticket):
    for event in (
        bash("gh pr merge 12 --disable-auto"),
        bash("gh api -X DELETE repos/acme/demo/pulls/12/ccr/auto_merge"),
        bash("gh api repos/acme/demo/pulls/12"),
        mcp("disable_pr_auto_merge", pullNumber=12),
        mcp("pull_request_read", method="get", pullNumber=12),
    ):
        d = run(ticket, event)
        assert d.action == "allow", (event, d.reason)


def test_admin_is_still_refused_even_pinned(ticket):
    d = run(ticket, bash(f"gh pr merge 12 --admin --match-head-commit {head(ticket)}"))
    assert d.action == "deny" and "--admin" in d.reason


# ---------- arming without a pin: the guard reads the pull request's head ----------


@pytest.fixture
def pr_heads(monkeypatch):
    """Fake pull requests: number -> (head branch, head sha); missing -> can't read."""
    heads: dict[int, tuple[str, str]] = {}
    calls: list[tuple[str, int]] = []

    def fake(repo, number):
        calls.append((repo, number))
        return heads.get(number)

    monkeypatch.setattr(guard, "_pr_head", fake)
    heads["calls"] = calls  # type: ignore[index]
    return heads


@pytest.mark.parametrize(
    "event",
    [
        mcp("enable_pr_auto_merge", pullNumber=12, mergeMethod="MERGE"),
        bash("gh api -X PUT repos/acme/demo/pulls/12/ccr/auto_merge -f merge_method=merge"),
        bash("gh api -X PUT repos/{owner}/{repo}/pulls/12/ccr/auto_merge"),
    ],
)
def test_arming_its_own_pull_request_is_allowed(ticket, pr_heads, event):
    pr_heads[12] = (BRANCH, head(ticket))
    d = run(ticket, event)
    assert d.action == "allow", d.reason
    assert pr_heads["calls"] == [("acme/demo", 12)]


@pytest.mark.parametrize(
    "event",
    [
        mcp("enable_pr_auto_merge", pullNumber=12, mergeMethod="MERGE"),
        mcp("enable_pr_auto_merge", pullNumber=12, expectedHeadSha="{sha}"),
        bash("gh api -X PUT repos/acme/demo/pulls/12/ccr/auto_merge -f merge_method=merge"),
        bash("gh api -X PUT repos/acme/demo/pulls/12/ccr/auto_merge -f sha={sha}"),
        bash("gh api -X PUT repos/acme/demo/pulls/12/ccr/auto_merge -f expected_head_oid={sha}"),
    ],
)
def test_arming_another_pull_request_is_refused(ticket, pr_heads, event):
    # A pin these routes aren't known to check never stands in for the read-back.
    pr_heads[12] = ("claude/build-99", head(ticket))
    d = run(ticket, json.loads(json.dumps(event).replace("{sha}", head(ticket))))
    assert d.action == "deny"
    assert "claude/build-99" in d.reason and BRANCH in d.reason and "its own pull request" in d.reason


def test_arming_its_own_pull_request_on_a_moved_head_is_refused(ticket, pr_heads):
    pr_heads[12] = (BRANCH, OTHER)
    d = run(ticket, mcp("enable_pr_auto_merge", pullNumber=12))
    assert d.action == "deny" and OTHER in d.reason and "git pull" in d.reason and "push" in d.reason


def test_arming_when_the_head_cant_be_read_is_refused_naming_the_pinned_way(ticket, pr_heads):
    d = run(ticket, mcp("enable_pr_auto_merge", pullNumber=12))
    assert d.action == "deny"
    assert "--match-head-commit" in d.reason and "conductor" in d.reason


def test_arming_with_no_pull_number_is_refused(ticket, pr_heads):
    d = run(ticket, mcp("enable_pr_auto_merge"))
    assert d.action == "deny"
    assert pr_heads["calls"] == []


def test_the_pr_is_read_in_the_repository_named(ticket, pr_heads):
    pr_heads[12] = (BRANCH, head(ticket))
    run(ticket, {"tool_name": "mcp__github__enable_pr_auto_merge", "tool_input": {"pullNumber": 12}})
    assert pr_heads["calls"] == [("acme/demo", 12)]  # the profile's repo when none is named


def test_pr_head_reads_github_with_gh(monkeypatch):
    seen = {}

    class Done:
        returncode = 0
        stdout = "claude/build-87 abc acme/demo\n"

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["timeout"] = kw.get("timeout")
        seen["stdin"] = kw.get("stdin")
        return Done()

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    assert guard._pr_head("acme/demo", 12) == ("claude/build-87", "abc")
    assert seen["argv"][:3] == ["gh", "api", "repos/acme/demo/pulls/12"]
    assert seen["timeout"] and seen["stdin"] is guard.subprocess.DEVNULL

    Done.stdout = "claude/build-87 abc ACME/Demo\n"
    assert guard._pr_head("acme/demo", 12) == ("claude/build-87", "abc")
    Done.stdout = "claude/build-87 abc someone/fork\n"  # a fork's branch of the same name
    assert guard._pr_head("acme/demo", 12) == ("someone/fork:claude/build-87", "abc")
    Done.stdout = "claude/build-87 abc\n"  # the head's repository is gone
    assert guard._pr_head("acme/demo", 12) is None

    Done.returncode = 1
    assert guard._pr_head("acme/demo", 12) is None

    def boom(argv, **kw):
        raise OSError("no gh")

    monkeypatch.setattr(guard.subprocess, "run", boom)
    assert guard._pr_head("acme/demo", 12) is None


# ---------- conductor and attended sessions are unchanged ----------


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "event",
    [
        bash("gh pr merge 12 --merge"),
        bash("gh pr merge 12 --auto --merge"),
        bash("gh api -X PUT repos/acme/demo/pulls/12/merge -f merge_method=merge"),
        mcp("merge_pull_request", pullNumber=12, merge_method="merge"),
        mcp("merge_pull_request", pullNumber=12, expectedHeadSha=OTHER),
        mcp("enable_pr_auto_merge", pullNumber=12),
    ],
)
def test_conductor_and_attended_are_unchanged(ticket, pr_heads, role, event):
    d = run(ticket, event, role)
    assert d.action == "allow", d.reason
    assert pr_heads["calls"] == []

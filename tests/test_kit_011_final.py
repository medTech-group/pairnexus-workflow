"""Kit 0.1.1, the final pass's findings: each pinned.

Every command here is data passed to `decide`; none is run.
"""

import gc
import json
import time

import pytest

from conftest import pinned
from workflow import posts, render
from workflow.guard import decide
from workflow.issues import protected_named
from workflow.posts import AGENT_MARKER
from workflow.profile import DEFAULT_PROTECTED

M = AGENT_MARKER

# How the linear-time checks below measure: the same call at size n/8 and at
# size n, in this process's CPU time (time other processes take on a busy
# machine isn't counted), interleaved and best of a few repeats each with the
# garbage collector off (as `timeit` does). The ratio of the two is what is
# judged, never seconds. Linear work grows about 8 times from one size to the
# other, quadratic about 64 times and exponential beyond measure; a ratio
# under 24 passes. A large run past ENOUGH_CPU_SECONDS ends the repeats: a
# run that long is a regression to judge now, never noise.
GROWTH = 8
LINEAR_LIMIT = 24
REPEATS = 5
ENOUGH_CPU_SECONDS = 2


def assert_grows_linearly(run, make, n):
    """Asserts that `run(make(n))`'s best time is under LINEAR_LIMIT times
    `run(make(n // GROWTH))`'s. `make` builds the input outside the timing."""
    inputs = [make(n // GROWTH), make(n)]
    best = [float("inf"), float("inf")]
    enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(REPEATS):
            for i, arg in enumerate(inputs):
                start = time.process_time()
                run(arg)
                best[i] = min(best[i], time.process_time() - start)
            if best[1] > ENOUGH_CPU_SECONDS:
                break
    finally:
        if enabled:
            gc.enable()
    ratio = best[1] / max(best[0], 1e-9)
    assert ratio < LINEAR_LIMIT, f"{n // GROWTH} -> {n} took {ratio:.1f} times as long ({best[0]:.4f}s, {best[1]:.4f}s)"


def act(profile, root, cmd, role="conductor"):
    branch = "claude/build-1" if role == "ticket" else "main"
    return decide({"tool_name": "Bash", "tool_input": {"command": cmd}}, profile, role, root, branch, role_from_env=True)


# ---------- 1, 2. a body GraphQL hides from a plain reading ----------

HIDDEN = {
    "a variable's default value": 'mutation($i:UpdateIssueInput={id:"x",body:"secret"}){updateIssue(input:$i){issue{id}}}',
    "a comma before the arguments": 'mutation{updateIssue , (input:{id:"x",body:"secret"}){issue{id}}}',
    "a comment before the arguments": 'mutation{updateIssue #c\n(input:{id:"x",body:"secret"}){issue{id}}}',
    "a comma before an alias's arguments": 'mutation{a : updateIssue ,(input:{id:"x",body:"secret"}){issue{id}}}',
    "a comment holding a quote": 'mutation{updateIssue # it"s\n(input:{id:"x",body:"secret"}){issue{id}}}',
}


@pytest.mark.parametrize("case", sorted(HIDDEN))
def test_a_hidden_body_needs_the_marker(case, profile, tmp_path):
    q = HIDDEN[case]
    d = act(profile, tmp_path, f"gh api graphql -f query='{q}'")
    assert d.action == "deny" and M in d.reason, case
    (tmp_path / "q.json").write_text(json.dumps({"query": q}))
    d = act(profile, tmp_path, "gh api graphql --input q.json")
    assert d.action == "deny" and M in d.reason, case
    marked = q.replace('"secret"', f'"secret {M}"')
    assert act(profile, tmp_path, f"gh api graphql -f query='{marked}'").action != "deny", case


def test_a_hash_or_comma_in_a_string_stays_text(profile, tmp_path):
    q = 'mutation{updateIssue(input:{id:"x#,",state:CLOSED}){issue{body}}}'
    assert act(profile, tmp_path, f"gh api graphql -f query='{q}'").action != "deny"


# ---------- 3. readiness notes: when in doubt, note ----------

NOTED = {
    "never mind": "Never mind the earlier note; update `.claude/settings.json`.",
    "a don't in an earlier clause": "Don't break the build: edit `.github/workflows/ci.yml`.",
    "a load in an earlier clause": "Load times are slow; make `.github/workflows/ci.yml` cache pip.",
    "a parse in an earlier sentence": "Parsing is slow. Tweak `.github/workflows/ci.yml`.",
    "a fence after 'to'": "Add a job to:\n\n```yaml\n# .github/workflows/ci.yml\njobs: {}\n```\n",
}


@pytest.mark.parametrize("case", sorted(NOTED))
def test_change_requests_are_noted(case):
    assert [p for p, _ in protected_named(NOTED[case], DEFAULT_PROTECTED)] == [
        ".claude/settings.json" if case == "never mind" else ".github/workflows/ci.yml"
    ], case


# ---------- 4, 5. comments in odd shapes are errors, not tracebacks ----------


def _c(**kw):
    c = {"id": 7, "user": {"login": "owner"}, "body": "hi", "html_url": "https://github.com/a/b/issues/1#issuecomment-7"}
    c.update(kw)
    return c


def test_a_body_that_isnt_text_is_a_comments_error():
    with pytest.raises(posts.CommentsError, match="body is a int"):
        posts.owner_words([_c(body=5)], "owner")


def test_a_digit_like_id_falls_back_to_the_url():
    assert [w["id"] for w in posts.owner_words([_c(id="²")], "owner")] == [7]


def test_issue_view_with_its_comments_reads_the_comments():
    view = {
        "body": "the issue",
        "url": "https://github.com/a/b/issues/1",
        "comments": [{"id": "IC_x", "author": {"login": "owner"}, "body": "go", "url": "https://github.com/a/b/issues/1#issuecomment-9"}],
    }
    assert [(w["id"], w["body"]) for w in posts.owner_words(view, "owner")] == [(9, "go")]


# ---------- 6. the seal is read in linear time ----------


def test_seal_of_many_blank_lines_is_fast():
    assert render.seal_of("x" + "\n" * 200_000 + "y") == (None, None)
    assert_grows_linearly(render.seal_of, lambda n: "x" + "\n" * n + "y", 200_000)


def test_seal_still_reads_as_before():
    sealed = render.seal("line one\n  line two\n")
    assert render.sealed_intact(sealed)
    assert render.sealed_intact(sealed.replace("\n", "\r\n") + "\n\n  \n")
    assert not render.sealed_intact(sealed.replace("two", "2"))
    assert render.seal_of("Briefing 0123456789ab")[0] == "0123456789ab"


# ---------- the second pass on the final fixes ----------

M_SAFE = f'mutation{{addComment(input:{{subjectId:"x",body:"y {M}"}}){{clientMutationId}}}}'
DELETE = 'mutation{deleteIssue(input:{issueId:"z"}){clientMutationId}}'


@pytest.mark.parametrize(
    "decoy",
    [
        f"-f a='{M_SAFE} #'",
        f"-H 'X-A: {M_SAFE} #'",
        f"-f a='{M_SAFE} \"'",
    ],
)
def test_ticket_reads_only_the_query(decoy, profile, tmp_path):
    cmd = f"gh api graphql {decoy} -f query='{DELETE}' -f b='\"'"
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", decoy


def test_ticket_sessions_use_no_graphql(profile, tmp_path):
    for q in (M_SAFE, "query{viewer{login}}", 'mutation{enablePullRequestAutoMerge(input:{pullRequestId:"x"}){clientMutationId}}'):
        d = act(profile, tmp_path, f"gh api graphql -f query='{q}'", role="ticket")
        assert d.action == "deny" and "enable_pr_auto_merge" in d.reason, q
    # The same calls through the MCP tools and REST stay open to them.
    merge = pinned("gh api -X PUT repos/acme/demo/pulls/3/merge -f merge_method=merge -f sha={sha}", tmp_path)  # pinned (#87)
    assert act(profile, tmp_path, merge, role="ticket").action == "allow"


CONDUCTOR_HIDDEN = {
    "an escaped quote in a block string": 'mutation{a:updateIssue(input:{id:"x",title:"""t \\""" """}){issue{id}} addComment(input:{subjectId:"x",body:"hi",clientMutationId:"""z"""}){clientMutationId}}',
    "an inline fragment on Mutation": 'mutation{... on Mutation{addComment(input:{subjectId:"x",body:"hi"}){clientMutationId}}}',
    "a named fragment on Mutation": 'mutation{...F} fragment F on Mutation{updateIssue(input:{id:"x",body:"hi"}){issue{id}}}',
    "an unterminated string": 'mutation{updateIssue(input:{id:"x",body:"hi}){issue{id}}}',
}


@pytest.mark.parametrize("case", sorted(CONDUCTOR_HIDDEN))
def test_conductor_reads_what_graphql_reads(case, profile, tmp_path):
    (tmp_path / "q.json").write_text(json.dumps({"query": CONDUCTOR_HIDDEN[case]}))
    d = act(profile, tmp_path, "gh api graphql --input q.json")
    assert d.action == "deny" and M in d.reason, case


def test_gql_lexing_is_linear():
    from workflow.guard import _gql_plain

    assert _gql_plain('"' + '\\"' * 200_000) is None
    assert _gql_plain('"""' + '\\"""' * 100_000) is None
    assert_grows_linearly(_gql_plain, lambda n: '"' + '\\"' * n, 200_000)
    assert_grows_linearly(_gql_plain, lambda n: '"""' + '\\"""' * n, 100_000)


def test_into_is_linear():
    assert_grows_linearly(
        lambda text: protected_named(text, DEFAULT_PROTECTED),
        lambda n: "Add it to" + " " * n + "x\n```\n.env\n```\n",
        200_000,
    )


def test_more_clauses_and_fences():
    assert [p for p, _ in protected_named("Don't break anything, just edit `.github/workflows/ci.yml`.", DEFAULT_PROTECTED)] == [".github/workflows/ci.yml"]
    assert [p for p, _ in protected_named("Append this to:\n```\n.github/workflows/ci.yml\n```\n", DEFAULT_PROTECTED)] == [".github/workflows/ci.yml"]
    # A second fence later doesn't count on the first one's "to:".
    body = "Add a job to:\n```\njobs: {}\n```\n```\ncp .env.example .env\n```\n"
    assert protected_named(body, DEFAULT_PROTECTED) == []


def test_a_rest_issue_object_isnt_a_comment():
    issue = {"id": 99999, "number": 3, "body": "x", "url": "https://api.github.com/repos/a/b/issues/3", "user": {"login": "owner"}, "comments": 3}
    with pytest.raises(posts.CommentsError):
        posts.owner_words([issue], "owner")


# ---------- the third pass: fields the parse doesn't know ----------


@pytest.mark.parametrize(
    "form",
    [
        "-f=query='{q}'",
        "-F=query='{q}'",
        "-if query='{q}'",
        "-ifquery='{q}'",
        "-iFquery='{q}'",
        "-if=query='{q}'",
        "-f \"$Q=\"'{q}'",
        "-f \"${{Q}}=\"'{q}'",
        "-f \"$(echo query)=\"'{q}'",
        "{{-f,query='{q}'}}",
    ],
)
def test_ticket_backstop_catches_unparsed_fields(form, profile, tmp_path):
    cmd = "gh api graphql " + form.format(q=DELETE)
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", form


@pytest.mark.parametrize("form", ["-f=query='{q}'", "-if query='{q}'"])
def test_conductor_reads_short_flag_forms(form, profile, tmp_path):
    q = 'mutation{addComment(input:{subjectId:"x",body:"b"}){clientMutationId}}'
    d = act(profile, tmp_path, "gh api graphql " + form.format(q=q))
    assert d.action == "deny" and M in d.reason, form


def test_a_name_graphql_doesnt_allow_fails_closed(profile, tmp_path):
    from workflow.guard import _mutation_calls

    assert _mutation_calls('mutation{ñ deleteIssue(input:{issueId:"x"}){clientMutationId}}') is None


def test_many_mutation_words_are_read_in_linear_time():
    from workflow.guard import _mutation_calls

    assert_grows_linearly(_mutation_calls, lambda n: "mutation " * n + "{a}", 20_000)
    assert_grows_linearly(_mutation_calls, lambda n: "mutation{" + "a " * n + "}", 50_000)


# ---------- the last pass: older routes it found ----------

MERGE = "mutation{mergeBranch(input:{}){clientMutationId}}"


@pytest.mark.parametrize(
    "cmd",
    [
        f"f() {{ gh api \"$@\"; }}; f graphql -f query='{MERGE}'",
        f"f() {{\n  gh api \"$@\"\n}}\nf graphql -f query='{MERGE}'",
        "f() { git push \"$@\"; }; f origin main",
        "g() { git push origin \"$1\"; }; g main",
        "g() { gh pr merge \"${1}\" --admin; }; g 3",
    ],
)
def test_ticket_gh_and_git_take_no_parameters(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "curl -d'{\"query\":\"mutation{x}\"}' https://api.github.com/graphql",
        "curl -d@q.json https://api.github.com/graphql",
        "curl -Tq.json https://api.github.com/repos/acme/demo/issues",
        "curl -Fquery=x https://api.github.com/graphql",
        "curl -K cfg https://api.github.com/graphql",
        "curl -sd x https://API.GITHUB.COM/graphql",
    ],
)
def test_curl_writes_to_github_with_joined_flags(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


@pytest.mark.parametrize("cmd", ["gh auth status --show-token", "gh auth status -t", "gh auth status -ht github.com"])
def test_ticket_never_prints_the_token(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "gh auth status",
        "curl -fsSL https://api.github.com/repos/acme/demo/issues/3",
        "for n in 3 4; do gh pr view $n; done",
        "git log -1 --format=%H",
    ],
)
def test_ordinary_ticket_commands_still_run(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "allow", cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "GH_REPO=other/repo gh api -X PUT 'repos/{owner}/{repo}/pulls/1/merge'",
        "export GH_REPO=other/repo; gh pr merge 1 --merge",
        "env GH_REPO=o/r gh pr merge 1",
        "gh pr merge 1 --merge -R other/repo",
        "gh pr merge 1 --merge --repo=other/repo",
        "gh pr view 1 -Rother/repo",
        "GH_HOST=x gh pr list",
    ],
)
def test_ticket_gh_stays_in_this_repository(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


def test_ticket_gh_may_name_this_repository(profile, tmp_path):
    assert act(profile, tmp_path, "gh pr view 3 -R acme/demo", role="ticket").action == "allow"
    assert act(profile, tmp_path, "gh pr view 3 --repo ACME/demo", role="ticket").action == "allow"


# ---------- the review of the older routes' fixes ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -m \"$(cat <<'EOF'\nHandle \"$@\" in the wrapper\nEOF\n)\"",
        f"gh pr create --title t --body \"$(cat <<'EOF'\nUses $1 now\n{M}\nEOF\n)\"",
        "gh pr list -R=acme/demo",
        "gh pr list -R github.com/acme/demo",
        "gh pr list -R acme/demo.git",
        "gh pr list -R git@github.com:acme/demo.git",
        f"gh pr comment 3 --body 'see https://github.com/other/repo/issues/5 {M}'",
        "curl -d @github-payload.json https://hooks.example.com/x",
        "gh pr merge https://github.com/acme/demo/pull/5 --merge --match-head-commit {sha}",
    ],
)
def test_ticket_text_that_only_mentions_these_is_fine(cmd, profile, tmp_path):
    cmd = pinned(cmd, tmp_path)  # a ticket session's merge is pinned to its branch's head (#87)
    d = act(profile, tmp_path, cmd, role="ticket")
    assert d.action == "allow", (cmd, d.reason)


@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr merge https://github.com/other/repo/pull/5 --merge",
        "gh pr close github.com/other/repo/pull/5",
        f"gh issue comment https://github.com/other/repo/issues/5 --body 'x {M}'",
        "gh pr merge 1 -mR other/repo",
        "gh pr merge 1 -mRother/repo",
        "GH_REPO+=other/repo gh pr merge 1 --merge",
        "gh auth status -t=true",
        "f() { /usr/lib/git-core/git-push \"$@\"; }; f origin main",
        "f() { git push origin HEAD:$1; }; f main",
        "curl -sX PATCH https://api.github.com/repos/acme/demo/issues/1",
        "curl --expand-data x https://api.github.com/graphql",
    ],
)
def test_ticket_routes_the_review_found(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


# ---------- parameters are refused outside free text ----------


@pytest.mark.parametrize(
    "cmd",
    [
        'f(){ git push "--$1" origin claude/build-1; }; f force',
        'f(){ git push "-$1" origin claude/build-1; }; f f',
        'f(){ git push origin "$1":claude/build-1; }; f +HEAD',
        'f(){ gh pr merge 3 "--$1"; }; f admin',
        'f(){ gh pr merge "https://github.com/$1/pull/5"; }; f other/repo',
        'gh pr merge "$(echo $1)"',
        "gh pr merge https://github.com:443/other/repo/pull/5",
        "gh pr merge https://x@github.com/other/repo/pull/5",
        "curl --expand-json x https://api.github.com/graphql",
        "curl --upl f https://uploads.github.com/x",
        "curl --request=PATCH https://api.github.com/repos/acme/demo/issues/1",
    ],
)
def test_parameters_and_routes_outside_free_text(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


def test_bundled_repo_flag_is_linear(profile, tmp_path):
    from workflow.guard import _gh_problem  # noqa: F401  (the path the regex runs on)

    def run(cmd):  # each size reaches the `-R` reading, so the regex is what is timed
        decision = act(profile, tmp_path, cmd, role="ticket")
        assert decision.action == "deny" and "work only in acme/demo" in decision.reason

    assert_grows_linearly(run, lambda n: "gh pr list --search '-" + "R" * n + "\nx'", 80_000)


# ---------- what the guard can't tell from text: the heredoc is the way ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -m 'costs $5'",
        "git commit -m'Uses $@ now'",
        "git checkout -m \"$1\"",
        "git push -o -m \"$1\"",
        "gh pr merge 5 -A -t \"$1\"",
        "gh api repos/acme/demo/issues/3/comments -F body=@\"$1\"",
    ],
)
def test_a_parameter_outside_a_quoted_heredoc_is_refused(cmd, profile, tmp_path):
    d = act(profile, tmp_path, cmd, role="ticket")
    assert d.action == "deny" and "heredoc" in d.reason, cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -am \"$(cat <<'EOF'\nUses $1 and \"$@\"\nEOF\n)\"",
        "git commit -m \"$(cat <<\"EOF\"\nUses $1\nEOF\n)\"",
        "git commit -m \"$(cat <<-'EOF'\n\tUses $1\n\tEOF\n)\"",
        "git commit -m \"$(cat <<'EOF'\nUses $1\nEOF)\"",
        f"gh pr create -t \"$(cat <<'EOF'\nTitle $1\nEOF\n)\" -b \"$(cat <<'EOF'\n-R other/repo $@\n{M}\nEOF\n)\"",
    ],
)
def test_a_quoted_heredoc_is_text(cmd, profile, tmp_path):
    d = act(profile, tmp_path, cmd, role="ticket")
    assert d.action == "allow", (cmd, d.reason)


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -m \"$(cat <<EOF\nUses $1\nEOF\n)\"",  # unquoted: the shell expands it
        "git push origin \"$(cat <<'EOF'\nx\nEOF\n)$1\"",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF\n)\" \"$1\"",
        "git diff --output=.git/config",
        "git log --output=.claude/settings.json",
        "git rebase -x 'git push --force' main",
        "gh pr merge https://github.com:/other/repo/pull/5",
        "gh pr merge https://@github.com/other/repo/pull/5",
        "gh pr merge api.github.com/other/repo/pull/5",
    ],
)
def test_more_routes_refused(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


def test_many_words_stay_fast(profile, tmp_path):
    from workflow.guard import _NO_MARKER

    # Each size reads every word: an allow comes only at the end, and the
    # missing marker is found once every word has been read.
    def allowed(cmd):
        assert act(profile, tmp_path, cmd, role="ticket").action == "allow"

    def refused_for_the_marker(cmd):
        decision = act(profile, tmp_path, cmd, role="ticket")
        assert decision.action == "deny" and decision.reason == _NO_MARKER

    assert_grows_linearly(allowed, lambda n: "git status " + "a " * n, 5000)
    assert_grows_linearly(refused_for_the_marker, lambda n: "gh pr create " + "-t x " * n, 3000)


# ---------- the review of the heredoc rule ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "gh pr merge 5 --repo=$(echo other/repo)",
        "gh pr merge 5 --repo=\"$(echo other/repo)\"",
        "gh pr merge 5 -R\"$(echo other/repo)\"",
        "gh pr merge 5 --repo='https://github.com/other/repo?a b'",
        "gh pr merge 5 -R'https://github.com/other/repo#a b'",
        "gh pr merge 'https://github.com/other/repo/pull/5?a b'",
        "gh pr merge 'https://github.com/other/repo/pull/5 '",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF)$1\nEOF\n)\"",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF) $1\nEOF\n)\"",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF)$(git push --force origin main)\nEOF\n)\"",
        "echo \"$(cat <<'EOF'\nx\nEOF)$(rm .claude/settings.json)\nEOF\n)\"",
        "git rebase -ix make main",
        "git rebase -mx make main",
        "git rebase --exe make main",
        "git rebase --ex=make main",
    ],
)
def test_heredoc_review_routes_refused(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


def test_heredoc_review_ordinary_still_allowed(profile, tmp_path):
    for cmd in (
        "git rebase -i main",
        "git rebase -Xours main",
        "gh pr view 5 -R acme/demo",
        "gh pr view 'https://github.com/acme/demo/pull/5#issuecomment-1'",
        "git commit -m \"$(cat <<'EOF'\nFix\n\nEOF is a word $1\nEOF\n)\"",
    ):
        d = act(profile, tmp_path, cmd, role="ticket")
        assert d.action == "allow", (cmd, d.reason)


def test_a_title_starting_with_dash_r_goes_in_a_heredoc(profile, tmp_path):
    # gh would read `-Rate limit` as a repository flag's value; text like it goes in a heredoc.
    assert act(profile, tmp_path, "gh pr create --title '-Rate limit' --body 'x <!-- workflow:agent -->'", role="ticket").action == "deny"
    ok = "gh pr create --title \"$(cat <<'EOF'\n-Rate limit\nEOF\n)\" --body 'x <!-- workflow:agent -->'"
    assert act(profile, tmp_path, ok, role="ticket").action == "allow"


@pytest.mark.parametrize(
    "cmd",
    [
        "git -c sequence.editor=make rebase -i main",
        "GIT_SEQUENCE_EDITOR=make git rebase -i main",
        "GIT_EDITOR='make;:' git commit",
        "git bisect run make",
        "git submodule foreach make",
        "git difftool -x make",
        "git filter-branch --tree-filter make",
        "git mergetool --tool-cmd=make",
        "git -C .claude diff --output=settings.json",
        "git format-patch -ko .claude",
        "git archive -o .claude/settings.json HEAD",
        "git bundle create .claude/settings.json HEAD",
    ],
)
def test_git_running_programs_or_writing_protected_paths(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


def test_ordinary_git_still_runs(profile, tmp_path):
    for cmd in ("GIT_EDITOR=true git rebase --continue", "GIT_SEQUENCE_EDITOR=: git rebase -i main", "git bisect start", "git submodule update --init", "git archive -o /tmp/x.tar HEAD"):
        d = act(profile, tmp_path, cmd, role="ticket")
        assert d.action == "allow", (cmd, d.reason)


# ---------- bash's full rule for a heredoc inside $( ) ----------


@pytest.mark.parametrize(
    "cmd",
    [
        "git commit -m \"$(cat <<'A' <<'B'\na\nA)$(git push --force origin main)\nB\n)\"",
        "git commit -m \"$(cat <<'A'; cat <<'B'\na\nA)$(git push --force origin main)\nB\n)\"",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF )$(git push --force origin main)\nEOF\n)\"",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF\t)$(git push --force origin main)\nEOF\n)\"",
        "git commit -m \"$(cat <<'EOF'\nx\nEOF ) $1\nEOF\n)\"",
        "EDITOR=make git commit",
        "VISUAL=make git rebase -i main",
        "git -c gpg.program=make commit -S",
    ],
)
def test_full_heredoc_rule_and_editors(cmd, profile, tmp_path):
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny", cmd


def test_no_op_programs_and_harmless_settings_allowed(profile, tmp_path):
    for cmd in (
        "GIT_PAGER=cat git log --oneline -5",
        "GIT_PAGER= git log",
        "GIT_EDITOR=cat git commit --amend",
        "GIT_ASKPASS= git fetch",
        "git config mergetool.keepBackup false",
        "git config difftool.prompt false",
        "git commit -F - <<'EOF'\nTitle\nEOF)\nEOF\n",
    ):
        for role in ("ticket", "conductor"):
            d = act(profile, tmp_path, cmd, role=role)
            assert d.action == "allow", (role, cmd, d.reason)


def test_ssh_signing_key_command_is_a_program(profile, tmp_path):
    cmd = "git -c gpg.format=ssh -c gpg.ssh.defaultKeyCommand=make commit -S -m x"
    assert act(profile, tmp_path, cmd, role="ticket").action == "deny"

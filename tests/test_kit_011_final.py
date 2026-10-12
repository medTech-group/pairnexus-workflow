"""Kit 0.1.1, the final pass's findings: each pinned.

Every command here is data passed to `decide`; none is run.
"""

import json
import time

import pytest

from workflow import posts, render
from workflow.guard import decide
from workflow.issues import protected_named
from workflow.posts import AGENT_MARKER
from workflow.profile import DEFAULT_PROTECTED

M = AGENT_MARKER


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
    start = time.perf_counter()
    assert render.seal_of("x" + "\n" * 200_000 + "y") == (None, None)
    assert time.perf_counter() - start < 1


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


def test_ticket_addcomment_still_allowed(profile, tmp_path):
    assert act(profile, tmp_path, f"gh api graphql -f query='{M_SAFE}'", role="ticket").action != "deny"


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

    start = time.perf_counter()
    assert _gql_plain('"' + '\\"' * 200_000) is None
    assert _gql_plain('"""' + '\\"""' * 100_000) is None
    assert time.perf_counter() - start < 1


def test_into_is_linear():
    start = time.perf_counter()
    protected_named("Add it to" + " " * 200_000 + "x\n```\n.env\n```\n", DEFAULT_PROTECTED)
    assert time.perf_counter() - start < 1


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

    start = time.perf_counter()
    _mutation_calls("mutation " * 20_000 + "{a}")
    _mutation_calls("mutation{" + "a " * 50_000 + "}")
    assert time.perf_counter() - start < 1

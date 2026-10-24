"""Adding a pull request to a merge queue through REST `merge-async` (#244, #243's seam 5).

`PUT repos/<repo>/pulls/<n>/merge-async` is the one route the kit uses to queue
a pull request. A ticket session's call is pinned like its merges (#87): `sha`
must be its ticket branch's head. A conductor's or attended session's needs a
`sha` that is a full commit sha, or one the shell fills in. In every role
`bypass_rules` is refused in any form, and so is any `merge_action` but
`merge_queue`, a missing one included: GitHub reads that as `default`, which
merges directly when no queue is required. Attended
sessions are asked, as for the guard's other never-allowed merges, and refused
where nobody is asked.
"""

import pytest

from conftest import git
from workflow.guard import decide
from workflow.profile import load

BRANCH = "claude/build-244"
OTHER = "0123456789abcdef0123456789abcdef01234567"
ROUTE = "gh api -X PUT repos/acme/demo/pulls/12/merge-async"


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


def run(root, cmd, role="ticket", mode=None):
    event = {"tool_name": "Bash", "tool_input": {"command": cmd.replace("{sha}", head(root))}}
    if mode:
        event["permission_mode"] = mode
    return decide(event, load(root), role, root, BRANCH)


def refused(d, role):
    """Denied in ticket and conductor sessions; asked in an attended one."""
    return d.action == ("ask" if role == "attended" else "deny")


ROLES = ["ticket", "conductor", "attended"]


# ---------- queued, pinned: allowed ----------


@pytest.mark.parametrize(
    "form",
    [
        ROUTE + " -f merge_action=merge_queue -f sha={sha}",
        ROUTE + " -f sha={sha} -F merge_action=merge_queue",
        "gh api --method PUT repos/{owner}/{repo}/pulls/12/merge-async -f merge_action=merge_queue -f sha={sha}",
        "gh api -X PUT /repos/acme/demo/pulls/12/merge-async -f merge_action=merge_queue -f sha={sha} --jq .status",
    ],
)
def test_a_ticket_sessions_enqueue_pinned_to_its_head_is_allowed(ticket, form):
    d = run(ticket, form)
    assert d.action == "allow", d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
def test_a_conductors_or_attended_enqueue_with_sha_is_allowed(ticket, role):
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue -f sha={OTHER}", role)
    assert d.action == "allow", d.reason


def test_reading_an_enqueues_result_needs_nothing(ticket):
    for role in ROLES:
        d = run(ticket, "gh api repos/acme/demo/pulls/12/merge-async/0f6c2a9e-1111-2222-3333-444455556666", role)
        assert d.action == "allow", (role, d.reason)


# ---------- the pin ----------


@pytest.mark.parametrize(
    "form",
    [
        ROUTE + " -f merge_action=merge_queue",
        ROUTE + " -f merge_action=merge_queue -f sha=",
    ],
)
def test_a_ticket_sessions_enqueue_without_its_head_is_refused(ticket, form):
    d = run(ticket, form)
    assert d.action == "deny"
    assert ("sha=" in d.reason or "full commit sha" in d.reason) and "git rev-parse HEAD" in d.reason


@pytest.mark.parametrize(
    "form",
    [
        ROUTE + f" -f merge_action=merge_queue -f sha={OTHER}",
        ROUTE + f" -f merge_action=merge_queue -f sha={{sha}} -f sha={OTHER}",
    ],
)
def test_a_ticket_sessions_enqueue_pinned_to_another_head_is_refused(ticket, form):
    d = run(ticket, form)
    assert d.action == "deny"
    assert OTHER in d.reason and head(ticket) in d.reason and BRANCH in d.reason


def test_an_abbreviated_pin_is_refused(ticket):
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue -f sha={head(ticket)[:7]}")
    assert d.action == "deny" and "full" in d.reason


def test_off_the_ticket_branch_an_enqueue_is_refused(ticket):
    sha = head(ticket)
    git(ticket, "checkout", "-q", "main")
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue -f sha={sha}")
    assert d.action == "deny" and "claude/build-*" in d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize("form", [ROUTE + " -f merge_action=merge_queue", ROUTE + " -f merge_action=merge_queue -f sha="])
def test_a_conductors_or_attended_enqueue_without_sha_is_refused(ticket, role, form):
    d = run(ticket, form, role)
    assert refused(d, role), d
    assert "sha=" in d.reason


# ---------- bypass_rules, in any form ----------


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "extra",
    [
        "-F bypass_rules=true",
        "-f bypass_rules=true",
        "-F bypass_rules=false",
        "--field bypass_rules=true",
        "--raw-field=bypass_rules=true",
        "-Fbypass_rules=true",
        "-F BYPASS_RULES=true",
    ],
)
def test_bypass_rules_as_a_field_is_refused(ticket, role, extra):
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue -f sha={{sha}} {extra}", role)
    assert refused(d, role), d
    assert "bypass_rules" in d.reason


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "body",
    [
        '{"merge_action": "merge_queue", "sha": "{sha}", "bypass_rules": true}',
        '{"merge_action": "merge_queue", "sha": "{sha}", "bypass\\u005frules": true}',
    ],
)
def test_bypass_rules_in_an_input_body_is_refused(ticket, role, body):
    (ticket / "body.json").write_text(body.replace("{sha}", head(ticket)))
    d = run(ticket, ROUTE + " --input body.json", role)
    assert refused(d, role), d
    assert "bypass_rules" in d.reason


@pytest.mark.parametrize("role", ROLES)
def test_bypass_rules_in_a_heredoc_on_stdin_is_refused(ticket, role):
    cmd = ROUTE + ' --input - <<\'EOF\'\n{"merge_action": "merge_queue", "sha": "{sha}", "bypass_rules": true}\nEOF'
    d = run(ticket, cmd, role)
    assert refused(d, role), d
    assert "bypass_rules" in d.reason


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("form", [ROUTE + " --input body.json", ROUTE + " --input missing.json", ROUTE + " -f merge_action=merge_queue -F sha=@pin.txt"])
def test_an_enqueue_whose_body_the_guard_doesnt_read_is_refused(ticket, role, form):
    # Without bypass_rules in it, a body from a file is still one the guard reads
    # no pin or merge_action from: gh then sends the fields in the query string.
    (ticket / "body.json").write_text(f'{{"merge_action": "merge_queue", "sha": "{head(ticket)}"}}')
    (ticket / "pin.txt").write_text(head(ticket))
    d = run(ticket, form, role)
    assert refused(d, role), d
    assert "-f" in d.reason and "merge_action" in d.reason


# ---------- merge_action: merge_queue only ----------


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "action",
    [
        "",  # none: GitHub reads it as `default`
        "-f merge_action=default",
        "-f merge_action=direct_merge",
        "-F merge_action=direct_merge",
        "-f merge_action=",
        "-f merge_action=MERGE_QUEUE",
        "-f merge_action=merge_queue -f merge_action=direct_merge",
        "-f Merge_Action=merge_queue",
    ],
)
def test_any_merge_action_but_merge_queue_is_refused(ticket, role, action):
    d = run(ticket, ROUTE + f" -f sha={{sha}} {action}".rstrip(), role)
    assert refused(d, role), d
    assert "merge_action=merge_queue" in d.reason and "directly" in d.reason


# ---------- what the guard can't read ----------


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        ROUTE + " -f merge_action=merge_queue -f sha={sha} -f $X",
        ROUTE + " -f merge_action=merge_queue -f sha={sha} -f \"$(cat f)\"",
        ROUTE + " -f merge_action=merge_queue -f sha={sha} -F {a,bypass_rules}=true",
        "gh api -X PUT 'repos/acme/demo/pulls/12/merge-async?bypass_rules=true' -f merge_action=merge_queue -f sha={sha}",
    ],
)
def test_a_field_or_query_the_guard_cant_read_is_refused(ticket, role, form):
    d = run(ticket, form, role)
    assert refused(d, role), d
    assert "write" in d.reason and ("-f" in d.reason or "query string" in d.reason)


@pytest.mark.parametrize(
    "form",
    [
        ROUTE + " -f merge_action=merge_queue -f sha=$SHA",
        "echo x | xargs " + ROUTE + " -f merge_action=merge_queue -f sha={sha}",
        "gh api -X PUT repos/acme/demo/pulls/1?/merge-async -f merge_action=merge_queue -f sha={sha}",
    ],
)
def test_a_ticket_sessions_enqueue_the_shell_fills_in_is_refused(ticket, form):
    d = run(ticket, form)
    assert d.action == "deny", d.reason


def test_an_enqueue_in_another_repository_is_refused_in_a_ticket_session(ticket):
    d = run(ticket, "gh api -X PUT repos/other/x/pulls/12/merge-async -f merge_action=merge_queue -f sha={sha}")
    assert d.action == "deny" and "acme/demo" in d.reason


# ---------- attended: asked, and refused where nobody is asked ----------


def test_attended_bypass_rules_is_refused_where_nobody_is_asked(ticket):
    d = run(ticket, ROUTE + " -f merge_action=merge_queue -f sha={sha} -F bypass_rules=true", "attended", mode="bypassPermissions")
    assert d.action == "deny" and "bypass_rules" in d.reason


# ---------- text that mentions the route is no enqueue ----------


def test_text_that_mentions_the_route_is_no_enqueue(ticket):
    d = run(ticket, "gh api repos/acme/demo/issues/5/comments -f body='Queued with pulls/12/merge-async and bypass_rules off <!-- workflow:agent -->'")
    assert d.action == "allow", d.reason


# ---------- what the shell or the path's spelling can add ----------


SHA_ARGS = " -f merge_action=merge_queue -f sha={sha}"


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "form",
    [
        "printf -- '-F bypass_rules=true' | xargs " + ROUTE + SHA_ARGS,
        "printf -- '-f merge_action=direct_merge' | xargs " + ROUTE + SHA_ARGS,
        "X='-F bypass_rules=true'; sh -c \"" + ROUTE + SHA_ARGS + " $X\"",
        "X='-F bypass_rules=true'; eval \"" + ROUTE + SHA_ARGS + " $X\"",
    ],
)
def test_words_xargs_or_another_shell_add_are_refused(ticket, role, form):
    d = run(ticket, form, role)
    assert refused(d, role), (role, d)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "path",
    [
        "'repos/acme/demo/pulls/12/merge-async#x'",
        "HTTPS://api.github.com/repos/acme/demo/pulls/12/merge-async",
        "https://api.github.com/repos/acme/demo/pulls/12/merge-async",
        "repos/acme/demo/pulls/12//merge-async",
        "repos/acme/demo/pulls/12/./merge-async",
        "repos/acme/demo/pulls/12/merge%2Dasync",
        "repos/acme/demo/pulls/12/MERGE-ASYNC",
    ],
)
def test_another_spelling_of_the_path_is_still_checked(ticket, role, path):
    d = run(ticket, f"gh api -X PUT {path} -f sha={{sha}} -F bypass_rules=true -f merge_action=direct_merge", role)
    assert refused(d, role), (role, d)


@pytest.mark.parametrize("role", ROLES)
def test_bypass_rules_is_refused_whatever_the_path(ticket, role):
    d = run(ticket, 'gh api -X PUT "$P" -f merge_action=merge_queue -f sha={sha} -F bypass_rules=true', role)
    assert refused(d, role), (role, d)
    assert "bypass_rules" in d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize("pin", ["-F sha=null", "-F sha=true", "-F sha=12", "-f sha=HEAD"])
def test_a_sha_that_isnt_a_commit_is_refused(ticket, role, pin):
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue {pin}", role)
    assert refused(d, role), (role, d)
    assert "sha" in d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize("pin", ['-f sha="$SHA"', "-f sha=\"$(git rev-parse HEAD)\"", f"-f sha={OTHER.upper()}"])
def test_a_conductors_sha_the_shell_fills_in_is_allowed(ticket, role, pin):
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue {pin}", role)
    assert d.action == "allow", (role, d.reason)


@pytest.mark.parametrize(
    "form",
    [
        "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/merge-async -d '{\"merge_action\":\"merge_queue\",\"sha\":\"{sha}\",\"bypass_rules\":true}'",
        "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/merge-async -d '{\"merge_action\":\"direct_merge\",\"sha\":\"{sha}\"}'",
        "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/merge-async -d @body.json",
    ],
)
def test_an_attended_curl_enqueue_is_asked_unless_queued_and_pinned(ticket, form):
    (ticket / "body.json").write_text('{"merge_action":"merge_queue","sha":"x","bypass_rules":true}')
    d = run(ticket, form, "attended")
    assert d.action == "ask", d


def test_an_attended_curl_enqueue_queued_and_pinned_is_left_alone(ticket):
    form = "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/merge-async -d '{\"merge_action\":\"merge_queue\",\"sha\":\"{sha}\"}'"
    d = run(ticket, form, "attended")
    assert d.action == "allow", d.reason


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize(
    "form",
    [
        "E=--field=bypass_rules=true; " + ROUTE + SHA_ARGS + ' "$E"',
        ROUTE + SHA_ARGS + ' "${E:--fbypass_rules=true}"',
        "E=-fmerge_action=default; " + ROUTE + SHA_ARGS + ' "$E"',
        "E=--input=b.json; " + ROUTE + SHA_ARGS + ' "$E"',
        ROUTE + SHA_ARGS + ' -f "$K=true"',
        "M=merge-async; gh api -X PUT \"repos/acme/demo/pulls/12/$M\" -f sha={sha}",
        "gh api -X PUT \"repos/acme/demo/pulls/12/merge-$(echo async)\" -f sha={sha}",
        "echo repos/acme/demo/pulls/12/merge-async | xargs -I{} gh api -X PUT {} -f sha={sha}",
    ],
)
def test_a_quoted_expansion_that_may_be_a_flag_or_the_route_is_refused(ticket, role, form):
    d = run(ticket, form, role)
    assert refused(d, role), (role, d)


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        "gh api -X PUT \"repos/acme/demo/pulls/$N/merge-async\" -f merge_action=merge_queue -f sha=\"$SHA\" --jq \"$Q\"",
        "gh api -X PUT \"repos/$R/pulls/$N/update-branch\" -f expected_head_sha=\"$SHA\"",
        "gh api -X PUT repos/acme/demo/pulls/12/merge -f sha=\"$SHA\" -H \"$H\"",
    ],
)
def test_expansions_in_values_and_paths_are_fine(ticket, role, form):
    d = run(ticket, form, role)
    assert d.action == "allow", (role, d.reason)


def test_the_bypass_refusal_says_what_to_do(ticket):
    d = run(ticket, ROUTE + SHA_ARGS + " -F bypass_rules=true")
    assert "leave it out" in d.reason


def test_off_the_ticket_branch_the_refusal_names_queueing(ticket):
    sha = head(ticket)
    git(ticket, "checkout", "-q", "main")
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue -f sha={sha}")
    assert d.action == "deny" and "queues" in d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        "gh api -X POST \"repos/acme/demo/pulls/comments/$ID/replies\" -f body='Thanks <!-- workflow:agent -->'",
        "gh api -X PATCH \"repos/acme/demo/pulls/comments/$ID\" -f body='Fixed <!-- workflow:agent -->'",
        "gh api -X DELETE \"repos/acme/demo/pulls/comments/$ID\"",
        "gh api -X PATCH \"$ISSUE_URL\" -f state=closed",
    ],
)
def test_other_routes_with_a_filled_in_part_are_left_alone(ticket, role, form):
    d = run(ticket, form, role)
    assert d.action == "allow", (role, d.reason)


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        'gh api -X PUT "$P" -f sha={sha} "$E"',
        'gh api -X PUT "$P" "${E:--fmerge_action=direct_merge}" -f sha={sha}',
        "gh api -X PUT \"$P\" -f sha={sha} `printf x`",
    ],
)
def test_a_filled_in_path_with_a_word_that_may_be_a_flag_is_refused(ticket, role, form):
    d = run(ticket, form, role)
    assert refused(d, role), (role, d)
    assert "write" in d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        'gh api -X PUT "repos/$REPO/pulls/12/merge-async" -f sha={sha}',
        'gh api -X PUT "repos/${GITHUB_REPOSITORY}/pulls/12/merge-async" -f sha="$SHA"',
        'gh api -X PUT repos/"$REPO"/pulls/12/merge-async -f sha={sha}',
        'gh api -X PUT "repos/$REPO/pulls/12/merge-async" --input body.json',
        'gh api -X PUT "$URL" -f sha={sha}',
        'gh api -X PUT "$URL" --input body.json',
        'gh api -X PUT "${B}merge-async" -f sha={sha}',
        'gh api -X PUT "repos/acme/demo/$P/merge-async" -f sha={sha}',
    ],
)
def test_a_route_whose_start_the_shell_fills_in_is_still_checked(ticket, role, form):
    (ticket / "body.json").write_text('{"merge_action": "merge_queue", "sha": "x", "bypass_rules": true}')
    d = run(ticket, form, role)
    assert refused(d, role), (role, d)


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        'gh api -X PUT "repos/$REPO/pulls/12/merge-async" -f merge_action=merge_queue -f sha="$SHA"',
        'gh api -X PUT "$MERGE_URL" -f sha="$SHA" -f merge_method=merge',
        'gh api -X PUT "repos/$REPO/pulls/$N/update-branch" -f expected_head_sha="$SHA"',
        "gh api repos/acme/demo/issues/12/comments -F body=@c.md -F bypass_rules_note=x",
    ],
)
def test_ordinary_calls_with_filled_in_parts_still_pass(ticket, role, form):
    (ticket / "c.md").write_text("Done <!-- workflow:agent -->")
    d = run(ticket, form, role)
    assert d.action == "allow", (role, d.reason)


CURL = "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/merge-async"


@pytest.mark.parametrize(
    "form",
    [
        CURL + ' -d \'{"merge_action":"merge_queue","merge_action":"direct_merge","sha":"{sha}"}\'',
        CURL + ' -d \'{"merge_action":"merge_queue","sha":"{sha}","\\u0062ypass_rules":true}\'',
        "curl -X PUT -H 'X-Note: \"merge_action\":\"merge_queue\",\"sha\":\"x\"' https://api.github.com/repos/acme/demo/pulls/12/merge-async -d '{\"merge_action\":\"direct_merge\"}'",
        "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/merge-asyn%63 -d '{\"merge_action\":\"direct_merge\",\"sha\":\"{sha}\"}'",
        "curl -X PUT https://api.github.com/repos/acme/demo/pulls/12/$M -d '{\"merge_action\":\"direct_merge\",\"sha\":\"{sha}\"}'",
        "curl -X PUT 'https://api.github.com/repos/acme/demo/pulls/12/merge-{async,x}' -d '{\"merge_action\":\"direct_merge\",\"sha\":\"{sha}\"}'",
        "curl -X PUT -K cfg.txt",
        CURL + ' -d "$BODY"',
    ],
)
def test_an_attended_curl_enqueue_the_guard_cant_read_as_queued_is_asked(ticket, form):
    (ticket / "cfg.txt").write_text('url = "https://api.github.com/repos/acme/demo/pulls/12/merge-async"\ndata = "{\\"merge_action\\":\\"direct_merge\\"}"\n')
    d = run(ticket, form, "attended")
    assert d.action == "ask", d


def test_an_attended_curl_enqueue_with_a_json_file_is_read(ticket):
    (ticket / "ok.json").write_text(f'{{"merge_action": "merge_queue", "sha": "{head(ticket)}"}}')
    d = run(ticket, CURL + " --json @ok.json", "attended")
    assert d.action == "allow", d.reason


def test_the_attended_bypass_question_reads_plainly(ticket):
    d = run(ticket, ROUTE + SHA_ARGS + " -F bypass_rules=true", "attended")
    assert d.action == "ask"
    assert "leave it out" in d.reason and "allow it only if you mean to" in d.reason
    assert d.reason.index("leave it out") < d.reason.index("allow it only if you mean to")


def test_an_unquoted_expansion_refusal_says_to_quote_it(ticket):
    d = run(ticket, ROUTE + " -f merge_action=merge_queue -f sha=$SHA", "conductor")
    assert d.action == "deny" and 'sha="$SHA"' in d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        "printf '{\"merge_action\":\"merge_queue\",\"sha\":\"x\",\"bypass_rules\":true}' | gh api -X PUT \"$URL\" --input -",
        'gh api -X PUT "$URL" --input "$F"',
        'gh api -X PUT "$URL" --input direct.json',
    ],
)
def test_a_put_to_a_filled_in_path_whose_body_may_queue_it_is_refused(ticket, role, form):
    (ticket / "direct.json").write_text('{"merge_action": "direct_merge", "sha": "x"}')
    d = run(ticket, form, role)
    assert refused(d, role), (role, d)


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        'gh api -X POST "repos/$REPO/issues/$N/comments" -F body=@note.md',
        'gh api -X DELETE "repos/$R/pulls/$N/$X"',
        'gh api -X PUT "$URL" --input labels.json',
    ],
)
def test_ordinary_writes_that_mention_or_resemble_the_route_pass(ticket, role, form):
    (ticket / "note.md").write_text("The guard now refuses bypass_rules on merge-async. <!-- workflow:agent -->")
    (ticket / "labels.json").write_text('{"labels": ["ready"]}')
    d = run(ticket, form, role)
    assert d.action == "allow", (role, d.reason)


@pytest.mark.parametrize(
    "form",
    [
        "curl -X PUT -Kcfg.txt",
        "curl -X PUT -sK cfg.txt",
        CURL + " -G -d '{\"merge_action\":\"merge_queue\",\"sha\":\"{sha}\"}'",
        CURL + " --get -d '{\"merge_action\":\"merge_queue\",\"sha\":\"{sha}\"}'",
        "curl -X PUT \"$API/repos/acme/demo/pulls/12/merge-async\" -d '{\"merge_action\":\"direct_merge\",\"sha\":\"{sha}\"}'",
    ],
)
def test_more_attended_curl_enqueues_the_guard_cant_read_are_asked(ticket, form):
    (ticket / "cfg.txt").write_text('url = "https://api.github.com/repos/acme/demo/pulls/12/merge-async"\ndata = "{\\"merge_action\\":\\"direct_merge\\"}"\n')
    d = run(ticket, form, "attended")
    assert d.action == "ask", d


@pytest.mark.parametrize(
    "form",
    [
        "curl -X PATCH https://api.github.com/repos/acme/demo/pulls/$N -d '{\"title\":\"x\"}'",
        "curl -X PATCH https://api.github.com/repos/acme/demo/issues/$N -d '{\"state\":\"closed\"}'",
        "curl -X POST https://api.github.com/repos/acme/demo/issues/12/comments -d '{\"body\":\"queued with pulls/12/merge-async\"}'",
        "curl -X PUT -K missing.cfg https://example.com/upload -d x",
    ],
)
def test_attended_curl_writes_that_arent_queue_calls_are_left_alone(ticket, form):
    d = run(ticket, form, "attended")
    assert d.action == "allow", d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        'gh api -X PUT "$CONTENTS_URL" -f message=update -f content=aGk= -f sha="$BLOB"',
        'gh api -X PUT "$PR_URL/merge" -f sha="$SHA"',
        'gh api -X PUT "repos/$REPO/pulls/$N/$ACTION" -f sha="$SHA" -f merge_method=squash',
    ],
)
def test_other_puts_with_a_filled_in_path_pass(ticket, role, form):
    d = run(ticket, form, role)
    assert d.action == "allow", (role, d.reason)


def test_an_attended_curl_with_an_unread_config_and_its_own_url_is_left_alone(ticket):
    d = run(ticket, "curl -sS --config missing.curlrc https://api.github.com/repos/acme/demo/pulls/12", "attended")
    assert d.action == "allow", d.reason


@pytest.mark.parametrize("role", ["conductor", "attended"])
@pytest.mark.parametrize(
    "form",
    [
        "gh api -X PUT repos/{owner}/{repo}/pulls/12/{branch} -f merge_action=direct_merge -f sha={sha}",
        "gh api -X PUT repos/{owner}/{repo}/pulls/12/merge-{branch} -f sha={sha}",
        "gh api -X PUT repos/acme/demo/pulls/12/merge-asyn? -f merge_action=direct_merge -f sha={sha}",
        'gh api -X PUT "$URL" --input direct.json',
        'gh api -X PUT "$URL" --input - <<<\'{"merge_action":"direct_merge","sha":"x"}\'',
    ],
)
def test_more_hidden_routes_are_refused(ticket, role, form):
    (ticket / "direct.json").write_text('{"merge_action": "direct_merge", "sha": "x"}')
    d = run(ticket, form, role)
    assert refused(d, role), (role, d)


@pytest.mark.parametrize(
    "form",
    [
        "curl -X PUT 'https://api.github.com/repos/acme/demo/pulls/12/merge-async?bypass_rules=true' -d '{\"merge_action\":\"merge_queue\",\"sha\":\"{sha}\"}'",
        CURL + " --url-query bypass_rules=true -d '{\"merge_action\":\"merge_queue\",\"sha\":\"{sha}\"}'",
    ],
)
def test_an_attended_curl_enqueue_with_a_query_string_is_asked(ticket, form):
    d = run(ticket, form, "attended")
    assert d.action == "ask", d


def test_the_wrong_head_refusal_names_queueing(ticket):
    d = run(ticket, ROUTE + f" -f merge_action=merge_queue -f sha={OTHER}")
    assert d.action == "deny" and "merges or queues only its own" in d.reason

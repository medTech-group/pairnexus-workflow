"""Adding a pull request to a merge queue through REST `merge-async` (#244, #243's seam 5).

`PUT repos/<repo>/pulls/<n>/merge-async` is the one route the kit uses to queue
a pull request. A ticket session's call is pinned like its merges (#87): `sha`
must be its ticket branch's head. A conductor's or attended session's needs
`sha` present. In every role `bypass_rules` is refused in any form, and so is
any `merge_action` but `merge_queue`, a missing one included: GitHub reads that
as `default`, which merges directly when no queue is required. Attended
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
    assert "write" in d.reason


@pytest.mark.parametrize(
    "form",
    [
        ROUTE + " -f merge_action=merge_queue -f sha=$SHA",
        "echo x | xargs " + ROUTE[0:] + " -f merge_action=merge_queue -f sha={sha}",
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

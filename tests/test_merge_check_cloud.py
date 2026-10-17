"""`workflow merge-check --fetch` in a cloud session (#165), through the CLI and
the fake `gh` (`tests/fake_gh.py`).

A cloud session's proxy refuses GraphQL and `collaborators/<u>/permission`.
Threads then come from the session route `pulls/<n>/ccr/review_threads`, a
bare list of `{"resolved", "outdated", "path", "line", "comment_ids"}` with no
count, so it is complete only when every review comment of the pull request
(`pulls/<n>/comments`, every page) sits in one of its threads. Permissions
come from the token's own `permissions` on `repos/<repo>`, for the token's own
login (`user`); any other author can't be shown to have write access, so
counts as without it.
"""

import pytest

import fake_gh
from test_merge_check import comment, ids, inputs, project, review  # noqa: F401 (project is a fixture)
from test_merge_check_evidence import REPO, routes, run, with_report

REFUSED_GRAPHQL = fake_gh.reply(exit=1, stderr="gh: GraphQL is not available from Claude Code sessions (HTTP 403)")
REFUSED_PATH = fake_gh.reply(
    stdout='{"message":"Access to this GitHub API path is not permitted through this proxy."}',
    exit=1,
    stderr="gh: Access to this GitHub API path is not permitted through this proxy. (HTTP 403)",
)
ADMIN = {"admin": True, "maintain": True, "push": True, "triage": True, "pull": True}


def thread(resolved, *comment_ids, path="src/app.py"):
    return {"resolved": resolved, "outdated": False, "path": path, "line": 3, "comment_ids": list(comment_ids)}


def review_comment(cid, who="dev", reply_to=None):
    return {"id": cid, "user": {"login": who}, "in_reply_to_id": reply_to, "body": "a note", "path": "src/app.py"}


def cloud(data=None, threads=((),), comments=((),), me="owner", perms=ADMIN):
    """routes() as a cloud session's proxy answers them: GraphQL and the
    collaborator route refused, the session route and `user` answering."""
    data = data or with_report(inputs())
    data["pr"].setdefault("review_comments", sum(len(p) for p in comments))
    r = routes(data)
    r["graphql"] = REFUSED_GRAPHQL
    for k in [k for k in r if "/collaborators/" in k]:
        r[k] = REFUSED_PATH
    r[f"{REPO}/pulls/12/ccr/review_threads"] = fake_gh.pages(*[list(p) for p in threads])
    r[f"{REPO}/pulls/12/comments"] = fake_gh.pages(*[list(p) for p in comments])
    r["user"] = {"login": me}
    r[REPO] = {"full_name": "acme/demo", "permissions": perms}
    return r


def couldnt_read(got):
    return {x["input"]: x["wording"]["developer"]["message"] for x in got["reasons"] if x["id"] == "couldnt_read"}


# ---------- threads ----------


def test_a_cloud_session_reads_the_threads_from_the_session_route(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, cloud())
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0
    assert got["decision"] == "ready", got["reasons"]
    paths = [p.split("?")[0] for p in gh.paths()]
    assert paths.index("graphql") < paths.index(f"{REPO}/pulls/12/ccr/review_threads")  # GraphQL first


def test_resolved_and_unresolved_threads_across_two_pages(project, capsys, tmp_path, monkeypatch):
    r = cloud(
        threads=([thread(True, 501, 502)], [thread(False, 503)]),
        comments=([review_comment(501, "dev"), review_comment(502, "owner", 501)], [review_comment(503, "Keeper")]),
    )
    gh = fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert ids(got) == ["unresolved_threads"], got["reasons"]
    [x] = got["reasons"]
    assert "1 unresolved review thread" in x["message"] and "@Keeper" in x["message"]
    for args in gh.calls():  # both lists fetched whole
        if any(a.split("?")[0] in (f"{REPO}/pulls/12/ccr/review_threads", f"{REPO}/pulls/12/comments") for a in args):
            assert "--paginate" in args and "--slurp" in args, args


def test_every_thread_resolved_is_ready(project, capsys, tmp_path, monkeypatch):
    r = cloud(threads=([thread(True, 501)], [thread(True, 503, 504)]),
              comments=([review_comment(501)], [review_comment(503), review_comment(504, "owner", 503)]))
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


def test_a_gh_too_old_to_slurp_reads_the_session_route_too(project, capsys, tmp_path, monkeypatch):
    r = cloud(threads=([thread(True, 501)], [thread(False, 503)]), comments=([review_comment(501)], [review_comment(503)]))
    fake_gh.install(tmp_path, monkeypatch, r, slurp=False)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert ids(got) == ["unresolved_threads"], got["reasons"]


def test_a_session_route_that_ends_early_is_couldnt_read_never_ready(project, capsys, tmp_path, monkeypatch):
    # The second page of threads never came: review comment 503 sits in no thread given.
    r = cloud(threads=([thread(True, 501, 502)],), comments=([review_comment(501), review_comment(502, "owner", 501)], [review_comment(503)]))
    fake_gh.install(tmp_path, monkeypatch, r)
    got, code = run(project, capsys, {}, "--fetch", "12")
    assert code == 0 and got["decision"] == "not_yet"
    said = couldnt_read(got)
    assert list(said) == ["threads"]
    assert "give --threads as a file" in said["threads"]


def test_a_pull_request_that_doesnt_count_its_review_comments_leaves_the_threads_couldnt_read(project, capsys, tmp_path, monkeypatch):
    r = cloud(threads=([thread(True, 501)],), comments=([review_comment(501)],))
    del r[f"{REPO}/pulls/12"]["review_comments"]
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    said = couldnt_read(got)
    assert list(said) == ["threads"] and "review_comments" in said["threads"]


def test_review_comments_fewer_than_the_pull_request_counts_are_couldnt_read(project, capsys, tmp_path, monkeypatch):
    # The comments' last page never came either, so the cross-check can't show the threads are whole.
    data = with_report(inputs())
    data["pr"]["review_comments"] = 3
    r = cloud(data, threads=([thread(True, 501, 502)],), comments=([review_comment(501), review_comment(502, "owner", 501)],))
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "not_yet"
    assert list(couldnt_read(got)) == ["threads"]


def test_review_comments_the_pull_request_counts_are_ready(project, capsys, tmp_path, monkeypatch):
    data = with_report(inputs())
    data["pr"]["review_comments"] = 2
    r = cloud(data, threads=([thread(True, 501, 502)],), comments=([review_comment(501), review_comment(502, "owner", 501)],))
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


def test_review_comments_that_cant_be_read_leave_the_threads_couldnt_read(project, capsys, tmp_path, monkeypatch):
    r = cloud(threads=([thread(False, 501)],))
    r[f"{REPO}/pulls/12/comments"] = fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    said = couldnt_read(got)
    assert list(said) == ["threads"] and "HTTP 502" in said["threads"]


@pytest.mark.parametrize("bad", [
    [{"resolved": "yes", "comment_ids": [501]}],
    [{"resolved": False}],
    [{"resolved": False, "comment_ids": ["501"]}],
    ["a thread"],
    {"threads": []},
])
def test_a_session_route_in_another_shape_is_couldnt_read(project, capsys, tmp_path, monkeypatch, bad):
    r = cloud(comments=([review_comment(501)],))
    r[f"{REPO}/pulls/12/ccr/review_threads"] = fake_gh.pages(bad)
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "not_yet"
    assert list(couldnt_read(got)) == ["threads"]


def test_both_routes_failing_name_both(project, capsys, tmp_path, monkeypatch):
    r = cloud()
    del r[f"{REPO}/pulls/12/ccr/review_threads"]  # 404, as outside a cloud session
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    said = couldnt_read(got)["threads"]
    assert "not available from Claude Code sessions" in said and "ccr/review_threads" in said and "HTTP 404" in said


def test_outside_a_cloud_session_the_session_route_isnt_asked(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, routes())
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]
    asked = [p.split("?")[0] for p in gh.paths()]
    assert not [p for p in asked if "ccr/" in p or p.endswith("/pulls/12/comments") or p in ("user", REPO)]


def test_a_threads_file_still_wins_in_a_cloud_session(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, cloud())
    got, _ = run(project, capsys, {"threads": {"totalCount": 1, "nodes": [{"isResolved": False}]}}, "--fetch", "12")
    assert ids(got) == ["unresolved_threads"]
    assert not [p for p in gh.paths() if p == "graphql" or "ccr/" in p]


# ---------- permissions ----------


def test_a_refused_collaborator_route_gives_the_token_its_own_permission(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, cloud())
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]
    asked = gh.paths()
    assert f"{REPO}/collaborators/owner/permission" in asked  # tried first
    assert "user" in asked and REPO in asked


def test_the_tokens_login_is_matched_without_case(project, capsys, tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, cloud(me="OWNER"))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


def test_another_author_counts_as_without_write_access(project, capsys, tmp_path, monkeypatch):
    # dev may have write access on GitHub, but nothing the session can read shows it,
    # so the review record dev posted doesn't count.
    data = inputs()
    data["comments"] = [comment(data["comments"][0]["body"], author="dev")]
    r = cloud(data)
    r[f"{REPO}/collaborators/dev/permission"] = REFUSED_PATH
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert ids(got) == ["no_review"], got["reasons"]


def test_a_change_request_from_someone_whose_access_cant_be_shown_isnt_guessed(project, capsys, tmp_path, monkeypatch):
    # Counting dev as without write access would drop their "changes requested":
    # a reviewer's block is never lifted on a guess, so permissions stay couldn't read.
    data = with_report(inputs())
    data["reviews"] = [review("APPROVED", who="dev"), review("CHANGES_REQUESTED", who="dev", rid=2, when="2026-10-16T10:00:00Z")]
    r = cloud(data)
    r[f"{REPO}/collaborators/dev/permission"] = REFUSED_PATH
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "not_yet"
    said = couldnt_read(got)
    assert list(said) == ["permissions"] and "@dev" in said["permissions"] and "give --permissions as a file" in said["permissions"]


def test_a_change_request_is_read_in_time_order_and_in_graphqls_shape(project, capsys, tmp_path, monkeypatch):
    # Listed newest first, in GraphQL's shape: dev's change request (11:00) is still their latest.
    data = with_report(inputs())
    nodes = [{"author": {"login": "dev"}, "state": "CHANGES_REQUESTED", "submittedAt": "2026-10-16T11:00:00Z"},
             {"author": {"login": "dev"}, "state": "APPROVED", "submittedAt": "2026-10-16T10:00:00Z"}]
    r = cloud(data)
    r[f"{REPO}/collaborators/dev/permission"] = REFUSED_PATH
    fake_gh.install(tmp_path, monkeypatch, r)
    reviews = [review("CHANGES_REQUESTED", who="dev", rid=2, when="2026-10-16T11:00:00Z"), review("APPROVED", who="dev", rid=1)]
    got, _ = run(project, capsys, {"reviews": reviews}, "--fetch", "12")
    assert "@dev" in couldnt_read(got).get("permissions", ""), got["reasons"]
    got, _ = run(project, capsys, {"reviews": {"reviews": {"totalCount": 2, "nodes": nodes}}}, "--fetch", "12")
    assert got["decision"] == "not_yet", got["reasons"]


def test_a_change_request_whose_reviewer_was_asked_again_doesnt_stall(project, capsys, tmp_path, monkeypatch):
    # merge-check already sets aside a change request once its reviewer is asked to review again.
    data = with_report(inputs())
    data["reviews"] = [review("CHANGES_REQUESTED", who="dev")]
    data["pr"]["requested_reviewers"] = [{"login": "dev"}]
    r = cloud(data)
    r[f"{REPO}/collaborators/dev/permission"] = REFUSED_PATH
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


def test_a_change_request_later_approved_is_counted_as_without_write_access(project, capsys, tmp_path, monkeypatch):
    data = with_report(inputs())
    data["reviews"] = [review("CHANGES_REQUESTED", who="dev"), review("COMMENTED", who="dev", rid=2, when="2026-10-16T10:00:00Z"),
                       review("APPROVED", who="dev", rid=3, when="2026-10-16T11:00:00Z")]
    r = cloud(data)
    r[f"{REPO}/collaborators/dev/permission"] = REFUSED_PATH
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]


def test_the_tokens_own_change_request_still_blocks(project, capsys, tmp_path, monkeypatch):
    data = with_report(inputs())
    data["reviews"] = [review("CHANGES_REQUESTED", who="owner")]
    fake_gh.install(tmp_path, monkeypatch, cloud(data))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert ids(got) == ["changes_requested"], got["reasons"]


def test_the_token_without_push_has_no_write_access(project, capsys, tmp_path, monkeypatch):
    # The owner's token reads only: the owner's evidence and review record don't come from a write-access account.
    fake_gh.install(tmp_path, monkeypatch, cloud(perms={"admin": False, "maintain": False, "push": False, "triage": False, "pull": True}))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] != "ready"
    assert not couldnt_read(got)


def test_a_token_with_no_permission_flags_set_is_read_as_none(project, capsys, tmp_path, monkeypatch):
    fake_gh.install(tmp_path, monkeypatch, cloud(perms={"admin": False, "push": False, "pull": False}))
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] != "ready"
    assert not couldnt_read(got)


def test_the_asker_is_the_owner_only_through_the_tokens_own_permission(project, capsys, tmp_path, monkeypatch):
    path = project / ".claude/workflow/profile.toml"
    path.write_text(path.read_text().replace('owner = "owner"\n', ""))
    r = cloud()
    r[f"{REPO}/collaborators/Boss/permission"] = REFUSED_PATH
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12", "--asker", "@Boss")
    assert got["owner"] is False, got["reasons"]  # Boss isn't the token's login: no admin shown
    r = cloud(me="Boss")
    r[f"{REPO}/collaborators/Boss/permission"] = REFUSED_PATH
    (tmp_path / "again").mkdir()
    fake_gh.install(tmp_path / "again", monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12", "--asker", "@Boss")
    assert got["owner"] is True, got["reasons"]


@pytest.mark.parametrize("route, answer", [
    ("user", fake_gh.reply(exit=1, stderr="gh: Server Error (HTTP 502)")),
    (REPO, REFUSED_PATH),
    ("user", {"id": 1}),
    (REPO, {"full_name": "acme/demo"}),
])
def test_a_token_permission_that_cant_be_read_leaves_permissions_couldnt_read(project, capsys, tmp_path, monkeypatch, route, answer):
    r = cloud()
    r[route] = answer
    fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert got["decision"] == "not_yet"
    said = couldnt_read(got)
    assert list(said) == ["permissions"]
    assert "not permitted through this proxy" in said["permissions"]


@pytest.mark.parametrize("stderr", [
    "gh: Server Error (HTTP 502)",
    "gh: Must have push access to view repository collaborators. (HTTP 403)",
    "gh: You have exceeded a secondary rate limit. (HTTP 403)",
])
def test_a_collaborator_route_failing_otherwise_is_still_couldnt_read(project, capsys, tmp_path, monkeypatch, stderr):
    # Only the proxy's refusal falls back: GitHub's own 403s and server errors stay failures, as before.
    r = cloud()
    r[f"{REPO}/collaborators/owner/permission"] = fake_gh.reply(exit=1, stderr=stderr)
    gh = fake_gh.install(tmp_path, monkeypatch, r)
    got, _ = run(project, capsys, {}, "--fetch", "12")
    assert list(couldnt_read(got)) == ["permissions"]
    assert "user" not in gh.paths()


def test_the_tokens_permission_is_fetched_once(project, capsys, tmp_path, monkeypatch):
    data = with_report(inputs())
    data["reviews"] = [review("APPROVED", who="dev"), review("COMMENTED", who="keeper", rid=2)]
    r = cloud(data)
    r[f"{REPO}/collaborators/dev/permission"] = REFUSED_PATH
    r[f"{REPO}/collaborators/keeper/permission"] = REFUSED_PATH
    gh = fake_gh.install(tmp_path, monkeypatch, r)
    run(project, capsys, {}, "--fetch", "12")
    asked = gh.paths()
    assert asked.count("user") == 1 and asked.count(REPO) == 1


def test_a_permissions_file_still_wins_in_a_cloud_session(project, capsys, tmp_path, monkeypatch):
    gh = fake_gh.install(tmp_path, monkeypatch, cloud(perms={"pull": True}))
    got, _ = run(project, capsys, {"permissions": {"owner": "admin"}}, "--fetch", "12")
    assert got["decision"] == "ready", got["reasons"]
    assert not [p for p in gh.paths() if "/collaborators/" in p or p == "user"]


def test_reviewers_in_graphqls_shape_have_their_permission_fetched(project, capsys, tmp_path, monkeypatch):
    # Outside a cloud session too: a --reviews file in GraphQL's shape used to leave its reviewers
    # unasked, so their change request counted as from someone without write access.
    r = routes()
    r[f"{REPO}/collaborators/dev/permission"] = {"permission": "write", "user": {"login": "dev"}}
    gh = fake_gh.install(tmp_path, monkeypatch, r)
    nodes = [{"author": {"login": "dev"}, "state": "CHANGES_REQUESTED", "submittedAt": "2026-10-16T11:00:00Z"}]
    got, _ = run(project, capsys, {"reviews": {"reviews": {"totalCount": 1, "nodes": nodes}}}, "--fetch", "12")
    assert ids(got) == ["changes_requested"], got["reasons"]
    assert f"{REPO}/collaborators/dev/permission" in gh.paths()

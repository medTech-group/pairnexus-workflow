"""Reading GitHub through `gh api`, for commands that otherwise take files.

`merge_inputs` fetches what `workflow merge-check --fetch <n>` needs, in the
shapes its files take (`merge.INPUTS`), every page: each input becomes
`(value, None)`, or `(None, why)` when it couldn't be fetched, so the command
says which input is missing and how to give it as a file. It only reads:
nothing is written, here or on GitHub.

`gh api --paginate --slurp` gives the pages as one list; a gh too old for
`--slurp` prints them one after another, which are read one by one.

A Claude Code cloud session's proxy refuses two routes (#165): GraphQL, where
review threads come from, and `collaborators/<u>/permission`. The usual route
is tried first; then threads come from the session route (`session_threads`)
and permissions from the token's own (`token_permission`), each only as far
as it can be shown: what can't be shown stays "couldn't read", never a guess.
"""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import quote

from . import merge
from .posts import CommentsError, _login, comments_from, decode_values

TIMEOUT = 120  # seconds for one `gh api` call, every page
NOT_INSTALLED = "gh (the GitHub CLI) isn't installed here"
AS_A_FILE = "so it couldn't be fetched: give --{name} as a file"
PROXY_REFUSED = "not permitted through this proxy"  # a cloud session's proxy, refusing a route

# A pull request's review threads come only from GraphQL, 100 to a page; gh's
# --paginate follows pageInfo.endCursor through $endCursor.
THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $endCursor) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes { isResolved comments(first: 1) { nodes { author { login } } } }
      }
    }
  }
}
""".strip()


class GhError(Exception):
    """A `gh api` call failed: the message says why, in gh's words."""


def available() -> bool:
    return shutil.which("gh") is not None


def _run(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT)
    except FileNotFoundError:
        raise GhError(NOT_INSTALLED) from None
    except subprocess.TimeoutExpired:
        raise GhError(f"gh api took longer than {TIMEOUT} seconds") from None
    except OSError as e:
        raise GhError(f"couldn't run gh: {e.strerror or e}") from None


def _failed(p: subprocess.CompletedProcess) -> GhError:
    said = (p.stderr or p.stdout or "").strip().splitlines()
    return GhError(f"gh api failed: {said[-1][:300] if said else f'exit {p.returncode}'}")


def _values(text: str):
    try:
        values = decode_values(text)
    except CommentsError as e:
        raise GhError(f"gh api's output isn't JSON ({e})") from None
    if not values:
        raise GhError("gh api printed nothing")
    return values[0] if len(values) == 1 else values


def api(path: str, paginate: bool = False, fields: list[tuple[str, str]] | None = None):
    """`gh api <path>`'s JSON; with `paginate`, every page as a list of pages.
    `fields` are (flag, "key=value") pairs, `-f` for text and `-F` for a
    number, for GraphQL's query only: on a REST path they would make gh send
    a POST, a write."""
    if fields and path != "graphql":
        raise ValueError("fields go only with graphql")
    extra = [a for flag, kv in (fields or []) for a in (flag, kv)]
    if not paginate:
        p = _run(["api", path, *extra])
        if p.returncode:
            raise _failed(p)
        return _values(p.stdout)
    p = _run(["api", "--paginate", "--slurp", path, *extra])
    if p.returncode == 0:
        return _values(p.stdout)
    if "slurp" not in (p.stderr + p.stdout).lower():
        raise _failed(p)
    p = _run(["api", "--paginate", path, *extra])
    if p.returncode:
        raise _failed(p)
    try:
        return decode_values(p.stdout)  # the pages, one after another
    except CommentsError as e:
        raise GhError(f"gh api's output isn't JSON ({e})") from None


def _items(v) -> list:
    """The items of a paginated answer: its pages' items, a page taken as one item."""
    out = []
    for page in v if isinstance(v, list) else [v]:
        out += page if isinstance(page, list) else [page]
    return out


def _not_found(e: GhError) -> bool:
    return "HTTP 404" in str(e)


def _refused(e: GhError) -> bool:
    """The cloud session's proxy refused the route, not GitHub (whose own 403s,
    for a token without push access or a rate limit, stay failures)."""
    return PROXY_REFUSED in str(e)


def _id(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def session_threads(r: str, number: int, pr) -> dict:
    """The pull request's review threads from the cloud session's route
    `<r>/pulls/<n>/ccr/review_threads`, in GraphQL's shape, as `--threads`
    takes it. The route gives a bare list (`resolved`, `comment_ids`, no count
    and no authors), so it counts as whole only when every review comment of
    the pull request (`pulls/<n>/comments`, every page, and as many as `pr`'s
    `review_comments` says) sits in one of its threads. Raises GhError when it
    can't be shown whole."""
    listed = _items(api(f"{r}/pulls/{number}/ccr/review_threads?per_page=100", paginate=True))
    threads = []
    for t in listed:
        ids = t.get("comment_ids") if isinstance(t, dict) else None
        if not isinstance(t, dict) or not isinstance(t.get("resolved"), bool) or not isinstance(ids, list) or any(_id(i) is None for i in ids):
            raise GhError("the session route's threads aren't a list of threads, each with resolved and comment_ids")
        threads.append((t["resolved"], ids))
    comments = _items(api(f"{r}/pulls/{number}/comments?per_page=100", paginate=True))
    authors: dict[int, str] = {}
    for c in comments:
        cid = _id(c.get("id")) if isinstance(c, dict) else None
        if cid is None:
            raise GhError("a review comment has no id")
        authors[cid] = _login(c)
    counted = _id(pr.get("review_comments")) if isinstance(pr, dict) else None
    if counted is None:
        raise GhError("the pull request doesn't say how many review comments it has (review_comments), so the session route's threads can't be shown whole")
    if len(authors) < counted:
        raise GhError(f"gh api gave {len(authors)} of the pull request's {counted} review comments, so the session route's threads can't be shown whole")
    in_threads = {i for _, ids in threads for i in ids}
    if set(authors) - in_threads:
        raise GhError("the session route left out the threads of some review comments, so its list isn't whole")
    nodes = []
    for resolved, ids in threads:
        first = authors.get(ids[0], "") if ids else ""
        nodes.append({"isResolved": resolved, "comments": {"nodes": [{"author": {"login": first}}] if first else []}})
    return {"totalCount": len(nodes), "pageInfo": {"hasNextPage": False, "hasPreviousPage": False}, "nodes": nodes}


def token_permission(r: str) -> tuple[str, str]:
    """(the token's own login, its permission on the repository), from `user`
    and `<r>`'s `permissions`: what a cloud session can read when the
    collaborator route is refused. Raises GhError when either can't be read."""
    me = api("user")
    login = me.get("login") if isinstance(me, dict) else None
    if not isinstance(login, str) or not login:
        raise GhError("gh api user gave no login")
    repo = api(r)
    flags = repo.get("permissions") if isinstance(repo, dict) else None
    if not isinstance(flags, dict):
        raise GhError(f"gh api {r} gave no permissions")
    for flag, perm in (("admin", "admin"), ("maintain", "maintain"), ("push", "write"), ("triage", "triage"), ("pull", "read")):
        if flags.get(flag) is True:
            return login, perm
    return login, "none"


def _reviews_read(reviews, pr) -> tuple[list[tuple[str, str]], set[str]]:
    """(login, state) for each review, as merge-check reads them (any shape it
    takes, oldest first, drafts left out), and the logins (casefolded) asked
    to review again. Raises GhError when the reviews can't be read."""
    ctx = merge.Context({"reviews": (reviews, None), "pr": (pr, None)}, None, None)
    try:
        revs = ctx.reviews()
    except merge.Unreadable as e:
        raise GhError(f"not fetched: the reviews couldn't be read ({e})") from None
    try:
        asked = ctx.pr().requested
    except merge.Unreadable:
        asked = set()
    return revs, asked


def _standing_change_requests(revs: list[tuple[str, str]], asked: set[str]) -> set[str]:
    """The logins (casefolded) whose change request still stands, as
    merge-check's `_people` reads it: their latest approving,
    change-requesting or dismissed review requests changes, and they haven't
    been asked to review again."""
    standing: dict[str, str] = {}
    for login, state in revs:
        if login and state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            standing[login.casefold()] = state
    return {w for w, state in standing.items() if state == "CHANGES_REQUESTED" and w not in asked}


def merge_inputs(repo: str, number: int, have: dict, names, asker: str | None = None) -> dict:
    """`merge-check`'s inputs `names`, fetched for pull request `number` of
    `repo` (owner/name). `have` holds the inputs already given as files: those
    win, and the head commit, base branch and authors are read from them when
    given there. `asker` (a login) has their permission fetched too: the CLI
    passes it only when the profile names no `project.owner`, where it says
    whether they count as the owner."""
    out: dict = {}
    names = [n for n in names if n not in have]
    if not names:
        return out
    if not available():
        return {n: (None, f"{NOT_INSTALLED}, {AS_A_FILE.format(name=n)}") for n in names}
    r = f"repos/{repo}"
    owner, _, name = repo.partition("/")

    def get(n: str, fn) -> None:
        if n in names:
            try:
                out[n] = (fn(), None)
            except GhError as e:
                out[n] = (None, f"{e}, {AS_A_FILE.format(name=n)}")

    def given(n: str):
        got = have.get(n) or out.get(n)
        return got[0] if got and got[1] is None else None

    get("pr", lambda: api(f"{r}/pulls/{number}"))
    pr = given("pr")
    pr = pr[0] if isinstance(pr, list) and len(pr) == 1 else pr
    head = base = None
    if isinstance(pr, dict):
        h, b = pr.get("head"), pr.get("base")
        head = h.get("sha") if isinstance(h, dict) else pr.get("headRefOid")
        base = b.get("ref") if isinstance(b, dict) else pr.get("baseRefName")
    head = head if isinstance(head, str) and head else None
    base = base if isinstance(base, str) and base else None

    def need(what, v):
        if v is None:
            raise GhError(f"not fetched: it needs the pull request's {what}, and --pr couldn't be read")
        return v

    get("files", lambda: api(f"{r}/pulls/{number}/files?per_page=100", paginate=True))
    get("commits", lambda: api(f"{r}/pulls/{number}/commits?per_page=100", paginate=True))

    def checks():
        sha = need("head commit", head)
        runs = api(f"{r}/commits/{sha}/check-runs?per_page=100", paginate=True)
        status = api(f"{r}/commits/{sha}/status?per_page=100", paginate=True)
        return _items(runs) + _items(status)  # the pages of each: every value one after another, as --checks takes them

    get("checks", checks)

    def rulesets():
        listed = api(f"{r}/rulesets?includes_parents=true&per_page=100", paginate=True)
        flat = _items(listed)
        ids = [x.get("id") for x in flat if isinstance(x, dict)]
        if any(not isinstance(i, int) for i in ids) or len(ids) != len(flat):
            raise GhError("gh api's list of rulesets has an entry without an id")
        return [api(f"{r}/rulesets/{i}") for i in ids]  # each in full: the list gives summaries

    get("rulesets", rulesets)

    def threads():
        try:
            return api("graphql", paginate=True, fields=[("-f", f"query={THREADS_QUERY}"), ("-f", f"owner={owner}"), ("-f", f"name={name}"), ("-F", f"number={number}")])
        except GhError as refused:  # a cloud session refuses GraphQL: its own route, if it can be shown whole
            try:
                return session_threads(r, number, pr)
            except GhError as e:
                raise GhError(f"{refused}; then pulls/{number}/ccr/review_threads: {e}") from None

    get("threads", threads)
    get("reviews", lambda: api(f"{r}/pulls/{number}/reviews?per_page=100", paginate=True))
    get("comments", lambda: api(f"{r}/issues/{number}/comments?per_page=100", paginate=True))

    def permissions():
        logins: dict[str, str] = {}
        comments, reviews = given("comments"), given("reviews")
        if comments is None or reviews is None:
            raise GhError("not fetched: it needs the comments' and reviews' authors, and those couldn't be read")
        try:
            items = comments_from(comments)
        except CommentsError as e:
            raise GhError(f"not fetched: the comments couldn't be read ({e})") from None
        unread = None
        try:
            revs, asked = _reviews_read(reviews, pr)  # in any shape merge-check takes, so no reviewer is left out
        except GhError as bad:  # merge-check says so for --reviews; the authors it can see still get theirs
            revs, asked, unread = [(_login(x), "") for x in _items(reviews) if isinstance(x, dict)], set(), bad
        for who in [_login(x) for x in items] + [login for login, _ in revs] + [(asker or "").strip().lstrip("@")]:
            if who:
                logins.setdefault(who.casefold(), who)
        answers, token, blocking = [], None, None
        for who in logins.values():
            try:
                answers.append(api(f"{r}/collaborators/{quote(who, safe='')}/permission"))
            except GhError as e:
                if _not_found(e):
                    answers.append({"permission": "none", "user": {"login": who}})  # GitHub doesn't know them here
                    continue
                if not _refused(e):
                    raise
                # A cloud session's proxy refuses the route: the token's own permission shows its
                # login's; nothing the session can read shows anyone else's, so they count as
                # without write access, but a change request of theirs isn't dropped on that guess.
                if token is None:
                    try:
                        token = token_permission(r)
                    except GhError as e2:
                        raise GhError(f"{e}; then the token's own permission: {e2}") from None
                    if unread is not None:  # a change request can't be told from the reviews, so none is dropped
                        raise GhError(f"{e}; then {unread}") from None
                    blocking = _standing_change_requests(revs, asked)
                token_login, token_perm = token
                if who.casefold() == token_login.casefold():
                    answers.append({"permission": token_perm, "user": {"login": who}})
                elif who.casefold() in blocking:
                    raise GhError(f"{e}, so whether @{who}, who requested changes, has write access can't be shown") from None
                else:
                    answers.append({"permission": "none", "user": {"login": who}})
        return answers

    get("permissions", permissions)
    get("compare", lambda: api(f"{r}/compare/{quote(need('base branch', base), safe='/')}...{need('head commit', head)}"))
    return out


# `workflow preview --fetch <n>`'s inputs, by their flags.
PREVIEW_INPUTS = ("comments", "checks", "sha")


def _give(name: str) -> str:
    """How to give an input that couldn't be fetched: a file, or the head's SHA itself."""
    return "so it couldn't be fetched: give --sha" if name == "sha" else AS_A_FILE.format(name=name)


def preview_inputs(repo: str, number: int, have: dict) -> dict:
    """`workflow preview`'s inputs not in `have`, fetched for pull request
    `number` of `repo` (owner/name), each `(value, None)` or `(None, why)`:
    the pull request's issue comments, its head commit's check runs (every
    page of each, through REST routes a cloud session allows), and the head
    SHA from the pull request. A head given in `have` wins, so its check runs
    are fetched and the pull request isn't."""
    names = [n for n in PREVIEW_INPUTS if n not in have]
    if not names:
        return {}
    if not available():
        return {n: (None, f"{NOT_INSTALLED}, {_give(n)}") for n in names}
    r = f"repos/{repo}"
    out: dict = {}

    def get(n: str, fn) -> None:
        if n in names:
            try:
                out[n] = (fn(), None)
            except GhError as e:
                out[n] = (None, f"{e}, {_give(n)}")

    def head():
        pr = api(f"{r}/pulls/{number}")
        h = pr.get("head") if isinstance(pr, dict) else None
        sha = h.get("sha") if isinstance(h, dict) else None
        if merge._sha(sha) is None:
            raise GhError(f"gh api {r}/pulls/{number} gave no head commit's SHA")
        return merge._sha(sha)

    get("sha", head)
    get("comments", lambda: api(f"{r}/issues/{number}/comments?per_page=100", paginate=True))
    got = have.get("sha") or out.get("sha")
    sha = got[0] if got and got[1] is None else None

    def checks():
        if sha is None:
            raise GhError("it needs the pull request's head commit, which couldn't be read")
        return api(f"{r}/commits/{sha}/check-runs?per_page=100", paginate=True)

    get("checks", checks)
    return out

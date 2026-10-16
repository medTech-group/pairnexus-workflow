"""Reading GitHub through `gh api`, for commands that otherwise take files.

`merge_inputs` fetches what `workflow merge-check --fetch <n>` needs, in the
shapes its files take (`merge.INPUTS`), every page: each input becomes
`(value, None)`, or `(None, why)` when it couldn't be fetched, so the command
says which input is missing and how to give it as a file. It only reads: every
call is a GET (GraphQL's query included), and nothing is written.

`gh api --paginate --slurp` gives the pages as one list; a gh too old for
`--slurp` prints them one after another, which are read one by one.
"""

from __future__ import annotations

import shutil
import subprocess
from urllib.parse import quote

from .posts import CommentsError, _login, comments_from, decode_values

TIMEOUT = 120  # seconds for one `gh api` call, every page
NO_GH = "gh (the GitHub CLI) isn't installed here, so it couldn't be fetched: give --{name} as a file"

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
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        raise GhError("gh (the GitHub CLI) isn't installed here") from None
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
    `fields` are (flag, "key=value") pairs: `-f` for text, `-F` for a number."""
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
    v = decode_values(p.stdout) if p.stdout.strip() else []
    return v  # the pages, one after another


def _not_found(e: GhError) -> bool:
    return "HTTP 404" in str(e)


def merge_inputs(repo: str, number: int, have: dict, names) -> dict:
    """`merge-check`'s inputs `names`, fetched for pull request `number` of
    `repo` (owner/name). `have` holds the inputs already given as files: those
    win, and the head commit, base branch and authors are read from them when
    given there."""
    out: dict = {}
    names = [n for n in names if n not in have]
    if not names:
        return out
    if not available():
        return {n: (None, NO_GH.format(name=n)) for n in names}
    r = f"repos/{repo}"
    owner, _, name = repo.partition("/")

    def get(n: str, fn) -> None:
        if n in names:
            try:
                out[n] = (fn(), None)
            except GhError as e:
                out[n] = (None, str(e))

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
        return [*(runs if isinstance(runs, list) else [runs]), *(status if isinstance(status, list) else [status])]

    get("checks", checks)

    def rulesets():
        listed = api(f"{r}/rulesets?includes_parents=true&per_page=100", paginate=True)
        flat = [x for page in (listed if isinstance(listed, list) else [listed]) for x in (page if isinstance(page, list) else [page])]
        ids = [x.get("id") for x in flat if isinstance(x, dict)]
        if any(not isinstance(i, int) for i in ids) or len(ids) != len(flat):
            raise GhError("gh api's list of rulesets has an entry without an id")
        return [api(f"{r}/rulesets/{i}") for i in ids]  # each in full: the list gives summaries

    get("rulesets", rulesets)
    get("threads", lambda: api("graphql", paginate=True, fields=[("-f", f"query={THREADS_QUERY}"), ("-f", f"owner={owner}"), ("-f", f"name={name}"), ("-F", f"number={number}")]))
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
        items += [x for page in (reviews if isinstance(reviews, list) else [reviews]) for x in (page if isinstance(page, list) else [page]) if isinstance(x, dict)]
        for x in items:
            who = _login(x)
            if who:
                logins.setdefault(who.casefold(), who)
        answers = []
        for who in logins.values():
            try:
                answers.append(api(f"{r}/collaborators/{quote(who, safe='')}/permission"))
            except GhError as e:
                if not _not_found(e):
                    raise
                answers.append({"permission": "none", "user": {"login": who}})  # GitHub doesn't know them here
        return answers

    get("permissions", permissions)
    get("compare", lambda: api(f"{r}/compare/{quote(need('base branch', base), safe='/')}...{need('head commit', head)}"))
    return out

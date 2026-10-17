"""The preview reader (#41, #113): whether a pull request's try-it link is
ready for its head commit, so a person, `merge-check` and the conductor never
disagree about a preview.

`read(comments, checks, sha)` takes the pull request's issue comments and its
head commit's check runs, as the GitHub API (or the MCP tools) return them,
and the head SHA. It answers `Preview(state, url, commit)`; `as_dict()` is the
JSON `workflow merge-check --preview` takes:

- **The state** comes from Cloudflare's check runs on the head: those named
  `Workers Builds: <worker>` from the `cloudflare-workers-and-pages` app (a
  check from another app, or another of Cloudflare's, is ignored), each by its
  latest result (`protection.latest`). Any failed is `failed`, any still
  running is `building`. A skipped or neutral run built nothing, so it is left
  out; with only those, there's no preview of the head: `none`.
- **The URL** comes from the Cloudflare bot's comment, read as it stands (it
  edits one comment for each build; with several, each Worker's row comes from
  the newest): the Preview URL of the head's row, and only when that row says
  the deployment succeeded. A head row that says it failed is `failed`. With
  every check passed and no row for the head, the link shown is an older
  commit's, so it is `building`, never `built`. A successful row with an empty
  Preview URL cell (a build that ran no `wrangler preview`) is `none`, with
  the head as its commit.
- **No bot comment and no check** is `none`. A bot comment but no check on
  the head yet is `building`.

The comment's shape is Cloudflare's documented one (`tests/fixtures/cloudflare/README.md`):
a Markdown table with Status, Name, Latest Commit and Preview URL columns. A
bot comment, a row or a Preview URL cell the reader can't make out raises
PreviewError, so a change in its format shows up rather than reading as "no
preview". It reads only what it is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from . import protection
from .reviews import _shown
from .posts import CommentsError, _login, comments_from

APP = "cloudflare-workers-and-pages"  # the GitHub App's slug, and its bot's login (`<slug>[bot]` in REST)
CHECK = "Workers Builds: "
NO_BUILD = ("skipped", "neutral")  # conclusions of a run that built nothing
OLDEST = datetime.min.replace(tzinfo=timezone.utc)
SHA = re.compile(r"[0-9a-fA-F]{7,40}")
_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])")
_MD_LINK = re.compile(r"\[([^\]]*)\]\(((?:[^\s()]|\([^\s()]*\))+)\)")
_HTML_LINK = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
_BARE = re.compile(r"https?://[^\s<>()|\]]+")
_SUCCESS = re.compile(r"✅|\bsuccess", re.I)
_NOT_SUCCESS = re.compile(r"❌|\bfail|\berror|\bcancel", re.I)


class PreviewError(Exception):
    """An input can't be read: `name` is its flag's name, the message says why."""

    def __init__(self, name: str, why: str):
        super().__init__(why)
        self.name = name


@dataclass
class Preview:
    state: str  # built, building, failed or none
    url: str | None
    commit: str | None

    def as_dict(self) -> dict:
        return {"state": self.state, "url": self.url, "commit": self.commit}


@dataclass
class Row:
    """One row of the bot's table: a Worker's latest build."""

    worker: str
    commit: str  # as the row gives it, lower case: 7 to 40 hex characters
    success: bool
    failed: bool
    url: str | None
    empty: bool  # the Preview URL cell holds nothing
    newest: bool = False  # from the bot's newest comment


def is_sha(v) -> bool:
    return isinstance(v, str) and SHA.fullmatch(v) is not None


def same_commit(a: str, b: str) -> bool:
    """Two SHAs, either of them short, name the same commit."""
    a, b = a.lower(), b.lower()
    return a.startswith(b) or b.startswith(a)


def _runs(value) -> list[dict]:
    """The check-run pages in `value`: one response of GET .../check-runs, its
    pages, a bare list of check runs, or merge-check's `--checks` (statuses
    beside them are left out)."""
    pages: list[dict] = []
    bare: list[dict] = []

    def go(v, depth: int) -> None:
        if depth > 6:
            raise PreviewError("checks", "it is nested deeper than GitHub nests check runs")
        if isinstance(v, list):
            for x in v:
                go(x, depth + 1)
        elif isinstance(v, dict) and "check_runs" in v:
            pages.append(v)
        elif isinstance(v, dict) and ("statuses" in v or "context" in v):
            return  # a commit status: Cloudflare's builds report as check runs
        elif isinstance(v, dict) and "name" in v and "status" in v:
            bare.append(v)
        else:
            raise PreviewError("checks", "it isn't check runs, as GET repos/<repo>/commits/<sha>/check-runs returns them")

    go(value, 0)
    if bare:
        pages.append({"check_runs": bare})
    return pages


def _builds(value, sha: str) -> tuple[list[protection.Ran], bool, str]:
    """Cloudflare's Workers Builds runs on the head, each name by its latest
    result; whether one was skipped (or neutral), building nothing; and the
    head's full SHA when a short one names a single run's commit."""
    pages = _runs(value)
    try:
        protection.latest(pages, None, None)  # reads every run, and refuses a list shorter than its total_count
    except protection.ProtectionError as e:
        said = str(e)
        if said.startswith("the check runs file: "):  # "…: each check run must…" reads as the reason itself
            said = said.removeprefix("the check runs file: ")
        elif said.startswith("the check runs file "):  # "… holds 2 of the commit's 7" reads as "it holds …"
            said = "it " + said.removeprefix("the check runs file ")
        raise PreviewError("checks", said) from None

    def theirs(r: dict) -> bool:
        # Another app's run of the same name mustn't stand in for Cloudflare's latest result,
        # nor a run for another commit (a short SHA is matched as a prefix).
        on = r.get("head_sha")
        return r["app"]["slug"].casefold() == APP and r["name"].startswith(CHECK) and (not isinstance(on, str) or same_commit(on, sha))

    runs = [r for p in pages for r in p["check_runs"] if theirs(r)]
    # Each name by its latest run; one whose latest built nothing (skipped, neutral) is left out.
    nothing = {id(r) for r in runs if r["status"] == "completed" and r.get("conclusion") in NO_BUILD}
    latest = {}
    for r in runs:
        ran = protection.latest([{"check_runs": [r]}])[0]
        have = latest.get(ran.name)
        if have is None or (ran.when or OLDEST, ran.id) >= (have[0].when or OLDEST, have[0].id):
            latest[ran.name] = (ran, id(r))
    built = [ran for ran, raw in latest.values() if raw not in nothing]
    full = {r["head_sha"].lower() for r in runs if isinstance(r.get("head_sha"), str) and len(r["head_sha"]) == 40}
    return sorted(built, key=lambda r: r.name), len(built) < len(latest), full.pop() if len(full) == 1 else sha


def _is_bot(c: dict) -> bool:
    """The comment is the Cloudflare bot's: its login, and GitHub saying it is
    a bot (REST's `type`, a `[bot]` login, the app it came through, or
    GraphQL's `__typename`/`is_bot`). A person can't stand in for it with a
    login alone."""
    login = _login(c).casefold()
    who = next((c[k] for k in ("user", "author") if isinstance(c.get(k), dict)), {})
    app = c.get("performed_via_github_app")
    said = (
        login.endswith("[bot]")
        or (isinstance(app, dict) and str(app.get("slug", "")).casefold() == APP)
        or who.get("type") == "Bot"
        or who.get("__typename") == "Bot"
        or who.get("is_bot") is True
    )
    return login.removesuffix("[bot]") == APP and said and who.get("type") in (None, "Bot")


def _cells(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|"):
        return None
    line = line[1:-1] if line.endswith("|") and not line.endswith("\\|") else line[1:]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line)]


def _words(cell: str) -> str:
    """The cell's own words: links' text kept, their URLs, HTML and bare URLs left out."""
    cell = _MD_LINK.sub(lambda m: m.group(1), cell)
    cell = _BARE.sub(" ", re.sub(r"<[^>]+>", " ", cell))
    return cell


def _link(cell: str) -> str | None:
    """The cell's Preview URL: the branch's (a "Branch Preview URL", or a
    "Preview URL" beside a commit's or deployment's), else its only link."""
    links = [(text, url) for text, url in _MD_LINK.findall(cell)] + [(text, url) for url, text in _HTML_LINK.findall(cell)]
    if not links and "](" not in cell and "<a" not in cell.lower():  # a link it couldn't parse isn't guessed at
        bare = _BARE.findall(cell)
        rest = _BARE.sub(" ", re.sub(r"<[^>]+>", " ", cell))
        if rest.strip(" -—–") or any(u[-1] in ".,;:!?" for u in bare):
            return None  # words beside it, or a URL that may run on past a space or into a full stop
        links = [("", url) for url in bare]
    links = [(re.sub(r"<[^>]+>", "", t).strip().casefold(), u) for t, u in links]
    links = [(t, u) for t, u in links if u.startswith(("https://", "http://")) and u.isprintable() and " " not in u]
    for wanted in (lambda t: "branch" in t, lambda t: "preview" in t and not any(w in t for w in ("commit", "deployment"))):
        for t, u in links:
            if wanted(t):
                return u
    return links[0][1] if len(links) == 1 else None


def _unknown(why: str) -> PreviewError:
    return PreviewError("comments", f"the Cloudflare bot's comment: {why}: has its format changed?")


def _rows(body: str) -> list[Row] | None:
    """The rows of the bot's table, or None when the body has no table it knows."""
    lines = (body or "").splitlines()
    for i, line in enumerate(lines):
        head = _cells(line)
        if head is None:
            continue
        names = [h.casefold() for h in head]
        col = {
            "status": next((k for k, h in enumerate(names) if "status" in h), None),
            "commit": next((k for k, h in enumerate(names) if "commit" in h), None),
            "url": next((k for k, h in enumerate(names) if "preview url" in h), None),
            "name": next((k for k, h in enumerate(names) if h == "name"), None),
        }
        if None in (col["status"], col["commit"], col["url"]):
            continue
        rows: list[Row] = []
        for below in lines[i + 1 :]:
            cells = _cells(below)
            if cells is None:
                break
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue  # the separator
            if len(cells) <= max(k for k in col.values() if k is not None):
                raise _unknown("a row of its table has fewer cells than its header")
            hexes = sorted(_HEX.findall(cells[col["commit"]]), key=len, reverse=True)
            if not hexes:
                raise _unknown("a row of its table names no commit")
            status = _words(cells[col["status"]])
            failed = bool(_NOT_SUCCESS.search(status))
            cell = cells[col["url"]]
            empty = not _words(cell).strip(" -—–") and not _MD_LINK.search(cell) and not _HTML_LINK.search(cell) and not _BARE.search(cell)
            worker = cells[col["name"]] if col["name"] is not None else ""
            rows.append(Row(worker, hexes[0].lower(), bool(_SUCCESS.search(status)) and not failed, failed, _link(cell), empty))
        if not rows:
            raise _unknown("its table has no rows")
        return rows
    return None


def _name(worker: str) -> str:
    """A Worker's name as a row or a check gives it, for matching: its words, any case."""
    return _words(worker).strip(" `*_").casefold()


def _when(c: dict) -> str:
    return str(c.get("updated_at") or c.get("updatedAt") or c.get("created_at") or c.get("createdAt") or "")


def _bot_rows(value, head: str) -> tuple[bool, list[Row]]:
    """(whether the bot commented, each Worker's row from its newest comment
    that has one: in that comment, the row for the head when it has one, else
    its first)."""
    try:
        comments = comments_from(value)
    except CommentsError as e:
        raise PreviewError("comments", str(e)) from None
    by_bot = [c for c in comments if _is_bot(c)]
    if not by_bot:
        return False, []
    by_bot.sort(key=lambda c: (_when(c), c.get("id") if isinstance(c.get("id"), int) else 0), reverse=True)
    tables = [_rows(c.get("body") or "") for c in by_bot]
    if all(t is None for t in tables):
        raise _unknown("it has no table the reader knows (Status, Latest Commit and Preview URL columns)")
    rows: dict[str, Row] = {}
    for table in tables[:1]:
        for r in table or []:
            r.newest = True
    for table in tables:
        mine: dict[str, Row] = {}
        for r in table or []:
            have = mine.get(_name(r.worker))
            if have is None or (same_commit(r.commit, head) and not same_commit(have.commit, head)):
                mine[_name(r.worker)] = r
        for key, r in mine.items():
            rows.setdefault(key, r)  # the newest comment's row wins
    return True, list(rows.values())


def read(comments, checks, sha: str) -> Preview:
    """The preview of the head commit `sha`, from the pull request's comments and
    the head's check runs. Raises PreviewError for an input it can't read."""
    builds, skipped, head = _builds(checks, sha.lower())
    commented, rows = _bot_rows(comments, head)
    workers = [_name(b.name[len(CHECK) :]) for b in builds]
    rows.sort(key=lambda r: workers.index(_name(r.worker)) if _name(r.worker) in workers else len(workers))
    on_head = [r for r in rows if same_commit(r.commit, head)]
    if len(head) < 40:  # a short SHA: the full one the bot's row names
        head = next((r.commit for r in on_head if len(r.commit) == 40), head)
    older = next((r.commit for r in rows if not same_commit(r.commit, head)), None)

    def broken(r: Row) -> bool:
        """A row that says its deployment failed: the head's; or, once the head's builds have
        started (or were skipped), an older one in the bot's newest comment of a Worker with no
        check on the head (build watch paths kept it from rebuilding, so its preview is still the
        broken one; a Worker gone from the newest comment doesn't count)."""
        if not r.failed:
            return False
        if same_commit(r.commit, head):
            return True
        return bool(builds or skipped) and r.newest and bool(r.worker) and _name(r.worker) not in workers

    if any(b.result == "failing" for b in builds):
        return Preview("failed", None, head)
    if any(b.result == "pending" for b in builds):
        return Preview("building", None, head)  # a re-run still going, whatever the comment said of the last
    if any(broken(r) for r in rows):
        return Preview("failed", None, head)
    if not builds:
        if skipped:
            return Preview("none", None, head)  # Cloudflare built nothing for the head
        if not commented:
            return Preview("none", None, None)
        # The bot has commented, but the head's build hasn't started (Cloudflare can take minutes).
        return Preview("building", None, head if on_head else older)
    # Each Worker built on the head needs its row to say so; a Worker with no check on the head
    # (build watch paths: Cloudflare skipped it) doesn't hold the others up.
    by_worker = {_name(r.worker): r for r in rows}
    if any(w in by_worker for w in workers):
        theirs = [by_worker.get(w) for w in workers]
    else:  # rows that don't name the Workers (no Name column): the head's
        theirs = on_head or [None]
    if any(r is None or not r.success or not same_commit(r.commit, head) for r in theirs):
        return Preview("building", None, head if on_head else older or head)
    for r in theirs:
        if r.url is None and not r.empty:
            raise _unknown(f"the head's row{' for ' + _shown(r.worker, 60) if r.worker else ''} has a Preview URL cell the reader can't make out")
    linked = [r for r in theirs if r.url]
    if linked:
        return Preview("built", linked[0].url, head)
    return Preview("none", None, head)  # built, with no link to try


def text(p: Preview, sha: str) -> str:
    """The answer in plain words, then its three fields."""
    head = sha[:7]
    if p.state == "built":
        said = f"The try-it link for {head} is ready: {p.url}"
    elif p.state == "failed":
        said = f"The try-it link for {head} didn't build: Cloudflare's check or its comment says it failed. Its log is linked from the check's Details."
    elif p.state == "building" and p.commit and not same_commit(p.commit, sha):
        said = f"Cloudflare's comment is still for {p.commit[:7]}, not the head {head}: the head's try-it link is still building (Cloudflare's builds can take a few minutes to start)."
    elif p.state == "building":
        said = f"The try-it link for {head} is still building (Cloudflare's builds can take a few minutes to start)."
    elif p.commit:
        said = f"No try-it link for {head}: Cloudflare built nothing to try for it (its build was skipped, or ran no `wrangler preview`)."
    else:
        said = "No try-it link: this pull request has no Cloudflare Workers Builds check or comment."
    return "\n".join([said, f"state: {p.state}", f"url: {p.url or '-'}", f"commit: {p.commit or '-'}"])

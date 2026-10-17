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
  running is `building`.
- **The URL** comes from the Cloudflare bot's comment, read as it stands (it
  edits one comment for each build): the Preview URL of its row for the head
  SHA, and only when that row says the deployment succeeded. With every check
  passed and no such row, the preview shown is an older commit's, so it is
  `building`, never `built`; a successful row with no link (a build that ran
  no `wrangler preview`) is `none`.
- **No bot comment and no check** is `none`. A bot comment but no check on
  the head yet is `building`.

The comment's shape is Cloudflare's documented one (`tests/fixtures/cloudflare/README.md`):
a Markdown table with Status, Name, Latest Commit and Preview URL columns. A
bot comment with no such table raises PreviewError, so a change in its format
shows up rather than reading as "no preview". It reads only what it is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import protection
from .posts import CommentsError, _login, comments_from

APP = "cloudflare-workers-and-pages"
BOT = APP  # the bot's login, `cloudflare-workers-and-pages[bot]` in REST and without `[bot]` from gh's GraphQL
CHECK = "Workers Builds: "
STATES = ("built", "building", "failed", "none")
SHA = re.compile(r"[0-9a-fA-F]{7,40}")
_HEX = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])")
_MD_LINK = re.compile(r"\[([^\]]*)\]\((\S+?)\)")
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
    state: str
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
    url: str | None


def is_sha(v) -> bool:
    return isinstance(v, str) and SHA.fullmatch(v) is not None


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


def _builds(value, sha: str) -> list[protection.Ran]:
    """Cloudflare's Workers Builds runs on the head, each name by its latest result."""
    pages = _runs(value)
    if len(sha) < 40:  # a short SHA: the runs' own head_sha, when they name one commit it starts
        named = {r["head_sha"].lower() for p in pages for r in p.get("check_runs") or [] if isinstance(r, dict) and isinstance(r.get("head_sha"), str)}
        full = [s for s in named if s.startswith(sha)]
        sha = full[0] if len(full) == 1 else sha
    commit = sha if len(sha) == 40 else None
    try:
        protection.latest(pages, None, commit)  # every run read, and the list whole
        # Another app's run of the same name mustn't stand in for Cloudflare's latest result.
        theirs = [{"check_runs": [r for r in p["check_runs"] if r["app"]["slug"].casefold() == APP]} for p in pages]
        ran = protection.latest(theirs, None, commit)
    except protection.ProtectionError as e:
        raise PreviewError("checks", str(e).replace("the check runs file", "it")) from None
    return sorted((r for r in ran if r.name.startswith(CHECK)), key=lambda r: r.name)


def _is_bot(c: dict) -> bool:
    who = _login(c).casefold().removesuffix("[bot]")
    user = c.get("user") if isinstance(c.get("user"), dict) else c.get("author") if isinstance(c.get("author"), dict) else {}
    kind = user.get("type") if isinstance(user, dict) else None
    return who == BOT and kind in (None, "Bot")


def _cells(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|"):
        return None
    return [c.strip() for c in line.strip("|").split("|")]


def _link(cell: str) -> str | None:
    """The cell's Preview URL: the branch's (a "Branch Preview URL", or a
    "Preview URL" beside a commit's or deployment's), else its only link."""
    links = [(text, url) for text, url in _MD_LINK.findall(cell)] + [(text, url) for url, text in _HTML_LINK.findall(cell)]
    if not links:
        links = [("", url) for url in _BARE.findall(cell)]
    links = [(re.sub(r"<[^>]+>", "", t).strip().casefold(), u) for t, u in links]
    links = [(t, u) for t, u in links if u.startswith(("https://", "http://")) and u.isprintable() and " " not in u]
    for wanted in (lambda t: "branch" in t, lambda t: "preview" in t and not any(w in t for w in ("commit", "deployment"))):
        for t, u in links:
            if wanted(t):
                return u
    return links[0][1] if len(links) == 1 else None


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
        out: list[Row] = []
        for line2 in lines[i + 1 :]:
            cells = _cells(line2)
            if cells is None:
                break
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue  # the separator
            if len(cells) <= max(k for k in col.values() if k is not None):
                continue
            hexes = sorted(_HEX.findall(cells[col["commit"]]), key=len, reverse=True)
            if not hexes:
                continue
            status = cells[col["status"]]
            success = bool(_SUCCESS.search(status)) and not _NOT_SUCCESS.search(status)
            worker = cells[col["name"]] if col["name"] is not None else ""
            out.append(Row(worker, hexes[0].lower(), success, _link(cells[col["url"]])))
        return out
    return None


def _when(c: dict) -> str:
    return str(c.get("updated_at") or c.get("updatedAt") or c.get("created_at") or c.get("createdAt") or "")


def _bot_rows(value) -> tuple[bool, list[Row]]:
    """(whether the bot commented, its rows, newest comment first)."""
    try:
        comments = comments_from(value)
    except CommentsError as e:
        raise PreviewError("comments", str(e)) from None
    mine = [c for c in comments if _is_bot(c)]
    if not mine:
        return False, []
    mine.sort(key=lambda c: (_when(c), c.get("id") if isinstance(c.get("id"), int) else 0), reverse=True)
    tables = [_rows(c.get("body") or "") for c in mine]
    if all(t is None for t in tables):
        raise PreviewError(
            "comments",
            "the Cloudflare bot's comment has no table the reader knows (Status, Latest Commit and Preview URL columns): has its format changed?",
        )
    return True, [r for t in tables if t for r in t]


def read(comments, checks, sha: str) -> Preview:
    """The preview of the head commit `sha`, from the pull request's comments and
    the head's check runs. Raises PreviewError for an input it can't read."""
    head = sha.lower()

    def for_head(r: Row) -> bool:
        return head.startswith(r.commit) or r.commit.startswith(head)

    builds = _builds(checks, head)
    commented, rows = _bot_rows(comments)
    if not builds:
        if not commented:
            return Preview("none", None, None)
        # The bot has commented, but the head's build hasn't started (Cloudflare can take minutes).
        return Preview("building", None, head if any(for_head(r) for r in rows) else rows[0].commit if rows else None)
    if any(b.result == "failing" for b in builds):
        return Preview("failed", None, head)
    if any(b.result == "pending" for b in builds):
        return Preview("building", None, head)
    workers = [b.name[len(CHECK) :] for b in builds]
    mine = [r for r in rows if for_head(r)]
    done = [r for r in mine if r.success]

    def order(r: Row) -> int:
        return workers.index(r.worker) if r.worker in workers else len(workers)

    linked = sorted((r for r in done if r.url), key=order)
    if linked:
        return Preview("built", linked[0].url, head)
    if done:
        return Preview("none", None, head)  # built, with no link to try
    return Preview("building", None, head if mine else (rows[0].commit if rows else head))


def _short(commit: str | None) -> str:
    return (commit or "")[:7]


def text(p: Preview, sha: str) -> str:
    """The answer in plain words, then its three fields."""
    head = _short(sha)
    if p.state == "built":
        said = f"The try-it link for {head} is ready: {p.url}"
    elif p.state == "failed":
        said = f"The try-it link for {head} didn't build: Cloudflare's check failed. Its log is linked from the check's Details."
    elif p.state == "building" and p.commit and not sha.lower().startswith(p.commit) and not p.commit.startswith(sha.lower()):
        said = f"The try-it link shown is for {_short(p.commit)}, not the head {head}: the head's is still building (Cloudflare's builds can take a few minutes to start)."
    elif p.state == "building":
        said = f"The try-it link for {head} is still building (Cloudflare's builds can take a few minutes to start)."
    elif p.commit:
        said = f"No try-it link for {head}: Cloudflare built it but its comment gives no Preview URL."
    else:
        said = "No try-it link: this pull request has no Cloudflare Workers Builds check or comment."
    return "\n".join([said, f"state: {p.state}", f"url: {p.url or '-'}", f"commit: {p.commit or '-'}"])
